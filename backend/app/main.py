"""PSX Co-Pilot API server."""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import auth, config, db
from .logging_setup import setup_logging

setup_logging()
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    conn = db.connect()
    db.init_db(conn)
    conn.close()
    from . import alerts, scheduler
    scheduler.on_scan = alerts.notify_proposals
    sched = scheduler.start()
    log.info("startup complete", extra={"ctx": {"mock_agents": config.MOCK_AGENTS}})
    yield
    sched.shutdown(wait=False)


app = FastAPI(title="PSX Co-Pilot", docs_url=None, redoc_url=None, lifespan=lifespan)

# Vite dev server origin only; prod serves frontend from same origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginBody(BaseModel):
    password: str


@app.post("/api/login")
def login(body: LoginBody, response: Response):
    stored = config.APP_PASSWORD_HASH
    if not stored:
        raise HTTPException(500, "APP_PASSWORD_HASH not set — run: python -m app.cli set-password")
    if not auth.verify_password(body.password, stored):
        log.warning("failed login attempt")
        raise HTTPException(401, "Wrong password")
    token = auth.issue_token()
    response.set_cookie(
        auth.COOKIE_NAME, token,
        httponly=True, samesite="lax", secure=False,  # secure=True behind HTTPS tunnel
        max_age=auth.TOKEN_TTL_DAYS * 86400,
    )
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(auth.COOKIE_NAME)
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"ok": True, "mock_agents": config.MOCK_AGENTS}


@app.get("/api/me", dependencies=[Depends(auth.require_owner)])
def me():
    return {"user": "owner"}


from .api import router as api_router  # noqa: E402

app.include_router(api_router)
