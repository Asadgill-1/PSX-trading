"""DB init + settings tests."""
from app import db


def test_init_idempotent_and_seeded(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.init_db(conn)
    db.init_db(conn)  # second run must not error or duplicate

    # risk settings seeded
    assert db.get_setting(conn, "risk.max_position_pct") == "5.0"
    assert db.get_setting(conn, "risk.daily_loss_halt_pct") == "2.0"

    # portfolio seeded once, 1M PKR
    rows = conn.execute("SELECT cash FROM portfolio").fetchall()
    assert len(rows) == 1
    assert rows[0]["cash"] == 1_000_000.0


def test_settings_roundtrip(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.init_db(conn)
    db.set_setting(conn, "risk.max_position_pct", "7.5")
    assert db.get_setting(conn, "risk.max_position_pct") == "7.5"
    assert db.get_setting(conn, "missing.key") is None


def test_proposal_status_constraint(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.init_db(conn)
    import sqlite3

    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO proposals(symbol, side, qty, entry_price, stop_loss, strategy,"
            " scout_case, devil_case, judge_report, conviction, max_loss_pkr, status,"
            " created_at, expires_at)"
            " VALUES ('LUCK','hold',10,480,456,'s','a','b','c',5,1000,'pending','t','t')"
        )
