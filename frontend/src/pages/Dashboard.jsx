import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { inr, inrCompact } from "@/lib/format";
import { StatusPill } from "@/components/StatusPill";
import DraftModal from "@/components/DraftModal";
import { ArrowUpRight, CheckCircle2, Sparkles, TrendingDown, Wallet, Receipt } from "lucide-react";

export default function Dashboard() {
  const [summary, setSummary] = useState(null);
  const [actions, setActions] = useState([]);
  const [done, setDone] = useState({});
  const [draftCtx, setDraftCtx] = useState(null);

  const load = async () => {
    const [s, a] = await Promise.all([
      api.get("/dashboard/summary"),
      api.get("/dashboard/today"),
    ]);
    setSummary(s.data);
    setActions(a.data);
  };

  useEffect(() => { load(); }, []);

  const openDraft = (act) => {
    setDraftCtx({
      mode: act.kind,
      id: act.id,
      client_id: act.client_id,
      label: `${act.title} · ${act.client_name}${act.client_company ? " (" + act.client_company + ")" : ""}`,
    });
  };

  const markFollowedUp = async (act) => {
    if (act.kind !== "proposal") return;
    setDone((d) => ({ ...d, [act.id]: true }));
    try {
      await api.post(`/proposals/${act.id}/touch`);
      setTimeout(load, 350);
    } catch {
      setDone((d) => ({ ...d, [act.id]: false }));
    }
  };

  return (
    <div className="p-6 md:p-10 max-w-[1300px]" data-testid="dashboard-page">
      <Header />

      {/* Hero numbers */}
      <section className="grid grid-cols-1 md:grid-cols-12 gap-6 mt-8" data-testid="hero-grid">
        <HeroCard
          big
          label="Revenue at Risk"
          value={summary?.revenue_at_risk}
          sub={`${(summary?.proposal_counts?.cold || 0) + (summary?.proposal_counts?.dead || 0)} proposals going / gone cold`}
          icon={TrendingDown}
          testId="revenue-at-risk"
        />
        <HeroCard
          label="Recoverable today"
          value={summary?.recoverable}
          sub={`${summary?.proposal_counts?.cold || 0} cold proposals — act before they die`}
          icon={Sparkles}
          accent
          testId="recoverable"
        />
        <HeroCard
          label="Outstanding invoices"
          value={summary?.outstanding_invoices}
          sub={`${(summary?.invoice_counts?.overdue || 0) + (summary?.invoice_counts?.critical || 0)} overdue · ${summary?.invoice_counts?.due || 0} due`}
          icon={Receipt}
          testId="outstanding-invoices"
        />
      </section>

      {/* Secondary metrics */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-6 mt-6" data-testid="secondary-grid">
        <Metric label="Active pipeline" value={inr(summary?.proposal_buckets?.active)} count={summary?.proposal_counts?.active} testId="metric-active" />
        <Metric label="Cold pipeline" value={inr(summary?.proposal_buckets?.cold)} count={summary?.proposal_counts?.cold} testId="metric-cold" />
        <Metric label="Dead pipeline" value={inr(summary?.proposal_buckets?.dead)} count={summary?.proposal_counts?.dead} testId="metric-dead" />
        <Metric label="Collected (paid)" value={inr(summary?.collected)} count={summary?.invoice_counts?.paid} testId="metric-paid" icon={Wallet} />
      </section>

      {/* Today's action list */}
      <section className="mt-10" data-testid="action-list-section">
        <div className="flex items-end justify-between mb-4">
          <div>
            <h2 className="font-serif-display text-3xl">Today's Action List</h2>
            <p className="text-sm text-stone-500 mt-1">
              Ranked by recoverable value × days silent. Draft a follow-up, copy, send.
            </p>
          </div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-stone-500">{actions.length} actions</div>
        </div>

        {actions.length === 0 ? (
          <div className="revora-card p-10 text-center text-stone-500" data-testid="empty-actions">
            <CheckCircle2 className="w-6 h-6 mx-auto text-green-600 mb-2" />
            Inbox zero. Nothing's going cold today. Beautiful.
          </div>
        ) : (
          <div className="revora-card overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-[0.18em] text-stone-500 border-b border-stone-200">
                  <th className="px-4 py-3 font-medium">Client / Item</th>
                  <th className="px-4 py-3 font-medium">Value</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Silent</th>
                  <th className="px-4 py-3 font-medium text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {actions.map((a) => (
                  <tr
                    key={`${a.kind}-${a.id}`}
                    className={`row-hover border-b last:border-0 border-stone-100 ${done[a.id] ? "action-done" : ""}`}
                    data-testid={`action-row-${a.id}`}
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium">{a.title}</div>
                      <div className="text-xs text-stone-500">
                        {a.client_name}{a.client_company ? <> · <span className="text-stone-400">{a.client_company}</span></> : null}
                        {" · "}
                        <span className="uppercase tracking-wider text-[10px]">{a.kind}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 font-mono-num tnum text-stone-900">{inr(a.value)}</td>
                    <td className="px-4 py-3"><StatusPill status={a.status} testId={`action-pill-${a.id}`} /></td>
                    <td className="px-4 py-3 text-stone-500 tnum">{a.days}d</td>
                    <td className="px-4 py-3 text-right">
                      <div className="inline-flex items-center gap-2">
                        <button
                          onClick={() => openDraft(a)}
                          className="cta-primary"
                          data-testid={`draft-btn-${a.id}`}
                        >
                          <Sparkles className="w-3.5 h-3.5" /> Draft follow-up
                        </button>
                        {a.kind === "proposal" && (
                          <button
                            onClick={() => markFollowedUp(a)}
                            className="cta-ghost"
                            data-testid={`done-btn-${a.id}`}
                          >
                            <CheckCircle2 className="w-3.5 h-3.5" /> Done
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <DraftModal open={!!draftCtx} onOpenChange={(o) => !o && setDraftCtx(null)} context={draftCtx} />
    </div>
  );
}

function Header() {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <div className="text-[11px] uppercase tracking-[0.22em] text-stone-500">Operator console</div>
        <h1 className="font-serif-display text-4xl md:text-5xl mt-1.5">Where's the money?</h1>
        <p className="text-sm text-stone-500 mt-2 max-w-xl">
          Every rupee that's slipping out of follow-up — surfaced, ranked, and one click from a draft.
        </p>
      </div>
      <a href="/proposals" className="cta-ghost hidden md:inline-flex" data-testid="header-add-proposal">
        Go to proposals <ArrowUpRight className="w-3.5 h-3.5" />
      </a>
    </div>
  );
}

function HeroCard({ big, label, value, sub, icon: Icon, accent, testId }) {
  const Big = big;
  return (
    <div
      className={`revora-card p-6 md:p-7 ${Big ? "md:col-span-6" : "md:col-span-3"} relative overflow-hidden`}
      data-testid={`hero-${testId}`}
    >
      {Big && (
        <div className="absolute -top-12 -right-10 w-44 h-44 rounded-full bg-amber-100/60 blur-2xl pointer-events-none" />
      )}
      <div className="flex items-center justify-between">
        <div className="revora-stat-label">{label}</div>
        {Icon ? <Icon className={`w-4 h-4 ${accent ? "text-amber-700" : "text-stone-400"}`} /> : null}
      </div>
      <div className={`mt-3 ${Big ? "text-7xl md:text-[5.5rem]" : "text-4xl"} hero-rupee`} data-testid={`${testId}-value`}>
        {value == null ? "—" : (Big ? inrCompact(value) : inr(value))}
      </div>
      <div className="mt-2 text-sm text-stone-500" data-testid={`${testId}-sub`}>{sub}</div>
    </div>
  );
}

function Metric({ label, value, count, testId, icon: Icon }) {
  return (
    <div className="revora-card p-5" data-testid={testId}>
      <div className="flex items-center justify-between">
        <div className="revora-stat-label">{label}</div>
        {Icon ? <Icon className="w-3.5 h-3.5 text-stone-400" /> : null}
      </div>
      <div className="mt-2 text-2xl font-serif-display tnum" data-testid={`${testId}-value`}>{value}</div>
      <div className="text-xs text-stone-500 mt-1">{count ?? 0} {count === 1 ? "item" : "items"}</div>
    </div>
  );
}
