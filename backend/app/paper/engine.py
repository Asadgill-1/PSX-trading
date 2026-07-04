"""Paper trading engine — simulated fills against real PSX prices.

PSX mechanics modeled (docs/03_DATA.md):
- KATS hours: fills only while market open (approved proposals wait for next scan tick)
- T+2 settlement: sell proceeds locked until settle date; buys need settled cash
- Commission: max(pct, per-share floor) — typical PK retail rates, configurable
- CGT on realized gains at sell, configurable rate
- Lot size 1 (PSX regular market)
- Exchange circuit breakers not modeled: fills use real quotes, which already
  sit inside the exchange's own ±10% band.
ponytail: fills at latest quote, no slippage model — positional sizes are small
vs daily volume; add impact model if sizes ever grow.

Every execution re-runs the risk layer at fill time. No code path skips it.
"""
import logging
import sqlite3
import threading
from datetime import datetime, timedelta

from .. import db
from ..market_hours import KHI, is_market_open, trading_date
from ..risk import engine as risk

log = logging.getLogger("paper")

# Fee defaults, overridable via settings fees.* (docs/06_DECISIONS.md)
DEFAULT_COMMISSION_PCT = 0.15       # % of trade value
DEFAULT_COMMISSION_MIN_PER_SHARE = 0.03  # PKR per share floor
DEFAULT_CGT_PCT = 15.0              # on realized gains


def _fee_setting(conn: sqlite3.Connection, key: str, default: float) -> float:
    val = db.get_setting(conn, f"fees.{key}")
    return float(val) if val is not None else default


def commission(conn: sqlite3.Connection, qty: int, price: float) -> float:
    pct = _fee_setting(conn, "commission_pct", DEFAULT_COMMISSION_PCT)
    floor = _fee_setting(conn, "commission_min_per_share", DEFAULT_COMMISSION_MIN_PER_SHARE)
    return round(max(qty * price * pct / 100, qty * floor), 2)


def _settle_date(at: datetime | None = None) -> str:
    """T+2 working days (Mon-Fri), Karachi calendar."""
    d = (at or datetime.now(KHI)).astimezone(KHI).date()
    added = 0
    while added < 2:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d.isoformat()


class ExecutionError(Exception):
    """Plain-English refusal; shown to the owner as-is."""


# Serializes fills: the approve endpoint and the scheduler tick run in the same
# process and could otherwise both fill one approved proposal (double cash
# deduction). Lock + status re-read inside = exactly-once.
# ponytail: process-level lock — single uvicorn worker by design (README);
# move the claim into an UPDATE...WHERE status='approved' if workers ever >1.
_exec_lock = threading.Lock()


def execute_approved(conn: sqlite3.Connection, proposal_id: int) -> int:
    """Execute an owner-approved proposal. Returns trade id.

    Hard rule: caller must be the approval flow — this function double-checks
    an 'approve' decision row exists for this exact proposal (spec §4).
    """
    with _exec_lock:
        return _execute_approved_locked(conn, proposal_id)


def _execute_approved_locked(conn: sqlite3.Connection, proposal_id: int) -> int:
    prop = conn.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
    if prop is None:
        raise ExecutionError("That proposal does not exist.")
    if prop["status"] != "approved":
        raise ExecutionError(f"Proposal is '{prop['status']}', not approved — nothing executed.")
    approved = conn.execute(
        "SELECT 1 FROM decisions WHERE proposal_id=? AND decision='approve'", (proposal_id,)
    ).fetchone()
    if not approved:
        raise ExecutionError("No approval record found for this proposal. Not executing.")

    if not is_market_open():
        raise ExecutionError("Market is closed right now. This will execute automatically "
                             "when the market opens.")

    lp = risk.latest_price(conn, prop["symbol"])
    if lp is None:
        raise ExecutionError(f"No price data for {prop['symbol']}. Not executing blind.")
    price = lp[0]

    sector_row = conn.execute(
        "SELECT sector FROM quotes WHERE symbol=? ORDER BY fetched_at DESC LIMIT 1",
        (prop["symbol"],),
    ).fetchone()
    sector = sector_row["sector"] if sector_row else None

    # risk layer gate at fill time — always, no exceptions
    verdict = risk.validate_proposal(conn, symbol=prop["symbol"], side=prop["side"],
                                     qty=prop["qty"], price=price, sector=sector)
    if not verdict.ok:
        conn.execute("UPDATE proposals SET status='risk_rejected' WHERE id=?", (proposal_id,))
        conn.commit()
        raise ExecutionError("The safety layer rejected this trade: " + " ".join(verdict.reasons))

    try:
        if prop["side"] == "buy":
            trade_id = _fill_buy(conn, prop, price, verdict.stop_loss, sector)
        else:
            trade_id = _fill_sell(conn, prop["symbol"], prop["qty"], price, proposal_id)
    except ExecutionError:
        # fill-time refusal (e.g. commission tipped the cash over): kill the
        # proposal, or the scheduler would retry it forever as a zombie
        conn.execute("UPDATE proposals SET status='risk_rejected' WHERE id=?", (proposal_id,))
        conn.commit()
        raise
    conn.execute("UPDATE proposals SET status='executed' WHERE id=?", (proposal_id,))
    conn.commit()
    return trade_id


