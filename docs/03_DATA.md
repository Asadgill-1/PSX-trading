# 03 — Data

Source of truth for data shape. Update when schema changes.

## Data sources (investigation pending — first build task)
| Source | What | Status |
|--------|------|--------|
| sarmaaya.pk | Live prices, fundamentals, technicals, announcements, screeners. PSX-authorized redistributor. | INVESTIGATE: public endpoints, robots.txt, ToS, scrape feasibility |
| dps.psx.com.pk | Official PSX data portal: prices, indices, company info | INVESTIGATE: endpoints, delay, ToS |
| PSX Data Services | Licensed real-time feeds | Document license cost/contact if real-time needed |

Decision + trade-offs recorded here after investigation. All ingestion behind adapter
interface (`backend/app/data/base.py`) so source swaps without touching consumers.
Respect robots.txt + ToS. If licensed feed required → stub adapter + document exactly
what license to buy and from whom.

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
