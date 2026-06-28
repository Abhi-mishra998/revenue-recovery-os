import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { inr, inrCompact } from "@/lib/format";
import { StatusBadge } from "@/components/StatusPill";
import { useCountUp } from "@/lib/useCountUp";
import { TrendingDown, AlertTriangle, Wallet, Sparkles, ArrowUpRight } from "lucide-react";

export default function Dashboard() {
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    api.get("/dashboard/summary").then((r) => setSummary(r.data));
  }, []);

  const splitTotal = (summary?.active_inr || 0) + (summary?.cold_inr || 0) + (summary?.dead_inr || 0);

  return (
    <div className="p-6 md:p-10 max-w-[1300px] mx-auto" data-testid="dashboard-page">
      <header>
        <div className="text-[11px] uppercase tracking-[0.08em] text-zinc-500 font-medium">Overview</div>
        <h1 className="text-[28px] md:text-[32px] font-semibold mt-1 text-zinc-900 tracking-tight">Dashboard</h1>
        <p className="text-[13.5px] text-zinc-500 mt-1.5">A live snapshot of your revenue health.</p>
      </header>

      {/* Hero metrics */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-5 mt-6" data-testid="dashboard-cards">
        <div className="reveal">
          <Card
            label="Total Pipeline"
            target={summary?.total_pipeline_inr}
            sub="Open proposals (excl. won/lost)"
            icon={Wallet}
            testId="card-pipeline"
          />
        </div>
        <div className="reveal">
          <Card
            label="Overdue Invoices"
            target={summary?.overdue_invoices_inr}
            sub={summary ? `${summary.overdue_invoices_count} invoices past due` : "—"}
            icon={AlertTriangle}
            testId="card-overdue"
          />
        </div>
        <div className="reveal">
          <Card
            label="Revenue at Risk"
            target={summary?.revenue_at_risk_inr}
            sub="Cold + Dead pipeline"
            icon={TrendingDown}
            testId="card-risk"
          />
        </div>
        <div className="reveal">
          <Card
            label="Est. Recoverable"
            target={summary?.estimated_recoverable_inr}
            sub={`Assumes ${summary?.recoverable_assumption_pct ?? 25}% of at-risk (rule-of-thumb)`}
            icon={Sparkles}
            testId="card-recoverable"
            accent="assumption"
          />
        </div>
      </section>

      {/* Pipeline split by auto status */}
      <section className="grid grid-cols-1 sm:grid-cols-3 gap-3 md:gap-4 mt-4" data-testid="dashboard-splits">
        <div className="reveal"><SplitCard label="Active" value={summary?.active_inr} count={summary?.by_status?.active} status="active" testId="card-active" /></div>
        <div className="reveal"><SplitCard label="Cold" value={summary?.cold_inr} count={summary?.by_status?.cold} status="cold" testId="card-cold" /></div>
        <div className="reveal"><SplitCard label="Dead" value={summary?.dead_inr} count={summary?.by_status?.dead} status="dead" testId="card-dead" /></div>
      </section>

      {/* Donut + Top 5 list */}
      <section className="grid grid-cols-1 lg:grid-cols-5 gap-4 mt-4">
        <div className="revora-card p-5 lg:col-span-2" data-testid="dashboard-donut">
          <div className="flex items-center justify-between">
            <div>
              <div className="revora-stat-label">Pipeline by status</div>
              <p className="text-[12px] text-zinc-500 mt-1">By ₹ value · open proposals only</p>
            </div>
          </div>
          <Donut
            total={splitTotal}
            slices={[
              { key: "active", label: "Active", value: summary?.active_inr || 0, color: "#059669" },
              { key: "cold",   label: "Cold",   value: summary?.cold_inr || 0,   color: "#D97706" },
              { key: "dead",   label: "Dead",   value: summary?.dead_inr || 0,   color: "#E11D48" },
            ]}
          />
        </div>

        <div className="revora-card p-5 lg:col-span-3" data-testid="dashboard-top-risk">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="revora-stat-label">Top 5 proposals at risk</div>
              <p className="text-[12px] text-zinc-500 mt-1">Ranked by value × days silent</p>
            </div>
            <Link to="/proposals" className="text-[12px] text-zinc-900 hover:text-zinc-700 inline-flex items-center gap-1 underline-offset-4 hover:underline" data-testid="top-risk-see-all">
              See all <ArrowUpRight className="w-3 h-3" />
            </Link>
          </div>

          <div className="mt-3 divide-y" style={{ borderColor: "var(--border-soft)" }}>
            {(summary?.top_at_risk || []).length === 0 && (
              <div className="text-sm text-zinc-400 py-6 text-center" data-testid="top-risk-empty">
                Nothing at risk. You&apos;re caught up.
              </div>
            )}
            {(summary?.top_at_risk || []).map((p, idx) => (
              <Link
                key={p.id}
                to={`/proposals/${p.id}`}
                className="flex items-center gap-3 py-3 hover:bg-zinc-50 rounded-md px-2 -mx-2 transition group"
                data-testid={`top-risk-row-${p.id}`}
              >
                <span className="w-6 h-6 shrink-0 rounded-md grid place-items-center font-mono-num text-[11px]"
                  style={{ background: "var(--surface-2)", color: "var(--text-soft)", border: "1px solid var(--border)" }}>
                  {idx + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-[13.5px] font-medium text-zinc-900 truncate">{p.title}</div>
                  <div className="text-[12px] text-zinc-500 truncate">
                    {p.client_company_name} <span className="text-zinc-300">·</span> {p.client_contact_name}
                  </div>
                </div>
                <div className="hidden sm:flex items-center gap-3 text-[12px] text-zinc-500 shrink-0">
                  <span className="tnum">{p.days_silent}d silent</span>
                  <StatusBadge status={p.status} />
                </div>
                <div className="font-mono-num tnum text-[13px] text-zinc-900 shrink-0" data-testid={`top-risk-value-${p.id}`}>
                  {inr(p.value_inr)}
                </div>
              </Link>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function Card({ label, target, sub, icon: Icon, testId, accent }) {
  const animated = useCountUp(target == null ? null : Number(target));
  const display = animated == null
    ? "—"
    : inrCompact(animated);
  return (
    <div className="revora-card p-5 lift-on-hover" data-testid={testId}>
      <div className="flex items-start justify-between">
        <div className="revora-stat-label">{label}</div>
        {Icon && (
          <span className="w-7 h-7 rounded-md grid place-items-center text-zinc-500" style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}>
            <Icon className="w-3.5 h-3.5" strokeWidth={1.75} />
          </span>
        )}
      </div>
      <div className="mt-3 text-[28px] md:text-[30px] font-semibold text-zinc-900 tracking-tight tnum" data-testid={`${testId}-value`}>
        {display}
      </div>
      <div className={`mt-1.5 text-[12px] ${accent === "assumption" ? "text-zinc-600 italic" : "text-zinc-500"}`} data-testid={`${testId}-sub`}>
        {sub}
      </div>
    </div>
  );
}

function SplitCard({ label, value, count, status, testId }) {
  const animated = useCountUp(value == null ? null : Number(value));
  return (
    <div className="revora-card p-5 lift-on-hover" data-testid={testId}>
      <div className="flex items-center justify-between">
        <div className="revora-stat-label">{label}</div>
        <StatusBadge status={status} />
      </div>
      <div className="mt-3 text-[22px] font-semibold text-zinc-900 tracking-tight tnum" data-testid={`${testId}-value`}>
        {animated == null ? "—" : inr(animated)}
      </div>
      <div className="text-[12px] text-zinc-500 mt-1">{count ?? 0} {count === 1 ? "proposal" : "proposals"}</div>
    </div>
  );
}

function Donut({ slices, total }) {
  const size = 200, stroke = 28, radius = (size - stroke) / 2;
  const cx = size / 2, cy = size / 2;
  const circumference = 2 * Math.PI * radius;

  // Build slices
  let offset = 0;
  const segments = slices.map((s) => {
    const fraction = total > 0 ? s.value / total : 0;
    const dash = fraction * circumference;
    const seg = { ...s, fraction, dash, offset };
    offset += dash;
    return seg;
  });

  return (
    <div className="mt-4 flex flex-col md:flex-row items-center gap-5">
      <div className="relative" data-testid="donut-svg">
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
          <circle cx={cx} cy={cy} r={radius} fill="none" stroke="#F1F5F9" strokeWidth={stroke} />
          {segments.map((s) => (
            <circle
              key={s.key}
              cx={cx} cy={cy} r={radius}
              fill="none"
              stroke={s.color}
              strokeWidth={stroke}
              strokeDasharray={`${s.dash} ${circumference - s.dash}`}
              strokeDashoffset={-s.offset}
              data-testid={`donut-slice-${s.key}`}
            />
          ))}
        </svg>
        <div className="absolute inset-0 grid place-items-center">
          <div className="text-center">
            <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500 font-semibold">Open</div>
            <div className="text-xl font-semibold text-slate-900 tnum mt-0.5">{inrCompact(total)}</div>
          </div>
        </div>
      </div>
      <ul className="flex-1 space-y-2 text-sm w-full">
        {segments.map((s) => (
          <li key={s.key} className="flex items-center gap-2" data-testid={`donut-legend-${s.key}`}>
            <span className="dot" style={{ background: s.color }} />
            <span className="text-slate-700 capitalize w-14">{s.label}</span>
            <span className="font-mono-num tnum text-slate-900">{inr(s.value)}</span>
            <span className="ml-auto text-xs text-slate-500 tnum">{(s.fraction * 100).toFixed(0)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
