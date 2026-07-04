"""HARDCODED RISK LAYER — deterministic, agent-unreachable.

Hard rule (docs/00_SPEC.md §2): agents submit proposals; this module validates
or rejects. Nothing in app.agents may be imported here, and this module exposes
no mutation of its own rules at runtime — limits live in the DB settings table,
changeable ONLY through the authenticated settings UI with confirmation
(see api routes), never through any agent code path.

Every rejection/halt/trip is recorded in risk_events. All reasons are plain
English — the owner is a beginner.
"""
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .. import db
from ..market_hours import is_market_open, trading_date

log = logging.getLogger("risk")

# Keys of limits this layer enforces (seeded by db.init_db from config.RISK_DEFAULTS)
LIMIT_KEYS = (
    "max_position_pct", "max_sector_pct", "stop_loss_pct",
    "daily_loss_halt_pct", "max_exposure_pct", "quote_stale_seconds",
)


def _limit(conn: sqlite3.Connection, key: str) -> float:
    val = db.get_setting(conn, f"risk.{key}")
    if val is None:  # settings row missing = broken install; refuse to trade
        raise RuntimeError(f"risk setting risk.{key} missing — database not initialized")
    return float(val)


def _event(conn: sqlite3.Connection, kind: str, detail: str) -> None:
    conn.execute(
        "INSERT INTO risk_events(kind, detail, created_at) VALUES (?,?,?)",
        (kind, detail, db.utcnow()),
    )
    conn.commit()
    log.warning("risk event", extra={"ctx": {"kind": kind, "detail": detail}})


# ---------- valuation ----------

def latest_price(conn: sqlite3.Connection, symbol: str) -> tuple[float, str] | None:
    # id DESC tie-break: multiple quotes can share a second-precision timestamp
    row = conn.execute(
        "SELECT price, fetched_at FROM quotes WHERE symbol=? ORDER BY fetched_at DESC, id DESC LIMIT 1",
        (symbol,),
    ).fetchone()
    return (row["price"], row["fetched_at"]) if row else None


def portfolio_value(conn: sqlite3.Connection) -> float:
    """Cash + mark-to-market of open positions (last known price, else avg cost)."""
    cash = conn.execute("SELECT cash FROM portfolio WHERE id=1").fetchone()["cash"]
    total = cash
    for pos in conn.execute("SELECT symbol, qty, avg_cost FROM positions"):
        lp = latest_price(conn, pos["symbol"])
        total += pos["qty"] * (lp[0] if lp else pos["avg_cost"])
    return total


def invested_value(conn: sqlite3.Connection) -> float:
    return portfolio_value(conn) - conn.execute(
        "SELECT cash FROM portfolio WHERE id=1"
    ).fetchone()["cash"]


def sector_value(conn: sqlite3.Connection, sector: str) -> float:
    total = 0.0
    for pos in conn.execute("SELECT symbol, qty, avg_cost FROM positions WHERE sector=?", (sector,)):
        lp = latest_price(conn, pos["symbol"])
        total += pos["qty"] * (lp[0] if lp else pos["avg_cost"])
    return total


# ---------- day halt ----------

def record_day_start(conn: sqlite3.Connection) -> None:
    """Snapshot portfolio value once per trading day; baseline for the loss cutoff."""
    key = f"day.start_value.{trading_date()}"
    if db.get_setting(conn, key) is None:
        db.set_setting(conn, key, str(portfolio_value(conn)))


def day_halted(conn: sqlite3.Connection) -> bool:
    """True once today's portfolio drop exceeds the daily loss cutoff. Sticky for the day."""
    today = trading_date()
    if db.get_setting(conn, f"day.halted.{today}") == "1":
        return True
    start = db.get_setting(conn, f"day.start_value.{today}")
    if start is None:
        return False  # no baseline snapshot yet today — scan job records one at first tick
    start_val = float(start)
    if start_val <= 0:
        return False
    drop_pct = (start_val - portfolio_value(conn)) / start_val * 100
    if drop_pct >= _limit(conn, "daily_loss_halt_pct"):
        db.set_setting(conn, f"day.halted.{today}", "1")
        _event(conn, "day_halt",
               f"Trading stopped for today: portfolio is down {drop_pct:.1f}% "
               f"(limit {_limit(conn, 'daily_loss_halt_pct'):.1f}%). Resets tomorrow.")
        return True
    return False


# ---------- circuit breaker ----------

def circuit_tripped(conn: sqlite3.Connection) -> str | None:
    """Returns trip reason if frozen. Cleared only by owner via settings UI."""
    return db.get_setting(conn, "circuit.tripped")


def trip_circuit(conn: sqlite3.Connection, reason: str) -> None:
    db.set_setting(conn, "circuit.tripped", reason)
    _event(conn, "circuit_breaker", f"Trading frozen: {reason}")


def clear_circuit(conn: sqlite3.Connection) -> None:
    """Owner-only (called from authenticated settings route)."""
    conn.execute("DELETE FROM settings WHERE key='circuit.tripped'")
    conn.commit()
    _event(conn, "circuit_cleared", "Owner cleared the circuit breaker.")


