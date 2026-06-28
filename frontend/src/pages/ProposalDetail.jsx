import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { inr, dateShort } from "@/lib/format";
import { StatusBadge, StageBadge } from "@/components/StatusPill";
import { ArrowLeft, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { ProposalDialog } from "@/pages/Proposals";

export default function ProposalDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [client, setClient] = useState(null);
  const [clients, setClients] = useState([]);
  const [editing, setEditing] = useState(false);

  const load = async () => {
    const { data: p } = await api.get(`/proposals/${id}`);
    setData(p);
    const cl = await api.get(`/clients/${p.client_id}`);
    setClient(cl.data.client);
    const all = await api.get("/clients");
    setClients(all.data);
  };
  useEffect(() => { load(); }, [id]);

  const remove = async () => {
    if (!confirm("Delete this proposal?")) return;
    await api.delete(`/proposals/${id}`);
    toast.success("Proposal deleted");
    nav("/proposals");
  };

  if (!data) return <div className="p-8 text-slate-500">Loading…</div>;

  return (
    <div className="p-5 md:p-8 max-w-[900px]" data-testid={`proposal-detail-${id}`}>
      <Link to="/proposals" className="inline-flex items-center text-xs text-slate-500 hover:text-slate-800 gap-1 mb-4" data-testid="back-to-proposals">
        <ArrowLeft className="w-3.5 h-3.5" /> All proposals
      </Link>

      <div className="revora-card p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl md:text-3xl font-semibold text-slate-900">{data.title}</h1>
            {client && (
              <Link to={`/clients/${client.id}`} className="text-sm text-indigo-700 hover:text-indigo-800 mt-1 inline-block">
                {client.company_name} · {client.contact_name}
              </Link>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setEditing(true)} className="cta-ghost" data-testid="edit-proposal-detail"><Pencil className="w-3.5 h-3.5" /> Edit</button>
            <button onClick={remove} className="cta-danger" data-testid="delete-proposal-detail"><Trash2 className="w-3.5 h-3.5" /> Delete</button>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-5 mt-6">
          <Field label="Value" value={inr(data.value_inr)} mono />
          <Field label="Stage" value={<StageBadge stage={data.stage} />} />
          <Field label="Status" value={<StatusBadge status={data.status} />} />
          <Field label="Days silent" value={`${data.days_silent}d`} />
          <Field label="Sent" value={dateShort(data.sent_date)} />
          <Field label="Last contact" value={dateShort(data.last_contact_date)} />
        </div>

        {data.notes && (
          <div className="mt-6">
            <div className="field-label">Notes</div>
            <div className="text-sm text-slate-700 mt-1 whitespace-pre-wrap">{data.notes}</div>
          </div>
        )}
      </div>

      <ProposalDialog
        open={editing}
        onOpenChange={(o) => !o && setEditing(false)}
        proposal={data}
        clients={clients}
        onSaved={() => { setEditing(false); load(); }}
      />
    </div>
  );
}

function Field({ label, value, mono }) {
  return (
    <div>
      <div className="field-label">{label}</div>
      <div className={`text-base mt-1 text-slate-900 ${mono ? "font-mono-num tnum" : ""}`}>{value}</div>
    </div>
  );
}
