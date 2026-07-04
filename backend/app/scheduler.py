"""Background jobs: market scans during KATS hours, nightly reflection after close.

Scan job ingests data every 15 min while market open; the agent pipeline (M6)
hooks into on_scan. Reflection job (M8) hooks into on_reflect.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import db
from .data import ingest
from .market_hours import KHI, is_market_open

log = logging.getLogger("scheduler")

# M6/M8 register real handlers; default = data ingest only.
on_scan = None      # callable(conn) -> None
on_reflect = None   # callable(conn) -> None


def scan_job() -> None:
    if not is_market_open():
        return
    conn = db.connect()
    try:
        rows = ingest.ingest_market_watch(conn)
        log.info("scan tick", extra={"ctx": {"quotes": rows}})
        if on_scan:
            on_scan(conn)
    except Exception:
        log.exception("scan job failed")  # circuit breaker (M4) watches quote staleness
    finally:
        conn.close()


def reflect_job() -> None:
    conn = db.connect()
    try:
        if on_reflect:
            on_reflect(conn)
            log.info("nightly reflection done")
    except Exception:
        log.exception("reflection job failed")
    finally:
        conn.close()


def start() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone=KHI)
    sched.add_job(scan_job, CronTrigger(day_of_week="mon-fri", hour="9-16", minute="*/15", timezone=KHI))
    sched.add_job(reflect_job, CronTrigger(day_of_week="mon-fri", hour=17, minute=0, timezone=KHI))
    sched.start()
    log.info("scheduler started")
    return sched
