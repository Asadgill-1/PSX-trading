"""Scout -> Devil's Advocate -> Judge pipeline.

Runs on the scan tick during market hours. Produces PROPOSALS ONLY — rows in
the proposals table with status 'pending'. Execution happens elsewhere, after
owner approval, behind the safety layer. This module cannot touch that layer
(enforced by tests/test_risk.py::test_agents_module_never_imports_risk).

Independent Devil/Judge calls run per-candidate in parallel threads (spec §3).
"""
import json
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import db
from . import llm, prompts

log = logging.getLogger("agents.pipeline")

MAX_CANDIDATES = 8          # deterministic pre-filter keeps LLM costs bounded
MAX_OPEN_PROPOSALS = 5      # don't flood the owner
PROPOSAL_TTL_HOURS = 24
LESSONS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "lessons"


def read_lessons(limit: int = 20) -> str:
    """One-line summaries (first non-empty line) of lesson files, newest first."""
    if not LESSONS_DIR.exists():
        return "No lessons recorded yet."
    files = sorted(LESSONS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    lines = []
    for f in files[:limit]:
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip().lstrip("# ")
            if line:
                lines.append(f"- {line}")
                break
    return "\n".join(lines) or "No lessons recorded yet."


def pick_candidates(conn: sqlite3.Connection, n: int = MAX_CANDIDATES) -> list[dict]:
    """Cheap deterministic pre-filter: most active symbols by traded value with
    a real price move, latest snapshot only. LLM never sees the full board."""
    rows = conn.execute(
        """SELECT q.symbol, q.sector, q.price, q.open, q.high, q.low, q.ldcp,
                  q.change_pct, q.volume
           FROM quotes q
           JOIN (SELECT symbol, MAX(id) AS mid FROM quotes GROUP BY symbol) m
             ON q.id = m.mid
           WHERE q.price > 0 AND q.volume > 0 AND q.change_pct IS NOT NULL
           ORDER BY q.price * q.volume DESC
           LIMIT 60"""
    ).fetchall()
    scored = sorted(rows, key=lambda r: abs(r["change_pct"] or 0) * (r["price"] * r["volume"]) ** 0.5,
                    reverse=True)
    out = []
    for r in scored[:n]:
        d = dict(r)
        f = conn.execute(
            "SELECT eps, pe, market_cap FROM fundamentals WHERE symbol=? ORDER BY as_of DESC LIMIT 1",
            (r["symbol"],),
        ).fetchone()
        if f:
            d.update(dict(f))
        out.append(d)
    return out


def strategy_weights(conn: sqlite3.Connection) -> dict[str, float]:
    return {r["strategy"]: r["weight"] for r in conn.execute("SELECT * FROM strategy_weights")}


def run_scan(conn: sqlite3.Connection) -> list[int]:
    """Full pipeline pass. Returns ids of new pending proposals."""
    open_count = conn.execute(
        "SELECT COUNT(*) AS c FROM proposals WHERE status='pending'"
    ).fetchone()["c"]
    if open_count >= MAX_OPEN_PROPOSALS:
        log.info("skipping scan: enough pending proposals", extra={"ctx": {"pending": open_count}})
        return []

    _expire_stale(conn)
    candidates = pick_candidates(conn)
    if not candidates:
        log.info("no candidates in data")
        return []

    lessons = read_lessons()
    weights = strategy_weights(conn)
    scout_input = json.dumps({
        "lessons_from_past_trades": lessons,
        "strategy_weights (higher = has worked better for us)": weights,
        "market_data": candidates,
    }, default=str)

    ideas = llm.complete_json("scout", prompts.SCOUT_SYSTEM, scout_input, llm.SCOUT_MODEL)
    if not isinstance(ideas, list):
        raise ValueError("scout reply was not a list")
    ideas = [i for i in ideas if _valid_idea(conn, i)]
    if not ideas:
        return []
    log.info("scout ideas", extra={"ctx": {"count": len(ideas),
                                           "symbols": [i["symbol"] for i in ideas]}})

    # Devil + Judge per idea, fresh contexts, parallel across ideas
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda i: _debate(conn, i, candidates), ideas))

    created = []
    for idea, debate in zip(ideas, results):
        if debate is None:
            continue
        devil, judge = debate
        if judge.get("verdict") != "propose" or float(judge.get("conviction", 0)) < 6:
            log.info("judge dropped idea", extra={"ctx": {"symbol": idea["symbol"]}})
            continue
        pid = _insert_proposal(conn, idea, devil, judge)
        if pid:
            created.append(pid)
    return created


