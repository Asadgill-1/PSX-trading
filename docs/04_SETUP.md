# 04 — Setup & Run

## Requirements
- Windows 10 dev PC (current) or Linux VPS (later)
- Python 3.12+, Node 20+ (dev machine has 3.12.10 / 24.16.0)
- Docker OPTIONAL locally (not installed on dev PC; Windows 10 Home needs WSL2). Dockerfile provided for VPS deploy.

## Install (bare, current dev PC)
```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

cd ../frontend
npm install
```

## Environment variables (`backend/.env`, copy from `.env.example`)
| Var | Purpose | Where to get |
|-----|---------|--------------|
| ANTHROPIC_API_KEY | Agent pipeline. Empty = mock-agent mode | console.anthropic.com → API keys. Costs: see 09 + README |
| APP_SECRET_KEY | Session/JWT signing | generate: `python -c "import secrets;print(secrets.token_hex(32))"` |
| APP_PASSWORD_HASH | Owner login password hash | set via `python -m app.cli set-password` |
| TELEGRAM_BOT_TOKEN | Alerts | @BotFather on Telegram → /newbot |
| TELEGRAM_CHAT_ID | Where alerts go | message bot, then `python -m app.cli get-chat-id` |

Secrets live in `backend/.env` only. Never commit. `.env` is gitignored.

## Run (dev)
```
# terminal 1 — backend
cd backend && .venv\Scripts\activate && uvicorn app.main:app --reload

# terminal 2 — frontend
cd frontend && npm run dev
```
Open http://localhost:5173

## Run (VPS, later)
```
docker compose up -d
```
Expose via Cloudflare Tunnel or Tailscale (never raw port on public internet). Steps in README.

## Test
```
cd backend && .venv\Scripts\activate && pytest
```
Risk layer + paper engine = thorough coverage (money-adjacent). Others = boundary tests.

## Common problems
(fill as found)