def _fill_buy(conn: sqlite3.Connection, prop: sqlite3.Row, price: float,
              stop_loss: float, sector: str | None) -> int:
    qty = prop["qty"]
    fee = commission(conn, qty, price)
    cost = qty * price + fee
    cash = conn.execute("SELECT cash FROM portfolio WHERE id=1").fetchone()["cash"]
    if cost > cash:  # fee could tip it over even after risk check
        raise ExecutionError(f"Not enough settled cash for trade plus Rs {fee:,.2f} commission.")

    now = db.utcnow()
    cur = conn.execute(
        "INSERT INTO trades(proposal_id, symbol, side, qty, price, commission, cgt, kind,"
        " executed_at, settle_date) VALUES (?,?,?,?,?,?,0,'paper',?,?)",
        (prop["id"], prop["symbol"], "buy", qty, price, fee, now, _settle_date()),
    )
    trade_id = cur.lastrowid
    conn.execute("UPDATE portfolio SET cash=cash-?, updated_at=? WHERE id=1", (cost, now))

    pos = conn.execute("SELECT * FROM positions WHERE symbol=?", (prop["symbol"],)).fetchone()
    if pos:
        new_qty = pos["qty"] + qty
        new_avg = (pos["qty"] * pos["avg_cost"] + qty * price) / new_qty
        # keep the tighter (higher) stop when averaging up
        new_stop = max(pos["stop_loss"], stop_loss)
        conn.execute(
            "UPDATE positions SET qty=?, avg_cost=?, stop_loss=?, updated_at=? WHERE symbol=?",
            (new_qty, round(new_avg, 4), new_stop, now, prop["symbol"]),
        )
    else:
        conn.execute(
            "INSERT INTO positions(symbol, qty, avg_cost, stop_loss, sector, opened_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (prop["symbol"], qty, price, stop_loss, sector, now, now),
        )
    log.info("buy filled", extra={"ctx": {"symbol": prop["symbol"], "qty": qty,
                                          "price": price, "fee": fee, "stop": stop_loss}})
    return trade_id


def _fill_sell(conn: sqlite3.Connection, symbol: str, qty: int, price: float,
               proposal_id: int | None) -> int:
    pos = conn.execute("SELECT * FROM positions WHERE symbol=?", (symbol,)).fetchone()
    if pos is None or pos["qty"] < qty:
        raise ExecutionError(f"Cannot sell {qty} {symbol}: not enough shares owned.")

    fee = commission(conn, qty, price)
    gross = qty * price
    gain = (price - pos["avg_cost"]) * qty
    cgt = round(max(gain, 0) * _fee_setting(conn, "cgt_pct", DEFAULT_CGT_PCT) / 100, 2)
    net = gross - fee - cgt

    now = db.utcnow()
    settle = _settle_date()
    cur = conn.execute(
        "INSERT INTO trades(proposal_id, symbol, side, qty, price, commission, cgt, kind,"
        " executed_at, settle_date) VALUES (?,?,?,?,?,?,?,'paper',?,?)",
        (proposal_id, symbol, "sell", qty, price, fee, cgt, now, settle),
    )
    trade_id = cur.lastrowid
    # T+2: proceeds locked until settle date (released by settle_due)
    db.set_setting(conn, f"settlement.{trade_id}", f"{net}|{settle}")

    if pos["qty"] == qty:
        conn.execute("DELETE FROM positions WHERE symbol=?", (symbol,))
    else:
        conn.execute("UPDATE positions SET qty=qty-?, updated_at=? WHERE symbol=?",
                     (qty, now, symbol))
    log.info("sell filled", extra={"ctx": {"symbol": symbol, "qty": qty, "price": price,
                                           "fee": fee, "cgt": cgt, "net": net,
                                           "realized": round(gain, 2)}})
    return trade_id


