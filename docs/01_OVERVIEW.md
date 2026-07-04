# 01 — Overview

## One line
PSX Co-Pilot: personal AI trading co-pilot webapp for Pakistan Stock Exchange — three AI agents debate every trade, a hardcoded risk layer guards it, owner approves every trade in plain English, paper trading first.

## Problem it solves
Owner wants to trade PSX but is NOT a trader and doesn't know market jargon. System does the analysis (bull case, bear case, judgment), explains everything beginner-plain, enforces risk limits the AI cannot touch, and never trades without explicit per-trade approval.

## Scope
- In scope (Phase 1): PSX market data ingestion, hardcoded risk layer, 3-agent analysis pipeline (Anthropic API + mock mode), plain-English proposals with approve/reject gate, full paper-trading engine with realistic PSX mechanics, self-learning lessons store + nightly reflection, dashboard, auth, Telegram + in-app alerts, Dockerfile for deployment.
- Out of scope (Phase 2, adapter interface only): real-broker execution. Research broker APIs, document, do NOT build until owner explicitly asks.
- Never in scope: any trade (paper or real) without owner's explicit approval for that specific trade. Hard rule, no exceptions.

## Current state
See `08_PROGRESS_LOG.md` last entry. As of 2026-07-04: docs complete, implementation starting.

## Success criteria (Definition of done, Phase 1)
Owner opens webapp → sees live PSX data → agents debate real opportunities during market hours → plain-English proposal arrives (Telegram + in-app) → owner approves → trade executes in paper portfolio with stop-loss auto-attached by risk layer → lessons database grows after trading day. Runs locally, documented setup.

## Key facts
- Owner: single user, beginner, plain English only. Email: wadialdagaya@gmail.com
- Repo: https://github.com/Asadgill-1/PSX-trading
- Paper capital: PKR 1,000,000 default (configurable)
- Risk profile: Conservative (see 06_DECISIONS.md)
- Trading style: positional, days–weeks
- No profit target metric — honest metrics only (owner removed 50k/day target)
