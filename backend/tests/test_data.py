"""Offline parser tests against real fixture snapshots (saved 2026-07-04)."""
from pathlib import Path

import pytest

from app.data.psx_portal import parse_company_stats, parse_market_watch, parse_timeseries

FX = Path(__file__).parent / "fixtures"


def test_parse_market_watch_full_board():
    quotes = parse_market_watch((FX / "market_watch.html").read_bytes())
    assert len(quotes) > 400  # full PSX board
    by_sym = {q.symbol: q for q in quotes}
    assert "LUCK" in by_sym
    luck = by_sym["LUCK"]
    assert luck.price and luck.price > 0
    assert luck.volume is not None and luck.volume >= 0
    assert luck.sector  # sector code present
    # every quote has a symbol and non-negative price
    assert all(q.symbol and q.price >= 0 for q in quotes)


def test_parse_eod_timeseries():
    bars = parse_timeseries((FX / "timeseries_eod_LUCK.json").read_bytes())
    assert len(bars) > 100
    ts, close, volume, open_ = bars[0]
    assert ts > 1_600_000_000
    assert close > 0 and open_ > 0 and volume >= 0
    # newest-first ordering
    assert bars[0][0] > bars[-1][0]


def test_parse_index_timeseries():
    ticks = parse_timeseries((FX / "timeseries_int_KSE100.json").read_bytes())
    assert ticks and ticks[0][1] > 10_000  # KSE-100 level sanity


def test_parse_company_stats():
    stats = parse_company_stats((FX / "company_LUCK.html").read_bytes())
    assert stats.get("Open") and stats["Open"] > 0
    # P/E present on company page (label 'P/E Ratio (TTM) **')
    assert any(k.startswith("P/E") for k in stats)


def test_parse_timeseries_error_status():
    with pytest.raises(ValueError):
        parse_timeseries(b'{"status":0,"message":"boom","data":[]}')


def test_ingest_writes_quotes(tmp_path, monkeypatch):
    from app import db
    from app.data import ingest
    from app.data.base import Quote

    class Fake:
        name = "fake"
        def market_watch(self):
            return [Quote(symbol="LUCK", sector="0800", price=480.0, open=481.0,
                          high=485.0, low=476.0, ldcp=479.0, change_pct=0.2, volume=1000)]

    monkeypatch.setattr(ingest, "_source", Fake())
    conn = db.connect(tmp_path / "t.db")
    db.init_db(conn)
    assert ingest.ingest_market_watch(conn) == 1
    latest = ingest.latest_quotes(conn)
    assert latest["LUCK"]["price"] == 480.0