def check_data_freshness(conn: sqlite3.Connection) -> None:
    """During market hours, stale quotes = something is wrong -> freeze."""
    if not is_market_open():
        return
    row = conn.execute("SELECT MAX(fetched_at) AS ft FROM quotes").fetchone()
    if row["ft"] is None:
        return  # nothing ingested yet — scan job will populate
    age = datetime.now(timezone.utc) - datetime.fromisoformat(row["ft"])
    if age > timedelta(seconds=_limit(conn, "quote_stale_seconds")):
        trip_circuit(conn, f"Market data is {int(age.total_seconds() // 60)} minutes old during "
                           "trading hours. Not trading on stale prices.")


# ---------- proposal validation ----------

@dataclass
class RiskVerdict:
    ok: bool
    stop_loss: float = 0.0            # enforced stop for buys
    reasons: list[str] = field(default_factory=list)  # plain-English rejections


def validate_proposal(conn: sqlite3.Connection, *, symbol: str, side: str,
                      qty: int, price: float, sector: str | None) -> RiskVerdict:
    """The single gate every trade passes through. Called at execution time
    (after owner approval) — never skipped, never bypassed."""
    reasons: list[str] = []

    # 0) frozen states first
    tripped = circuit_tripped(conn)
    if tripped:
        reasons.append(f"System is frozen by the circuit breaker: {tripped}")
    if day_halted(conn):
        reasons.append("Today's loss limit was already hit. No more trades today.")

    if side not in ("buy", "sell"):
        reasons.append(f"Unknown trade direction '{side}'.")
    if qty <= 0 or price <= 0:
        reasons.append("Trade size and price must be positive numbers.")

    if reasons:
        _reject(conn, symbol, side, reasons)
        return RiskVerdict(ok=False, reasons=reasons)

    pv = portfolio_value(conn)
    trade_value = qty * price

    if side == "buy":
        cash = conn.execute("SELECT cash FROM portfolio WHERE id=1").fetchone()["cash"]
        if trade_value > cash:
            reasons.append(f"Not enough cash: trade needs Rs {trade_value:,.0f} "
                           f"but only Rs {cash:,.0f} is available.")

        max_pos = _limit(conn, "max_position_pct")
        existing = conn.execute("SELECT qty, avg_cost FROM positions WHERE symbol=?",
                                (symbol,)).fetchone()
        # value existing holding at market like portfolio_value does, else the
        # 5% cap leaks when a position's price has moved off its avg cost
        existing_val = 0.0
        if existing:
            lp = latest_price(conn, symbol)
            existing_val = existing["qty"] * (lp[0] if lp else existing["avg_cost"])
        if pv > 0 and (existing_val + trade_value) / pv * 100 > max_pos:
            reasons.append(f"Too many eggs in one basket: this would put "
                           f"{(existing_val + trade_value) / pv * 100:.1f}% of the portfolio "
                           f"in {symbol}. The limit is {max_pos:.0f}%.")

        max_sec = _limit(conn, "max_sector_pct")
        if sector and pv > 0:
            sec_val = sector_value(conn, sector)
            if (sec_val + trade_value) / pv * 100 > max_sec:
                reasons.append(f"Too much in one industry: sector {sector} would hold "
                               f"{(sec_val + trade_value) / pv * 100:.1f}% of the portfolio. "
                               f"The limit is {max_sec:.0f}%.")

        max_exp = _limit(conn, "max_exposure_pct")
        if pv > 0 and (invested_value(conn) + trade_value) / pv * 100 > max_exp:
            reasons.append(f"Total invested money would exceed {max_exp:.0f}% of the portfolio.")

    else:  # sell — no short selling; must own enough shares
        pos = conn.execute("SELECT qty FROM positions WHERE symbol=?", (symbol,)).fetchone()
        owned = pos["qty"] if pos else 0
        if qty > owned:
            reasons.append(f"Cannot sell {qty} shares of {symbol}: only {owned} owned. "
                           "Short selling is not allowed.")

    if reasons:
        _reject(conn, symbol, side, reasons)
        return RiskVerdict(ok=False, reasons=reasons)

    # stop-loss attached to every buy; risk layer's number, not the agent's
    stop = round(price * (1 - _limit(conn, "stop_loss_pct") / 100), 2) if side == "buy" else 0.0
    return RiskVerdict(ok=True, stop_loss=stop)


def _reject(conn: sqlite3.Connection, symbol: str, side: str, reasons: list[str]) -> None:
    _event(conn, "reject", f"{side} {symbol}: " + " | ".join(reasons))


# ---------- stop-loss monitor ----------

def positions_below_stop(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Open positions whose latest price breached their stop — paper engine sells these."""
    hits = []
    for pos in conn.execute("SELECT * FROM positions"):
        lp = latest_price(conn, pos["symbol"])
        if lp and lp[0] <= pos["stop_loss"]:
            hits.append(pos)
    return hits
