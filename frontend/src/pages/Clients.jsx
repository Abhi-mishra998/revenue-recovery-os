import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Plus, ArrowUpRight } from "lucide-react";
import { toast } from "sonner";

export default function Clients() {
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(false);

  const load = async () => {
    const { data } = await api.get("/clients");
    setRows(data);
  };
  useEffect(() => { load(); }, []);

  return (
    <div className="p-6 md:p-10 max-w-[1200px]" data-testid="clients-page">
      <div className="flex items-end justify-between">
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-stone-500">Roster</div>
          <h1 className="font-serif-display text-4xl mt-1.5">Clients</h1>
          <p className="text-sm text-stone-500 mt-2">All the people & companies you're working with.</p>
        </div>
        <button className="cta-primary" onClick={() => setOpen(true)} data-testid="new-client-btn">
          <Plus className="w-4 h-4" /> New client
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-6" data-testid="clients-grid">
        {rows.length === 0 && (
          <div className="revora-card p-8 text-stone-400 col-span-full" data-testid="empty-clients">No clients yet. Add your first one.</div>
        )}
        {rows.map((c) => (
          <Link
            key={c.id}
            to={`/clients/${c.id}`}
            className="revora-card p-5 row-hover group block"
            data-testid={`client-card-${c.id}`}
          >
            <div className="flex items-start justify-between">
              <div>
                <div className="font-serif-display text-xl">{c.name}</div>
                {c.company && <div className="text-sm text-stone-500 mt-0.5">{c.company}</div>}
              </div>
              <ArrowUpRight className="w-4 h-4 text-stone-300 group-hover:text-stone-600 transition" />
            </div>
            <div className="mt-4 text-xs text-stone-500 space-y-1">
              {c.email && <div>{c.email}</div>}
              {c.phone && <div className="font-mono-num">{c.phone}</div>}
            </div>
          </Link>
        ))}
      </div>

      <NewClient open={open} onOpenChange={setOpen} onCreated={load} />
    </div>
  );
}

function NewClient({ open, onOpenChange, onCreated }) {
  const [form, setForm] = useState({ name: "", company: "", email: "", phone: "" });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post("/clients", {
        name: form.name,
        company: form.company || null,
        email: form.email || null,
        phone: form.phone || null,
      });
      toast.success("Client added");
      setForm({ name: "", company: "", email: "", phone: "" });
      onOpenChange(false);
      onCreated();
    } catch {
      toast.error("Could not add client");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#FAF9F6] border-stone-200">
        <DialogHeader><DialogTitle className="font-serif-display text-2xl">New client</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="space-y-3 mt-2" data-testid="new-client-form">
          <input required placeholder="Name" value={form.name} onChange={set("name")} className="w-full border border-stone-200 bg-white rounded-md px-3 py-2.5" data-testid="new-client-name" />
          <input placeholder="Company" value={form.company} onChange={set("company")} className="w-full border border-stone-200 bg-white rounded-md px-3 py-2.5" data-testid="new-client-company" />
          <input placeholder="Email" type="email" value={form.email} onChange={set("email")} className="w-full border border-stone-200 bg-white rounded-md px-3 py-2.5" data-testid="new-client-email" />
          <input placeholder="Phone (+91...)" value={form.phone} onChange={set("phone")} className="w-full border border-stone-200 bg-white rounded-md px-3 py-2.5" data-testid="new-client-phone" />
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={() => onOpenChange(false)} className="cta-ghost">Cancel</button>
            <button type="submit" className="cta-primary" data-testid="new-client-submit">Add</button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
