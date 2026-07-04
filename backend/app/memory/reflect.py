"""Self-learning memory (spec §6): journals, daily metrics, strategy weights,
lessons store, nightly reflection.

Lessons: one file per lesson in lessons/, one-line summary on top. The pipeline
reads them before every scan (agents/pipeline.read_lessons). Reflection updates
existing notes instead of duplicating and can delete ones proven wrong.
"""
import json
import logging
import re
import sqlite3
from pathlib import Path

from .. import config, db
from ..market_hours import khi_day_utc_range, trading_date

log = logging.getLogger("memory")

LESSONS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "lessons"

LOSS_CATEGORIES = ("bad_thesis", "bad_timing", "news_misread", "risk_sizing")


# ---------- journal ----------

def write_missing_journals(conn: sqlite3.Connection) -> int:
    """One journal entry per trade, written from the proposal's debate. Idempotent —
    covers every fill path (approvals, deferred fills, stop-loss sells)."""
    rows = conn.execute(
        """SELECT t.id, t.symbol, t.side, t.qty, t.price, t.proposal_id
           FROM trades t LEFT JOIN journal j ON j.trade_id = t.id
           WHERE j.id IS NULL"""
    ).fetchall()
    for t in rows:
        rationale = f"{t['side'].capitalize()} {t['qty']} {t['symbol']} at Rs {t['price']:.2f}."
        if t["proposal_id"]:
            p = conn.execute("SELECT judge_report FROM proposals WHERE id=?",
                             (t["proposal_id"],)).fetchone()
            if p:
                try:
                    rationale += " Reason: " + json.loads(p["judge_report"]).get("why_now", "")
                except (json.JSONDecodeError, TypeError):
                    pass
        else:
            rationale += " Reason: automatic stop-loss sale to cap the loss."
        conn.execute("INSERT INTO journal(trade_id, entry, created_at) VALUES (?,?,?)",
                     (t["id"], rationale, db.utcnow()))
    conn.commit()
    return len(rows)


# ---------- daily metrics ----------

def compute_daily_metrics(conn: sqlite3.Connection, date: str | None = None) -> dict:
    """Hit rate / avg win / avg loss from today's SELLS (realized outcomes only),
    plus cash-flow P&L and running drawdown of cumulative realized P&L."""
    date = date or trading_date()
    lo, hi = khi_day_utc_range(date)
    sells = conn.execute(
        """SELECT s.qty, s.price, s.commission, s.cgt, s.symbol,
                  (SELECT AVG(b.price) FROM trades b
                   WHERE b.symbol = s.symbol AND b.side='buy' AND b.executed_at <= s.executed_at)
                  AS avg_buy
           FROM trades s WHERE s.side='sell' AND s.executed_at >= ? AND s.executed_at < ?""",
        (lo, hi),
    ).fetchall()
    wins, losses = [], []
    for s in sells:
        if s["avg_buy"] is None:
            continue
        net = (s["price"] - s["avg_buy"]) * s["qty"] - s["commission"] - s["cgt"]
        (wins if net > 0 else losses).append(net)

    n_trades = conn.execute(
        "SELECT COUNT(*) c FROM trades WHERE executed_at >= ? AND executed_at < ?",
        (lo, hi)).fetchone()["c"]
    flow = conn.execute(
        """SELECT COALESCE(SUM(CASE WHEN side='sell' THEN qty*price - commission - cgt
                                    ELSE -(qty*price + commission) END), 0) f
           FROM trades WHERE executed_at >= ? AND executed_at < ?""", (lo, hi)).fetchone()["f"]

    closed = len(wins) + len(losses)
    metrics = {
        "date": date,
        "pnl": round(flow, 2),
        "trades": n_trades,
        "hit_rate": round(len(wins) / closed, 3) if closed else None,
        "avg_win": round(sum(wins) / len(wins), 2) if wins else None,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
        "drawdown": _running_drawdown(conn, date, flow),
    }
    conn.execute(
        "INSERT OR REPLACE INTO metrics_daily(date, pnl, trades, hit_rate, avg_win, avg_loss,"
        " drawdown) VALUES (:date, :pnl, :trades, :hit_rate, :avg_win, :avg_loss, :drawdown)",
        metrics,
    )
    conn.commit()
    return metrics


