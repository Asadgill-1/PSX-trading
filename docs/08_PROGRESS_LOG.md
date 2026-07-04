# 08 — Progress log

Append after every work session. Newest on top.
Format: date — who — what changed — what's next — blockers.

---

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
