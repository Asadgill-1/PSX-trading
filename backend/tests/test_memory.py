"""Memory system tests: journals, metrics, weights, lessons, nightly run."""
import json

import pytest

from app import db
from app.memory import reflect


@pytest.fixture()
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.init_db(c)
    return c


@pytest.fixture()
def lessons_dir(tmp_path, monkeypatch):
    d = tmp_path / "lessons"
    monkeypatch.setattr(reflect, "LESSONS_DIR", d)
    return d


def make_proposal(conn, symbol="X", strategy="momentum"):
    cur = conn.execute(
        "INSERT INTO proposals(symbol, side, qty, entry_price, stop_loss, strategy,"
        " scout_case, devil_case, judge_report, conviction, max_loss_pkr, status,"
        " created_at, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,'executed',?,?)",
        (symbol, "buy", 100, 100.0, 95.0, strategy, "{}", "{}",
         json.dumps({"why_now": "momentum looked strong"}), 7, 500,
         db.utcnow(), db.utcnow()))
    conn.commit()
    return cur.lastrowid


def make_trade(conn, symbol="X", side="buy", qty=100, price=100.0, pid=None,
               commission=15.0, cgt=0.0):
    cur = conn.execute(
        "INSERT INTO trades(proposal_id, symbol, side, qty, price, commission, cgt, kind,"
        " executed_at, settle_date) VALUES (?,?,?,?,?,?,?,'paper',?,?)",
        (pid, symbol, side, qty, price, commission, cgt, db.utcnow(), "2099-01-01"))
    conn.commit()
    return cur.lastrowid


# ---------- journal ----------

def test_journals_written_once_with_rationale(conn):
    pid = make_proposal(conn)
    make_trade(conn, pid=pid)
    make_trade(conn, side="sell", price=110.0, pid=None)   # stop-loss style
    assert reflect.write_missing_journals(conn) == 2
    assert reflect.write_missing_journals(conn) == 0       # idempotent
    entries = [r["entry"] for r in conn.execute("SELECT entry FROM journal")]
    assert any("momentum looked strong" in e for e in entries)
    assert any("stop-loss" in e for e in entries)


# ---------- metrics ----------

def test_daily_metrics_hit_rate_and_pnl(conn):
    pid = make_proposal(conn)
    make_trade(conn, symbol="W", side="buy", price=100.0, pid=pid)
    make_trade(conn, symbol="W", side="sell", price=120.0, cgt=300.0)   # win
    make_trade(conn, symbol="L", side="buy", price=100.0)
    make_trade(conn, symbol="L", side="sell", price=90.0)               # loss
    m = reflect.compute_daily_metrics(conn)
    assert m["trades"] == 4
    assert m["hit_rate"] == 0.5
    assert m["avg_win"] == pytest.approx(2000 - 15 - 300)
    assert m["avg_loss"] == pytest.approx(-1000 - 15)
    row = conn.execute("SELECT * FROM metrics_daily").fetchone()
    assert row["hit_rate"] == 0.5


def test_drawdown_accumulates_across_days(conn):
    conn.execute("INSERT INTO metrics_daily(date, pnl, trades) VALUES ('2026-07-01', 5000, 1)")
    conn.execute("INSERT INTO metrics_daily(date, pnl, trades) VALUES ('2026-07-02', -3000, 1)")
    conn.commit()
    m = reflect.compute_daily_metrics(conn)   # today: 0 pnl
    assert m["drawdown"] == 3000.0            # peak 5000 -> trough 2000


# ---------- weights ----------

def test_weights_nudge_up_on_win_down_on_loss(conn):
    pid_w = make_proposal(conn, symbol="W", strategy="winner")
    make_trade(conn, symbol="W", side="buy", price=100.0, pid=pid_w)
    make_trade(conn, symbol="W", side="sell", price=120.0, pid=pid_w)
    pid_l = make_proposal(conn, symbol="L", strategy="loser")
    make_trade(conn, symbol="L", side="buy", price=100.0, pid=pid_l)
    make_trade(conn, symbol="L", side="sell", price=80.0, pid=pid_l)
    w = reflect.update_strategy_weights(conn)
    assert w["winner"] == 1.15
    assert w["loser"] == 0.85


def test_weights_bounded(conn):
    conn.execute("INSERT INTO strategy_weights(strategy, weight, updated_at)"
                 " VALUES ('loser', 0.25, 't')")
    pid = make_proposal(conn, symbol="L", strategy="loser")
    make_trade(conn, symbol="L", side="buy", price=100.0, pid=pid)
    make_trade(conn, symbol="L", side="sell", price=80.0, pid=pid)
    w = reflect.update_strategy_weights(conn)
    assert w["loser"] == 0.2                  # floor, never zero


# ---------- lessons ----------

def test_apply_lesson_actions_create_update_delete(lessons_dir):
    changed = reflect.apply_lesson_actions([
        {"action": "create", "file": "a.md", "content": "# lesson A\n\nbody"},
    ])
    assert changed and (lessons_dir / "a.md").read_text(encoding="utf-8").startswith("# lesson A")
    reflect.apply_lesson_actions([{"action": "update", "file": "a.md", "content": "# lesson A2\n\nbody"}])
    assert "A2" in (lessons_dir / "a.md").read_text(encoding="utf-8")
    reflect.apply_lesson_actions([{"action": "delete", "file": "a.md"}])
    assert not (lessons_dir / "a.md").exists()


def test_apply_lesson_actions_rejects_garbage(lessons_dir):
    changed = reflect.apply_lesson_actions([
        {"action": "create", "file": "../evil.md", "content": "# x"},   # traversal -> basename
        {"action": "create", "file": "no-ext", "content": "# x"},       # skipped
        {"action": "create", "file": "empty.md", "content": ""},        # skipped
        "not-a-dict",
    ])
    assert changed == ["created evil.md"]
    assert (lessons_dir / "evil.md").exists()   # written INSIDE lessons dir
    assert not (lessons_dir.parent / "evil.md").exists()


def test_nightly_run_mock_end_to_end(conn, lessons_dir):
    pid = make_proposal(conn, symbol="X", strategy="momentum")
    make_trade(conn, symbol="X", side="buy", price=100.0, pid=pid)
    make_trade(conn, symbol="X", side="sell", price=95.0, pid=None)     # stop-loss sale
    result = reflect.run_nightly(conn)
    assert result["journals_written"] == 2
    assert result["metrics"]["trades"] == 2
    assert result["lessons_changed"]                                     # mock lesson written
    files = list(lessons_dir.glob("*.md"))
    assert files
    first_line = files[0].read_text(encoding="utf-8").splitlines()[0]
    assert first_line.startswith("# ")                                   # one-line summary on top


def test_nightly_no_trades_no_lessons(conn, lessons_dir):
    result = reflect.run_nightly(conn)
    assert result["lessons_changed"] == []
    assert not lessons_dir.exists() or not list(lessons_dir.glob("*.md"))
