import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { inr, relativeDateISO } from "@/lib/format";
import { StatusPill } from "@/components/StatusPill";
import DraftModal from "@/components/DraftModal";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sparkles, Plus, CheckCircle2, Trash2 } from "lucide-react";
import { toast } from "sonner";

const STATUS_FILTERS = ["all", "active", "cold", "dead", "won", "lost"];

export default function Proposals() {
  const [rows, setRows] = useState([]);
  const [clients, setClients] = useState([]);
  const [filter, setFilter] = useState("all");
  const [draftCtx, setDraftCtx] = useState(null);
  const [openNew, setOpenNew] = useState(false);

  const load = async () => {
    const [pr, cl] = await Promise.all([api.get("/proposals"), api.get("/clients")]);
    setRows(pr.data);
    setClients(cl.data);
  };
  useEffect(() => { load(); }, []);

  const filtered = filter === "all" ? rows : rows.filter((r) => r.status === filter);

  const touch = async (id) => {
    await api.post(`/proposals/${id}/touch`);
    toast.success("Marked as followed-up today");
    load();
  };
  const remove = async (id) => {
    if (!confirm("Delete this proposal?")) return;
    await api.delete(`/proposals/${id}`);
    toast.success("Proposal deleted");
    load();
  };

  return (
    <div className="p-6 md:p-10 max-w-[1400px]" data-testid="proposals-page">
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-stone-500">Pipeline</div>
          <h1 className="font-serif-display text-4xl mt-1.5">Proposals</h1>
          <p className="text-sm text-stone-500 mt-2">All proposals, auto-categorized by days since last contact.</p>
        </div>
        <button className="cta-primary" onClick={() => setOpenNew(true)} data-testid="new-proposal-btn">
          <Plus className="w-4 h-4" /> New proposal
        </button>
      </div>

      <div className="flex items-center gap-2 mt-6 flex-wrap" data-testid="proposal-filters">
        {STATUS_FILTERS.map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            data-testid={`filter-${s}`}
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
              <th className="px-4 py-3 font-medium">Title</th>
              <th className="px-4 py-3 font-medium">Client</th>
              <th className="px-4 py-3 font-medium">Value</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Sent</th>
              <th className="px-4 py-3 font-medium">Last contact</th>
              <th className="px-4 py-3 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-10 text-center text-stone-400" data-testid="empty-proposals">No proposals here.</td></tr>
            )}
            {filtered.map((r) => (
              <tr key={r.id} className="row-hover border-b last:border-0 border-stone-100" data-testid={`proposal-row-${r.id}`}>
                <td className="px-4 py-3 font-medium">{r.title}</td>
                <td className="px-4 py-3 text-stone-700">
                  {r.client_name}
                  {r.client_company && <div className="text-xs text-stone-400">{r.client_company}</div>}
                </td>
                <td className="px-4 py-3 font-mono-num tnum">{inr(r.value)}</td>
                <td className="px-4 py-3"><StatusPill status={r.status} testId={`status-${r.id}`} /></td>
                <td className="px-4 py-3 text-stone-500">{relativeDateISO(r.sent_at)}</td>
                <td className="px-4 py-3 text-stone-500">{relativeDateISO(r.last_contact_at)} <span className="text-stone-400">· {r.days_silent}d</span></td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-1.5">
                    <button
                      onClick={() => setDraftCtx({ mode: "proposal", id: r.id, client_id: r.client_id, label: `${r.title} · ${r.client_name}` })}
                      className="cta-primary"
                      data-testid={`draft-btn-${r.id}`}
                    >
                      <Sparkles className="w-3.5 h-3.5" /> Draft
                    </button>
                    <button onClick={() => touch(r.id)} className="cta-ghost" data-testid={`touch-btn-${r.id}`}>
                      <CheckCircle2 className="w-3.5 h-3.5" />
                    </button>
                    <button onClick={() => remove(r.id)} className="cta-ghost text-red-600" data-testid={`delete-btn-${r.id}`}>
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
      <NewProposalDialog open={openNew} onOpenChange={setOpenNew} clients={clients} onCreated={load} />
    </div>
  );
}

function NewProposalDialog({ open, onOpenChange, clients, onCreated }) {
  const [form, setForm] = useState({ client_id: "", title: "", value: "", notes: "" });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post("/proposals", {
        client_id: form.client_id,
        title: form.title,
        value: parseFloat(form.value),
        notes: form.notes,
      });
      toast.success("Proposal created");
      setForm({ client_id: "", title: "", value: "", notes: "" });
      onOpenChange(false);
      onCreated();
    } catch (e) {
      toast.error("Could not create proposal");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#FAF9F6] border-stone-200">
        <DialogHeader>
          <DialogTitle className="font-serif-display text-2xl">New proposal</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3 mt-2" data-testid="new-proposal-form">
          <select required value={form.client_id} onChange={set("client_id")} className="w-full border border-stone-200 bg-white rounded-md px-3 py-2.5" data-testid="new-proposal-client">
            <option value="">Select client</option>
            {clients.map((c) => <option key={c.id} value={c.id}>{c.name} · {c.company || ""}</option>)}
          </select>
          <input required placeholder="Title" value={form.title} onChange={set("title")} className="w-full border border-stone-200 bg-white rounded-md px-3 py-2.5" data-testid="new-proposal-title" />
          <input required placeholder="Value in ₹" type="number" value={form.value} onChange={set("value")} className="w-full border border-stone-200 bg-white rounded-md px-3 py-2.5" data-testid="new-proposal-value" />
          <textarea placeholder="Notes (optional)" value={form.notes} onChange={set("notes")} rows={3} className="w-full border border-stone-200 bg-white rounded-md px-3 py-2.5" />
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={() => onOpenChange(false)} className="cta-ghost">Cancel</button>
            <button type="submit" className="cta-primary" data-testid="new-proposal-submit">Create</button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
