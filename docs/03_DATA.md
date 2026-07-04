# 03 — Data

Source of truth for data shape. Update when schema changes.

## Data sources — DECIDED 2026-07-04 (probed live, evidence in session tool output)

**PRIMARY: dps.psx.com.pk (official PSX data portal).** Free, public, no auth, no robots.txt (404 = no restrictions declared). JSON where it matters:

| Endpoint | Returns | Verified |
|----------|---------|----------|
| `GET /market-watch` | HTML table, ALL symbols: sector, LDCP, open/high/low/current, volume, buy/sell orders (~478KB) | ✅ 200 |
| `GET /timeseries/int/{SYMBOL}` | JSON intraday ticks `[[unix_ts, price, volume], ...]` | ✅ 200, real data |
| `GET /timeseries/int/KSE100` | JSON index intraday (KMI30 same pattern — verify) | ✅ 200 |
| `GET /timeseries/eod/{SYMBOL}` | JSON daily history `[[unix_ts, close, volume, open], ...]` | ✅ 200 |
| `GET /company/{SYMBOL}` | HTML: EPS, P/E, Market Cap, Free Float + profile | ✅ 200 |
| `GET /announcements/companies` | HTML announcements list | ✅ 200 |

Trade-offs: official + free + stable URLs + JSON core; data delayed (portal standard, fine for positional style); fundamentals partial on company page (no dividend yield/book value there — supplement from financial results pages or secondary adapter).

**SECONDARY (adapter stub): sarmaaya.pk.** robots.txt allows all (one enterprise path disallowed). Next.js App Router — no `__NEXT_DATA__` JSON, RSC payload parsing = brittle. Richer fundamentals + screeners exist but harder to extract. Build adapter only if PSX portal fundamentals prove insufficient.

**Real-time licensed feed:** not needed for positional days–weeks style. If ever needed: PSX Data Services (psx.com.pk → Data Services), license sold by PSX directly.

All ingestion behind adapter interface (`backend/app/data/base.py`) so source swaps without touching consumers. Polite scraping: throttle requests, cache, identify via User-Agent, back off on errors.

## Needed data
- Prices: symbol, OHLC, last, volume, change %, timestamp
- Indices: KSE-100, KMI-30 (level, change)
- Market movers: gainers/losers, sector summaries
- Fundamentals: EPS, P/E, book value, dividend yield, debt ratios
- Announcements + news headlines (PSX-listed companies)

## Storage
- DB: SQLite at `data/copilot.db` (WAL mode). Swap-path to Postgres documented but not built (YAGNI).
- Lessons: one file per lesson in `lessons/`, one-line summary at top.

## Core tables (implemented schema lives in `backend/app/db.py` — keep in sync)
| Table | Holds |
|-------|-------|
| quotes | price snapshots per symbol per fetch |
| fundamentals | per-symbol fundamental metrics + as-of date |
| news | headlines/announcements, symbol-tagged |
| proposals | every agent proposal: full debate (scout/devil/judge), status, timestamps |
| decisions | owner approve/reject + timestamp per proposal |
| trades | paper fills: symbol, qty, price, commission, tax, stop-loss |
| positions | open positions, avg cost, stop level |
| journal | post-trade rationale entries |
| strategy_weights | per-strategy-module weight, updated nightly |
| risk_events | every risk-layer rejection, halt, circuit-break |
| metrics_daily | hit rate, avg win/loss, drawdown per day |

## PSX market mechanics (paper engine must model)
- Trading hours (KATS): Mon–Thu 9:17–15:30, Fri split session (9:17–12:00, 14:32–16:30) — verify current times during build
- Lot size: 1 share (odd lots exist historically; regular market = 1)
- Circuit breakers: ±10% or PKR 1 (whichever higher) per symbol per day — verify current rule
- Settlement: T+2
- Brokerage commission: configurable, default ~0.15% or PKR 0.03/share (whichever higher) — verify typical retail rates
- CGT: per current FBR schedule, configurable rate, default 15% on gains
- Currency: PKR. Timezone: Asia/Karachi everywhere.

## Gotchas
- Stale data = circuit breaker trigger (risk layer watches quote timestamps)
- Symbol changes/delistings; bonus/rights issues affect price continuity
- Friday split session; Ramadan hours differ
- No short-selling for retail (deliverable futures exist — out of scope)