def _running_drawdown(conn: sqlite3.Connection, date: str, today_pnl: float) -> float:
    """Max peak-to-trough of cumulative realized P&L up to and including today."""
    rows = conn.execute("SELECT pnl FROM metrics_daily WHERE date < ? ORDER BY date", (date,)).fetchall()
    cum, peak, max_dd = 0.0, 0.0, 0.0
    for pnl in [r["pnl"] for r in rows] + [today_pnl]:
        cum += pnl
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    return round(max_dd, 2)


# ---------- strategy weights ----------

def update_strategy_weights(conn: sqlite3.Connection, date: str | None = None) -> dict[str, float]:
    """EMA nudge from realized outcomes: strategies that closed profitably today
    drift up, losers drift down. Bounded [0.2, 3.0] so no strategy ever gets
    absolute power or dies completely.
    ponytail: sign-based nudge, not magnitude-weighted — revisit after enough
    closed trades exist to fit anything smarter."""
    date = date or trading_date()
    lo, hi = khi_day_utc_range(date)
    rows = conn.execute(
        """SELECT p.strategy,
                  SUM(CASE WHEN t.side='sell'
                       THEN (t.price - (SELECT AVG(b.price) FROM trades b
                                        WHERE b.symbol=t.symbol AND b.side='buy'
                                          AND b.executed_at <= t.executed_at)) * t.qty
                            - t.commission - t.cgt
                       ELSE 0 END) AS realized
           FROM trades t JOIN proposals p ON p.id = t.proposal_id
           WHERE t.executed_at >= ? AND t.executed_at < ? GROUP BY p.strategy""",
        (lo, hi),
    ).fetchall()
    out = {}
    for r in rows:
        if r["realized"] is None:
            continue
        cur = conn.execute("SELECT weight FROM strategy_weights WHERE strategy=?",
                           (r["strategy"],)).fetchone()
        w = cur["weight"] if cur else 1.0
        nudge = 0.15 if r["realized"] > 0 else -0.15 if r["realized"] < 0 else 0.0
        w = min(3.0, max(0.2, round(w + nudge, 3)))
        conn.execute(
            "INSERT INTO strategy_weights(strategy, weight, updated_at) VALUES (?,?,?)"
            " ON CONFLICT(strategy) DO UPDATE SET weight=excluded.weight,"
            " updated_at=excluded.updated_at",
            (r["strategy"], w, db.utcnow()),
        )
        out[r["strategy"]] = w
    conn.commit()
    return out


# ---------- lessons ----------

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def apply_lesson_actions(actions: list[dict]) -> list[str]:
    """Apply create/update/delete lesson actions. Returns changed filenames.
    Validation at the boundary: bad actions are skipped, never fatal."""
    LESSONS_DIR.mkdir(exist_ok=True)
    changed = []
    for a in actions[:10]:  # hard cap per night
        if not isinstance(a, dict):
            continue
        act, name = a.get("action"), a.get("file", "")
        name = Path(name).name  # no path traversal
        if not name.endswith(".md") or act not in ("create", "update", "delete"):
            continue
        path = LESSONS_DIR / name
        if act == "delete":
            if path.exists():
                path.unlink()
                changed.append(f"deleted {name}")
        else:
            content = a.get("content", "").strip()
            if not content:
                continue
            path.write_text(content + "\n", encoding="utf-8")
            changed.append(f"{'created' if act == 'create' else 'updated'} {name}")
    return changed


