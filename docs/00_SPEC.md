# 00 — Original specification (verbatim, from owner, 2026-07-04)

This is the contract. Every build decision traces back here or to 06_DECISIONS.md.

---

I'm building a personal AI trading co-pilot webapp for myself, for the Pakistan Stock Exchange (PSX). I am NOT a trader and don't understand stock market jargon, so everything the system tells me must be in plain, simple English, and the system must protect me from my own inexperience. The end goal: the app continuously analyzes the full PSX market, proposes trades with a full risk debate, explains everything to me like I'm a beginner, and only ever trades after I explicitly approve. With that in mind, build the following, end to end, production grade — not a concept or demo.

## What to build

A web application ("PSX Co-Pilot") with this architecture, inspired by the risk-first philosophy of institutional platforms like BlackRock's Aladdin (risk analytics wrapped around every position, portfolio-level exposure view, scenario stress-testing) — build our own original implementation, not a copy:

### 1. Market data layer (PSX only)

- Integrate live/delayed PSX data: prices, KSE-100/KMI-30 indices, volumes, gainers/losers, sector summaries, company fundamentals (EPS, P/E, book value, dividend yield, debt ratios), announcements, and news headlines relevant to PSX-listed companies.
- Primary candidate source: sarmaaya.pk (a PSX-authorized data redistributor with live prices, fundamentals, technicals, announcements, and screeners). Investigate what it exposes (public endpoints, scraping feasibility, terms of service) and also evaluate the official PSX data portal (dps.psx.com.pk) and PSX Data Services licensing. Choose the most reliable legal option, document the trade-offs, and build the ingestion behind a clean adapter interface so the data source can be swapped later. Respect robots.txt and terms of service; if real-time licensed feeds are required for production, stub the adapter and tell me exactly what license to buy and from whom.
- Also research publicly documented strategies of reputable Pakistani market participants and brokerage research (e.g., sector rotation around KSE-100 heavyweights, dividend-capture patterns, result-season plays) and encode the useful, verifiable ideas as named strategy modules. Cite where each idea came from in code comments.

### 2. Hardcoded risk layer (NOT controllable by any AI agent)

A separate, deterministic module that no agent can modify or bypass at runtime:

- Per-position size limit (% of portfolio, configurable by me only via settings UI with confirmation).
- Total portfolio exposure cap and per-sector concentration cap.
- Automatic stop-loss attached to every position.
- Daily loss cutoff that halts all trading for the day when hit.
- Circuit breaker: any anomaly (stale data, repeated order errors) freezes trading and alerts me.
- Enforce these in code paths the agents cannot reach; agents submit proposals, the risk layer validates or rejects them.

### 3. Three-agent analysis pipeline (runs on Anthropic API)

- Scout (bull case): scans the whole PSX market on a schedule during market hours, finds opportunities, builds the case for each trade with evidence (price action, fundamentals, news catalyst).
- Devil's Advocate (bear case): independently attacks each proposal — liquidity risk, valuation, news misread, sector risk, "what kills this trade" — with fresh context, not the Scout's context.
- Judge: reads both cases, checks claims against the actual data, scores conviction, and writes the final report for me.
- Use separate API calls with fresh context for each role; a fresh-context reviewer outperforms self-critique. Delegate independent subtasks (e.g., scanning different sectors) to parallel subagent calls and keep working while they run.

### 4. Plain-English reporting + approval gate

Every proposal reaches me as a report a complete beginner can understand: what the company does, why buy/sell now, exactly how much money at risk, worst realistic case in rupees, the Devil's Advocate's strongest objection, and the Judge's verdict. One-tap Approve / Reject buttons. The system NEVER executes any trade — paper or real — without my explicit approval for that specific trade. This is a hard rule with no exceptions.

### 5. Paper trading first

Phase 1 is a full paper-trading engine: simulated fills against real market prices, realistic PSX constraints (lot sizes, circuit breakers, KATS trading hours, T+2 settlement, brokerage commission and CGT/taxes modeled), full P&L tracking. Real-broker execution is a Phase 2 adapter interface only — research which Pakistani brokers offer APIs (if any) and document findings, but do not build live execution until I explicitly ask after reviewing paper results.

### 6. Self-learning memory system (files + database)

- Database (SQLite or Postgres) storing every proposal, debate, my decision, the outcome, and a journal entry written after every trade explaining the rationale.
- A lessons store the agents read before every analysis session. Store one lesson per file with a one-line summary at the top. Record corrections and confirmed approaches alike, including why they mattered — why losses happened (categorized: bad thesis, bad timing, news misread, risk sizing) and which strategies won and under what market conditions. Don't save what the database already records; update an existing note rather than creating a duplicate; delete notes that turn out to be wrong.
- A nightly reflection job: after market close, review the day's trades, update lessons, and adjust strategy-module weights based on realized performance. The system should measurably improve over time, and the dashboard must show learning metrics (hit rate, average win/loss, drawdown) trending across weeks.

### 7. Dashboard

Portfolio value, open positions, P&L (daily/total), pending proposals awaiting my approval, learning metrics, risk-layer status. (Original spec had PKR 50,000/day target tracker — owner removed it in interview: "forget this 50000 thing make real bot system". Honest metrics only.)

## Engineering requirements

- Production grade: authentication, environment-based secrets, error handling at system boundaries, retries on data feeds, structured logging, tests for the risk layer and paper-trading engine (these two must have thorough test coverage — money-adjacent code), Dockerized, with a README covering deployment and the exact env vars/API keys owner must supply.
- Check whether any MCP servers would genuinely help (e.g., a Postgres/Supabase MCP for the database, a fetch MCP for data ingestion). Use one only if it's better than a direct integration; document the decision either way.
- Don't add features, refactor, or introduce abstractions beyond what the task requires. Don't design for hypothetical future requirements: do the simplest thing that works well. Only validate at system boundaries (user input, external APIs, market data feeds).

## How to work

- When you have enough information to act, act. Do not re-litigate decisions owner already made, or narrate options you will not pursue. If weighing a choice, give a recommendation, not an exhaustive survey.
- Pause for owner only when work genuinely requires them: destructive/irreversible action, real scope change (e.g., paid license needed), or input only owner can provide (API keys, broker account). Otherwise proceed end to end.
- At every major milestone (data layer, risk layer, agent pipeline, paper engine, dashboard), verify work with a fresh-context review against this specification before moving on.
- Before reporting progress, audit each claim against a tool result from the session. Only report work with evidence; if not verified, say so. If tests fail, say so with output.
- Final summaries: for a reader who saw none of the work. Outcome first, then what works, what's stubbed, how to run, decisions needed — plain language.

## Definition of done (Phase 1)

Owner can open the webapp, see live PSX market data, watch the three agents debate real opportunities during market hours, receive plain-English trade proposals, approve one, see it execute in the paper portfolio with a stop-loss attached by the risk layer, and see the lessons database grow after the trading day — all running locally with documented setup (Docker optional locally; Dockerfile provided for VPS).
