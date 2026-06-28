import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { inr, dateShort } from "@/lib/format";
import { StatusBadge, StageBadge } from "@/components/StatusPill";
import { ArrowLeft, Pencil, Trash2, Mail, Phone, MessageSquare, Languages, Briefcase } from "lucide-react";
import { toast } from "sonner";
import { ClientDialog } from "@/pages/Clients";

export default function ClientDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [editing, setEditing] = useState(false);

  const load = async () => {
    const { data: d } = await api.get(`/clients/${id}`);
    setData(d);
  };
  useEffect(() => { load(); }, [id]);

  const remove = async () => {
    if (!confirm("Delete this client?")) return;
    await api.delete(`/clients/${id}`);
    toast.success("Client deleted");
    nav("/clients");
  };

  if (!data) return <div className="p-8 text-slate-500">Loading…</div>;
  const { client, proposals, invoices } = data;

  return (
    <div className="p-6 md:p-10 max-w-[1100px] mx-auto" data-testid={`client-detail-${id}`}>
      <Link to="/clients" className="inline-flex items-center text-[12px] text-zinc-500 hover:text-zinc-800 gap-1 mb-4" data-testid="back-to-clients">
        <ArrowLeft className="w-3.5 h-3.5" /> All clients
      </Link>

      <div className="revora-card p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-[22px] md:text-[26px] font-semibold text-zinc-900 tracking-tight">{client.company_name}</h1>
            <div className="text-zinc-500 mt-0.5 text-[13.5px]">{client.contact_name}</div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setEditing(true)} className="cta-ghost" data-testid="edit-client-detail"><Pencil className="w-3.5 h-3.5" /> Edit</button>
            <button onClick={remove} className="cta-danger" data-testid="delete-client-detail"><Trash2 className="w-3.5 h-3.5" /> Delete</button>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mt-6">
          {client.email && <InfoRow icon={Mail} label="Email" value={client.email} />}
          {client.phone && <InfoRow icon={Phone} label="Phone" value={<span className="font-mono-num">{client.phone}</span>} />}
          {client.whatsapp && <InfoRow icon={MessageSquare} label="WhatsApp" value={<span className="font-mono-num">{client.whatsapp}</span>} />}
          {client.industry && <InfoRow icon={Briefcase} label="Industry" value={client.industry} />}
          {client.language && <InfoRow icon={Languages} label="Language" value={client.language} />}
        </div>

        {client.notes && (
          <div className="mt-5">
            <div className="field-label">Notes</div>
            <div className="text-sm text-slate-700 mt-1 whitespace-pre-wrap">{client.notes}</div>
          </div>
        )}
      </div>

      <Section title="Proposals" count={proposals.length} testId="client-proposals">
        {proposals.length === 0 ? (
          <Empty>No proposals for this client yet.</Empty>
        ) : (
          <ul className="divide-y divide-slate-100">
            {proposals.map((p) => (
              <li key={p.id} className="py-3 flex flex-wrap items-center justify-between gap-3" data-testid={`client-proposal-${p.id}`}>
                <div>
                  <Link to={`/proposals/${p.id}`} className="font-medium text-slate-900 hover:text-indigo-700">{p.title}</Link>
                  <div className="text-xs text-slate-500 mt-0.5">Sent {dateShort(p.sent_date)} · {p.days_silent}d silent</div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-mono-num tnum text-slate-700">{inr(p.value_inr)}</span>
                  <StageBadge stage={p.stage} />
                  <StatusBadge status={p.status} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Invoices" count={invoices.length} testId="client-invoices">
        {invoices.length === 0 ? (
          <Empty>No invoices for this client.</Empty>
        ) : (
          <ul className="divide-y divide-slate-100">
            {invoices.map((i) => (
              <li key={i.id} className="py-3 flex flex-wrap items-center justify-between gap-3" data-testid={`client-invoice-${i.id}`}>
                <div>
                  <div className="font-medium font-mono-num text-slate-900">#{i.invoice_no}</div>
                  <div className="text-xs text-slate-500 mt-0.5">Due {dateShort(i.due_date)}{i.days_overdue ? ` · ${i.days_overdue}d overdue` : ""}</div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-mono-num tnum text-slate-700">{inr(i.amount_inr)}</span>
                  <StatusBadge status={i.status} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <ClientDialog open={editing} onOpenChange={(o) => !o && setEditing(false)} client={client} onSaved={() => { setEditing(false); load(); }} />
    </div>
  );
}

function InfoRow({ icon: Icon, label, value }) {
  return (
    <div className="flex items-start gap-2">
      <span className="w-7 h-7 rounded-md border border-slate-200 bg-slate-50 grid place-items-center text-slate-500">
        <Icon className="w-3.5 h-3.5" />
      </span>
      <div>
        <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500 font-semibold">{label}</div>
        <div className="text-sm text-slate-900">{value}</div>
      </div>
    </div>
  );
}

function Section({ title, count, children, testId }) {
  return (
    <section className="mt-6" data-testid={testId}>
      <div className="flex items-end justify-between mb-3">
        <h2 className="text-xl font-semibold text-slate-900">{title}</h2>
        <span className="text-[11px] uppercase tracking-[0.16em] text-slate-500 font-semibold">{count} item{count === 1 ? "" : "s"}</span>
      </div>
      <div className="revora-card p-5">{children}</div>
    </section>
  );
}

function Empty({ children }) {
  return <div className="text-sm text-slate-400 py-3">{children}</div>;
}