def reflect_lessons(conn: sqlite3.Connection, date: str | None = None) -> list[str]:
    """Nightly lesson pass. Mock mode: deterministic template lessons from
    realized losses. Real mode: fresh-context LLM reviews the day and returns
    lesson file actions."""
    date = date or trading_date()
    day = _day_summary(conn, date)
    if day["closed_trades"] == 0:
        return []

    if config.MOCK_AGENTS:
        actions = _mock_lesson_actions(day)
    else:
        from ..agents import llm
        existing = []
        if LESSONS_DIR.exists():
            for f in sorted(LESSONS_DIR.glob("*.md")):
                first = f.read_text(encoding="utf-8").splitlines()
                existing.append({"file": f.name, "summary": first[0].lstrip("# ") if first else ""})
        system = (
            "You review one day of paper trading on the Pakistan Stock Exchange and maintain "
            "a lessons store the analysis agents read before every session. One lesson per file, "
            "first line = one-line summary starting with '# '. Categorize losses as one of: "
            f"{', '.join(LOSS_CATEGORIES)}. Record wins too (which strategy worked and under what "
            "conditions). Do NOT record what the database already stores (raw trades/P&L). "
            "Update an existing file rather than duplicating it; delete notes proven wrong. "
            'Reply ONLY JSON: [{"action":"create"|"update"|"delete","file":"slug.md",'
            '"content":"# one-line summary\\n\\nwhy it mattered..."}] — max 5 actions, [] if nothing learned.'
        )
        user = json.dumps({"date": date, "day": day, "existing_lessons": existing}, default=str)
        try:
            actions = llm.complete_json("judge", system, user, llm.DEBATE_MODEL)
        except Exception:
            log.exception("lesson reflection failed")
            return []
        if not isinstance(actions, list):
            return []
    return apply_lesson_actions(actions)


def _day_summary(conn: sqlite3.Connection, date: str) -> dict:
    lo, hi = khi_day_utc_range(date)
    trades = [dict(r) for r in conn.execute(
        """SELECT t.*, p.strategy, p.conviction FROM trades t
           LEFT JOIN proposals p ON p.id = t.proposal_id
           WHERE t.executed_at >= ? AND t.executed_at < ?""", (lo, hi))]
    journals = [r["entry"] for r in conn.execute(
        "SELECT entry FROM journal WHERE created_at >= ? AND created_at < ?", (lo, hi))]
    closed = [t for t in trades if t["side"] == "sell"]
    return {"trades": trades, "journals": journals, "closed_trades": len(closed)}


def _mock_lesson_actions(day: dict) -> list[dict]:
    actions = []
    for t in day["trades"]:
        if t["side"] != "sell":
            continue
        strat = t.get("strategy") or "unknown"
        # stop-loss sales (no proposal) = timing/sizing lesson; others = strategy note
        if t.get("proposal_id") is None:
            actions.append({
                "action": "create",
                "file": f"stop-loss-{_slug(t['symbol'])}.md",
                "content": f"# [MOCK] {t['symbol']} hit its stop-loss — check entry timing "
                           f"(category: bad_timing)\n\nSold {t['qty']} at Rs {t['price']:.2f} "
                           "automatically. Next time check whether the entry chased a spike.",
            })
        else:
            actions.append({
                "action": "create",
                "file": f"strategy-{_slug(strat)}.md",
                "content": f"# [MOCK] Strategy '{strat}' closed a trade on {t['symbol']}\n\n"
                           "Track whether this setup keeps working; conditions recorded in the DB.",
            })
    return actions


# ---------- nightly orchestration ----------

def run_nightly(conn: sqlite3.Connection) -> dict:
    """After-close reflection: journals -> metrics -> weights -> lessons."""
    journals = write_missing_journals(conn)
    metrics = compute_daily_metrics(conn)
    weights = update_strategy_weights(conn)
    lessons = reflect_lessons(conn)
    result = {"journals_written": journals, "metrics": metrics,
              "weights": weights, "lessons_changed": lessons}
    log.info("nightly reflection", extra={"ctx": result})
    return result
