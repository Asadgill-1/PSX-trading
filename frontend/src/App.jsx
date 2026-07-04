import { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";

const rs = (n) =>
  n == null ? "—" : "Rs " + Number(n).toLocaleString("en-PK", { maximumFractionDigits: 0 });
const rs2 = (n) =>
  n == null ? "—" : "Rs " + Number(n).toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pnlClass = (n) => (n > 0 ? "text-gain" : n < 0 ? "text-loss" : "text-ink-dim");

export default function App() {
  const [authed, setAuthed] = useState(null);
  useEffect(() => {
    api.get("/api/me").then(() => setAuthed(true)).catch(() => setAuthed(false));
  }, []);
  if (authed === null) return <Shell><p className="text-ink-dim p-8">Connecting…</p></Shell>;
  return authed ? <Dashboard onLogout={() => setAuthed(false)} /> : <Login onLogin={() => setAuthed(true)} />;
}

function Shell({ children }) {
  return <div className="scanlines min-h-screen bg-ground">{children}</div>;
}

/* ---------- login ---------- */

function Login({ onLogin }) {
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post("/api/login", { password: pw });
      onLogin();
    } catch (e2) {
      setErr(e2.message === "401" ? "Wrong password." : e2.message);
    }
  };
  return (
    <Shell>
      <div className="flex min-h-screen items-center justify-center">
        <form onSubmit={submit} className="w-80 border border-line bg-panel p-8">
          <h1 className="font-display text-3xl text-brass">PSX Co-Pilot</h1>
          <p className="mt-1 mb-6 text-xs text-ink-dim">Your market, explained. Nothing trades without you.</p>
          <input
            type="password"
            value={pw}
            onChange={(e) => setPw(e.target.value)}
            placeholder="Owner password"
            className="w-full border border-line bg-ground px-3 py-2 text-sm outline-none focus:border-brass"
            autoFocus
          />
          {err && <p className="mt-2 text-xs text-loss">{err}</p>}
          <button className="mt-4 w-full border border-brass-dim bg-panel-2 py-2 text-sm text-brass hover:bg-brass hover:text-ground transition-colors">
            Enter
          </button>
        </form>
      </div>
    </Shell>
  );
}

/* ---------- dashboard ---------- */

