# START HERE — read this first

You are an LLM/agent picking up this project. This file is your entry point.
Everything you need to finish the project is in this folder. Do not guess — read.

## Reading order (do in sequence)

0. `docs/00_SPEC.md` — the owner's original specification, verbatim. THE CONTRACT.
1. `docs/01_OVERVIEW.md` — what this project is, goal, current state
2. `docs/02_ARCHITECTURE.md` — how it is built, components, how they connect
3. `docs/03_DATA.md` — data sources, schemas, formats, where data lives
4. `docs/04_SETUP.md` — install, env vars, how to run + test
5. `docs/05_ROADMAP.md` — what is done, what is next (your task list)
6. `docs/06_DECISIONS.md` — locked decisions + why (do not re-litigate)
7. `docs/07_GLOSSARY.md` — domain terms (PSX / trading)
8. `docs/08_PROGRESS_LOG.md` — running log; read last entry to know where prev agent stopped
9. `docs/09_SKILLS.md` — which Claude skills/modes to use for coding + UI/UX

## Rules for whoever works here

- Before coding: read the docs above end to end. Trace real flow.
- After a work session: append to `docs/08_PROGRESS_LOG.md` (date, what changed, what's next, blockers).
- Made a real architecture/tech choice? Record it in `docs/06_DECISIONS.md`.
- Changed data shape? Update `docs/03_DATA.md`.
- Finished/added a task? Update `docs/05_ROADMAP.md`.
- Keep docs true. Stale doc worse than no doc.

## Hard rules (non-negotiable, from owner spec)

- NO trade — paper or real — ever executes without owner's explicit approval of that specific trade.
- Risk layer is deterministic code; agents can NEVER modify, bypass, or reach it.
- All owner-facing text: plain beginner English. Owner is not a trader.
- Phase 2 (real-broker execution) is NOT built until owner explicitly asks.
- Do not re-litigate decisions in `docs/06_DECISIONS.md` without owner sign-off.

## Fast facts

- Project name: PSX Co-Pilot (folder: PSX Stock Trading)
- Owner: single user, beginner trader, wadialdagaya@gmail.com
- Repo: https://github.com/Asadgill-1/PSX-trading
- Status: docs complete, implementation in progress — see roadmap + last log entry.
