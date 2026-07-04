"""KATS session calendar tests."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.market_hours import is_market_open, trading_date

KHI = ZoneInfo("Asia/Karachi")


def dt(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=KHI)


def test_weekday_sessions():
    assert is_market_open(dt(2026, 7, 6, 10, 0))       # Mon mid-session
    assert is_market_open(dt(2026, 7, 6, 9, 17))       # Mon open bell
    assert not is_market_open(dt(2026, 7, 6, 9, 0))    # Mon pre-open
    assert not is_market_open(dt(2026, 7, 6, 15, 31))  # Mon after close


def test_friday_split():
    assert is_market_open(dt(2026, 7, 10, 11, 0))      # Fri first session
    assert not is_market_open(dt(2026, 7, 10, 13, 0))  # Fri prayer break
    assert is_market_open(dt(2026, 7, 10, 15, 0))      # Fri second session
    assert not is_market_open(dt(2026, 7, 10, 16, 31))


def test_weekend_closed():
    assert not is_market_open(dt(2026, 7, 4, 11, 0))   # Sat
    assert not is_market_open(dt(2026, 7, 5, 11, 0))   # Sun


def test_trading_date_is_khi_local():
    # 23:00 UTC on the 4th = 04:00 on the 5th in Karachi
    utc = datetime(2026, 7, 4, 23, 0, tzinfo=ZoneInfo("UTC"))
    assert trading_date(utc) == "2026-07-05"
