"""Alerts: Telegram push (stdlib urllib, no extra dep) + log fallback.

In-app alerting = the pending-proposals queue on the dashboard; this module
covers the push channel. Unconfigured Telegram degrades to a log line, never
an error — alerts must not break trading paths.
"""
import json
import logging
import urllib.request

from . import config

log = logging.getLogger("alerts")


def send(text: str) -> bool:
    """Send plain-text message to the owner's Telegram. True if delivered."""
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        log.info("telegram not configured — alert logged only", extra={"ctx": {"text": text[:200]}})
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    body = json.dumps({"chat_id": config.TELEGRAM_CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = resp.status == 200
    except Exception as e:  # alert failure must never propagate into trading code
        log.warning("telegram send failed", extra={"ctx": {"err": str(e)}})
        return False
    if not ok:
        log.warning("telegram send non-200")
    return ok


def notify_proposals(conn, proposal_ids: list[int]) -> None:
    for pid in proposal_ids:
        p = conn.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
        if not p:
            continue
        judge = json.loads(p["judge_report"])
        send(
            f"📈 New trade idea #{pid}: {p['side'].upper()} {p['qty']} {p['symbol']} "
            f"near Rs {p['entry_price']:.2f}\n"
            f"Worst case: about Rs {p['max_loss_pkr']:,.0f} loss (auto stop-loss at "
            f"Rs {p['stop_loss']:.2f})\n"
            f"Conviction: {p['conviction']:.1f}/10\n\n"
            f"{judge.get('report', '')[:500]}\n\n"
            f"Open the dashboard to Approve or Reject. Nothing happens without you."
        )


def notify_risk_event(kind: str, detail: str) -> None:
    icons = {"circuit_breaker": "🚨", "day_halt": "🛑", "stop_loss": "⚠️"}
    send(f"{icons.get(kind, 'ℹ️')} {detail}")
