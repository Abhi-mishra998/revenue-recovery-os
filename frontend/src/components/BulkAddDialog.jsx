import { useMemo, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { Check, AlertTriangle, Upload, FileText } from "lucide-react";
import { toast } from "sonner";

/**
 * Bulk-add dialog for proposals and invoices.
 * Parses comma- OR tab-separated rows with header. Header order is flexible.
 *
 * mode="proposals" expects columns:
 *   client_company_name, title, value_inr, stage?, sent_date?, last_contact_date?, contact_name?, notes?
 *
 * mode="invoices" expects columns:
 *   client_company_name, invoice_no, amount_inr, due_date, paid_date?, contact_name?, notes?
 *
 * If client_company_name doesn't match an existing client, one is auto-created
 * (contact_name defaults to company name).
 */

const PROPOSAL_SAMPLE = `client_company_name,title,value_inr,stage,sent_date,last_contact_date,notes
Nexora Retail,Catalog redesign sprint,180000,sent,2026-02-10,2026-02-18,Phase 1 only
Trikon Labs,ML feature flag service,220000,negotiating,2026-02-12,2026-02-22,
Bloom Wellness,Subscription billing flow,135000,sent,2026-02-15,2026-02-20,`;

const INVOICE_SAMPLE = `client_company_name,invoice_no,amount_inr,due_date,paid_date,notes
Nexora Retail,BH-2026-002,225000,2026-03-15,,Net 30
Trikon Labs,BH-2026-003,142500,2026-03-20,,
Mantra Media,BH-2026-001,85000,2026-02-25,2026-02-24,Cleared`;

const STAGE_OPTIONS = ["sent", "negotiating", "won", "lost"];

export default function BulkAddDialog({ open, onOpenChange, mode, clients, onDone }) {
  const [raw, setRaw] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const sample = mode === "invoices" ? INVOICE_SAMPLE : PROPOSAL_SAMPLE;
  const requiredCols = mode === "invoices"
    ? ["client_company_name", "invoice_no", "amount_inr", "due_date"]
    : ["client_company_name", "title", "value_inr"];

  const parsed = useMemo(() => {
    if (!raw.trim()) return { rows: [], errors: [] };
    return parseRows(raw, mode, clients);
  }, [raw, mode, clients]);

  const validRows = parsed.rows.filter((r) => !r.error);
  const errorRows = parsed.rows.filter((r) => !!r.error);

  const submit = async () => {
    if (validRows.length === 0) {
      toast.error("No valid rows to add");
      return;
    }
    setSubmitting(true);
    let created = 0;
    let clientsCreated = 0;
    // Build a lookup of existing companies (case-insensitive)
    const byCompany = new Map();
    for (const c of clients) byCompany.set((c.company_name || "").toLowerCase(), c);

    try {
      for (const r of validRows) {
        let clientId = r.client_id;
        if (!clientId) {
          // Ensure client exists; create if missing
          const key = r.client_company_name.toLowerCase();
          let existing = byCompany.get(key);
          if (!existing) {
            const { data: newC } = await api.post("/clients", {
              company_name: r.client_company_name,
              contact_name: r.contact_name || r.client_company_name,
              language: "English",
            });
            byCompany.set(key, newC);
            existing = newC;
            clientsCreated += 1;
          }
          clientId = existing.id;
        }

        if (mode === "proposals") {
          await api.post("/proposals", {
            client_id: clientId,
            title: r.title,
            value_inr: r.value_inr,
            stage: r.stage || "sent",
            sent_date: r.sent_date || null,
            last_contact_date: r.last_contact_date || null,
            notes: r.notes || null,
          });
        } else {
          await api.post("/invoices", {
            client_id: clientId,
            invoice_no: r.invoice_no,
            amount_inr: r.amount_inr,
            due_date: r.due_date,
            paid_date: r.paid_date || null,
            notes: r.notes || null,
          });
        }
        created += 1;
      }
      const extra = clientsCreated > 0 ? ` (and ${clientsCreated} new client${clientsCreated === 1 ? "" : "s"})` : "";
      toast.success(`Added ${created} ${mode}${extra}`);
      setRaw("");
      onOpenChange(false);
      onDone();
    } catch (e) {
      toast.error("Failed mid-batch. Added " + created + " before error. Check the data and try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white border-slate-200 max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold flex items-center gap-2">
            <Upload className="w-5 h-5 text-indigo-700" />
            Bulk add {mode}
          </DialogTitle>
          <DialogDescription className="text-slate-500">
            Paste comma- or tab-separated rows (e.g. from Excel/Google Sheets). First row must be the header.
            Required columns: <span className="font-mono text-xs">{requiredCols.join(", ")}</span>.
            Unknown clients are auto-created.
          </DialogDescription>
        </DialogHeader>

        <div className="mt-3 space-y-3" data-testid={`bulk-add-${mode}`}>
          <div className="flex items-center justify-between">
            <label className="field-label">Paste rows below</label>
            <button
              type="button"
              className="text-xs text-indigo-700 hover:text-indigo-800 inline-flex items-center gap-1"
              onClick={() => setRaw(sample)}
              data-testid="bulk-add-load-sample"
            >
              <FileText className="w-3 h-3" /> Load sample
            </button>
          </div>
          <textarea
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
            rows={9}
            placeholder={sample}
            className="field font-mono text-xs"
            data-testid="bulk-add-textarea"
            spellCheck={false}
          />

          {raw.trim() && (
            <div className="border border-slate-200 rounded-md max-h-56 overflow-y-auto" data-testid="bulk-add-preview">
              <table className="w-full text-xs">
                <thead className="bg-slate-50 sticky top-0">
                  <tr className="text-left text-slate-500">
                    <th className="px-3 py-2 font-medium w-8"></th>
                    <th className="px-3 py-2 font-medium">Row</th>
                    <th className="px-3 py-2 font-medium">Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {parsed.rows.map((r, idx) => (
                    <tr key={idx} className="border-t border-slate-100" data-testid={`bulk-add-row-${idx}`}>
                      <td className="px-3 py-2 align-top">
                        {r.error
                          ? <AlertTriangle className="w-3.5 h-3.5 text-red-600" />
                          : <Check className="w-3.5 h-3.5 text-green-600" />}
                      </td>
                      <td className="px-3 py-2 align-top text-slate-700 tnum">{idx + 1}</td>
                      <td className="px-3 py-2 align-top">
                        <div className="text-slate-900 font-medium truncate max-w-md">
                          {r.client_company_name || "—"} <span className="text-slate-400">·</span> {r.title || r.invoice_no || "(missing)"}
                        </div>
                        <div className={r.error ? "text-red-600" : "text-slate-500"}>
                          {r.error || (mode === "invoices"
                            ? `₹ ${formatNum(r.amount_inr)} · due ${r.due_date || "?"}`
                            : `₹ ${formatNum(r.value_inr)} · ${r.stage || "sent"}`)}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {parsed.errors.length > 0 && (
            <div className="text-xs text-red-700 bg-red-50 border border-red-100 rounded-md p-2" data-testid="bulk-add-format-errors">
              {parsed.errors.join(" · ")}
            </div>
          )}

          <div className="flex items-center justify-between pt-2">
            <div className="text-xs text-slate-500" data-testid="bulk-add-counts">
              {raw.trim()
                ? <>{validRows.length} valid · {errorRows.length} with errors</>
                : "Paste rows to preview"}
            </div>
            <div className="flex items-center gap-2">
              <button type="button" onClick={() => onOpenChange(false)} className="cta-ghost">Cancel</button>
              <button
                type="button"
                onClick={submit}
                disabled={submitting || validRows.length === 0}
                className="cta-primary"
                data-testid="bulk-add-submit"
              >
                {submitting ? "Adding…" : `Add ${validRows.length} ${mode}`}
              </button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ---------- Parser ----------
function parseRows(text, mode, clients) {
  const lines = text.replace(/\r\n/g, "\n").split("\n").map((l) => l.trim()).filter(Boolean);
  if (lines.length === 0) return { rows: [], errors: [] };

  // Detect separator from header line (prefer tab over comma)
  const headerLine = lines[0];
  const sep = headerLine.includes("\t") ? "\t" : ",";
  const headers = splitCsvLine(headerLine, sep).map((h) => h.trim().toLowerCase());

  const required = mode === "invoices"
    ? ["client_company_name", "invoice_no", "amount_inr", "due_date"]
    : ["client_company_name", "title", "value_inr"];

  const missing = required.filter((c) => !headers.includes(c));
  if (missing.length > 0) {
    return {
      rows: [],
      errors: [`Missing required column${missing.length === 1 ? "" : "s"}: ${missing.join(", ")}`],
    };
  }

  // Build company → client map (case-insensitive)
  const byCompany = new Map();
  for (const c of clients) byCompany.set((c.company_name || "").toLowerCase(), c);

  const rows = lines.slice(1).map((line) => {
    const cells = splitCsvLine(line, sep);
    const r = {};
    headers.forEach((h, i) => { r[h] = (cells[i] || "").trim(); });

    // Type coercion + validation
    if (mode === "invoices") {
      r.amount_inr = Number(String(r.amount_inr).replace(/[,_₹\s]/g, ""));
      r.due_date = toIsoDate(r.due_date);
      r.paid_date = toIsoDate(r.paid_date);
      if (!r.client_company_name) r.error = "Missing client_company_name";
      else if (!r.invoice_no) r.error = "Missing invoice_no";
      else if (!Number.isFinite(r.amount_inr) || r.amount_inr <= 0) r.error = "Invalid amount_inr";
      else if (!r.due_date) r.error = "Invalid or missing due_date";
    } else {
      r.value_inr = Number(String(r.value_inr).replace(/[,_₹\s]/g, ""));
      r.sent_date = toIsoDate(r.sent_date);
      r.last_contact_date = toIsoDate(r.last_contact_date);
      if (r.stage && !STAGE_OPTIONS.includes(r.stage)) r.error = `Invalid stage '${r.stage}' — use sent/negotiating/won/lost`;
      else if (!r.client_company_name) r.error = "Missing client_company_name";
      else if (!r.title) r.error = "Missing title";
      else if (!Number.isFinite(r.value_inr) || r.value_inr <= 0) r.error = "Invalid value_inr";
    }

    // Resolve client (case-insensitive)
    const existing = byCompany.get((r.client_company_name || "").toLowerCase());
    if (existing) r.client_id = existing.id;
    // else: client_id remains undefined → auto-created on submit

    return r;
  });

  return { rows, errors: [] };
}

function splitCsvLine(line, sep) {
  // Minimal CSV/TSV split with double-quote escaping
  const out = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"' && line[i + 1] === '"') { cur += '"'; i++; }
      else if (ch === '"') inQuotes = false;
      else cur += ch;
    } else {
      if (ch === '"') inQuotes = true;
      else if (ch === sep) { out.push(cur); cur = ""; }
      else cur += ch;
    }
  }
  out.push(cur);
  return out;
}

function toIsoDate(v) {
  if (!v) return "";
  // Accept YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY
  const s = String(v).trim();
  let m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (m) return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])).toISOString();
  m = s.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/);
  if (m) return new Date(Date.UTC(+m[3], +m[2] - 1, +m[1])).toISOString();
  const d = new Date(s);
  return isNaN(d.getTime()) ? "" : d.toISOString();
}

function formatNum(n) {
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("en-IN").format(n);
}
