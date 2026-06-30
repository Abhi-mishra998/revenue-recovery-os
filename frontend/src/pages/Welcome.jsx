import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { inrCompact } from "@/lib/format";
import { resetOnboardingCache } from "@/App";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { UploadCloud, FileSpreadsheet, Sparkles, ArrowRight, Loader2, Database } from "lucide-react";

// 4-step onboarding flow:
//   choose -> upload+teaser -> mapping -> committing -> redirect
// Demo Data card jumps choose -> committing -> redirect.

const TARGET_FIELDS = {
  clients: ["company_name", "contact_name", "email", "phone"],
  proposals: ["client_name", "title", "value_inr", "stage", "sent_date", "last_contact_date"],
  invoices: ["client_name", "invoice_no", "amount_inr", "due_date", "status"],
};

function ConfidenceChip({ score }) {
  if (score == null) return null;
  const pct = Math.round(score * 100);
  let tone = "bg-zinc-100 text-zinc-700";
  if (score >= 0.85) tone = "bg-emerald-100 text-emerald-700";
  else if (score >= 0.6) tone = "bg-amber-100 text-amber-700";
  else if (score > 0) tone = "bg-rose-100 text-rose-700";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${tone}`}
      data-testid="confidence-chip"
    >
      {pct}%
    </span>
  );
}

export default function Welcome() {
  const navigate = useNavigate();
  const fileRef = useRef(null);
  const [step, setStep] = useState("choose"); // choose | upload | mapping | committing
  const [parsing, setParsing] = useState(false);
  const [parsed, setParsed] = useState(null); // {file_id, headers, sample_rows, column_types, data_quality, quick_signals}
  const [target, setTarget] = useState("clients");
  const [mapping, setMapping] = useState(null); // {target_field: source_header|null}
  const [mappingMeta, setMappingMeta] = useState([]); // [{target_field, source_header, confidence}]
  const [submitting, setSubmitting] = useState(false);

  function pickCsv() {
    fileRef.current?.click();
  }

  async function onFileChosen(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      toast.error("File too large — 5 MB max.");
      return;
    }
    setParsing(true);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await api.post("/import/parse", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setParsed(r.data);
      // Smart default: if the file has money + date columns, it's almost certainly a
      // proposals/deals export — pick that target. The /commit endpoint then lazy-creates
      // clients via _ensure_client so a SINGLE upload populates both tables, and
      // Revenue Health renders on the first try (instead of looking empty).
      const ct = r.data.column_types || {};
      const hasMoney = (ct.money || []).length > 0;
      const hasDate = (ct.date || []).length > 0;
      setTarget(hasMoney && hasDate ? "proposals" : "clients");
      setStep("upload"); // shows the teaser + target picker
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not parse file");
    } finally {
      setParsing(false);
    }
  }

  async function runMapper() {
    setSubmitting(true);
    try {
      const r = await api.post("/import/map", { file_id: parsed.file_id, target });
      const picked = r.data.ai_mapping || r.data.heuristic_mapping;
      setMappingMeta(picked);
      const flat = {};
      for (const m of picked) if (m.source_header) flat[m.target_field] = m.source_header;
      setMapping(flat);
      setStep("mapping");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Mapping failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function commitImport() {
    setSubmitting(true);
    setStep("committing");
    try {
      const r = await api.post("/import/commit", { file_id: parsed.file_id, mapping });
      toast.success(
        `Imported ${r.data.clients_inserted || 0} clients, ${r.data.proposals_inserted || 0} proposals, ${r.data.invoices_inserted || 0} invoices`,
      );
      resetOnboardingCache();
      navigate("/health");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Commit failed");
      setStep("mapping");
    } finally {
      setSubmitting(false);
    }
  }

  async function seedDemo() {
    setSubmitting(true);
    setStep("committing");
    try {
      const r = await api.post("/import/seed-demo");
      toast.success(`Loaded ${r.data.clients} demo clients, ${r.data.proposals} proposals, ${r.data.invoices} invoices`);
      resetOnboardingCache();
      navigate("/health");
    } catch (err) {
      const msg = err.response?.data?.detail || "Demo seed failed";
      toast.error(msg);
      setStep("choose");
    } finally {
      setSubmitting(false);
    }
  }

  // --------- Step renderers ---------
  if (step === "choose") {
    const cards = [
      {
        key: "csv",
        onClick: pickCsv,
        testId: "welcome-upload-csv",
        icon: UploadCloud,
        iconBg: "bg-zinc-900",
        iconColor: "text-white",
        title: "Upload CSV",
        sub: ".csv export from any CRM, sheet, or invoice tool.",
        cta: "Choose file",
      },
      {
        key: "xlsx",
        onClick: pickCsv,
        testId: "welcome-upload-xlsx",
        icon: FileSpreadsheet,
        iconBg: "bg-emerald-600",
        iconColor: "text-white",
        title: "Upload Excel",
        sub: ".xlsx export — single sheet only for now.",
        cta: "Choose file",
      },
      {
        key: "demo",
        onClick: seedDemo,
        testId: "welcome-use-demo",
        icon: Database,
        iconBg: "bg-indigo-600",
        iconColor: "text-white",
        title: "Use Demo Data",
        sub: "Realistic clients, proposals, invoices — perfect for a 90-second tour.",
        cta: "Load demo",
      },
    ];

    return (
      <div className="min-h-screen p-6 bg-gradient-to-b from-zinc-50 to-zinc-100" data-testid="welcome-page">
        <div className="w-full max-w-4xl mx-auto pt-12 md:pt-20">
          <div className="text-center mb-10">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white border border-zinc-200 text-[11px] uppercase tracking-[0.16em] text-zinc-600 mb-5">
              <Sparkles className="size-3" aria-hidden="true" /> Welcome to Revora
            </div>
            <h1 className="text-[32px] md:text-[40px] font-semibold tracking-tight text-zinc-900">
              Find the revenue your spreadsheet is hiding.
            </h1>
            <p className="text-[15px] text-zinc-600 mt-3 max-w-xl mx-auto">
              Drop your CRM data. In under three seconds, Revora shows what's at risk, why, and the three actions to take today.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {cards.map((c) => {
              const Icon = c.icon;
              return (
                <button
                  key={c.key}
                  type="button"
                  onClick={c.onClick}
                  disabled={submitting}
                  className="group relative rounded-2xl border border-zinc-200 bg-white p-7 text-left shadow-sm hover:border-zinc-900 hover:shadow-xl hover:-translate-y-1 active:translate-y-0 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-zinc-900 focus:ring-offset-2"
                  data-testid={c.testId}
                  aria-label={c.title}
                >
                  <div className={`inline-flex items-center justify-center w-12 h-12 rounded-xl ${c.iconBg} ${c.iconColor} shadow-md group-hover:scale-105 transition-transform`}>
                    <Icon className="size-6" aria-hidden="true" />
                  </div>
                  <div className="font-semibold mt-5 text-[17px] text-zinc-900">{c.title}</div>
                  <div className="text-[13px] text-zinc-600 mt-1.5 leading-relaxed">{c.sub}</div>
                  <span className="inline-flex items-center mt-6 text-[13px] font-medium text-zinc-900 group-hover:gap-2 transition-all">
                    {c.cta} <ArrowRight className="size-4 ml-1 group-hover:translate-x-0.5 transition-transform" aria-hidden="true" />
                  </span>
                </button>
              );
            })}
          </div>

          <input
            type="file"
            accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ref={fileRef}
            onChange={onFileChosen}
            className="hidden"
            data-testid="welcome-file-input"
          />

          {parsing && (
            <div className="mt-6 flex items-center justify-center gap-2 text-[13px] text-zinc-600">
              <Loader2 className="size-4 animate-spin" /> Parsing your file…
            </div>
          )}
        </div>
      </div>
    );
  }

  if (step === "upload" && parsed) {
    const qs = parsed.quick_signals;
    const dq = parsed.data_quality;
    return (
      <div className="min-h-screen grid place-items-center p-6 bg-zinc-50" data-testid="welcome-page">
        <div className="w-full max-w-3xl">
          <div className="rounded-xl border bg-white p-6 shadow-sm">
            <div className="flex items-center gap-2 text-[12px] uppercase tracking-[0.16em] text-zinc-500">
              <Sparkles className="size-3.5" /> Revora already sees
            </div>
            <ul className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3 text-[14px]" data-testid="welcome-teaser">
              <li>
                ✓ <span className="font-semibold tnum">{dq.rows}</span> rows ·{" "}
                <span className="text-zinc-500">{dq.currency}</span>
              </li>
              <li>
                ✓ <span className="font-semibold tnum">{qs.silent_clients_count}</span> silent 14+ days
              </li>
              <li>
                ✓ <span className="font-semibold tnum">{qs.overdue_invoices_count}</span> overdue-looking rows
              </li>
              <li>
                ✓ <span className="font-semibold tnum">{inrCompact(qs.pipeline_inr || 0)}</span> pipeline detected
              </li>
            </ul>
            {(dq.duplicates > 0 || dq.blank_names > 0 || dq.blank_dates > 0) && (
              <p className="mt-3 text-[12.5px] text-zinc-500" data-testid="welcome-quality">
                Also found: {dq.duplicates} duplicate{dq.duplicates === 1 ? "" : "s"} ·{" "}
                {dq.blank_names} blank name{dq.blank_names === 1 ? "" : "s"} ·{" "}
                {dq.blank_dates} blank date{dq.blank_dates === 1 ? "" : "s"}. We'll clean these on import.
              </p>
            )}
            <div className="mt-6 flex flex-col md:flex-row md:items-end gap-3 justify-between">
              <div>
                <label className="text-[12px] uppercase tracking-[0.16em] text-zinc-500">
                  Map this file as
                </label>
                <div className="mt-1" style={{ minWidth: 220 }}>
                  <Select value={target} onValueChange={setTarget}>
                    <SelectTrigger data-testid="welcome-target">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="clients">Clients</SelectItem>
                      <SelectItem value="proposals">Proposals</SelectItem>
                      <SelectItem value="invoices">Invoices</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <button
                type="button"
                onClick={runMapper}
                disabled={submitting}
                data-testid="welcome-run-mapper"
                className="inline-flex items-center justify-center gap-2 rounded-md bg-zinc-900 hover:bg-zinc-800 active:bg-black text-white font-medium px-5 py-2.5 text-sm shadow-sm hover:shadow disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-zinc-900 focus:ring-offset-2 transition-colors"
              >
                {submitting ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <>Continue <ArrowRight className="size-4" aria-hidden="true" /></>}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (step === "mapping" && parsed) {
    const fields = TARGET_FIELDS[target];
    return (
      <div className="min-h-screen grid place-items-center p-6 bg-zinc-50" data-testid="welcome-page">
        <div className="w-full max-w-3xl">
          <div className="rounded-xl border bg-white p-6 shadow-sm">
            <div className="text-[12px] uppercase tracking-[0.16em] text-zinc-500">Confirm the column mapping</div>
            <h2 className="text-[20px] font-semibold mt-1">Map columns into {target}</h2>
            <p className="text-[13px] text-zinc-500 mt-1">
              Revora's best guess is filled in. Adjust anything that looks off, then confirm.
            </p>

            <div className="mt-5 divide-y border rounded-lg">
              {fields.map((field) => {
                const meta = mappingMeta.find((m) => m.target_field === field);
                const score = meta?.confidence ?? 0;
                return (
                  <div
                    key={field}
                    className="flex flex-col md:flex-row md:items-center gap-3 p-3"
                    data-testid={`mapping-row-${field}`}
                  >
                    <div className="md:w-1/3 flex items-center gap-2">
                      <span className="font-mono text-[12.5px]">{field}</span>
                      <ConfidenceChip score={score} />
                    </div>
                    <div className="md:flex-1">
                      <Select
                        value={mapping[field] || "__none__"}
                        onValueChange={(v) =>
                          setMapping((m) => ({ ...m, [field]: v === "__none__" ? null : v }))
                        }
                      >
                        <SelectTrigger data-testid={`mapping-select-${field}`}>
                          <SelectValue placeholder="Unmapped" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__none__">— Unmapped —</SelectItem>
                          {parsed.headers.map((h) => (
                            <SelectItem key={h} value={h}>
                              {h}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="mt-6 flex items-center justify-between">
              <button
                type="button"
                className="text-[13px] text-zinc-500 hover:text-zinc-800"
                onClick={() => setStep("upload")}
                data-testid="welcome-back"
              >
                ← Back
              </button>
              <button
                type="button"
                onClick={commitImport}
                disabled={submitting}
                data-testid="welcome-commit"
                className="inline-flex items-center justify-center gap-2 rounded-md bg-zinc-900 hover:bg-zinc-800 active:bg-black text-white font-medium px-5 py-2.5 text-sm shadow-sm hover:shadow disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-zinc-900 focus:ring-offset-2 transition-colors"
              >
                {submitting ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <>Import {parsed.data_quality.rows} rows</>}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // committing — skeleton placeholders for the report cards that are about
  // to appear, so the founder sees the page shape before /health renders.
  return (
    <div className="min-h-screen p-6 md:p-10 bg-zinc-50" data-testid="welcome-page">
      <div className="max-w-[1100px] mx-auto">
        <div className="flex items-center gap-3 text-zinc-700 mb-6" role="status" aria-live="polite">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          <span className="text-[14px] font-medium">Importing your data and computing Revenue Health…</span>
        </div>
        <div className="space-y-4">
          <div className="rounded-xl border bg-white p-6 shadow-sm">
            <div className="h-3 w-32 rounded bg-zinc-200 animate-pulse" />
            <div className="mt-4 flex items-center gap-6">
              <div className="size-[170px] rounded-full bg-zinc-100 animate-pulse" />
              <div className="flex-1 space-y-3">
                <div className="h-4 w-24 rounded bg-zinc-200 animate-pulse" />
                <div className="h-3 w-40 rounded bg-zinc-100 animate-pulse" />
                <div className="h-3 w-56 rounded bg-zinc-100 animate-pulse" />
              </div>
            </div>
          </div>
          <div className="rounded-xl border bg-white p-6 shadow-sm">
            <div className="h-3 w-40 rounded bg-zinc-200 animate-pulse" />
            <div className="mt-4 space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="flex items-center gap-3">
                  <div className="size-6 rounded-full bg-zinc-100 animate-pulse" />
                  <div className="h-3 flex-1 rounded bg-zinc-100 animate-pulse" />
                  <div className="h-3 w-16 rounded bg-zinc-100 animate-pulse" />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
