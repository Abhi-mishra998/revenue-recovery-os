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
    return (
      <div className="min-h-screen grid place-items-center p-6 bg-zinc-50" data-testid="welcome-page">
        <div className="w-full max-w-3xl">
          <div className="text-center mb-8">
            <div className="text-xs uppercase tracking-[0.16em] text-zinc-500">Welcome to Revora</div>
            <h1 className="text-[28px] md:text-[32px] font-semibold mt-2 tracking-tight">
              Find the revenue your spreadsheet is hiding.
            </h1>
            <p className="text-[13.5px] text-zinc-500 mt-2">
              Upload your CRM data — Revora will surface what's at risk, why, and what to do today.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <button
              type="button"
              onClick={pickCsv}
              className="group rounded-xl border bg-white p-6 text-left hover:border-zinc-400 hover:shadow-sm transition"
              data-testid="welcome-upload-csv"
            >
              <UploadCloud className="size-7 text-zinc-700" />
              <div className="font-semibold mt-4">Upload CSV</div>
              <div className="text-[12.5px] text-zinc-500 mt-1">
                .csv export from any CRM, sheet, or invoice tool.
              </div>
              <span className="inline-flex items-center mt-4 text-[12.5px] text-zinc-700 group-hover:underline">
                Choose file <ArrowRight className="size-3.5 ml-1" />
              </span>
            </button>

            <button
              type="button"
              onClick={pickCsv}
              className="group rounded-xl border bg-white p-6 text-left hover:border-zinc-400 hover:shadow-sm transition"
              data-testid="welcome-upload-xlsx"
            >
              <FileSpreadsheet className="size-7 text-zinc-700" />
              <div className="font-semibold mt-4">Upload Excel</div>
              <div className="text-[12.5px] text-zinc-500 mt-1">
                .xlsx export — single sheet only for now.
              </div>
              <span className="inline-flex items-center mt-4 text-[12.5px] text-zinc-700 group-hover:underline">
                Choose file <ArrowRight className="size-3.5 ml-1" />
              </span>
            </button>

            <button
              type="button"
              onClick={seedDemo}
              disabled={submitting}
              className="group rounded-xl border bg-white p-6 text-left hover:border-zinc-400 hover:shadow-sm transition disabled:opacity-60"
              data-testid="welcome-use-demo"
            >
              <Database className="size-7 text-zinc-700" />
              <div className="font-semibold mt-4">Use Demo Data</div>
              <div className="text-[12.5px] text-zinc-500 mt-1">
                Realistic clients, proposals, and invoices — perfect for a tour.
              </div>
              <span className="inline-flex items-center mt-4 text-[12.5px] text-zinc-700 group-hover:underline">
                Load demo <ArrowRight className="size-3.5 ml-1" />
              </span>
            </button>
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
              <Button onClick={runMapper} disabled={submitting} data-testid="welcome-run-mapper">
                {submitting ? <Loader2 className="size-4 animate-spin" /> : <>Continue <ArrowRight className="size-4" /></>}
              </Button>
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
              <Button onClick={commitImport} disabled={submitting} data-testid="welcome-commit">
                {submitting ? <Loader2 className="size-4 animate-spin" /> : <>Import {parsed.data_quality.rows} rows</>}
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // committing
  return (
    <div className="min-h-screen grid place-items-center p-6 bg-zinc-50" data-testid="welcome-page">
      <div className="flex items-center gap-3 text-zinc-600">
        <Loader2 className="size-5 animate-spin" /> Importing…
      </div>
    </div>
  );
}
