"""Paper engine tests — money-adjacent, thorough by requirement.

Seeded portfolio: 1,000,000 PKR. Conservative risk limits active.
"""
import pytest

from app import db
from app.paper import engine as paper
from app.risk import engine as risk


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    c = db.connect(tmp_path / "t.db")
    db.init_db(c)
    monkeypatch.setattr(paper, "is_market_open", lambda: True)
    return c


def put_quote(conn, symbol, price, sector="0800"):
    conn.execute(
        "INSERT INTO quotes(symbol, sector, price, fetched_at, source) VALUES (?,?,?,?,?)",
        (symbol, sector, price, db.utcnow(), "test"),
    )
    conn.commit()


def make_approved(conn, symbol="LUCK", side="buy", qty=100, price=480.0):
    cur = conn.execute(
        "INSERT INTO proposals(symbol, side, qty, entry_price, stop_loss, strategy,"
        " scout_case, devil_case, judge_report, conviction, max_loss_pkr, status,"
        " created_at, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,'approved',?,?)",
        (symbol, side, qty, price, 0, "test", "bull", "bear", "report", 7, 2400,
         db.utcnow(), db.utcnow()),
    )
    pid = cur.lastrowid
    conn.execute(
        "INSERT INTO decisions(proposal_id, decision, decided_at) VALUES (?,'approve',?)",
        (pid, db.utcnow()),
    )
    conn.commit()
    return pid


# ---------- commission / fees ----------

def test_commission_pct_vs_floor(conn):
    # 100 * 480 * 0.15% = 72 > floor 100*0.03=3
    assert paper.commission(conn, 100, 480.0) == 72.0
    # penny stock: floor wins. 1000*2*0.15%=3 < 1000*0.03=30
    assert paper.commission(conn, 1000, 2.0) == 30.0


def test_commission_configurable(conn):
    db.set_setting(conn, "fees.commission_pct", "0.5")
    assert paper.commission(conn, 100, 480.0) == 240.0


# ---------- buy flow ----------

def test_buy_executes_with_stop_and_cash_deduction(conn):
    put_quote(conn, "LUCK", 480.0, "0804")
    pid = make_approved(conn, qty=100)
    tid = paper.execute_approved(conn, pid)

    trade = conn.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone()
    assert trade["side"] == "buy" and trade["qty"] == 100 and trade["price"] == 480.0
    assert trade["commission"] == 72.0

    pos = conn.execute("SELECT * FROM positions WHERE symbol='LUCK'").fetchone()
    assert pos["qty"] == 100
    assert pos["stop_loss"] == 456.0          # risk layer -5%, attached automatically
    assert pos["sector"] == "0804"

    cash = conn.execute("SELECT cash FROM portfolio WHERE id=1").fetchone()["cash"]
    assert cash == 1_000_000 - 48_000 - 72.0

    status = conn.execute("SELECT status FROM proposals WHERE id=?", (pid,)).fetchone()["status"]
    assert status == "executed"


def test_buy_averaging_up_keeps_tighter_stop(conn):
    put_quote(conn, "X", 100.0)
    pid1 = make_approved(conn, symbol="X", qty=100, price=100.0)
    paper.execute_approved(conn, pid1)
    put_quote(conn, "X", 110.0)
    pid2 = make_approved(conn, symbol="X", qty=100, price=110.0)
    paper.execute_approved(conn, pid2)
    pos = conn.execute("SELECT * FROM positions WHERE symbol='X'").fetchone()
    assert pos["qty"] == 200
    assert pos["avg_cost"] == 105.0
    assert pos["stop_loss"] == 104.5          # 110*0.95, tighter than 95


# ---------- approval gate is absolute ----------

def test_pending_proposal_refuses_execution(conn):
    put_quote(conn, "LUCK", 480.0)
    pid = make_approved(conn)
    conn.execute("UPDATE proposals SET status='pending' WHERE id=?", (pid,))
    conn.commit()
    with pytest.raises(paper.ExecutionError, match="not approved"):
        paper.execute_approved(conn, pid)


def test_approved_status_without_decision_row_refuses(conn):
    put_quote(conn, "LUCK", 480.0)
    pid = make_approved(conn)
    conn.execute("DELETE FROM decisions WHERE proposal_id=?", (pid,))
    conn.commit()
    with pytest.raises(paper.ExecutionError, match="No approval record"):
        paper.execute_approved(conn, pid)


def test_market_closed_defers(conn, monkeypatch):
    put_quote(conn, "LUCK", 480.0)
    pid = make_approved(conn)
    monkeypatch.setattr(paper, "is_market_open", lambda: False)
    with pytest.raises(paper.ExecutionError, match="Market is closed"):
        paper.execute_approved(conn, pid)
    # proposal stays approved for the next open-market tick
    assert conn.execute("SELECT status FROM proposals WHERE id=?", (pid,)).fetchone()["status"] == "approved"


def test_risk_rejection_marks_proposal(conn):
    put_quote(conn, "LUCK", 480.0)
    pid = make_approved(conn, qty=2000)       # ~10% of portfolio > 5% limit
    with pytest.raises(paper.ExecutionError, match="safety layer"):
        paper.execute_approved(conn, pid)
    assert conn.execute("SELECT status FROM proposals WHERE id=?", (pid,)).fetchone()["status"] == "risk_rejected"


def test_no_price_data_refuses(conn):
    pid = make_approved(conn, symbol="GHOST")
    with pytest.raises(paper.ExecutionError, match="No price data"):
        paper.execute_approved(conn, pid)


