import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Plus, ArrowUpRight, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";

export default function Clients() {
  const [rows, setRows] = useState([]);
  const [editing, setEditing] = useState(null); // client or { __new: true }

  const load = async () => {
    const { data } = await api.get("/clients");
    setRows(data);
  };
  useEffect(() => { load(); }, []);

  const remove = async (id, e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm("Delete this client? Their proposals & invoices stay.")) return;
    await api.delete(`/clients/${id}`);
    toast.success("Client deleted");
    load();
  };

  return (
    <div className="p-6 md:p-10 max-w-[1300px] mx-auto" data-testid="clients-page">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.08em] text-zinc-500 font-medium">Roster</div>
          <h1 className="text-[28px] md:text-[32px] font-semibold mt-1 text-zinc-900 tracking-tight">Clients</h1>
          <p className="text-[13.5px] text-zinc-500 mt-1.5">All your clients and contacts.</p>
        </div>
        <button className="cta-primary" onClick={() => setEditing({ __new: true })} data-testid="new-client-btn">
          <Plus className="w-4 h-4" /> New client
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-6" data-testid="clients-grid">
        {rows.length === 0 && (
          <div className="revora-card p-8 text-slate-400 col-span-full" data-testid="empty-clients">No clients yet. Add your first one.</div>
        )}
        {rows.map((c) => (
          <Link
            key={c.id}
            to={`/clients/${c.id}`}
            className="revora-card p-5 hover:border-indigo-300 hover:shadow-sm transition group block"
            data-testid={`client-card-${c.id}`}
          >
            <div className="flex items-start justify-between">
              <div>
                <div className="text-lg font-semibold text-slate-900">{c.company_name}</div>
                <div className="text-sm text-slate-500 mt-0.5">{c.contact_name}</div>
              </div>
              <ArrowUpRight className="w-4 h-4 text-slate-300 group-hover:text-indigo-600 transition" />
            </div>
            {c.industry && (
              <div className="mt-3 inline-flex items-center text-[11px] uppercase tracking-[0.16em] px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 font-semibold">
                {c.industry}
              </div>
            )}
            <div className="mt-3 text-xs text-slate-500 space-y-0.5">
              {c.email && <div className="truncate">{c.email}</div>}
              {c.phone && <div className="font-mono-num">{c.phone}</div>}
            </div>
            <div className="mt-4 flex items-center gap-2 pt-3 border-t border-slate-100" onClick={(e) => e.preventDefault()}>
              <button onClick={(e) => { e.preventDefault(); e.stopPropagation(); setEditing(c); }} className="cta-ghost text-xs" data-testid={`edit-client-${c.id}`}>
                <Pencil className="w-3 h-3" /> Edit
              </button>
              <button onClick={(e) => remove(c.id, e)} className="cta-danger text-xs" data-testid={`delete-client-${c.id}`}>
                <Trash2 className="w-3 h-3" /> Delete
              </button>
            </div>
          </Link>
        ))}
      </div>

      <ClientDialog
        open={!!editing}
        onOpenChange={(o) => !o && setEditing(null)}
        client={editing && !editing.__new ? editing : null}
        onSaved={() => { setEditing(null); load(); }}
      />
    </div>
  );
}

export function ClientDialog({ open, onOpenChange, client, onSaved }) {
  const empty = { company_name: "", contact_name: "", email: "", phone: "", whatsapp: "", industry: "", language: "English", notes: "" };
  const [form, setForm] = useState(empty);

  useEffect(() => {
    if (client) {
      setForm({
        company_name: client.company_name || "",
        contact_name: client.contact_name || "",
        email: client.email || "",
        phone: client.phone || "",
        whatsapp: client.whatsapp || "",
        industry: client.industry || "",
        language: client.language || "English",
        notes: client.notes || "",
      });
    } else {
      setForm(empty);
    }
    // eslint-disable-next-line
  }, [client, open]);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    const body = {
      company_name: form.company_name,
      contact_name: form.contact_name,
      email: form.email || null,
      phone: form.phone || null,
      whatsapp: form.whatsapp || null,
      industry: form.industry || null,
      language: form.language || "English",
      notes: form.notes || null,
    };
    try {
      if (client) {
        await api.patch(`/clients/${client.id}`, body);
        toast.success("Client updated");
      } else {
        await api.post("/clients", body);
        toast.success("Client added");
      }
      onSaved();
    } catch {
      toast.error("Could not save client");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white border-slate-200 max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold">{client ? "Edit client" : "New client"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3 mt-2" data-testid="client-form">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="field-label">Company</label>
              <input required value={form.company_name} onChange={set("company_name")} className="field" data-testid="client-form-company" />
            </div>
            <div>
              <label className="field-label">Contact name</label>
              <input required value={form.contact_name} onChange={set("contact_name")} className="field" data-testid="client-form-contact" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="field-label">Email</label>
              <input type="email" value={form.email} onChange={set("email")} className="field" data-testid="client-form-email" />
            </div>
            <div>
              <label className="field-label">Phone</label>
              <input value={form.phone} onChange={set("phone")} className="field" data-testid="client-form-phone" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="field-label">WhatsApp</label>
              <input value={form.whatsapp} onChange={set("whatsapp")} className="field" data-testid="client-form-whatsapp" />
            </div>
            <div>
              <label className="field-label">Industry</label>
              <input value={form.industry} onChange={set("industry")} className="field" data-testid="client-form-industry" />
            </div>
          </div>
          <div>
            <label className="field-label">Language</label>
            <input value={form.language} onChange={set("language")} className="field" data-testid="client-form-language" />
          </div>
          <div>
            <label className="field-label">Notes</label>
            <textarea value={form.notes} onChange={set("notes")} rows={3} className="field" data-testid="client-form-notes" />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={() => onOpenChange(false)} className="cta-ghost">Cancel</button>
            <button type="submit" className="cta-primary" data-testid="client-form-submit">{client ? "Save" : "Add"}</button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