def _valid_idea(conn: sqlite3.Connection, idea: dict) -> bool:
    """Boundary check on LLM output + drop symbols already pending/held-for-buy."""
    if not isinstance(idea, dict):
        return False
    if idea.get("action") not in ("buy", "sell"):
        return False
    sym = idea.get("symbol", "")
    if not sym or not conn.execute(
        "SELECT 1 FROM quotes WHERE symbol=? LIMIT 1", (sym,)
    ).fetchone():
        return False  # symbol must exist in our data — no hallucinated tickers
    dup = conn.execute(
        "SELECT 1 FROM proposals WHERE symbol=? AND status IN ('pending','approved')", (sym,)
    ).fetchone()
    return not dup


def _debate(conn: sqlite3.Connection, idea: dict, candidates: list[dict]):
    sym = idea["symbol"]
    data = next((c for c in candidates if c["symbol"] == sym), {"symbol": sym})
    devil_input = json.dumps({
        "trade_idea": {"symbol": sym, "action": idea["action"],
                       "summary": idea.get("thesis", "")},
        "market_data": data,
    }, default=str)
    try:
        devil = llm.complete_json("devil", prompts.DEVIL_SYSTEM, devil_input, llm.DEBATE_MODEL)
        if devil.get("fatal"):
            log.info("devil killed idea", extra={"ctx": {"symbol": sym}})
            return None
        judge_input = json.dumps({
            "bull_case": idea, "bear_case": devil, "market_data": data,
        }, default=str)
        judge = llm.complete_json("judge", prompts.JUDGE_SYSTEM, judge_input, llm.DEBATE_MODEL)
        return devil, judge
    except Exception:
        log.exception("debate failed", extra={"ctx": {"symbol": sym}})
        return None


def _insert_proposal(conn: sqlite3.Connection, idea: dict, devil: dict, judge: dict) -> int | None:
    sym = idea["symbol"]
    row = conn.execute(
        "SELECT price FROM quotes WHERE symbol=? ORDER BY fetched_at DESC, id DESC LIMIT 1",
        (sym,),
    ).fetchone()
    if not row or row["price"] <= 0:
        return None
    price = row["price"]

    # sizing is arithmetic, not agent opinion: stay under the per-position cap
    # with a small buffer; settings are read-only here.
    max_pos_pct = float(db.get_setting(conn, "risk.max_position_pct") or 5.0)
    stop_pct = float(db.get_setting(conn, "risk.stop_loss_pct") or 5.0)
    cash = conn.execute("SELECT cash FROM portfolio WHERE id=1").fetchone()["cash"]
    pv_floor = cash  # conservative: ignore open positions' value for sizing
    budget = pv_floor * (max_pos_pct * 0.9) / 100
    qty = int(budget // price)
    if qty < 1:
        return None
    stop = round(price * (1 - stop_pct / 100), 2)
    max_loss = round(qty * price * stop_pct / 100, 2)

    now = datetime.now(timezone.utc)
    cur = conn.execute(
        "INSERT INTO proposals(symbol, side, qty, entry_price, stop_loss, strategy,"
        " scout_case, devil_case, judge_report, conviction, max_loss_pkr, status,"
        " created_at, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,'pending',?,?)",
        (sym, idea["action"], qty, price, stop,
         idea.get("strategy", "unnamed"),
         json.dumps(idea), json.dumps(devil), json.dumps(judge),
         float(judge["conviction"]), max_loss,
         now.isoformat(timespec="seconds"),
         (now + timedelta(hours=PROPOSAL_TTL_HOURS)).isoformat(timespec="seconds")),
    )
    conn.commit()
    log.info("proposal created", extra={"ctx": {"id": cur.lastrowid, "symbol": sym,
                                                "qty": qty, "price": price}})
    return cur.lastrowid


def _expire_stale(conn: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute("UPDATE proposals SET status='expired' WHERE status='pending' AND expires_at < ?",
                 (now,))
    conn.commit()
