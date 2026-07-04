"""Risk layer tests — money-adjacent, thorough by requirement (docs/00_SPEC.md).

Portfolio in fixtures: 1,000,000 PKR cash (seeded by init_db).
Conservative limits: 5% position / 20% sector / -5% stop / -2% day halt.
"""
import pytest

from app import db
from app.risk import engine as risk


@pytest.fixture()
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.init_db(c)
    return c


def put_quote(conn, symbol, price, sector="0800", fetched_at=None):
    conn.execute(
        "INSERT INTO quotes(symbol, sector, price, fetched_at, source) VALUES (?,?,?,?,?)",
        (symbol, sector, price, fetched_at or db.utcnow(), "test"),
    )
    conn.commit()


def put_position(conn, symbol, qty, avg_cost, stop_loss, sector="0800"):
    conn.execute(
        "INSERT INTO positions(symbol, qty, avg_cost, stop_loss, sector, opened_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (symbol, qty, avg_cost, stop_loss, sector, db.utcnow(), db.utcnow()),
    )
    conn.commit()


def set_cash(conn, amount):
    conn.execute("UPDATE portfolio SET cash=? WHERE id=1", (amount,))
    conn.commit()


# ---------- position size limit ----------

def test_buy_within_position_limit_ok(conn):
    v = risk.validate_proposal(conn, symbol="LUCK", side="buy", qty=100, price=480.0, sector="0804")
    assert v.ok  # 48,000 = 4.8% of 1M — under 5%


def test_buy_over_position_limit_rejected(conn):
    v = risk.validate_proposal(conn, symbol="LUCK", side="buy", qty=110, price=480.0, sector="0804")
    assert not v.ok  # 52,800 = 5.28% > 5%
    assert any("basket" in r for r in v.reasons)


def test_position_limit_counts_existing_holding(conn):
    put_position(conn, "LUCK", 60, 480.0, 456.0, sector="0804")
    put_quote(conn, "LUCK", 480.0, sector="0804")
    # existing 28,800 + new 24,000 = 52,800 vs pv 1,028,800-> still >5%? pv=cash 1M + pos 28.8k
    v = risk.validate_proposal(conn, symbol="LUCK", side="buy", qty=50, price=480.0, sector="0804")
    assert not v.ok


def test_position_limit_values_holding_at_market_not_cost(conn):
    """Regression (review 2026-07-04): existing holding must be marked to market,
    else a position that ran up 4x sneaks under the 5% cap using stale cost."""
    put_position(conn, "RUNNER", 150, 100.0, 95.0, sector="0700")
    put_quote(conn, "RUNNER", 400.0, sector="0700")
    # market value 60,000 = 5.7% of (1M cash + 60k) — already over the 5% cap
    v = risk.validate_proposal(conn, symbol="RUNNER", side="buy", qty=10, price=400.0, sector="0700")
    assert not v.ok


def test_boundary_exactly_at_limit_allowed(conn):
    # exactly 5.0% of 1,000,000 = 50,000
    v = risk.validate_proposal(conn, symbol="X", side="buy", qty=500, price=100.0, sector="0900")
    assert v.ok


# ---------- sector concentration ----------

def test_sector_cap_rejected(conn):
    set_cash(conn, 1_000_000)
    put_position(conn, "A", 1000, 100.0, 95.0, sector="0777")   # 100k in sector
    put_position(conn, "B", 1000, 100.0, 95.0, sector="0777")   # 200k total sector
    put_quote(conn, "A", 100.0, "0777")
    put_quote(conn, "B", 100.0, "0777")
    # pv = 1M cash + 200k = 1.2M; sector at 200k = 16.7%; +50k -> 20.8% > 20%
    v = risk.validate_proposal(conn, symbol="C", side="buy", qty=500, price=100.0, sector="0777")
    assert not v.ok
    assert any("industry" in r for r in v.reasons)


def test_different_sector_unaffected(conn):
    put_position(conn, "A", 2000, 100.0, 95.0, sector="0777")
    put_quote(conn, "A", 100.0, "0777")
    v = risk.validate_proposal(conn, symbol="C", side="buy", qty=500, price=100.0, sector="0888")
    assert v.ok


# ---------- cash / exposure ----------

def test_insufficient_cash_rejected(conn):
    set_cash(conn, 10_000)
    v = risk.validate_proposal(conn, symbol="X", side="buy", qty=200, price=100.0, sector="0900")
    assert not v.ok
    assert any("Not enough cash" in r for r in v.reasons)


# ---------- stop-loss attach ----------

def test_stop_loss_attached_to_buy(conn):
    v = risk.validate_proposal(conn, symbol="X", side="buy", qty=100, price=100.0, sector="0900")
    assert v.ok
    assert v.stop_loss == 95.0  # -5%


def test_positions_below_stop_detected(conn):
    put_position(conn, "X", 100, 100.0, 95.0)
    put_quote(conn, "X", 94.5)
    hits = risk.positions_below_stop(conn)
    assert [p["symbol"] for p in hits] == ["X"]


def test_positions_above_stop_not_flagged(conn):
    put_position(conn, "X", 100, 100.0, 95.0)
    put_quote(conn, "X", 96.0)
    assert risk.positions_below_stop(conn) == []


# ---------- sell rules ----------

