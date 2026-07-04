"""Auth boundary tests: password hashing + login endpoint + protected routes."""
import os

os.environ["APP_SECRET_KEY"] = "test-secret-key-not-for-production-0000"

from fastapi.testclient import TestClient  # noqa: E402

from app import auth, config  # noqa: E402
from app.main import app  # noqa: E402


def test_password_roundtrip():
    h = auth.hash_password("correct horse battery staple")
    assert auth.verify_password("correct horse battery staple", h)
    assert not auth.verify_password("wrong password", h)
    assert not auth.verify_password("", h)


def test_verify_garbage_hash():
    assert not auth.verify_password("x", "not-a-valid-stored-hash")
    assert not auth.verify_password("x", "")


def test_login_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "APP_PASSWORD_HASH", auth.hash_password("hunter2hunter2"))
    client = TestClient(app)

    # no session -> 401
    assert client.get("/api/me").status_code == 401
    # wrong password -> 401
    assert client.post("/api/login", json={"password": "nope"}).status_code == 401
    # right password -> cookie set, /api/me works
    r = client.post("/api/login", json={"password": "hunter2hunter2"})
    assert r.status_code == 200
    assert auth.COOKIE_NAME in r.cookies
    assert client.get("/api/me").status_code == 200
    # logout clears
    client.post("/api/logout")
    assert client.get("/api/me").status_code == 401


def test_login_without_hash_configured(monkeypatch):
    monkeypatch.setattr(config, "APP_PASSWORD_HASH", "")
    client = TestClient(app, raise_server_exceptions=False)
    assert client.post("/api/login", json={"password": "x"}).status_code == 500


def test_token_verify_rejects_forged():
    assert not auth.verify_token("forged.token.here")
    assert auth.verify_token(auth.issue_token())