# ---------- sell flow + CGT + T+2 ----------

def sell_via_engine(conn, symbol, qty, price):
    put_quote(conn, symbol, price)
    return paper._fill_sell(conn, symbol, qty, price, None)


def test_sell_with_gain_charges_cgt_and_locks_proceeds(conn):
    put_quote(conn, "X", 100.0)
    pid = make_approved(conn, symbol="X", qty=100, price=100.0)
    paper.execute_approved(conn, pid)
    cash_after_buy = conn.execute("SELECT cash FROM portfolio WHERE id=1").fetchone()["cash"]

    tid = sell_via_engine(conn, "X", 100, 120.0)
    trade = conn.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone()
    # gain = 20*100 = 2000; CGT 15% = 300
    assert trade["cgt"] == 300.0
    # proceeds NOT in cash yet (T+2)
    assert conn.execute("SELECT cash FROM portfolio WHERE id=1").fetchone()["cash"] == cash_after_buy
    # position closed
    assert conn.execute("SELECT * FROM positions WHERE symbol='X'").fetchone() is None


def test_sell_at_loss_no_cgt(conn):
    put_quote(conn, "X", 100.0)
    pid = make_approved(conn, symbol="X", qty=100, price=100.0)
    paper.execute_approved(conn, pid)
    tid = sell_via_engine(conn, "X", 100, 90.0)
    assert conn.execute("SELECT cgt FROM trades WHERE id=?", (tid,)).fetchone()["cgt"] == 0.0


def test_partial_sell_keeps_position(conn):
    put_quote(conn, "X", 100.0)
    pid = make_approved(conn, symbol="X", qty=100, price=100.0)
    paper.execute_approved(conn, pid)
    sell_via_engine(conn, "X", 40, 110.0)
    pos = conn.execute("SELECT * FROM positions WHERE symbol='X'").fetchone()
    assert pos["qty"] == 60
    assert pos["avg_cost"] == 100.0


def test_settlement_releases_on_t2(conn, monkeypatch):
    put_quote(conn, "X", 100.0)
    pid = make_approved(conn, symbol="X", qty=100, price=100.0)
    paper.execute_approved(conn, pid)
    tid = sell_via_engine(conn, "X", 100, 120.0)

    before = conn.execute("SELECT cash FROM portfolio WHERE id=1").fetchone()["cash"]
    assert paper.settle_due(conn) == 0.0      # not due yet

    # fast-forward: pretend today is the settle date
    settle = conn.execute("SELECT settle_date FROM trades WHERE id=?", (tid,)).fetchone()["settle_date"]
    monkeypatch.setattr(paper, "trading_date", lambda: settle)
    released = paper.settle_due(conn)
    net = 120.0 * 100 - paper.commission(conn, 100, 120.0) - 300.0
    assert released == net
    after = conn.execute("SELECT cash FROM portfolio WHERE id=1").fetchone()["cash"]
    assert after == before + net


def test_settle_date_skips_weekend():
    from datetime import datetime
    from app.market_hours import KHI
    # Thu 2026-07-09 -> Fri, Mon => 2026-07-13
    assert paper._settle_date(datetime(2026, 7, 9, 11, 0, tzinfo=KHI)) == "2026-07-13"
    # Fri 2026-07-10 -> Mon, Tue => 2026-07-14
    assert paper._settle_date(datetime(2026, 7, 10, 11, 0, tzinfo=KHI)) == "2026-07-14"


# ---------- stop-loss automation ----------

def test_stop_loss_auto_sells_and_logs(conn):
    put_quote(conn, "X", 100.0)
    pid = make_approved(conn, symbol="X", qty=100, price=100.0)
    paper.execute_approved(conn, pid)          # stop at 95
    put_quote(conn, "X", 94.0)                 # breach
    trades = paper.check_stops(conn)
    assert len(trades) == 1
    assert conn.execute("SELECT * FROM positions WHERE symbol='X'").fetchone() is None
    ev = conn.execute("SELECT * FROM risk_events WHERE kind='stop_loss'").fetchall()
    assert len(ev) == 1 and "cap the loss" in ev[0]["detail"]


def test_stops_not_checked_when_market_closed(conn, monkeypatch):
    put_quote(conn, "X", 100.0)
    pid = make_approved(conn, symbol="X", qty=100, price=100.0)
    paper.execute_approved(conn, pid)
    put_quote(conn, "X", 90.0)
    monkeypatch.setattr(paper, "is_market_open", lambda: False)
    assert paper.check_stops(conn) == []
    assert conn.execute("SELECT qty FROM positions WHERE symbol='X'").fetchone()["qty"] == 100


# ---------- P&L ----------

def test_unrealized_pnl(conn):
    put_quote(conn, "X", 100.0)
    pid = make_approved(conn, symbol="X", qty=100, price=100.0)
    paper.execute_approved(conn, pid)
    put_quote(conn, "X", 110.0)
    assert paper.unrealized_pnl(conn) == 1000.0


def test_realized_flow_roundtrip(conn):
    put_quote(conn, "X", 100.0)
    pid = make_approved(conn, symbol="X", qty=100, price=100.0)
    paper.execute_approved(conn, pid)
    sell_via_engine(conn, "X", 100, 120.0)
    flow = paper.realized_pnl(conn)
    # buy: -(10000 + 15 fee floor vs pct: 100*100*0.0015=15) ; sell: 12000 - 18 - 300
    assert flow == pytest.approx(-10_015 + 12_000 - 18 - 300)
