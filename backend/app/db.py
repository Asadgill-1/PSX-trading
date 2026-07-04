"""SQLite storage. Schema here is the source of truth — keep docs/03_DATA.md in sync.

stdlib sqlite3, WAL mode, no ORM. Single user, single writer.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quotes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol     TEXT NOT NULL,
    sector     TEXT,
    price      REAL NOT NULL,
    open       REAL, high REAL, low REAL,
    ldcp       REAL,               -- last day closing price
    change_pct REAL,
    volume     INTEGER,
    fetched_at TEXT NOT NULL,      -- UTC ISO
    source     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_quotes_symbol_time ON quotes(symbol, fetched_at DESC);

CREATE TABLE IF NOT EXISTS fundamentals (
    symbol         TEXT NOT NULL,
    as_of          TEXT NOT NULL,
    eps            REAL, pe REAL, market_cap REAL, free_float REAL,
    dividend_yield REAL, book_value REAL, debt_ratio REAL,
    source         TEXT NOT NULL,
    PRIMARY KEY (symbol, as_of)
);

CREATE TABLE IF NOT EXISTS news (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol       TEXT,              -- NULL = market-wide
    headline     TEXT NOT NULL,
    body         TEXT,
    published_at TEXT,
    source       TEXT NOT NULL,
    fetched_at   TEXT NOT NULL,
    UNIQUE (headline, published_at)
);

CREATE TABLE IF NOT EXISTS proposals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol        TEXT NOT NULL,
    side          TEXT NOT NULL CHECK (side IN ('buy','sell')),
    qty           INTEGER NOT NULL CHECK (qty > 0),
    entry_price   REAL NOT NULL,
    stop_loss     REAL NOT NULL,
    strategy      TEXT NOT NULL,
    scout_case    TEXT NOT NULL,    -- bull case, plain English
    devil_case    TEXT NOT NULL,    -- bear case, plain English
    judge_report  TEXT NOT NULL,    -- final beginner-readable report
    conviction    REAL NOT NULL,    -- 0..10 from Judge
    max_loss_pkr  REAL NOT NULL,    -- worst realistic case in rupees
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','approved','rejected','expired',
                                    'executed','risk_rejected')),
    created_at    TEXT NOT NULL,
    expires_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);

CREATE TABLE IF NOT EXISTS decisions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id INTEGER NOT NULL REFERENCES proposals(id),
    decision    TEXT NOT NULL CHECK (decision IN ('approve','reject')),
    note        TEXT,
    decided_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id INTEGER REFERENCES proposals(id),
    symbol      TEXT NOT NULL,
    side        TEXT NOT NULL CHECK (side IN ('buy','sell')),
    qty         INTEGER NOT NULL CHECK (qty > 0),
    price       REAL NOT NULL,
    commission  REAL NOT NULL DEFAULT 0,
    cgt         REAL NOT NULL DEFAULT 0,
    kind        TEXT NOT NULL DEFAULT 'paper' CHECK (kind IN ('paper','real')),
    executed_at TEXT NOT NULL,
    settle_date TEXT NOT NULL      -- T+2
);

CREATE TABLE IF NOT EXISTS positions (
    symbol     TEXT PRIMARY KEY,
    qty        INTEGER NOT NULL,
    avg_cost   REAL NOT NULL,
    stop_loss  REAL NOT NULL,      -- risk layer attaches; never NULL
    sector     TEXT,
    opened_at  TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    cash       REAL NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journal (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id   INTEGER REFERENCES trades(id),
    entry      TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS strategy_weights (
    strategy   TEXT PRIMARY KEY,
    weight     REAL NOT NULL DEFAULT 1.0,
    notes      TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL,       -- reject/stop_loss/day_halt/circuit_breaker/settings_change
    detail     TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS metrics_daily (
    date     TEXT PRIMARY KEY,      -- YYYY-MM-DD Asia/Karachi
    pnl      REAL NOT NULL,
    trades   INTEGER NOT NULL,
    hit_rate REAL,
    avg_win  REAL,
    avg_loss REAL,
    drawdown REAL
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Idempotent: creates schema, seeds risk settings + starting cash once."""
    conn.executescript(SCHEMA)
    now = utcnow()
    for key, val in config.RISK_DEFAULTS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES (?,?,?)",
            (f"risk.{key}", str(val), now),
        )
    conn.execute(
        "INSERT OR IGNORE INTO portfolio(id, cash, updated_at) VALUES (1, ?, ?)",
        (config.PAPER_STARTING_CASH, now),
    )
    conn.commit()


def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value, updated_at) VALUES (?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, value, utcnow()),
    )
    conn.commit()
