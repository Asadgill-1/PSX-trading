"""Environment-based configuration. Secrets come from backend/.env, never code."""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
APP_SECRET_KEY = os.environ.get("APP_SECRET_KEY", "").strip()
APP_PASSWORD_HASH = os.environ.get("APP_PASSWORD_HASH", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

DB_PATH = Path(os.environ.get("DB_PATH", BACKEND_DIR.parent / "data" / "copilot.db"))
PAPER_STARTING_CASH = float(os.environ.get("PAPER_STARTING_CASH", "1000000"))

MOCK_AGENTS = not ANTHROPIC_API_KEY  # no key = mock-agent mode, zero API cost

TIMEZONE = "Asia/Karachi"

# Conservative risk defaults (owner-locked, 06_DECISIONS.md). Live values sit in
# the DB settings table; these seed it on first init. Changeable only via
# settings UI with confirmation — never by agents.
RISK_DEFAULTS = {
    "max_position_pct": 5.0,       # max % of portfolio in one position
    "max_sector_pct": 20.0,        # max % of portfolio in one sector
    "stop_loss_pct": 5.0,          # auto stop-loss below entry
    "daily_loss_halt_pct": 2.0,    # halt all trading for the day at this portfolio loss
    "max_exposure_pct": 100.0,     # total invested cap (rest stays cash)
    "quote_stale_seconds": 900,    # older quote than this during market hours = circuit breaker
}


def require(name: str) -> str:
    """Fail fast at startup for secrets the running mode actually needs."""
    val = os.environ.get(name, "").strip()
    if not val:
        raise RuntimeError(f"Missing required env var {name}. See backend/.env.example")
    return val
