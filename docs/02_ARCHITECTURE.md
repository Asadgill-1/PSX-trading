# 02 — Architecture

## Big picture
```
PSX data sources (sarmaaya.pk / dps.psx.com.pk)
        │  (adapter interface — swappable)
        ▼
 Market Data Layer ──► SQLite (prices, fundamentals, news)
        │
        ▼
 Agent Pipeline (Anthropic API, or mock mode without key)
   Scout (bull) ──► Devil's Advocate (bear, fresh context) ──► Judge (verdict)
        │  reads lessons store before each session
        ▼
 Proposal (plain English)
        │
        ▼
 ┌─────────────────────────────┐
 │ RISK LAYER (deterministic,  │  ◄── agents CANNOT reach or modify
 │ hardcoded, validates/rejects│
 └─────────────────────────────┘
        │ valid proposals only
        ▼
 Approval Gate (owner taps Approve/Reject — Telegram alert + in-app)
        │ approved only
        ▼
 Paper Trading Engine (fills vs real prices, PSX mechanics, P&L)
        │
        ▼
 Nightly Reflection Job ──► lessons store + strategy weights
        │
        ▼
 Dashboard (portfolio, P&L, proposals, learning metrics, risk status)
```

## Trust boundaries (critical)
1. Agents PROPOSE only. Risk layer validates in code agents cannot import or call with write access.
2. Nothing executes without owner approval — approval gate is server-side, per-trade, logged.
3. Risk settings changeable only via settings UI with confirmation (auth required), never via agent or API used by agents.

## Components
| Component | Responsibility | Tech | Location |
|-----------|----------------|------|----------|
| Data adapters | Fetch PSX prices/fundamentals/news behind common interface | Python, Scrapling | `backend/app/data/` |
| Risk layer | Deterministic limit checks, stop-loss attach, day halt, circuit breaker | Pure Python, no LLM imports | `backend/app/risk/` |
| Agent pipeline | Scout/Devil/Judge via Anthropic API; mock mode | Python, anthropic SDK | `backend/app/agents/` |
| Paper engine | Simulated fills, PSX mechanics (lots, T+2, commission, CGT), P&L | Pure Python | `backend/app/paper/` |
| Memory/lessons | Lessons files + DB records + nightly reflection | Python | `backend/app/memory/`, `lessons/` |
| API server | REST + auth + approval endpoints | FastAPI | `backend/app/` |
| Scheduler | Market-hours scans, nightly reflection | APScheduler | `backend/app/scheduler.py` |
| Alerts | Telegram bot + in-app notifications | python-telegram-bot or raw API | `backend/app/alerts/` |
| Dashboard | Web UI | React + Vite + Tailwind | `frontend/` |
| DB | All records | SQLite (file), swap-path to Postgres | `data/copilot.db` |

## Data flow
1. Scheduler triggers scan during PSX hours (Mon–Fri 9:15–15:30 PKT).
2. Data layer refreshes prices/news → SQLite.
3. Scout scans (parallel per-sector calls), drafts opportunities.
4. Each opportunity → Devil's Advocate (fresh context) → Judge (checks claims vs data).
5. Judge's proposals → risk layer pre-check → approval queue → Telegram + in-app alert.
6. Owner approves → risk layer final validation → paper engine executes with stop-loss attached.
7. Stop-loss/day-halt monitored continuously against live prices.
8. After close: reflection job writes journal, updates lessons, adjusts strategy weights.

## External services
- PSX data source: see `03_DATA.md` (investigation + choice documented there)
- Anthropic API: agents. No key yet → mock mode. Get key: console.anthropic.com
- Telegram Bot API: alerts. Owner creates bot via @BotFather (documented in 04_SETUP.md)

## MCP decision
Supabase MCP available but NOT used: single-user local app, SQLite is simpler, zero ops, file-backup trivial. Direct integration beats MCP here. Revisit only if multi-device sync needed.
