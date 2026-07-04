"""Definition-of-done walkthrough (docs/00_SPEC.md). Run: python demo_e2e.py

Proves, against LIVE PSX data + a throwaway DB:
  1. live market data lands in the DB
  2. agents debate and produce plain-English proposals
  3. owner approval (and ONLY approval) triggers a paper fill
  4. the risk layer attaches a stop-loss to the position
  5. a stop breach auto-sells to cap the loss
  6. nightly reflection grows the lessons store + metrics

Asserts throughout — exits non-zero if any link in the chain breaks.
Mock-agent mode (no API key needed). Market-hours gate is bypassed via
monkeypatching because the demo must run outside KATS hours too.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("APP_SECRET_KEY", "demo-secret-key-000000000000000000")

tmp = Path(tempfile.mkdtemp(prefix="psx_demo_"))
os.environ["DB_PATH"] = str(tmp / "demo.db")

from app import config, db  # noqa: E402

config.DB_PATH = tmp / "demo.db"

from app.agents import pipeline  # noqa: E402
from app.data import ingest  # noqa: E402
from app.memory import reflect  # noqa: E402
from app.paper import engine as paper  # noqa: E402
from app.risk import engine as risk  # noqa: E402

reflect.LESSONS_DIR = tmp / "lessons"

step = 0
def ok(msg):
    global step
    step += 1
    print(f"[{step}] PASS  {msg}")


conn = db.connect()
db.init_db(conn)

# 1 — live data
n = ingest.ingest_market_watch(conn)
assert n > 300, f"expected full board, got {n}"
ok(f"live PSX data: {n} symbols ingested from dps.psx.com.pk")

# 2 — agent debate (mock mode)
assert config.MOCK_AGENTS, "demo expects mock mode (no ANTHROPIC_API_KEY)"
created = pipeline.run_scan(conn)
assert created, "pipeline produced no proposals"
p = conn.execute("SELECT * FROM proposals WHERE id=?", (created[0],)).fetchone()
judge = json.loads(p["judge_report"])
assert judge["report"] and p["max_loss_pkr"] > 0 and p["stop_loss"] < p["entry_price"]
ok(f"agents debated {len(created)} idea(s); sample: {p['side']} {p['qty']} {p['symbol']} "
   f"— worst case Rs {p['max_loss_pkr']:,.0f}")

# 3 — nothing fills without approval
paper.is_market_open = lambda: True  # demo runs outside KATS hours
try:
    paper.execute_approved(conn, p["id"])
    sys.exit("FAIL: executed without approval!")
except paper.ExecutionError:
    ok("execution refused while proposal lacks owner approval")

# owner approves
conn.execute("INSERT INTO decisions(proposal_id, decision, decided_at) VALUES (?,?,?)",
             (p["id"], "approve", db.utcnow()))
conn.execute("UPDATE proposals SET status='approved' WHERE id=?", (p["id"],))
conn.commit()
trade_id = paper.execute_approved(conn, p["id"])
pos = conn.execute("SELECT * FROM positions WHERE symbol=?", (p["symbol"],)).fetchone()
cash = conn.execute("SELECT cash FROM portfolio WHERE id=1").fetchone()["cash"]
assert pos and pos["stop_loss"] > 0 and cash < 1_000_000
ok(f"approved -> paper fill #{trade_id}: {pos['qty']} {p['symbol']} @ market, "
   f"stop-loss Rs {pos['stop_loss']:.2f} attached by risk layer, cash now Rs {cash:,.0f}")

# 4 — risk layer really gates: oversized clone must bounce
verdict = risk.validate_proposal(conn, symbol=p["symbol"], side="buy",
                                 qty=p["qty"] * 30, price=p["entry_price"],
                                 sector=pos["sector"])
assert not verdict.ok and verdict.reasons
ok(f"risk layer rejected an oversized trade in plain English: {verdict.reasons[0][:80]}...")

# 5 — stop breach auto-sells
conn.execute("INSERT INTO quotes(symbol, sector, price, fetched_at, source) VALUES (?,?,?,?,?)",
             (p["symbol"], pos["sector"], round(pos["stop_loss"] * 0.99, 2), db.utcnow(), "demo"))
conn.commit()
sold = paper.check_stops(conn)
assert sold and conn.execute("SELECT * FROM positions WHERE symbol=?",
                             (p["symbol"],)).fetchone() is None
ev = conn.execute("SELECT detail FROM risk_events WHERE kind='stop_loss'").fetchone()
ok(f"stop breach auto-sold the position: {ev['detail'][:90]}...")

# 6 — nightly reflection grows memory
result = reflect.run_nightly(conn)
lessons = list(reflect.LESSONS_DIR.glob("*.md"))
assert result["journals_written"] >= 2 and lessons
assert conn.execute("SELECT COUNT(*) c FROM metrics_daily").fetchone()["c"] == 1
ok(f"nightly reflection: {result['journals_written']} journal entries, "
   f"{len(lessons)} lesson file(s), daily metrics row written")

print(f"\nDefinition of done: all {step} checks passed. Demo DB: {tmp}")
