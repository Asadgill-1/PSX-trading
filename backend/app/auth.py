"""Single-owner auth: scrypt password hash (stdlib) + JWT session cookie.

Trust boundary: everything under /api except /api/login requires a valid token.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Request

from . import config

TOKEN_TTL_DAYS = 7
COOKIE_NAME = "psx_session"

# scrypt parameters (OWASP-reasonable for interactive login)
_SCRYPT = dict(n=2**14, r=8, p=1, dklen=32)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, dk_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except (ValueError, AttributeError):
        return False


def issue_token() -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": "owner", "iat": now, "exp": now + timedelta(days=TOKEN_TTL_DAYS)}
    return jwt.encode(payload, config.require("APP_SECRET_KEY"), algorithm="HS256")


def verify_token(token: str) -> bool:
    try:
        jwt.decode(token, config.require("APP_SECRET_KEY"), algorithms=["HS256"])
        return True
    except jwt.InvalidTokenError:
        return False


def require_owner(request: Request) -> None:
    """FastAPI dependency: 401 unless valid session cookie or Bearer token."""
    token = request.cookies.get(COOKIE_NAME, "")
    if not token:
        authz = request.headers.get("authorization", "")
        if authz.lower().startswith("bearer "):
            token = authz[7:]
    if not token or not verify_token(token):
        raise HTTPException(status_code=401, detail="Not logged in")
