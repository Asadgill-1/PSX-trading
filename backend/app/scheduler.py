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
from .paper import engine as paper
from .risk import engine as risk

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

        # risk layer housekeeping — order matters: baseline before halt check
        risk.record_day_start(conn)
        risk.check_data_freshness(conn)
        paper.settle_due(conn)           # release T+2 sell proceeds
        paper.check_stops(conn)          # auto-sell breached stop-losses
        risk.day_halted(conn)            # evaluates + sticks the daily cutoff

        # agents propose only when nothing is frozen — proposals made during a
        # halt would just be rejected at execution anyway
        if not risk.circuit_tripped(conn) and not risk.day_halted(conn):
            from .agents import pipeline
            created = pipeline.run_scan(conn)
            if created and on_scan:
                on_scan(conn, created)   # M7 alert hook
    except Exception:
        log.exception("scan job failed")  # stale data then trips the circuit breaker
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