function Dashboard({ onLogout }) {
  const [pf, setPf] = useState(null);
  const [proposals, setProposals] = useState([]);
  const [riskStatus, setRiskStatus] = useState(null);
  const [metrics, setMetrics] = useState([]);
  const [flash, setFlash] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [p, pr, rsk, m] = await Promise.all([
        api.get("/api/portfolio"),
        api.get("/api/proposals?status=pending"),
        api.get("/api/risk/status"),
        api.get("/api/metrics"),
      ]);
      setPf(p); setProposals(pr); setRiskStatus(rsk); setMetrics(m);
    } catch (e) {
      if (e.message === "401") onLogout();
    }
  }, [onLogout]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 30_000);
    return () => clearInterval(t);
  }, [refresh]);

  const decide = async (id, action) => {
    try {
      const r = await api.post(`/api/proposals/${id}/${action}`);
      setFlash(r.message || "Done.");
      refresh();
    } catch (e) {
      setFlash(e.message);
    }
  };

  if (!pf) return <Shell><p className="text-ink-dim p-8">Loading the desk…</p></Shell>;

  const frozen = riskStatus?.circuit_tripped;
  const halted = riskStatus?.day_halted;

  return (
    <Shell>
      <div className="mx-auto max-w-6xl px-4 pb-16">
        <header className="flex items-baseline justify-between border-b border-line py-4">
          <div>
            <h1 className="font-display text-2xl text-brass">PSX Co-Pilot</h1>
            <p className="text-[11px] text-ink-dim">
              {pf.market_open ? "● market open" : "○ market closed"} · paper trading
            </p>
          </div>
          <div className="text-right">
            <p className="text-[11px] uppercase tracking-widest text-ink-dim">Portfolio value</p>
            <p className="font-display text-3xl">{rs(pf.portfolio_value)}</p>
          </div>
        </header>

        {(frozen || halted) && (
          <div className="mt-4 border border-loss/60 bg-loss/10 p-3 text-sm text-loss">
            {frozen ? <>🚨 Trading frozen: {frozen}</> : <>🛑 Today's loss limit hit — no more trades today.</>}
          </div>
        )}
        {flash && (
          <div className="mt-4 border border-brass-dim bg-panel p-3 text-sm text-brass"
               onClick={() => setFlash("")}>{flash}</div>
        )}

        {/* stat strip */}
        <section className="mt-6 grid grid-cols-2 gap-px border border-line bg-line md:grid-cols-4">
          <Stat label="Cash available" value={rs(pf.cash)} />
          <Stat label="Unrealized P&L" value={rs(pf.unrealized_pnl)} cls={pnlClass(pf.unrealized_pnl)}
                hint="paper profit/loss on positions still open" />
          <Stat label="Realized today" value={rs(pf.realized_pnl_today)} cls={pnlClass(pf.realized_pnl_today)} />
          <Stat label="Awaiting your decision" value={proposals.length} cls={proposals.length ? "text-brass" : ""} />
        </section>

        {/* pending proposals */}
        <SectionTitle n="01" title="Trade ideas waiting for you"
          sub="Nothing happens until you press Approve. Rejecting costs nothing." />
        {proposals.length === 0 ? (
          <Empty>No pending ideas. The agents scan the market every 15 minutes while it's open.</Empty>
        ) : (
          proposals.map((p) => <ProposalCard key={p.id} p={p} decide={decide} />)
        )}

        {/* positions */}
        <SectionTitle n="02" title="What you own" />
        {pf.positions.length === 0 ? (
          <Empty>No open positions yet.</Empty>
        ) : (
          <table className="w-full border border-line text-sm">
            <thead>
              <tr className="bg-panel text-left text-[11px] uppercase tracking-wider text-ink-dim">
                <th className="p-2">Company</th><th className="p-2 text-right">Shares</th>
                <th className="p-2 text-right">Bought at</th><th className="p-2 text-right">Now</th>
                <th className="p-2 text-right">Safety net</th><th className="p-2 text-right">P&L</th>
              </tr>
            </thead>
            <tbody>
              {pf.positions.map((pos) => (
                <tr key={pos.symbol} className="border-t border-line">
                  <td className="p-2 font-semibold">{pos.symbol}</td>
                  <td className="p-2 text-right">{pos.qty.toLocaleString()}</td>
                  <td className="p-2 text-right">{rs2(pos.avg_cost)}</td>
                  <td className="p-2 text-right">{rs2(pos.current_price)}</td>
                  <td className="p-2 text-right text-ink-dim" title="auto-sells if price falls here">
                    {rs2(pos.stop_loss)}
                  </td>
                  <td className={`p-2 text-right ${pnlClass(pos.unrealized_pnl)}`}>{rs(pos.unrealized_pnl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* learning metrics */}
        <SectionTitle n="03" title="Is it learning?"
          sub="Honest numbers only — hit rate is the share of closed trades that made money." />
        <LearningStrip metrics={metrics} />

        {/* risk layer */}
        <SectionTitle n="04" title="Safety layer"
          sub="These limits are enforced in code the AI cannot touch." />
        <RiskPanel status={riskStatus} />
      </div>
    </Shell>
  );
}

function Stat({ label, value, cls = "", hint }) {
  return (
    <div className="bg-panel p-4" title={hint}>
      <p className="text-[11px] uppercase tracking-widest text-ink-dim">{label}</p>
      <p className={`mt-1 font-display text-2xl ${cls}`}>{value}</p>
    </div>
  );
}

function SectionTitle({ n, title, sub }) {
  return (
    <div className="mt-10 mb-3 flex items-baseline gap-3">
      <span className="font-display text-brass-dim">{n}</span>
      <h2 className="font-display text-xl">{title}</h2>
      {sub && <span className="hidden text-[11px] text-ink-dim md:inline">{sub}</span>}
    </div>
  );
}

function Empty({ children }) {
  return <p className="border border-dashed border-line p-6 text-sm text-ink-dim">{children}</p>;
}

function ProposalCard({ p, decide }) {
  const [open, setOpen] = useState(false);
  const judge = p.judge_report || {};
  const devil = p.devil_case || {};
  return (
    <article className="mb-3 border border-brass-dim/40 bg-panel">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
        <div>
          <p className="font-display text-lg">
            <span className="uppercase text-brass">{p.side}</span> {p.qty.toLocaleString()} × {p.symbol}
          </p>
          <p className="text-[11px] text-ink-dim">
            near {rs2(p.entry_price)} · conviction {Number(p.conviction).toFixed(1)}/10 · strategy: {p.strategy}
          </p>
        </div>
        <div className="text-right text-sm">
          <p className="text-loss">worst case ≈ {rs(p.max_loss_pkr)}</p>
          <p className="text-[11px] text-ink-dim">auto safety-net sale at {rs2(p.stop_loss)}</p>
        </div>
      </div>
      <div className="p-4 text-sm leading-relaxed">
        <p>{judge.report}</p>
        {open && (
          <div className="mt-3 space-y-2 border-t border-line pt-3 text-[13px]">
            <p><span className="text-gain">Why buy:</span> {judge.why_now}</p>
            <p><span className="text-loss">Strongest objection:</span> {judge.strongest_objection || devil.strongest}</p>
            <p><span className="text-ink-dim">Worst case:</span> {judge.worst_case}</p>
            <p><span className="text-ink-dim">The company:</span> {judge.what_company_does}</p>
          </div>
        )}
        <button onClick={() => setOpen(!open)} className="mt-2 text-[11px] text-brass underline-offset-2 hover:underline">
          {open ? "less" : "full debate"}
        </button>
      </div>
      <div className="flex gap-px border-t border-line">
        <button onClick={() => decide(p.id, "approve")}
          className="flex-1 bg-panel-2 py-3 text-sm font-semibold text-gain hover:bg-gain hover:text-ground transition-colors">
          ✓ Approve this trade
        </button>
        <button onClick={() => decide(p.id, "reject")}
          className="flex-1 bg-panel-2 py-3 text-sm font-semibold text-loss hover:bg-loss hover:text-ground transition-colors">
          ✕ Reject
        </button>
      </div>
    </article>
  );
}

function LearningStrip({ metrics }) {
  if (!metrics.length) return <Empty>No completed trading days yet. Metrics appear after the first nightly review.</Empty>;
  const latest = metrics[0];
  const cum = metrics.reduce((s, m) => s + (m.pnl || 0), 0);
  return (
    <div className="grid grid-cols-2 gap-px border border-line bg-line md:grid-cols-5">
      <Stat label="Hit rate (latest day)" value={latest.hit_rate == null ? "—" : `${Math.round(latest.hit_rate * 100)}%`} />
      <Stat label="Avg win" value={rs(latest.avg_win)} cls="text-gain" />
      <Stat label="Avg loss" value={rs(latest.avg_loss)} cls="text-loss" />
      <Stat label="Max drawdown" value={rs(latest.drawdown)} hint="deepest dip from a profit peak so far" />
      <Stat label="All-time realized" value={rs(cum)} cls={pnlClass(cum)} />
    </div>
  );
}

function RiskPanel({ status }) {
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  if (!status) return null;
  const L = status.limits || {};
  const clear = async () => {
    if (!window.confirm("Clear the circuit breaker and allow trading again?")) return;
    setSaving(true);
    try {
      await api.post("/api/risk/clear-circuit", { confirm: true });
      setMsg("Circuit breaker cleared.");
    } catch (e) { setMsg(e.message); }
    setSaving(false);
  };
  return (
    <div className="border border-line bg-panel p-4 text-sm">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Limit k="Max per company" v={`${L.max_position_pct}%`} />
        <Limit k="Max per industry" v={`${L.max_sector_pct}%`} />
        <Limit k="Auto-sell loss" v={`-${L.stop_loss_pct}%`} />
        <Limit k="Daily stop-everything" v={`-${L.daily_loss_halt_pct}%`} />
        <Limit k="Stale-data freeze" v={`${Math.round(L.quote_stale_seconds / 60)} min`} />
      </div>
      {status.circuit_tripped && (
        <button onClick={clear} disabled={saving}
          className="mt-4 border border-loss px-4 py-2 text-loss hover:bg-loss hover:text-ground transition-colors">
          I understand — clear the freeze
        </button>
      )}
      {msg && <p className="mt-2 text-[11px] text-brass">{msg}</p>}
      <details className="mt-4">
        <summary className="cursor-pointer text-[11px] uppercase tracking-widest text-ink-dim">
          Recent safety events
        </summary>
        <ul className="mt-2 space-y-1 text-[12px] text-ink-dim">
          {(status.recent_events || []).map((e) => (
            <li key={e.id}>
              <span className="text-brass-dim">[{e.kind}]</span> {e.detail}
            </li>
          ))}
          {!status.recent_events?.length && <li>None yet.</li>}
        </ul>
      </details>
    </div>
  );
}

function Limit({ k, v }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-widest text-ink-dim">{k}</p>
      <p className="font-display text-lg">{v}</p>
    </div>
  );
}
