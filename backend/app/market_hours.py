"""PSX (KATS) trading session calendar, Asia/Karachi.

Regular hours (verify against PSX notices — Ramadan timings differ):
  Mon-Thu: 09:17 - 15:30
  Fri:     09:17 - 12:00, 14:32 - 16:30
ponytail: no holiday calendar yet — add PSX holiday list when a scan fires on Eid.
"""
from datetime import datetime, time
from zoneinfo import ZoneInfo

KHI = ZoneInfo("Asia/Karachi")

WEEKDAY_SESSIONS = {
    0: [(time(9, 17), time(15, 30))],                            # Mon
    1: [(time(9, 17), time(15, 30))],
    2: [(time(9, 17), time(15, 30))],
    3: [(time(9, 17), time(15, 30))],                            # Thu
    4: [(time(9, 17), time(12, 0)), (time(14, 32), time(16, 30))],  # Fri split
    5: [],                                                        # Sat
    6: [],                                                        # Sun
}


def now_khi() -> datetime:
    return datetime.now(KHI)


def is_market_open(at: datetime | None = None) -> bool:
    dt = (at or now_khi()).astimezone(KHI)
    return any(start <= dt.time() <= end for start, end in WEEKDAY_SESSIONS[dt.weekday()])


def trading_date(at: datetime | None = None) -> str:
    """YYYY-MM-DD in Karachi time — key for metrics_daily and day-halt scope."""
    return (at or now_khi()).astimezone(KHI).date().isoformat()
