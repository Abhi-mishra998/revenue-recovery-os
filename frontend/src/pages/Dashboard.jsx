import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { inr, inrCompact } from "@/lib/format";
import { StatusBadge } from "@/components/StatusPill";
import { TrendingDown, Snowflake, AlertTriangle, Wallet, Sparkles, Activity, Skull, ArrowUpRight } from "lucide-react";

export default function Dashboard() {
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    api.get("/dashboard/summary").then((r) => setSummary(r.data));
  }, []);

  const splitTotal = (summary?.active_inr || 0) + (summary?.cold_inr || 0) + (summary?.dead_inr || 0);

  return (
    <div className="p-5 md:p-8 max-w-[1300px]" data-testid="dashboard-page">
      <header>
        <div className="text-[11px] uppercase tracking-[0.22em] text-slate-500 font-semibold">Operator console</div>
        <h1 className="text-3xl md:text-4xl font-semibold mt-1.5 text-slate-900">Dashboard</h1>
        <p className="text-sm text-slate-500 mt-1.5">A live snapshot of your revenue health.</p>
      </header>

      {/* Hero metrics */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-5 mt-6" data-testid="dashboard-cards">
        <Card
          label="Total Pipeline"
          value={inrCompact(summary?.total_pipeline_inr)}
          sub="Open proposals (excl. won/lost)"
          icon={Wallet}
          tint="indigo"
          testId="card-pipeline"
        />
        <Card
          label="Overdue Invoices"
          value={inrCompact(summary?.overdue_invoices_inr)}
          sub={summary ? `${summary.overdue_invoices_count} invoices past due` : "—"}
          icon={AlertTriangle}
          tint="red"
          testId="card-overdue"
        />
        <Card
          label="Revenue at Risk"
          value={inrCompact(summary?.revenue_at_risk_inr)}
          sub="Cold + Dead pipeline"
          icon={TrendingDown}
          tint="amber"
          testId="card-risk"
        />
        <Card
          label="Est. Recoverable"
          value={inrCompact(summary?.estimated_recoverable_inr)}
          sub={`Assumes ${summary?.recoverable_assumption_pct ?? 25}% of at-risk (rule-of-thumb)`}
          icon={Sparkles}
          tint="teal"
          testId="card-recoverable"
          accent="assumption"
        />
      </section>

      {/* Pipeline split by auto status */}
      <section className="grid grid-cols-1 sm:grid-cols-3 gap-4 md:gap-5 mt-5" data-testid="dashboard-splits">
        <SplitCard label="Active" value={summary?.active_inr} count={summary?.by_status?.active} status="active" icon={Activity} testId="card-active" />
        <SplitCard label="Cold" value={summary?.cold_inr} count={summary?.by_status?.cold} status="cold" icon={Snowflake} testId="card-cold" />
        <SplitCard label="Dead" value={summary?.dead_inr} count={summary?.by_status?.dead} status="dead" icon={Skull} testId="card-dead" />
      </section>

      {/* Donut + Top 5 list */}
      <section className="grid grid-cols-1 lg:grid-cols-5 gap-5 mt-6">
        <div className="revora-card p-5 md:p-6 lg:col-span-2" data-testid="dashboard-donut">
          <div className="revora-stat-label">Pipeline by status</div>
          <p className="text-xs text-slate-500 mt-1">By ₹ value · stage = sent / negotiating</p>
          <Donut
            total={splitTotal}
            slices={[
              { key: "active", label: "Active", value: summary?.active_inr || 0, color: "#16A34A" },
              { key: "cold",   label: "Cold",   value: summary?.cold_inr || 0,   color: "#D97706" },
              { key: "dead",   label: "Dead",   value: summary?.dead_inr || 0,   color: "#DC2626" },
            ]}
          />
        </div>

        <div className="revora-card p-5 md:p-6 lg:col-span-3" data-testid="dashboard-top-risk">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="revora-stat-label">Top 5 proposals at risk</div>
              <p className="text-xs text-slate-500 mt-1">Ranked by value × days silent. Click to open.</p>
            </div>
            <Link to="/proposals" className="text-xs text-indigo-700 hover:text-indigo-800 inline-flex items-center gap-1" data-testid="top-risk-see-all">
              See all <ArrowUpRight className="w-3 h-3" />
            </Link>
          </div>

          <div className="mt-4 divide-y divide-slate-100">
            {(summary?.top_at_risk || []).length === 0 && (
              <div className="text-sm text-slate-400 py-6 text-center" data-testid="top-risk-empty">
                Nothing at risk. You&apos;re caught up.
              </div>
            )}
            {(summary?.top_at_risk || []).map((p, idx) => (
              <Link
                key={p.id}
                to={`/proposals/${p.id}`}
                className="flex items-center gap-3 py-3 hover:bg-indigo-50/40 rounded-md px-2 -mx-2 transition group"
                data-testid={`top-risk-row-${p.id}`}
              >
                <span className="w-6 h-6 shrink-0 rounded-md bg-slate-100 text-slate-500 text-xs grid place-items-center font-mono-num group-hover:bg-indigo-100 group-hover:text-indigo-700">
                  {idx + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-slate-900 truncate">{p.title}</div>
                  <div className="text-xs text-slate-500 truncate">
                    {p.client_company_name} <span className="text-slate-300">·</span> {p.client_contact_name}
                  </div>
                </div>
                <div className="hidden sm:flex items-center gap-3 text-xs text-slate-500 shrink-0">
                  <span className="tnum">{p.days_silent}d silent</span>
                  <StatusBadge status={p.status} />
                </div>
                <div className="font-mono-num tnum text-sm text-slate-900 shrink-0" data-testid={`top-risk-value-${p.id}`}>
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

function Card({ label, value, sub, icon: Icon, tint, testId, accent }) {
  const tints = {
    indigo: "bg-indigo-50 text-indigo-700 border-indigo-100",
    amber:  "bg-amber-50 text-amber-700 border-amber-100",
    red:    "bg-red-50 text-red-700 border-red-100",
    teal:   "bg-teal-50 text-teal-700 border-teal-100",
  };
  return (
    <div className="revora-card p-5 md:p-6" data-testid={testId}>
      <div className="flex items-start justify-between">
        <div className="revora-stat-label">{label}</div>
        {Icon && (
          <span className={`w-8 h-8 rounded-md border grid place-items-center ${tints[tint]}`}>
            <Icon className="w-4 h-4" />
          </span>
        )}
      </div>
      <div className="mt-4 text-3xl md:text-4xl font-semibold text-slate-900 tnum" data-testid={`${testId}-value`}>
        {value}
      </div>
      <div className={`mt-1 text-xs ${accent === "assumption" ? "text-teal-700" : "text-slate-500"}`} data-testid={`${testId}-sub`}>
        {sub}
      </div>
    </div>
  );
}

function SplitCard({ label, value, count, status, icon: Icon, testId }) {
  return (
    <div className="revora-card p-5" data-testid={testId}>
      <div className="flex items-center justify-between">
        <div className="revora-stat-label">{label}</div>
        <div className="flex items-center gap-2">
          {Icon && <Icon className="w-3.5 h-3.5 text-slate-400" />}
          <StatusBadge status={status} />
        </div>
      </div>
      <div className="mt-2 text-2xl font-semibold text-slate-900 tnum" data-testid={`${testId}-value`}>
        {inr(value)}
      </div>
      <div className="text-xs text-slate-500 mt-1">{count ?? 0} {count === 1 ? "proposal" : "proposals"}</div>
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