def test_sell_more_than_owned_rejected(conn):
    put_position(conn, "X", 100, 100.0, 95.0)
    v = risk.validate_proposal(conn, symbol="X", side="sell", qty=150, price=100.0, sector="0900")
    assert not v.ok
    assert any("Short selling" in r for r in v.reasons)


def test_sell_owned_ok(conn):
    put_position(conn, "X", 100, 100.0, 95.0)
    put_quote(conn, "X", 100.0)
    v = risk.validate_proposal(conn, symbol="X", side="sell", qty=100, price=100.0, sector="0900")
    assert v.ok
    assert v.stop_loss == 0.0


def test_sell_nothing_owned_rejected(conn):
    v = risk.validate_proposal(conn, symbol="GHOST", side="sell", qty=1, price=10.0, sector=None)
    assert not v.ok


# ---------- day halt ----------

def test_day_halt_triggers_and_sticks(conn, monkeypatch):
    risk.record_day_start(conn)               # baseline = 1,000,000
    set_cash(conn, 975_000)                   # -2.5% > 2% cutoff
    assert risk.day_halted(conn)
    # sticky: even if value recovers, stays halted today
    set_cash(conn, 1_100_000)
    assert risk.day_halted(conn)
    v = risk.validate_proposal(conn, symbol="X", side="buy", qty=10, price=100.0, sector="0900")
    assert not v.ok
    assert any("loss limit" in r for r in v.reasons)


def test_no_halt_within_limit(conn):
    risk.record_day_start(conn)
    set_cash(conn, 985_000)                   # -1.5% < 2%
    assert not risk.day_halted(conn)


def test_day_start_snapshot_once(conn):
    risk.record_day_start(conn)
    set_cash(conn, 500_000)
    risk.record_day_start(conn)               # must NOT overwrite baseline
    from app.market_hours import trading_date
    assert float(db.get_setting(conn, f"day.start_value.{trading_date()}")) == 1_000_000.0


# ---------- circuit breaker ----------

def test_circuit_trip_blocks_everything(conn):
    risk.trip_circuit(conn, "test anomaly")
    v = risk.validate_proposal(conn, symbol="X", side="buy", qty=1, price=10.0, sector=None)
    assert not v.ok
    assert any("circuit breaker" in r for r in v.reasons)


def test_circuit_clear_restores(conn):
    risk.trip_circuit(conn, "test anomaly")
    risk.clear_circuit(conn)
    v = risk.validate_proposal(conn, symbol="X", side="buy", qty=1, price=10.0, sector=None)
    assert v.ok


def test_stale_data_trips_breaker_in_market_hours(conn, monkeypatch):
    monkeypatch.setattr(risk, "is_market_open", lambda: True)
    put_quote(conn, "X", 100.0, fetched_at="2026-07-04T08:00:00+00:00")  # hours old
    risk.check_data_freshness(conn)
    assert risk.circuit_tripped(conn)


def test_fresh_data_no_trip(conn, monkeypatch):
    monkeypatch.setattr(risk, "is_market_open", lambda: True)
    put_quote(conn, "X", 100.0)
    risk.check_data_freshness(conn)
    assert risk.circuit_tripped(conn) is None


def test_stale_data_ignored_when_market_closed(conn, monkeypatch):
    monkeypatch.setattr(risk, "is_market_open", lambda: False)
    put_quote(conn, "X", 100.0, fetched_at="2026-07-04T08:00:00+00:00")
    risk.check_data_freshness(conn)
    assert risk.circuit_tripped(conn) is None


# ---------- garbage input at the boundary ----------

def test_garbage_inputs_rejected(conn):
    assert not risk.validate_proposal(conn, symbol="X", side="hold", qty=1, price=10, sector=None).ok
    assert not risk.validate_proposal(conn, symbol="X", side="buy", qty=0, price=10, sector=None).ok
    assert not risk.validate_proposal(conn, symbol="X", side="buy", qty=-5, price=10, sector=None).ok
    assert not risk.validate_proposal(conn, symbol="X", side="buy", qty=1, price=0, sector=None).ok


# ---------- rejections are recorded ----------

def test_rejections_logged_to_risk_events(conn):
    risk.validate_proposal(conn, symbol="X", side="buy", qty=0, price=10, sector=None)
    rows = conn.execute("SELECT * FROM risk_events WHERE kind='reject'").fetchall()
    assert len(rows) == 1


# ---------- agents cannot import risk internals to mutate ----------

def test_agents_module_never_imports_risk():
    """Static guarantee (spec §2): nothing under app/agents imports the risk
    engine or mutates risk settings. Agents talk in prose about 'risk' freely —
    they just can't touch the module or its settings keys."""
    import re
    from pathlib import Path
    agents_dir = Path(__file__).parent.parent / "app" / "agents"
    if not agents_dir.exists():
        return  # M6 not built yet — test still meaningful later
    forbidden = [
        re.compile(r"from\s+\S*risk\S*\s+import"),   # from ..risk import / from app.risk...
        re.compile(r"import\s+\S*\brisk\b"),          # import app.risk
        re.compile(r"set_setting\([^)]*['\"]risk\."), # writing risk.* settings
    ]
    for py in agents_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for pat in forbidden:
            assert not pat.search(text), f"{py} touches the risk layer: {pat.pattern}"
