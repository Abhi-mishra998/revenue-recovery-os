import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { inr, dateShort, dateForInput } from "@/lib/format";
import { StatusBadge, StageBadge } from "@/components/StatusPill";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Plus, Trash2, Pencil, Search, ArrowUpDown, ArrowDown, ArrowUp, Upload } from "lucide-react";
import { toast } from "sonner";
import BulkAddDialog from "@/components/BulkAddDialog";

const STAGE_OPTIONS = ["sent", "negotiating", "won", "lost"];
const STATUS_FILTERS = ["all", "active", "cold", "dead"];

export default function Proposals() {
  const nav = useNavigate();
  const [rows, setRows] = useState([]);
  const [clients, setClients] = useState([]);
  const [editing, setEditing] = useState(null); // proposal or { __new: true }
  const [bulkOpen, setBulkOpen] = useState(false);

  // Toolbar state
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortKey, setSortKey] = useState("days"); // 'days' | 'value'
  const [sortDir, setSortDir] = useState("desc"); // 'asc' | 'desc'

  const load = async () => {
    const [pr, cl] = await Promise.all([api.get("/proposals"), api.get("/clients")]);
    setRows(pr.data);
    setClients(cl.data);
  };
  useEffect(() => { load(); }, []);

  const remove = async (id, e) => {
    e.stopPropagation();
    if (!confirm("Delete this proposal?")) return;
    await api.delete(`/proposals/${id}`);
    toast.success("Proposal deleted");
    load();
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = rows.filter((r) => {
      if (statusFilter !== "all" && r.status !== statusFilter) return false;
      if (!q) return true;
      return (
        (r.title || "").toLowerCase().includes(q) ||
        (r.client_company_name || "").toLowerCase().includes(q) ||
        (r.client_contact_name || "").toLowerCase().includes(q)
      );
    });
    const keyFn = sortKey === "value"
      ? (x) => Number(x.value_inr || 0)
      : (x) => Number(x.days_silent || 0);
    const sorted = [...list].sort((a, b) => keyFn(a) - keyFn(b));
    if (sortDir === "desc") sorted.reverse();
    return sorted;
  }, [rows, query, statusFilter, sortKey, sortDir]);

  const toggleSort = (key) => {
    if (sortKey === key) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir("desc"); }
  };
  const sortIcon = (key) => {
    if (sortKey !== key) return <ArrowUpDown className="w-3 h-3 opacity-50" />;
    return sortDir === "desc" ? <ArrowDown className="w-3 h-3" /> : <ArrowUp className="w-3 h-3" />;
  };

  return (
    <div className="p-6 md:p-10 max-w-[1400px] mx-auto" data-testid="proposals-page">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="eyebrow-rule">Pipeline</div>
          <h1 className="text-[28px] md:text-[32px] font-semibold mt-2 text-zinc-900 tracking-tight">Proposals</h1>
          <p className="text-[13.5px] text-zinc-500 mt-1.5">Auto status: Active ≤ 7d · Cold 8–21d · Dead 22d+ since last contact.</p>
        </div>
        <div className="flex items-center gap-2">
          <button className="cta-ghost" onClick={() => setBulkOpen(true)} data-testid="bulk-add-proposals-btn">
            <Upload className="w-4 h-4" /> Bulk add
          </button>
          <button className="cta-primary" onClick={() => setEditing({ __new: true })} data-testid="new-proposal-btn">
            <Plus className="w-4 h-4" /> New proposal
          </button>
        </div>
      </div>

      {/* Toolbar: search + filters */}
      <div className="mt-6 flex flex-wrap items-center gap-3" data-testid="proposals-toolbar">
        <div className="relative flex-1 min-w-[220px] max-w-md">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by client or title…"
            className="field pl-9"
            data-testid="proposals-search"
          />
        </div>
        <div className="flex items-center gap-1.5" data-testid="proposals-status-filters">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              data-testid={`filter-${s}`}
              className={`text-xs px-3 py-1.5 rounded-full border transition capitalize ${
                statusFilter === s
                  ? "bg-zinc-900 text-zinc-50 border-zinc-900"
                  : "bg-white border-zinc-200 text-zinc-700 hover:bg-zinc-50 hover:border-zinc-300 hover:text-zinc-900"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="ml-auto text-xs text-slate-500" data-testid="proposals-count">
          {filtered.length} of {rows.length}
        </div>
      </div>

      <div className="revora-card overflow-hidden mt-4">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[900px]">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-[0.16em] text-slate-500 border-b border-slate-200 font-semibold">
                <th className="px-4 py-3">Client</th>
                <th className="px-4 py-3">Title</th>
                <th className="px-4 py-3">
                  <button onClick={() => toggleSort("value")} className="inline-flex items-center gap-1.5 uppercase tracking-[0.16em]" data-testid="sort-value">
                    Value {sortIcon("value")}
                  </button>
                </th>
                <th className="px-4 py-3">Last contact</th>
                <th className="px-4 py-3">
                  <button onClick={() => toggleSort("days")} className="inline-flex items-center gap-1.5 uppercase tracking-[0.16em]" data-testid="sort-days">
                    Days since contact {sortIcon("days")}
                  </button>
                </th>
                <th className="px-4 py-3">Stage</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr><td colSpan={8} className="px-4 py-10 text-center text-slate-400" data-testid="empty-proposals">
                  {rows.length === 0 ? "No proposals yet." : "No proposals match your search."}
                </td></tr>
              )}
              {filtered.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => nav(`/proposals/${r.id}`)}
                  className="row-hover border-b last:border-0 border-slate-100 cursor-pointer"
                  data-testid={`proposal-row-${r.id}`}
                >
                  <td className="px-4 py-3 text-slate-700">
                    <div className="font-medium">{r.client_company_name}</div>
                    <div className="text-xs text-slate-400">{r.client_contact_name}</div>
                  </td>
                  <td className="px-4 py-3 font-medium text-slate-900">{r.title}</td>
                  <td className="px-4 py-3 font-mono-num tnum" data-testid={`value-${r.id}`}>{inr(r.value_inr)}</td>
                  <td className="px-4 py-3 text-slate-500">{dateShort(r.last_contact_date)}</td>
                  <td className="px-4 py-3 tnum text-slate-700" data-testid={`days-${r.id}`}>{r.days_silent}d</td>
                  <td className="px-4 py-3"><StageBadge stage={r.stage} testId={`stage-${r.id}`} /></td>
                  <td className="px-4 py-3"><StatusBadge status={r.status} testId={`status-${r.id}`} /></td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
                      <button onClick={() => setEditing(r)} className="cta-ghost" data-testid={`edit-proposal-${r.id}`}>
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button onClick={(e) => remove(r.id, e)} className="cta-danger" data-testid={`delete-proposal-${r.id}`}>
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <ProposalDialog
        open={!!editing}
        onOpenChange={(o) => !o && setEditing(null)}
        proposal={editing && !editing.__new ? editing : null}
        clients={clients}
        onSaved={() => { setEditing(null); load(); }}
      />
      <BulkAddDialog
        open={bulkOpen}
        onOpenChange={setBulkOpen}
        mode="proposals"
        clients={clients}
        onDone={load}
      />
    </div>
  );
}

export function ProposalDialog({ open, onOpenChange, proposal, clients, onSaved }) {
  const empty = { client_id: "", title: "", value_inr: "", stage: "sent", sent_date: "", last_contact_date: "", notes: "" };
  const [form, setForm] = useState(empty);
  useEffect(() => {
    if (proposal) {
      setForm({
        client_id: proposal.client_id,
        title: proposal.title || "",
        value_inr: String(proposal.value_inr ?? ""),
        stage: proposal.stage || "sent",
        sent_date: dateForInput(proposal.sent_date),
        last_contact_date: dateForInput(proposal.last_contact_date),
        notes: proposal.notes || "",
      });
    } else {
      setForm(empty);
    }
    // eslint-disable-next-line
  }, [proposal, open]);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    const body = {
      client_id: form.client_id,
      title: form.title,
      value_inr: parseFloat(form.value_inr),
      stage: form.stage,
      sent_date: form.sent_date ? new Date(form.sent_date).toISOString() : null,
      last_contact_date: form.last_contact_date ? new Date(form.last_contact_date).toISOString() : null,
      notes: form.notes,
    };
    try {
      if (proposal) {
        await api.patch(`/proposals/${proposal.id}`, body);
        toast.success("Proposal updated");
      } else {
        await api.post("/proposals", body);
        toast.success("Proposal created");
      }
      onSaved();
    } catch {
      toast.error("Could not save proposal");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white border-slate-200">
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold">{proposal ? "Edit proposal" : "New proposal"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3 mt-2" data-testid="proposal-form">
          <div>
            <label className="field-label">Client</label>
            <select required value={form.client_id} onChange={set("client_id")} className="field" data-testid="proposal-form-client">
              <option value="">Select client</option>
              {clients.map((c) => <option key={c.id} value={c.id}>{c.company_name} · {c.contact_name}</option>)}
            </select>
          </div>
          <div>
            <label className="field-label">Title</label>
            <input required value={form.title} onChange={set("title")} className="field" data-testid="proposal-form-title" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="field-label">Value (₹)</label>
              <input required type="number" min="0" value={form.value_inr} onChange={set("value_inr")} className="field" data-testid="proposal-form-value" />
            </div>
            <div>
              <label className="field-label">Stage</label>
              <select value={form.stage} onChange={set("stage")} className="field" data-testid="proposal-form-stage">
                {STAGE_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="field-label">Sent date</label>
              <input type="date" value={form.sent_date} onChange={set("sent_date")} className="field" data-testid="proposal-form-sent" />
            </div>
            <div>
              <label className="field-label">Last contact date</label>
              <input type="date" value={form.last_contact_date} onChange={set("last_contact_date")} className="field" data-testid="proposal-form-last" />
            </div>
          </div>
          <div>
            <label className="field-label">Notes</label>
            <textarea value={form.notes} onChange={set("notes")} rows={3} className="field" data-testid="proposal-form-notes" />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={() => onOpenChange(false)} className="cta-ghost">Cancel</button>
            <button type="submit" className="cta-primary" data-testid="proposal-form-submit">{proposal ? "Save" : "Create"}</button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
