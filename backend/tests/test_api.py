"""API + approval-gate integration tests. Full loop in mock-agent mode:
scan -> pending proposal -> approve -> paper trade with stop attached."""
import os

os.environ["APP_SECRET_KEY"] = "test-secret-key-not-for-production-0000"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import auth, config, db  # noqa: E402
from app.agents import pipeline  # noqa: E402
from app.main import app  # noqa: E402
from app.paper import engine as paper  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "APP_PASSWORD_HASH", auth.hash_password("hunter2hunter2"))
    monkeypatch.setattr(paper, "is_market_open", lambda: True)
    c = TestClient(app)
    c.post("/api/login", json={"password": "hunter2hunter2"})
    return c


def seed_and_scan(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.init_db(conn)
    for sym, price, vol, chg, sec in [("LUCK", 480.0, 1_200_000, 2.4, "0804"),
                                      ("ENGRO", 350.0, 900_000, 1.8, "0810")]:
        conn.execute(
            "INSERT INTO quotes(symbol, sector, price, change_pct, volume, fetched_at, source)"
            " VALUES (?,?,?,?,?,?,?)", (sym, sec, price, chg, vol, db.utcnow(), "test"))
    conn.commit()
    created = pipeline.run_scan(conn)
    conn.close()
    return created


def test_routes_require_auth(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    c = TestClient(app)
    for method, path in [("GET", "/api/proposals"), ("GET", "/api/portfolio"),
                         ("POST", "/api/proposals/1/approve"), ("GET", "/api/risk/status"),
                         ("PUT", "/api/risk/settings")]:
        r = c.request(method, path, json={})
        assert r.status_code == 401, f"{path} not protected"


def test_full_loop_scan_approve_execute(client, tmp_path):
    created = seed_and_scan(tmp_path)
    assert created

    pending = client.get("/api/proposals?status=pending").json()
    assert len(pending) == len(created)
    prop = pending[0]
    assert prop["judge_report"]["report"]          # beginner-readable text present
    assert prop["max_loss_pkr"] > 0

    r = client.post(f"/api/proposals/{prop['id']}/approve", json={}).json()
    assert r["ok"] and r["executed"], r

    pf = client.get("/api/portfolio").json()
    syms = [p["symbol"] for p in pf["positions"]]
    assert prop["symbol"] in syms
    pos = next(p for p in pf["positions"] if p["symbol"] == prop["symbol"])
    assert pos["stop_loss"] > 0                    # risk layer attached the stop
    assert pf["cash"] < 1_000_000                  # cash actually moved

    trades = client.get("/api/trades").json()
    assert trades and trades[0]["symbol"] == prop["symbol"]


def test_reject_never_trades(client, tmp_path):
    created = seed_and_scan(tmp_path)
    pid = created[0]
    r = client.post(f"/api/proposals/{pid}/reject", json={"note": "not today"}).json()
    assert r["ok"]
    assert client.get("/api/trades").json() == []
    assert client.get("/api/portfolio").json()["cash"] == 1_000_000


def test_double_approve_conflicts(client, tmp_path):
    created = seed_and_scan(tmp_path)
    pid = created[0]
    assert client.post(f"/api/proposals/{pid}/approve", json={}).status_code == 200
    assert client.post(f"/api/proposals/{pid}/approve", json={}).status_code == 409


def test_risk_settings_require_confirm_and_bounds(client, tmp_path):
    seed_and_scan(tmp_path)
    assert client.put("/api/risk/settings",
                      json={"max_position_pct": 10}).status_code == 400   # no confirm
    assert client.put("/api/risk/settings",
                      json={"max_position_pct": 90, "confirm": True}).status_code == 400  # bounds
    r = client.put("/api/risk/settings",
                   json={"max_position_pct": 10, "confirm": True}).json()
    assert r["changed"] == {"max_position_pct": 10.0}
    status = client.get("/api/risk/status").json()
    assert status["limits"]["max_position_pct"] == "10.0"
    # audit trail written
    assert any(e["kind"] == "settings_change" for e in status["recent_events"])


def test_clear_circuit_needs_confirm(client, tmp_path):
    seed_and_scan(tmp_path)
    conn = db.connect(tmp_path / "t.db")
    from app.risk import engine as risk
    risk.trip_circuit(conn, "test")
    conn.close()
    assert client.post("/api/risk/clear-circuit", json={}).status_code == 400
    r = client.post("/api/risk/clear-circuit", json={"confirm": True}).json()
    assert r["ok"]
    assert client.get("/api/risk/status").json()["circuit_tripped"] is None


def test_alerts_degrade_gracefully_without_telegram(tmp_path, monkeypatch):
    from app import alerts
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    assert alerts.send("hello") is False   # no exception, just logged
