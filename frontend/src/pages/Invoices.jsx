import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { inr, relativeDateISO } from "@/lib/format";
import { StatusPill } from "@/components/StatusPill";
import DraftModal from "@/components/DraftModal";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sparkles, Plus, CheckCircle2, Trash2 } from "lucide-react";
import { toast } from "sonner";

const FILTERS = ["all", "due", "overdue", "critical", "paid"];

export default function Invoices() {
  const [rows, setRows] = useState([]);
  const [clients, setClients] = useState([]);
  const [filter, setFilter] = useState("all");
  const [draftCtx, setDraftCtx] = useState(null);
  const [openNew, setOpenNew] = useState(false);

  const load = async () => {
    const [iv, cl] = await Promise.all([api.get("/invoices"), api.get("/clients")]);
    setRows(iv.data);
    setClients(cl.data);
  };
  useEffect(() => { load(); }, []);

  const filtered = filter === "all" ? rows : rows.filter((r) => r.status === filter);

  const markPaid = async (id) => {
    await api.post(`/invoices/${id}/mark-paid`);
    toast.success("Marked paid");
    load();
  };
  const remove = async (id) => {
    if (!confirm("Delete this invoice?")) return;
    await api.delete(`/invoices/${id}`);
    toast.success("Invoice deleted");
    load();
  };

  return (
    <div className="p-6 md:p-10 max-w-[1400px]" data-testid="invoices-page">
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-stone-500">Receivables</div>
          <h1 className="font-serif-display text-4xl mt-1.5">Invoices</h1>
          <p className="text-sm text-stone-500 mt-2">Track what's outstanding and draft AI reminders.</p>
        </div>
        <button className="cta-primary" onClick={() => setOpenNew(true)} data-testid="new-invoice-btn">
          <Plus className="w-4 h-4" /> New invoice
        </button>
      </div>

      <div className="flex items-center gap-2 mt-6 flex-wrap">
        {FILTERS.map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            data-testid={`inv-filter-${s}`}
            className={`text-xs px-3 py-1.5 rounded-full border transition ${
              filter === s ? "bg-stone-900 text-amber-50 border-stone-900" : "bg-white border-stone-200 text-stone-700 hover:bg-stone-50"
            }`}
          >
            {s}
          </button>
        ))}
        <div className="ml-auto text-xs text-stone-500">{filtered.length} of {rows.length}</div>
      </div>

      <div className="revora-card overflow-hidden mt-4">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-[0.18em] text-stone-500 border-b border-stone-200">
              <th className="px-4 py-3 font-medium">Invoice #</th>
              <th className="px-4 py-3 font-medium">Client</th>
              <th className="px-4 py-3 font-medium">Amount</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Due</th>
              <th className="px-4 py-3 font-medium">Overdue</th>
              <th className="px-4 py-3 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-10 text-center text-stone-400">No invoices.</td></tr>
            )}
            {filtered.map((r) => (
              <tr key={r.id} className="row-hover border-b last:border-0 border-stone-100" data-testid={`invoice-row-${r.id}`}>
                <td className="px-4 py-3 font-medium font-mono-num">{r.invoice_number}</td>
                <td className="px-4 py-3 text-stone-700">
                  {r.client_name}
                  {r.client_company && <div className="text-xs text-stone-400">{r.client_company}</div>}
                </td>
                <td className="px-4 py-3 font-mono-num tnum">{inr(r.amount)}</td>
                <td className="px-4 py-3"><StatusPill status={r.status} testId={`inv-status-${r.id}`} /></td>
                <td className="px-4 py-3 text-stone-500">{relativeDateISO(r.due_date)}</td>
                <td className="px-4 py-3 text-stone-500 tnum">{r.status === "paid" ? "—" : `${r.days_overdue}d`}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-1.5">
                    {r.status !== "paid" && (
                      <button
                        onClick={() => setDraftCtx({ mode: "invoice", id: r.id, client_id: r.client_id, label: `Invoice #${r.invoice_number} · ${r.client_name}` })}
                        className="cta-primary"
                        data-testid={`inv-draft-${r.id}`}
                      >
                        <Sparkles className="w-3.5 h-3.5" /> Draft
                      </button>
                    )}
                    {r.status !== "paid" && (
                      <button onClick={() => markPaid(r.id)} className="cta-ghost text-green-700" data-testid={`mark-paid-${r.id}`}>
                        <CheckCircle2 className="w-3.5 h-3.5" /> Paid
                      </button>
                    )}
                    <button onClick={() => remove(r.id)} className="cta-ghost text-red-600" data-testid={`inv-delete-${r.id}`}>
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <DraftModal open={!!draftCtx} onOpenChange={(o) => !o && setDraftCtx(null)} context={draftCtx} />
      <NewInvoiceDialog open={openNew} onOpenChange={setOpenNew} clients={clients} onCreated={load} />
    </div>
  );
}

function NewInvoiceDialog({ open, onOpenChange, clients, onCreated }) {
  const [form, setForm] = useState({ client_id: "", invoice_number: "", amount: "", due_date: "" });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    try {
      const dueIso = new Date(form.due_date).toISOString();
      await api.post("/invoices", {
        client_id: form.client_id,
        invoice_number: form.invoice_number,
        amount: parseFloat(form.amount),
        due_date: dueIso,
      });
      toast.success("Invoice created");
      setForm({ client_id: "", invoice_number: "", amount: "", due_date: "" });
      onOpenChange(false);
      onCreated();
    } catch {
      toast.error("Could not create invoice");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#FAF9F6] border-stone-200">
        <DialogHeader>
          <DialogTitle className="font-serif-display text-2xl">New invoice</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3 mt-2" data-testid="new-invoice-form">
          <select required value={form.client_id} onChange={set("client_id")} className="w-full border border-stone-200 bg-white rounded-md px-3 py-2.5" data-testid="new-invoice-client">
            <option value="">Select client</option>
            {clients.map((c) => <option key={c.id} value={c.id}>{c.name} · {c.company || ""}</option>)}
          </select>
          <input required placeholder="Invoice number (e.g. BH-2025-019)" value={form.invoice_number} onChange={set("invoice_number")} className="w-full border border-stone-200 bg-white rounded-md px-3 py-2.5" data-testid="new-invoice-number" />
          <input required placeholder="Amount in ₹" type="number" value={form.amount} onChange={set("amount")} className="w-full border border-stone-200 bg-white rounded-md px-3 py-2.5" data-testid="new-invoice-amount" />
          <input required type="date" value={form.due_date} onChange={set("due_date")} className="w-full border border-stone-200 bg-white rounded-md px-3 py-2.5" data-testid="new-invoice-due" />
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={() => onOpenChange(false)} className="cta-ghost">Cancel</button>
            <button type="submit" className="cta-primary" data-testid="new-invoice-submit">Create</button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
