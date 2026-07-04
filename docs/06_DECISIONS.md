# 06 — Decisions log (ADR)

Locked choices. Do not re-litigate without owner sign-off. Newest on top.

### 2026-07-04 — Stack: FastAPI + SQLite + React/Vite/Tailwind
- Decision: Python 3.12 FastAPI backend, SQLite (WAL) DB, React+Vite+Tailwind frontend, APScheduler for jobs.
- Why: Python best for scraping (Scrapling installed) + anthropic SDK; SQLite = zero-ops single-user; React for production dashboard quality; all runtimes already on dev PC.
- Alternatives rejected: Postgres/Supabase (ops overhead, MCP unneeded for single user); Node backend (weaker scraping stack); server-rendered templates (dashboard interactivity needs).
- Consequences: single-writer DB fine for one user; Postgres swap documented if ever needed.

### 2026-07-04 — No Docker locally, Dockerfile for VPS
- Decision: run bare (venv + npm) on dev PC; ship Dockerfile + compose for VPS phase.
- Why: Docker not installed, Windows 10 Home needs WSL2 setup; bare run faster to iterate.
- Consequences: README covers both paths.

### 2026-07-04 — Owner interview results (all owner-confirmed)
1. NO profit target metric. Owner: "forget this 50000 thing make real bot system". Honest metrics only.
2. Paper capital: PKR 1,000,000 default, configurable in settings.
3. No Anthropic API key yet → mock-agent mode default; real adapter ready; docs state where to buy + est. cost.
4. Access: anywhere via internet → real auth + HTTPS via tunnel (Cloudflare Tunnel or Tailscale; never raw public port).
5. Host: this Windows PC now, cheap VPS later (Docker makes move trivial).
6. Risk profile: CONSERVATIVE — max 5% portfolio per position, max 20% per sector, stop-loss -5%, daily halt at -2% portfolio. Changeable only via settings UI with confirmation.
7. Style: positional, days–weeks holds. Fewer, higher-quality proposals (~1–5/week).
8. Alerts: Telegram bot + in-app both.

### 2026-07-04 — Supabase MCP not used
- Decision: direct SQLite, no MCP for DB or fetch.
- Why: single-user local app; MCP adds indirection, no benefit over sqlite3/Scrapling direct.
- Consequences: revisit only if cloud multi-device sync requested.

### 2026-07-04 — Hard rules (from spec, non-negotiable)
- No trade (paper or real) ever executes without owner's explicit per-trade approval.
- Risk layer is deterministic code agents cannot modify/bypass/import-with-write.
- Phase 2 live execution NOT built until owner explicitly asks.
- All owner-facing text: plain beginner English, no jargon (or jargon explained inline).
