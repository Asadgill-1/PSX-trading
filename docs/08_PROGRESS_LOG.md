# 08 — Progress log

Append after every work session. Newest on top.
Format: date — who — what changed — what's next — blockers.

---

## 2026-07-05 — Milestones 6-9 done (agents, approval+alerts, memory, dashboard)
- M6 agents: Scout/Devil/Judge fresh-context JSON calls, mock mode, parallel debates, hallucination guard, dedup, sizing arithmetic under cap.
- M7 approval gate API (decisions audit rows, deferred fills), Telegram alerts (stdlib, degrade-to-log), risk settings UI endpoints with confirm+bounds.
- M8 memory: journals, daily metrics (hit rate/avg win-loss/drawdown), bounded strategy-weight nudges, lessons file store with create/update/delete validation, nightly reflection wired. Fixed UTC-vs-Karachi date filter bug (khi_day_utc_range).
- M9 dashboard: React+Vite+Tailwind4, night-desk terminal aesthetic (Fraunces + Spline Sans Mono), login, stat strip, proposal cards with full debate + one-tap approve/reject, positions table, learning metrics, safety-layer panel with circuit-clear.
- VERIFIED in browser: login → real PSX data (GCIL/SGPL proposals) → approve while market closed → correct plain-English deferral, DB shows approved + decision row. 88 tests green.
- backend/.env created with TEMP password `changeme-owner-123` — owner must change via `python -m app.cli set-password`.
- Next: M10 strategy modules research, M11 Docker+README, M12 E2E demo.
- Blockers: none.

## 2026-07-04 — Milestones 4+5 done (risk layer + paper engine)
- M4 risk layer (app/risk/engine.py): position/sector/exposure caps, stop-loss attach, sticky day halt with day-start baseline, circuit breaker (manual trip + stale-data auto-trip), plain-English rejections, risk_events audit. 25 tests.
- Fresh-context review (cavecrew-reviewer) found 2 real bugs, both fixed + regression-tested: (1) existing holdings were valued at avg_cost while portfolio at market — 5% cap leaked on run-up positions; (2) record_day_start never called — wired into scan job.
- Self-found bug: latest_price tie-break on second-precision timestamps (ORDER BY fetched_at DESC, id DESC).
- M5 paper engine (app/paper/engine.py): fills only vs approved proposals WITH decision row (approval gate absolute), risk re-validation at fill time, commission max(0.15%, 0.03/share), CGT 15% on gains, T+2 settlement locks sell proceeds, stop-loss auto-sell during market hours, partial sells, avg-cost merging (keeps tighter stop), realized/unrealized P&L. 19 tests.
- Scheduler scan tick now: ingest → day-start baseline → freshness check → settle T+2 → check stops → day-halt eval → on_scan hook.
- 61 tests passing total.
- Next: M6 agent pipeline (Scout/Devil/Judge, mock mode + Anthropic adapter).
- Blockers: none.

## 2026-07-04 — Milestones 2+3 done (backend + data layer)
- M2: FastAPI + SQLite (12 tables, WAL) + scrypt/JWT auth + JSON logging + CLI. 8 tests.
- M3: PSX portal adapter (market-watch parser via data-order attrs, timeseries JSON, company stats), ingest service, KATS market-hours calendar (Fri split), APScheduler (15-min scans, 17:00 reflection hook). 18 tests total, all green.
- LIVE verified: 494 symbols ingested to SQLite; KSE100=185372.2; LUCK quote+fundamentals real.
- Known gaps: announcements stubbed (JS-rendered; StealthyFetcher upgrade path); EPS not on company page (derive price/PE); sector = code not name; no holiday calendar.
- Next: M4 risk layer (pure module + thorough tests).
- Blockers: none.

## 2026-07-04 — spec + interview + docs filled
- Owner delivered full spec (saved verbatim: docs/00_SPEC.md).
- Interview done, 8 decisions locked (docs/06_DECISIONS.md): no profit target, 1M PKR paper capital, no API key yet (mock mode), internet access, PC-then-VPS, conservative risk, positional style, Telegram+in-app alerts.
- Docs 01–07 filled: overview, architecture, data plan, setup, 12-milestone roadmap, decisions, glossary.
- Env checked: Python 3.12.10, Node 24.16.0, NO Docker (Windows 10 Home). Run bare locally, Dockerfile for VPS.
- Next: Milestone 1 — investigate sarmaaya.pk + dps.psx.com.pk endpoints/ToS, write decision to 03_DATA.md.
- Blockers: none.

## 2026-07-04 — setup
- Created handoff folder scaffold (START_HERE + docs/01–08).
- Project not yet described. Owner to fill 01_OVERVIEW next.
- Next: owner describes project, fill overview/architecture/data.
- Blockers: none.
