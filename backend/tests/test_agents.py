"""Agent pipeline tests — mock mode (deterministic, no API key, no network)."""
import json

import pytest

from app import db
from app.agents import mock, pipeline


@pytest.fixture()
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.init_db(c)
    return c


def put_quote(conn, symbol, price, volume=1_000_000, change_pct=2.0, sector="0800"):
    conn.execute(
        "INSERT INTO quotes(symbol, sector, price, change_pct, volume, fetched_at, source)"
        " VALUES (?,?,?,?,?,?,?)",
        (symbol, sector, price, change_pct, volume, db.utcnow(), "test"),
    )
    conn.commit()


def seed_market(conn):
    put_quote(conn, "LUCK", 480.0, volume=1_200_000, change_pct=2.4, sector="0804")
    put_quote(conn, "ENGRO", 350.0, volume=900_000, change_pct=1.8, sector="0810")
    put_quote(conn, "SLEEPY", 50.0, volume=100, change_pct=0.0, sector="0820")


# ---------- mock adapter contract ----------

def test_mock_roles_return_contract_shapes():
    scout = mock.respond("scout", json.dumps([{"symbol": "LUCK"}, {"symbol": "ENGRO"}]))
    assert isinstance(scout, list) and all(i["action"] in ("buy", "sell") for i in scout)
    devil = mock.respond("devil", '{"symbol": "LUCK"}')
    assert devil["objections"] and isinstance(devil["fatal"], bool)
    judge = mock.respond("judge", '{"symbol": "LUCK"}')
    assert judge["verdict"] in ("propose", "drop")
    assert (float(judge["conviction"]) >= 6) == (judge["verdict"] == "propose")


def test_json_parser_handles_fences_and_prose():
    from app.agents.llm import _parse_json
    assert _parse_json('```json\n{"a": 1}\n```', "t") == {"a": 1}
    assert _parse_json('Here you go:\n[{"b": 2}]', "t") == [{"b": 2}]
    with pytest.raises(ValueError):
        _parse_json("no json here", "t")


# ---------- candidate pre-filter ----------

def test_pick_candidates_prefers_active_movers(conn):
    seed_market(conn)
    cands = pipeline.pick_candidates(conn)
    syms = [c["symbol"] for c in cands]
    assert syms[0] in ("LUCK", "ENGRO")      # turnover + move
    assert "SLEEPY" not in syms[:2]


def test_pick_candidates_uses_latest_snapshot_only(conn):
    put_quote(conn, "X", 100.0, change_pct=5.0)
    put_quote(conn, "X", 90.0, change_pct=-1.0)  # newer
    cands = pipeline.pick_candidates(conn)
    x = next(c for c in cands if c["symbol"] == "X")
    assert x["price"] == 90.0


# ---------- full pipeline in mock mode ----------

def test_run_scan_creates_valid_pending_proposals(conn):
    seed_market(conn)
    created = pipeline.run_scan(conn)
    assert created                             # mock judge proposes for some
    for pid in created:
        p = conn.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
        assert p["status"] == "pending"
        assert p["qty"] >= 1
        assert p["stop_loss"] < p["entry_price"]
        assert p["max_loss_pkr"] > 0
        assert p["conviction"] >= 6
        # sizing respects the 5% cap with buffer: qty*price <= 4.5% of 1M
        assert p["qty"] * p["entry_price"] <= 45_000 + p["entry_price"]
        # debate stored
        assert json.loads(p["scout_case"])["symbol"] == p["symbol"]
        assert json.loads(p["devil_case"])["strongest"]
        assert json.loads(p["judge_report"])["report"]


def test_run_scan_no_duplicate_pending_for_same_symbol(conn):
    seed_market(conn)
    first = pipeline.run_scan(conn)
    second = pipeline.run_scan(conn)
    syms_first = {conn.execute("SELECT symbol FROM proposals WHERE id=?", (p,)).fetchone()[0]
                  for p in first}
    syms_second = {conn.execute("SELECT symbol FROM proposals WHERE id=?", (p,)).fetchone()[0]
                   for p in second}
    assert not (syms_first & syms_second)


def test_run_scan_respects_pending_ceiling(conn, monkeypatch):
    seed_market(conn)
    monkeypatch.setattr(pipeline, "MAX_OPEN_PROPOSALS", 0)
    assert pipeline.run_scan(conn) == []


def test_hallucinated_symbol_dropped(conn, monkeypatch):
    seed_market(conn)
    from app.agents import llm

    def fake(role, system, user, model):
        if role == "scout":
            return [{"symbol": "FAKECO", "action": "buy", "strategy": "s", "thesis": "t",
                     "evidence": []}]
        return mock.respond(role, user)

    monkeypatch.setattr(llm, "complete_json", fake)
    monkeypatch.setattr(pipeline.llm, "complete_json", fake)
    assert pipeline.run_scan(conn) == []       # FAKECO not in quotes -> dropped


def test_expired_proposals_marked(conn):
    seed_market(conn)
    conn.execute(
        "INSERT INTO proposals(symbol, side, qty, entry_price, stop_loss, strategy,"
        " scout_case, devil_case, judge_report, conviction, max_loss_pkr, status,"
        " created_at, expires_at) VALUES ('OLD','buy',1,10,9.5,'s','{}','{}','{}',7,100,"
        " 'pending','2026-01-01T00:00:00','2026-01-02T00:00:00')"
    )
    conn.commit()
    pipeline._expire_stale(conn)
    assert conn.execute("SELECT status FROM proposals WHERE symbol='OLD'").fetchone()[0] == "expired"


# ---------- lessons ----------

def test_read_lessons_missing_dir_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "LESSONS_DIR", tmp_path / "nope")
    assert "No lessons" in pipeline.read_lessons()


def test_read_lessons_reads_first_lines(tmp_path, monkeypatch):
    (tmp_path / "l1.md").write_text("# Volume spikes fooled us twice\ndetail...", encoding="utf-8")
    monkeypatch.setattr(pipeline, "LESSONS_DIR", tmp_path)
    out = pipeline.read_lessons()
    assert "Volume spikes fooled us twice" in out
