# PSX Co-Pilot

Personal AI trading co-pilot for the Pakistan Stock Exchange. Three AI agents
(Scout → Devil's Advocate → Judge) debate every trade idea in plain English, a
hardcoded risk layer the agents cannot touch enforces the limits, and **nothing
ever trades — paper or real — without your explicit approval of that specific
trade.** Phase 1 is paper trading only.

New here (human or AI)? Read [START_HERE.md](START_HERE.md) first.

## What it does

- Ingests live PSX market data (official portal, dps.psx.com.pk) every 15 min
  during KATS trading hours (Asia/Karachi, incl. Friday split session)
- Scout scans the most active movers; Devil's Advocate attacks each idea with a
  fresh context; Judge verifies claims against the data and writes a
  beginner-plain report
- You approve/reject on the dashboard (or after a Telegram ping); approved
  trades fill in a realistic paper engine (T+2 settlement, commission, CGT,
  auto stop-loss)
- Safety layer: 5% max per company, 20% per industry, −5% auto-sell, −2% daily
  halt, stale-data circuit breaker — changeable only in the UI with confirmation
- Nightly reflection writes journals, learning metrics, lessons files, and
  re-weights strategies by realized results

## Run — bare (Windows dev box)

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -c "import secrets;print('APP_SECRET_KEY='+secrets.token_hex(32))"  # paste into .env
python -m app.cli set-password

cd ..\frontend
npm install
npm run build          # or: npm run dev (hot reload on :5173, proxies to :8000)

cd ..\backend
uvicorn app.main:app --port 8000
```

Open http://localhost:8000 — the built dashboard is served by the API server.

## Run — Docker (VPS)

```bash
cp backend/.env.example backend/.env   # fill it (see below)
docker compose up -d --build
```

Serves on `:8000`. DB lives in the `copilot-data` volume; lessons in `./lessons`.

**Never expose port 8000 raw to the internet.** Use one of:
- Cloudflare Tunnel: `cloudflared tunnel --url http://localhost:8000` (free,
  gives you an HTTPS URL)
- Tailscale: install on server + phone, open `http://<machine-name>:8000`
  (private network, nothing public)

## Environment variables (backend/.env)

| Var | Required | What |
|-----|----------|------|
| `APP_SECRET_KEY` | yes | Session signing. `python -c "import secrets;print(secrets.token_hex(32))"` |
| `APP_PASSWORD_HASH` | yes | Login. Set with `python -m app.cli set-password` |
| `ANTHROPIC_API_KEY` | no | Real agents. Empty = mock mode (canned but realistic debates, zero cost). Get one at console.anthropic.com → expect roughly $1–10/day depending on market activity (Haiku scans + Sonnet debates) |
| `TELEGRAM_BOT_TOKEN` | no | Alerts. Telegram → @BotFather → `/newbot` |
| `TELEGRAM_CHAT_ID` | no | Message your bot once, then `python -m app.cli get-chat-id` |
| `PAPER_STARTING_CASH` | no | Default 1,000,000 PKR |
| `DB_PATH` | no | Default `data/copilot.db` |

## Tests

```powershell
cd backend && .venv\Scripts\activate && pytest
```

89 tests. The risk layer and paper engine are money-adjacent and carry the
thorough coverage on purpose.

## Architecture, decisions, roadmap

Everything lives in [docs/](docs/) — spec ([00](docs/00_SPEC.md)), architecture
([02](docs/02_ARCHITECTURE.md)), data sources ([03](docs/03_DATA.md)), locked
decisions ([06](docs/06_DECISIONS.md)), progress log ([08](docs/08_PROGRESS_LOG.md)).

Hard rules: agents propose, the risk layer disposes, the owner decides. Phase 2
(real broker execution) is not built and will not be until the owner asks after
reviewing paper results.
