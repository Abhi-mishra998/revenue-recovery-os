import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { inr, inrCompact } from "@/lib/format";
import { TrendingDown, Snowflake, AlertTriangle, Wallet } from "lucide-react";

export default function Dashboard() {
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    api.get("/dashboard/summary").then((r) => setSummary(r.data));
  }, []);

  return (
    <div className="p-5 md:p-8 max-w-[1300px]" data-testid="dashboard-page">
      <header>
        <div className="text-[11px] uppercase tracking-[0.22em] text-slate-500 font-semibold">Operator console</div>
        <h1 className="text-3xl md:text-4xl font-semibold mt-1.5 text-slate-900">Dashboard</h1>
        <p className="text-sm text-slate-500 mt-1.5">An overview of your revenue health.</p>
      </header>

      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-5 mt-6" data-testid="dashboard-cards">
        <Card
          label="Total Pipeline"
          value={inrCompact(summary?.total_pipeline_inr)}
          sub="Active + cold proposals"
          icon={Wallet}
          tint="indigo"
          testId="card-pipeline"
        />
        <Card
          label="Cold Proposals"
          value={summary == null ? "—" : String(summary.cold_proposals_count)}
          sub="No contact in 8–21 days"
          icon={Snowflake}
          tint="amber"
          testId="card-cold"
        />
        <Card
          label="Overdue Invoices"
          value={summary == null ? "—" : String(summary.overdue_invoices_count)}
          sub={summary ? inr(summary.overdue_invoices_inr) : "—"}
          icon={AlertTriangle}
          tint="red"
          testId="card-overdue"
        />
        <Card
          label="Revenue at Risk"
          value={inrCompact(summary?.revenue_at_risk_inr)}
          sub="Cold + dead pipeline"
          icon={TrendingDown}
          tint="teal"
          testId="card-risk"
        />
      </section>
    </div>
  );
}

function Card({ label, value, sub, icon: Icon, tint, testId }) {
  const tints = {
    indigo: "bg-indigo-50 text-indigo-700 border-indigo-100",
    amber: "bg-amber-50 text-amber-700 border-amber-100",
    red: "bg-red-50 text-red-700 border-red-100",
    teal: "bg-teal-50 text-teal-700 border-teal-100",
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
      <div className="mt-1 text-sm text-slate-500" data-testid={`${testId}-sub`}>{sub}</div>
    </div>
  );
}
