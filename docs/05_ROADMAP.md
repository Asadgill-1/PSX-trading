# 05 — Roadmap / Task list

Status keys: TODO | DOING | DONE | BLOCKED

## Phase 1 milestones (order = build order)
| # | Milestone | Status | Verify gate |
|---|-----------|--------|-------------|
| 0 | Docs + repo scaffold | DONE | pushed to GitHub |
| 1 | Data source investigation (sarmaaya, dps.psx) + decision written to 03_DATA | DONE | fetched real quote in tool output |
| 2 | Backend scaffold: FastAPI, SQLite schema, config, logging, auth | DONE | server starts, login works, pytest green |
| 3 | Market data layer: adapters + scheduler + retries | DONE | live PSX prices in DB, stale-data detection works |
| 4 | Risk layer (pure, deterministic) + THOROUGH tests | DONE | pytest: limits, stop-loss, day halt, circuit breaker all covered; fresh-context review vs spec |
| 5 | Paper trading engine (PSX mechanics) + THOROUGH tests | DONE | pytest: fills, lots, hours, T+2, commission, CGT, P&L; fresh-context review |
| 6 | Agent pipeline: mock mode + real Anthropic adapter, parallel sector scans | TODO | full Scout→Devil→Judge run produces valid proposal in mock mode |
| 7 | Approval gate + Telegram + in-app alerts | TODO | proposal → alert → approve → paper trade with stop attached |
| 8 | Memory: lessons store, journal, nightly reflection, strategy weights | TODO | reflection run writes lesson + adjusts weight |
| 9 | Dashboard (React+Vite+Tailwind, frontend-design skill) | TODO | all 7 dashboard elements visible with real data |
| 10 | Strategy modules (researched, cited) | TODO | each module named + source cited in code |
| 11 | Dockerfile + compose + README + deploy docs | TODO | compose builds; README complete |
| 12 | End-to-end demo vs Definition of done | TODO | full walkthrough, evidence per claim |

## Phase 2 (NOT built until owner asks)
- Real-broker execution adapter. Research PK broker APIs during Phase 1, document findings only.

## Next up
Milestone 6: agent pipeline (mock + Anthropic adapter).

## Backlog / nice-to-have
- VPS migration guide execution
- Postgres swap if ever multi-device
