import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { inr, inrCompact } from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { Download, ChevronRight, ArrowUp, ArrowDown, Minus, Sparkles, Loader2 } from "lucide-react";
import ThumbsFeedback from "@/components/ThumbsFeedback";

const STATUS_TONE = {
  red: "bg-rose-100 text-rose-700 border-rose-200",
  amber: "bg-amber-100 text-amber-700 border-amber-200",
  green: "bg-emerald-100 text-emerald-700 border-emerald-200",
};
const STATUS_DOT = { red: "🔴", amber: "🟡", green: "🟢" };

function RiskBadge({ status, label }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${STATUS_TONE[status] || ""}`}
      data-testid={`risk-badge-${status}`}
    >
      <span>{STATUS_DOT[status]}</span>
      <span>{label}</span>
    </span>
  );
}

function ConfidenceChip({ confidence }) {
  if (!confidence) return null;
  const { score, label, basis } = confidence;
  const tone =
    label === "High"
      ? "bg-emerald-100 text-emerald-700"
      : label === "Medium"
        ? "bg-amber-100 text-amber-700"
        : "bg-zinc-100 text-zinc-700";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${tone}`}
      title={basis}
      data-testid="confidence-chip"
    >
      {label} {Math.round((score || 0) * 100)}% · {basis}
    </span>
  );
}