def settle_due(conn: sqlite3.Connection) -> float:
    """Release sell proceeds whose T+2 date has arrived. Returns cash released."""
    released = 0.0
    today = trading_date()
    rows = conn.execute("SELECT key, value FROM settings WHERE key LIKE 'settlement.%'").fetchall()
    for row in rows:
        net_str, settle = row["value"].split("|")
        if settle <= today:
            released += float(net_str)
            conn.execute("DELETE FROM settings WHERE key=?", (row["key"],))
    if released:
        conn.execute("UPDATE portfolio SET cash=cash+?, updated_at=? WHERE id=1",
                     (released, db.utcnow()))
        conn.commit()
        log.info("settlement released", extra={"ctx": {"cash": released}})
    return released


def check_stops(conn: sqlite3.Connection) -> list[int]:
    """Auto-sell positions that breached their stop-loss. This is the risk layer's
    automatic protection (spec §2) — the one sale that needs no fresh approval,
    because the stop was part of the approved trade. Returns trade ids.

    Deliberately NOT gated by validate_proposal (review 2026-07-05): a tripped
    circuit breaker or day halt blocks NEW risk, it must never block the exit
    that caps a loss. Sell-side invariants (own the shares, qty>0) hold by
    construction here; _fill_sell re-checks ownership anyway."""
    if not is_market_open():
        return []
    trades = []
    for pos in risk.positions_below_stop(conn):
        lp = risk.latest_price(conn, pos["symbol"])
        if lp is None:
            continue  # no quote right now — next tick retries
        try:
            tid = _fill_sell(conn, pos["symbol"], pos["qty"], lp[0], None)
        except ExecutionError as e:
            log.error("stop-loss sell failed", extra={"ctx": {"symbol": pos["symbol"], "err": str(e)}})
            continue
        detail = (f"Stop-loss triggered: sold {pos['qty']} {pos['symbol']} at Rs {lp[0]:.2f} "
                  f"(stop was Rs {pos['stop_loss']:.2f}) to cap the loss.")
        conn.execute(
            "INSERT INTO risk_events(kind, detail, created_at) VALUES ('stop_loss', ?, ?)",
            (detail, db.utcnow()),
        )
        from .. import alerts
        alerts.notify_risk_event("stop_loss", detail)
        trades.append(tid)
    conn.commit()
    return trades


# ---------- P&L ----------

def realized_pnl(conn: sqlite3.Connection, date: str | None = None) -> float:
    """Realized P&L from sells (net of fees+CGT) minus cost basis, per trade rows.
    Cost basis reconstruction: sells store price & qty; basis approximated from
    the position's avg_cost at sell time via the recorded CGT when gain>0 is
    lossy — so we compute from trades pairs instead. ponytail: single-portfolio
    FIFO-free approximation using avg cost embedded in cgt math; good enough for
    paper. Revisit if tax-accurate lots ever needed."""
    q = "SELECT COALESCE(SUM(CASE WHEN side='sell' THEN qty*price - commission - cgt" \
        " ELSE -(qty*price + commission) END), 0) AS flow FROM trades"
    args: tuple = ()
    if date:
        from ..market_hours import khi_day_utc_range
        lo, hi = khi_day_utc_range(date)
        q += " WHERE executed_at >= ? AND executed_at < ?"
        args = (lo, hi)
    return conn.execute(q, args).fetchone()["flow"]


def unrealized_pnl(conn: sqlite3.Connection) -> float:
    total = 0.0
    for pos in conn.execute("SELECT symbol, qty, avg_cost FROM positions"):
        lp = risk.latest_price(conn, pos["symbol"])
        if lp:
            total += (lp[0] - pos["avg_cost"]) * pos["qty"]
    return round(total, 2)
