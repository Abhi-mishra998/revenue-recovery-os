import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { inr, dateShort, dateForInput } from "@/lib/format";
import { StatusBadge } from "@/components/StatusPill";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Plus, Trash2, Pencil } from "lucide-react";
import { toast } from "sonner";

export default function Invoices() {
  const [rows, setRows] = useState([]);
  const [clients, setClients] = useState([]);
  const [editing, setEditing] = useState(null); // invoice or { __new: true }

  const load = async () => {
    const [iv, cl] = await Promise.all([api.get("/invoices"), api.get("/clients")]);
    setRows(iv.data);
    setClients(cl.data);
  };
  useEffect(() => { load(); }, []);

  const remove = async (id) => {
    if (!confirm("Delete this invoice?")) return;
    await api.delete(`/invoices/${id}`);
    toast.success("Invoice deleted");
    load();
  };

  return (
    <div className="p-5 md:p-8 max-w-[1400px]" data-testid="invoices-page">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-slate-500 font-semibold">Receivables</div>
          <h1 className="text-3xl md:text-4xl font-semibold mt-1.5 text-slate-900">Invoices</h1>
          <p className="text-sm text-slate-500 mt-1.5">All invoices with auto status: paid / unpaid / overdue.</p>
        </div>
        <button className="cta-primary" onClick={() => setEditing({ __new: true })} data-testid="new-invoice-btn">
          <Plus className="w-4 h-4" /> New invoice
        </button>
      </div>

      <div className="revora-card overflow-hidden mt-6">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[820px]">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-[0.16em] text-slate-500 border-b border-slate-200 font-semibold">
                <th className="px-4 py-3">Invoice #</th>
                <th className="px-4 py-3">Client</th>
                <th className="px-4 py-3">Amount</th>
                <th className="px-4 py-3">Due</th>
                <th className="px-4 py-3">Overdue</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-400" data-testid="empty-invoices">No invoices yet.</td></tr>
              )}
              {rows.map((r) => (
                <tr key={r.id} className="row-hover border-b last:border-0 border-slate-100" data-testid={`invoice-row-${r.id}`}>
                  <td className="px-4 py-3 font-medium font-mono-num text-slate-900">{r.invoice_no}</td>
                  <td className="px-4 py-3 text-slate-700">
                    <div className="font-medium">{r.client_company_name}</div>
                    <div className="text-xs text-slate-400">{r.client_contact_name}</div>
                  </td>
                  <td className="px-4 py-3 font-mono-num tnum">{inr(r.amount_inr)}</td>
                  <td className="px-4 py-3 text-slate-500">{dateShort(r.due_date)}</td>
                  <td className="px-4 py-3 text-slate-500 tnum">{r.status === "paid" ? "—" : `${r.days_overdue}d`}</td>
                  <td className="px-4 py-3"><StatusBadge status={r.status} testId={`inv-status-${r.id}`} /></td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex items-center gap-1.5">
                      <button onClick={() => setEditing(r)} className="cta-ghost" data-testid={`edit-invoice-${r.id}`}><Pencil className="w-3.5 h-3.5" /></button>
                      <button onClick={() => remove(r.id)} className="cta-danger" data-testid={`delete-invoice-${r.id}`}><Trash2 className="w-3.5 h-3.5" /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <InvoiceDialog
        open={!!editing}
        onOpenChange={(o) => !o && setEditing(null)}
        invoice={editing && !editing.__new ? editing : null}
        clients={clients}
        onSaved={() => { setEditing(null); load(); }}
      />
    </div>
  );
}

function InvoiceDialog({ open, onOpenChange, invoice, clients, onSaved }) {
  const empty = { client_id: "", invoice_no: "", amount_inr: "", due_date: "", paid_date: "", notes: "" };
  const [form, setForm] = useState(empty);
  useEffect(() => {
    if (invoice) {
      setForm({
        client_id: invoice.client_id,
        invoice_no: invoice.invoice_no || "",
        amount_inr: String(invoice.amount_inr ?? ""),
        due_date: dateForInput(invoice.due_date),
        paid_date: dateForInput(invoice.paid_date),
        notes: invoice.notes || "",
      });
    } else {
      setForm(empty);
    }
    // eslint-disable-next-line
  }, [invoice, open]);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    const body = {
      client_id: form.client_id,
      invoice_no: form.invoice_no,
      amount_inr: parseFloat(form.amount_inr),
      due_date: form.due_date ? new Date(form.due_date).toISOString() : null,
      paid_date: form.paid_date ? new Date(form.paid_date).toISOString() : null,
      notes: form.notes,
    };
    try {
      if (invoice) {
        await api.patch(`/invoices/${invoice.id}`, body);
        toast.success("Invoice updated");
      } else {
        await api.post("/invoices", body);
        toast.success("Invoice created");
      }
      onSaved();
    } catch {
      toast.error("Could not save invoice");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white border-slate-200">
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold">{invoice ? "Edit invoice" : "New invoice"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3 mt-2" data-testid="invoice-form">
          <div>
            <label className="field-label">Client</label>
            <select required value={form.client_id} onChange={set("client_id")} className="field" data-testid="invoice-form-client">
              <option value="">Select client</option>
              {clients.map((c) => <option key={c.id} value={c.id}>{c.company_name} · {c.contact_name}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="field-label">Invoice #</label>
              <input required value={form.invoice_no} onChange={set("invoice_no")} className="field" data-testid="invoice-form-no" />
            </div>
            <div>
              <label className="field-label">Amount (₹)</label>
              <input required type="number" min="0" value={form.amount_inr} onChange={set("amount_inr")} className="field" data-testid="invoice-form-amount" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="field-label">Due date</label>
              <input required type="date" value={form.due_date} onChange={set("due_date")} className="field" data-testid="invoice-form-due" />
            </div>
            <div>
              <label className="field-label">Paid on (optional)</label>
              <input type="date" value={form.paid_date} onChange={set("paid_date")} className="field" data-testid="invoice-form-paid" />
            </div>
          </div>
          <div>
            <label className="field-label">Notes</label>
            <textarea value={form.notes} onChange={set("notes")} rows={3} className="field" data-testid="invoice-form-notes" />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={() => onOpenChange(false)} className="cta-ghost">Cancel</button>
            <button type="submit" className="cta-primary" data-testid="invoice-form-submit">{invoice ? "Save" : "Create"}</button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