function WhyChevron({ why }) {
  const [open, setOpen] = useState(false);
  if (!why || !why.length) return null;
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 text-[12px] text-zinc-500 hover:text-zinc-800"
        data-testid="why-toggle"
      >
        <ChevronRight className={`size-3 transition ${open ? "rotate-90" : ""}`} /> Why?
      </button>
      {open && (
        <ul className="mt-1 ml-4 list-disc text-[12.5px] text-zinc-600" data-testid="why-list">
          {why.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function VisibilityScoreCard({ score, delta, label, reasons, breakdown, benchmark }) {
  const radius = 70;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const arrowIcon =
    delta?.arrow === "↑" ? ArrowUp : delta?.arrow === "↓" ? ArrowDown : Minus;
  const ArrowIcon = arrowIcon;
  const arrowTone =
    delta?.value > 0 ? "text-emerald-600" : delta?.value < 0 ? "text-rose-600" : "text-zinc-500";

  return (
    <section className="rounded-xl border bg-white p-6 shadow-sm" data-testid="visibility-card">
      <div className="text-[12px] uppercase tracking-[0.16em] text-zinc-500">Revenue Visibility</div>
      <div className="flex items-center gap-6 mt-3">
        <svg width="170" height="170" viewBox="0 0 170 170" className="shrink-0">
          <circle cx="85" cy="85" r={radius} stroke="#f1f5f9" strokeWidth="14" fill="none" />
          <circle
            cx="85"
            cy="85"
            r={radius}
            stroke="#0f172a"
            strokeWidth="14"
            fill="none"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            transform="rotate(-90 85 85)"
          />
          <text x="85" y="92" textAnchor="middle" className="font-semibold" fontSize="36">
            {score}
          </text>
        </svg>
        <div>
          <div className="text-[22px] font-semibold">{label}</div>
          {delta && (
            <div className={`mt-1 inline-flex items-center gap-1 text-[12.5px] ${arrowTone}`} data-testid="visibility-delta">
              <ArrowIcon className="size-3.5" />
              {delta.value > 0 ? "+" : ""}{delta.value} since {delta.since_date}
            </div>
          )}
          {benchmark && !benchmark.available && (
            <div className="mt-1 text-[12px] text-zinc-500" data-testid="benchmark-placeholder">
              {benchmark.message}
            </div>
          )}
          {reasons?.length > 0 && (
            <details className="mt-3" data-testid="here-is-why">
              <summary className="cursor-pointer text-[12.5px] text-zinc-700 hover:underline">
                Here's why
              </summary>
              <ul className="mt-2 ml-4 list-disc text-[12.5px] text-zinc-600">
                {reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
              {breakdown && (
                <div className="mt-2 grid grid-cols-2 gap-1 text-[12px] text-zinc-500">
                  <div>Active clients · {breakdown.active_clients_pct}%</div>
                  <div>Non-silent proposals · {breakdown.non_silent_proposals_pct}%</div>
                  <div>Paid invoices · {breakdown.paid_invoices_pct}%</div>
                  <div>Pipeline spread · {breakdown.concentration_pct}%</div>
                </div>
              )}
            </details>
          )}
        </div>
      </div>
    </section>
  );
}

function DoTheseTodayList({ rows, totalMinutes, onPersonalize, showPersonalize }) {
  if (!rows?.length)
    return (
      <section className="rounded-xl border bg-white p-6 shadow-sm">
        <div className="text-[12px] uppercase tracking-[0.16em] text-zinc-500">Do These Today</div>
        <div className="mt-3 text-[13px] text-zinc-500" data-testid="do-today-empty">
          No open proposals — upload more data or wait until your next follow-ups.
        </div>
      </section>
    );
  return (
    <section className="rounded-xl border bg-white p-6 shadow-sm" data-testid="do-these-today">
      <div className="flex items-center justify-between">
        <div className="text-[12px] uppercase tracking-[0.16em] text-zinc-500">
          Do These Today · {rows.length} actions · ~{totalMinutes} minutes
        </div>
      </div>
      <ol className="mt-4 divide-y border rounded-lg">
        {rows.map((r, i) => (
          <li
            key={r.id}
            className="flex flex-col md:flex-row md:items-center gap-2 p-3"
            data-testid={`do-row-${i}`}
          >
            <div className="md:w-2/3">
              <div className="flex items-center gap-2">
                <RiskBadge status={r.status} label={`Step ${i + 1}`} />
                <span className="font-semibold">{r.action}</span>
                <span className="text-[12.5px] text-zinc-500">· {r.estimated_minutes} min</span>
              </div>
              <div className="mt-1 text-[12.5px] text-zinc-500">recover {inr(r.value_inr)}</div>
              <div className="mt-2 flex items-center gap-3">
                <ConfidenceChip confidence={r.confidence} />
                <ThumbsFeedback recommendationId={r.id} />
              </div>
              <div className="mt-2">
                <WhyChevron why={r.why} />
              </div>
            </div>
          </li>
        ))}
      </ol>
      {showPersonalize && onPersonalize && (
        <div className="mt-4">{onPersonalize}</div>
      )}
    </section>
  );
}

function IfYouActTodayBars({ if_you_act_today }) {
  if (!if_you_act_today) return null;
  const { do_nothing_loss_inr, act_recovery_inr, model_note } = if_you_act_today;
  const maxV = Math.max(do_nothing_loss_inr, act_recovery_inr, 1);
  const lossWidth = (do_nothing_loss_inr / maxV) * 100;
  const recWidth = (act_recovery_inr / maxV) * 100;
  return (
    <section className="rounded-xl border bg-white p-6 shadow-sm" data-testid="if-you-act-today">
      <div className="text-[12px] uppercase tracking-[0.16em] text-zinc-500">If You Act Today</div>
      <div className="mt-4 space-y-3">
        <div>
          <div className="flex justify-between text-[12.5px]">
            <span className="text-rose-700">Do nothing · {inr(do_nothing_loss_inr)} lost</span>
          </div>
          <div className="mt-1 h-3 rounded-full bg-rose-100">
            <div className="h-3 rounded-full bg-rose-500" style={{ width: `${lossWidth}%` }} />
          </div>
        </div>
        <div>
          <div className="flex justify-between text-[12.5px]">
            <span className="text-emerald-700">Act today · {inr(act_recovery_inr)} recovered</span>
          </div>
          <div className="mt-1 h-3 rounded-full bg-emerald-100">
            <div className="h-3 rounded-full bg-emerald-500" style={{ width: `${recWidth}%` }} />
          </div>
        </div>
      </div>
      <p className="mt-3 text-[11px] text-zinc-400">{model_note}</p>
    </section>
  );
}

function ImproveMyRecommendationsCard({ onSaved }) {
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({ preferred_channel: "whatsapp", follow_up_days: 7, priority: "cash" });

  async function save() {
    setSubmitting(true);
    try {
      await api.post("/personalize", form);
      toast.success("Recommendations updated");
      onSaved?.();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Could not save");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="rounded-lg border bg-zinc-50 p-4" data-testid="improve-card">
      <div className="flex items-start gap-2">
        <Sparkles className="size-4 text-zinc-700 mt-0.5" />
        <div className="flex-1">
          <div className="font-semibold text-[14px]">Improve My Recommendations · 30 seconds</div>
          <p className="text-[12.5px] text-zinc-500 mt-1">
            Help Revora get sharper on what to do today.
          </p>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
        <label className="text-[12px]">
          <span className="text-zinc-500">Which channel gets replies first?</span>
          <Select
            value={form.preferred_channel}
            onValueChange={(v) => setForm((f) => ({ ...f, preferred_channel: v }))}
          >
            <SelectTrigger className="mt-1" data-testid="imr-channel"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="whatsapp">WhatsApp</SelectItem>
              <SelectItem value="email">Email</SelectItem>
              <SelectItem value="phone">Phone</SelectItem>
            </SelectContent>
          </Select>
        </label>
        <label className="text-[12px]">
          <span className="text-zinc-500">Follow up after how many days?</span>
          <Select
            value={String(form.follow_up_days)}
            onValueChange={(v) => setForm((f) => ({ ...f, follow_up_days: parseInt(v, 10) }))}
          >
            <SelectTrigger className="mt-1" data-testid="imr-days"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="3">3 days</SelectItem>
              <SelectItem value="7">7 days</SelectItem>
              <SelectItem value="14">14 days</SelectItem>
            </SelectContent>
          </Select>
        </label>
        <label className="text-[12px]">
          <span className="text-zinc-500">What matters more?</span>
          <Select
            value={form.priority}
            onValueChange={(v) => setForm((f) => ({ ...f, priority: v }))}
          >
            <SelectTrigger className="mt-1" data-testid="imr-priority"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="cash">Recover cash</SelectItem>
              <SelectItem value="close">Close deals</SelectItem>
              <SelectItem value="relationship">Customer relationships</SelectItem>
            </SelectContent>
          </Select>
        </label>
      </div>
      <div className="mt-3 flex justify-end">
        <Button size="sm" onClick={save} disabled={submitting} data-testid="imr-save">
          {submitting ? <Loader2 className="size-4 animate-spin" /> : "Save & re-rank"}
        </Button>
      </div>
    </div>
  );
}

export default function RevenueHealth() {
  const [data, setData] = useState(null);
  const [hasPersonalized, setHasPersonalized] = useState(true);

  async function load() {
    const [r, state] = await Promise.all([
      api.get("/revenue-health"),
      api.get("/onboarding/state"),
    ]);
    setData(r.data);
    setHasPersonalized(!!state.data.has_personalized);
  }

  useEffect(() => { load(); }, []);

  if (!data) {
    return (
      <div className="p-10 grid place-items-center text-zinc-500">
        <Loader2 className="size-5 animate-spin" />
      </div>
    );
  }

  const vs = data.visibility_score;
  return (
    <div className="p-6 md:p-10 max-w-[1100px] mx-auto print:p-0" data-testid="health-page">
      <header className="flex flex-wrap items-end justify-between gap-3 print:hidden">
        <div>
          <div className="eyebrow-rule">Report</div>
          <h1 className="text-[28px] md:text-[32px] font-semibold mt-2 text-zinc-900 tracking-tight">
            Revenue Health
          </h1>
          <p className="text-[13.5px] text-zinc-500 mt-1.5">
            Score · what to do today · risks · forecast · counterfactual.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => window.print()}
          data-testid="download-pdf"
        >
          <Download className="size-4" /> Download PDF
        </Button>
      </header>

      <div className="mt-6 space-y-5">
        <VisibilityScoreCard
          score={vs.score}
          label={vs.label}
          delta={vs.delta}
          reasons={vs.reasons}
          breakdown={vs.breakdown}
          benchmark={data.benchmark}
        />

        <DoTheseTodayList
          rows={data.do_these_today}
          totalMinutes={data.estimated_total_minutes}
          showPersonalize={!hasPersonalized}
          onPersonalize={
            <ImproveMyRecommendationsCard onSaved={() => { setHasPersonalized(true); load(); }} />
          }
        />

        <section className="rounded-xl border bg-white p-6 shadow-sm" data-testid="risks-section">
          <div className="text-[12px] uppercase tracking-[0.16em] text-zinc-500">Risks</div>
          <ul className="mt-4 space-y-3">
            {data.risks.map((r, i) => (
              <li key={i} className="flex items-start gap-2" data-testid={`risk-row-${i}`}>
                <RiskBadge status={r.status} label={r.statement} />
                <span className="text-[13px] text-zinc-600">· {inrCompact(r.value_inr)}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="rounded-xl border bg-white p-6 shadow-sm" data-testid="forecast-section">
          <div className="text-[12px] uppercase tracking-[0.16em] text-zinc-500">
            Expected Revenue Next 30 Days
          </div>
          <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-[24px] font-semibold tnum">{inr(data.expected_revenue_30d.amount_inr)}</div>
              <div className="text-[12px] text-zinc-500 mt-1">expected</div>
            </div>
            <div>
              <ConfidenceChip confidence={data.expected_revenue_30d.confidence} />
            </div>
            <div>
              <div className="text-[12.5px] text-zinc-500">biggest risk</div>
              <div className="font-semibold">{data.expected_revenue_30d.biggest_risk_client || "—"}</div>
            </div>
            <div>
              <div className="text-[12.5px] text-zinc-500">biggest opportunity</div>
              <div className="font-semibold">{data.expected_revenue_30d.biggest_opportunity_client || "—"}</div>
            </div>
          </div>
        </section>

        <IfYouActTodayBars if_you_act_today={data.if_you_act_today} />

        <section className="rounded-xl border bg-white p-6 shadow-sm" data-testid="strengths-section">
          <div className="text-[12px] uppercase tracking-[0.16em] text-zinc-500">Strengths</div>
          {data.strengths?.length > 0 ? (
            <ul className="mt-3 space-y-2 text-[13px]">
              {data.strengths.map((s, i) => (
                <li key={i}>✓ {s.statement}</li>
              ))}
            </ul>
          ) : (
            <div className="mt-3 text-[12.5px] text-zinc-500">
              Still learning your clients — more signal arrives with each follow-up.
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
