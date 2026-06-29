import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { inrCompact } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Sparkles, RefreshCw, Loader2, ArrowUp, ArrowDown, ThumbsUp, ThumbsDown, Activity, Clock, BadgeIndianRupee, Reply } from "lucide-react";

export function MorningBriefCard() {
  const [brief, setBrief] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  async function load() {
    try {
      const r = await api.get("/brief/today");
      setBrief(r.data);
    } catch {
      // ignore — empty state below covers it
    }
  }
  useEffect(() => { load(); }, []);

  async function refresh() {
    setRefreshing(true);
    try {
      const r = await api.post("/brief/refresh");
      setBrief(r.data);
      toast.success("Brief refreshed");
    } catch (e) {
      const detail = e.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Could not refresh brief");
    } finally {
      setRefreshing(false);
    }
  }

  if (!brief) return null;
  const isLive = brief.source === "llm";
  const conf = Math.round((brief.brief?.confidence || 0) * 100);

  return (
    <section className="rounded-xl border bg-white p-5 shadow-sm" data-testid="morning-brief">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Sparkles className="size-4 text-zinc-700" />
          <div className="text-[12px] uppercase tracking-[0.16em] text-zinc-500">Morning Brief</div>
          {isLive ? (
            <span className="inline-flex items-center rounded-full bg-emerald-50 text-emerald-700 px-2 py-0.5 text-[11px] font-medium" data-testid="brief-live">
              AI brief — live
            </span>
          ) : (
            <span className="inline-flex items-center rounded-full bg-zinc-100 text-zinc-600 px-2 py-0.5 text-[11px] font-medium" data-testid="brief-fallback">
              template fallback
            </span>
          )}
        </div>
        <Button variant="ghost" size="sm" onClick={refresh} disabled={refreshing} data-testid="brief-refresh">
          {refreshing ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
        </Button>
      </div>
      <h2 className="mt-3 text-[18px] font-semibold">{brief.brief?.headline}</h2>
      <p className="mt-2 text-[14px] text-zinc-700 leading-relaxed">{brief.brief?.paragraph}</p>
      <div className="mt-3 text-[11.5px] text-zinc-500">
        Confidence {conf}% · generated {new Date(brief.generated_at).toLocaleString()}
      </div>
    </section>
  );
}

export function WhatChangedCard() {
  const [diff, setDiff] = useState(null);
  useEffect(() => {
    api.get("/health/diff").then((r) => setDiff(r.data)).catch(() => setDiff(null));
  }, []);
  if (!diff || !diff.available) return null;
  const delta = diff.visibility?.delta || 0;
  const ArrowIcon = delta > 0 ? ArrowUp : delta < 0 ? ArrowDown : null;
  const tone = delta > 0 ? "text-emerald-700" : delta < 0 ? "text-rose-700" : "text-zinc-700";
  return (
    <section className="rounded-xl border bg-white p-5 shadow-sm" data-testid="what-changed">
      <div className="text-[12px] uppercase tracking-[0.16em] text-zinc-500">
        What Changed Since {diff.from_date}
      </div>
      <div className="mt-3 flex items-center gap-4">
        <div className={`flex items-center gap-1 text-[20px] font-semibold ${tone}`}>
          {ArrowIcon && <ArrowIcon className="size-5" />}
          Visibility {diff.visibility.from} → {diff.visibility.to}
        </div>
        <div className="text-[13px] text-zinc-500">
          recovery diff: {inrCompact(diff.recovery_inr_delta || 0)}
        </div>
      </div>
    </section>
  );
}

export function LearningCard() {
  const [agg, setAgg] = useState(null);
  useEffect(() => {
    api.get("/learning/aggregate").then((r) => setAgg(r.data)).catch(() => setAgg(null));
  }, []);
  if (!agg) return null;
  const total = (agg.thumbs_up_count || 0) + (agg.thumbs_down_count || 0);
  return (
    <section className="rounded-xl border bg-white p-5 shadow-sm" data-testid="learning-card">
      <div className="text-[12px] uppercase tracking-[0.16em] text-zinc-500">Recommendation Accuracy</div>
      {total === 0 ? (
        <div className="mt-3 text-[13px] text-zinc-500">
          No feedback yet — thumb a row in Do These Today and we'll start learning.
        </div>
      ) : (
        <div className="mt-3 flex items-center gap-4">
          <div className="text-[28px] font-semibold tnum">{agg.accuracy_pct}%</div>
          <div className="text-[12.5px] text-zinc-600 flex items-center gap-3">
            <span className="inline-flex items-center gap-1"><ThumbsUp className="size-3.5 text-emerald-600" /> {agg.thumbs_up_count}</span>
            <span className="inline-flex items-center gap-1"><ThumbsDown className="size-3.5 text-rose-600" /> {agg.thumbs_down_count}</span>
          </div>
        </div>
      )}
    </section>
  );
}

function ImpactStat({ icon: Icon, label, value, sub }) {
  return (
    <div className="rounded-lg border bg-white p-4">
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.14em] text-zinc-500">
        <Icon className="size-3.5" /> {label}
      </div>
      <div className="text-[20px] font-semibold mt-2 tnum">{value}</div>
      {sub && <div className="text-[11.5px] text-zinc-500 mt-1">{sub}</div>}
    </div>
  );
}

export function ImpactCard() {
  const [impact, setImpact] = useState(null);
  useEffect(() => {
    api.get("/impact").then((r) => setImpact(r.data)).catch(() => setImpact(null));
  }, []);
  if (!impact) return null;
  return (
    <section className="rounded-xl border bg-white p-5 shadow-sm" data-testid="impact-card">
      <div className="text-[12px] uppercase tracking-[0.16em] text-zinc-500">Impact this week</div>
      <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3">
        <ImpactStat icon={Activity} label="Follow-ups" value={impact.followups_generated_week} sub="generated" />
        <ImpactStat icon={Clock} label="Hours saved" value={impact.hours_saved_week} sub="at 15 min each" />
        <ImpactStat icon={BadgeIndianRupee} label="Revenue protected" value={inrCompact(impact.revenue_protected_week)} sub="open deals followed up" />
        <ImpactStat icon={Reply} label="Response rate" value={`${Math.round((impact.response_rate_week || 0) * 100)}%`} sub="across clients" />
      </div>
    </section>
  );
}
