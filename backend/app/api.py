"""Owner-facing API routes. Everything here sits behind auth (require_owner).

The approval gate lives here: approve/reject writes a decisions row for THAT
proposal id. Execution only ever follows an 'approve' decision (spec §4).
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import alerts, db
from .auth import require_owner
from .market_hours import is_market_open, trading_date
from .paper import engine as paper
from .risk import engine as risk

log = logging.getLogger("api")
router = APIRouter(prefix="/api", dependencies=[Depends(require_owner)])


def _conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


# ---------- proposals + approval gate ----------

@router.get("/proposals")
def list_proposals(status: str = "pending", conn=Depends(_conn)):
    rows = conn.execute(
        "SELECT * FROM proposals WHERE status=? ORDER BY created_at DESC LIMIT 50", (status,)
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("scout_case", "devil_case", "judge_report"):
            try:
                d[k] = json.loads(d[k])
            except (json.JSONDecodeError, TypeError):
                pass
        out.append(d)
    return out


class DecisionBody(BaseModel):
    note: str | None = None


@router.post("/proposals/{pid}/approve")
def approve(pid: int, body: DecisionBody, conn=Depends(_conn)):
    p = conn.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
    if not p:
        raise HTTPException(404, "Proposal not found")
    if p["status"] != "pending":
        raise HTTPException(409, f"Proposal is already '{p['status']}'")

    conn.execute("INSERT INTO decisions(proposal_id, decision, note, decided_at)"
                 " VALUES (?,?,?,?)", (pid, "approve", body.note, db.utcnow()))
    conn.execute("UPDATE proposals SET status='approved' WHERE id=?", (pid,))
    conn.commit()
    log.info("proposal approved", extra={"ctx": {"id": pid}})

    try:
        trade_id = paper.execute_approved(conn, pid)
        return {"ok": True, "executed": True, "trade_id": trade_id,
                "message": "Approved and executed in the paper portfolio. "
                           "A stop-loss is attached automatically."}
    except paper.ExecutionError as e:
        still_approved = conn.execute(
            "SELECT status FROM proposals WHERE id=?", (pid,)).fetchone()["status"] == "approved"
        return {"ok": True, "executed": False,
                "message": str(e) + (" It stays approved and will fill on the next market tick."
                                     if still_approved else "")}


@router.post("/proposals/{pid}/reject")
def reject(pid: int, body: DecisionBody, conn=Depends(_conn)):
    p = conn.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
    if not p:
        raise HTTPException(404, "Proposal not found")
    if p["status"] != "pending":
        raise HTTPException(409, f"Proposal is already '{p['status']}'")
    conn.execute("INSERT INTO decisions(proposal_id, decision, note, decided_at)"
                 " VALUES (?,?,?,?)", (pid, "reject", body.note, db.utcnow()))
    conn.execute("UPDATE proposals SET status='rejected' WHERE id=?", (pid,))
    conn.commit()
    return {"ok": True, "message": "Rejected. Nothing was traded."}


# ---------- portfolio / dashboard data ----------

@router.get("/portfolio")
def portfolio(conn=Depends(_conn)):
    cash = conn.execute("SELECT cash FROM portfolio WHERE id=1").fetchone()["cash"]
    positions = []
    for pos in conn.execute("SELECT * FROM positions ORDER BY symbol"):
        lp = risk.latest_price(conn, pos["symbol"])
        cur = lp[0] if lp else pos["avg_cost"]
        positions.append({
            **dict(pos), "current_price": cur,
            "market_value": round(pos["qty"] * cur, 2),
            "unrealized_pnl": round((cur - pos["avg_cost"]) * pos["qty"], 2),
        })
    return {
        "cash": cash,
        "positions": positions,
        "portfolio_value": risk.portfolio_value(conn),
        "unrealized_pnl": paper.unrealized_pnl(conn),
        "realized_pnl_today": paper.realized_pnl(conn, trading_date()),
        "market_open": is_market_open(),
    }


@router.get("/trades")
def trades(limit: int = 50, conn=Depends(_conn)):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM trades ORDER BY executed_at DESC LIMIT ?", (min(limit, 200),))]


@router.get("/metrics")
def metrics(conn=Depends(_conn)):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM metrics_daily ORDER BY date DESC LIMIT 60")]


# ---------- risk status + owner-only controls ----------

@router.get("/risk/status")
def risk_status(conn=Depends(_conn)):
    limits = {k: db.get_setting(conn, f"risk.{k}") for k in risk.LIMIT_KEYS}
    return {
        "circuit_tripped": risk.circuit_tripped(conn),
        "day_halted": risk.day_halted(conn),
        "limits": limits,
        "recent_events": [dict(r) for r in conn.execute(
            "SELECT * FROM risk_events ORDER BY id DESC LIMIT 20")],
    }


class ConfirmBody(BaseModel):
    confirm: bool = False


@router.post("/risk/clear-circuit")
def clear_circuit(body: ConfirmBody, conn=Depends(_conn)):
    if not body.confirm:
        raise HTTPException(400, "Set confirm=true to clear the circuit breaker.")
    risk.clear_circuit(conn)
    return {"ok": True, "message": "Circuit breaker cleared. Trading can resume."}


class RiskSettingsBody(BaseModel):
    max_position_pct: float | None = None
    max_sector_pct: float | None = None
    stop_loss_pct: float | None = None
    daily_loss_halt_pct: float | None = None
    max_exposure_pct: float | None = None
    confirm: bool = False


@router.put("/risk/settings")
def update_risk_settings(body: RiskSettingsBody, conn=Depends(_conn)):
    """Owner-only, confirmation required (spec §2). Sane bounds enforced —
    the settings UI cannot turn the safety layer off."""
    if not body.confirm:
        raise HTTPException(400, "Set confirm=true after reviewing the change.")
    bounds = {
        "max_position_pct": (1, 25), "max_sector_pct": (5, 50),
        "stop_loss_pct": (1, 20), "daily_loss_halt_pct": (0.5, 10),
        "max_exposure_pct": (10, 100),
    }
    changed = {}
    for key, (lo, hi) in bounds.items():
        val = getattr(body, key)
        if val is None:
            continue
        if not (lo <= val <= hi):
            raise HTTPException(400, f"{key} must be between {lo} and {hi}.")
        db.set_setting(conn, f"risk.{key}", str(float(val)))
        changed[key] = val
    if changed:
        conn.execute("INSERT INTO risk_events(kind, detail, created_at) VALUES (?,?,?)",
                     ("settings_change", f"Owner changed limits: {changed}", db.utcnow()))
        conn.commit()
    return {"ok": True, "changed": changed}
