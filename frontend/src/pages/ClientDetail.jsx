import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "@/lib/api";
import { inr, relativeDateISO } from "@/lib/format";
import { StatusPill } from "@/components/StatusPill";
import { ArrowLeft, Mail, Phone, MessageSquare, FileText, Receipt, StickyNote } from "lucide-react";

const KIND_ICON = { call: Phone, whatsapp: MessageSquare, email: Mail, meeting: Phone, note: StickyNote, draft_copied: FileText };

export default function ClientDetail() {
  const { id } = useParams();
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get(`/clients/${id}`).then((r) => setData(r.data));
  }, [id]);

  if (!data) return <div className="p-10 text-stone-500">Loading…</div>;
  const { client, proposals, invoices, activities } = data;

  return (
    <div className="p-6 md:p-10 max-w-[1100px]" data-testid={`client-detail-${id}`}>
      <Link to="/clients" className="inline-flex items-center text-xs text-stone-500 hover:text-stone-800 gap-1 mb-4" data-testid="back-to-clients">
        <ArrowLeft className="w-3.5 h-3.5" /> All clients
      </Link>

      <div className="revora-card p-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="font-serif-display text-4xl">{client.name}</h1>
          {client.company && <div className="text-stone-500 mt-1">{client.company}</div>}
          <div className="flex items-center gap-4 text-xs text-stone-500 mt-3">
            {client.email && <span>{client.email}</span>}
            {client.phone && <span className="font-mono-num">{client.phone}</span>}
          </div>
        </div>
      </div>

      {/* Proposals */}
      <Section title="Proposals" count={proposals.length} testId="client-proposals">
        {proposals.length === 0 ? (
          <Empty>No proposals for this client yet.</Empty>
        ) : (
          <ul className="divide-y divide-stone-100">
            {proposals.map((p) => (
              <li key={p.id} className="py-3 flex items-center justify-between gap-4" data-testid={`client-proposal-${p.id}`}>
                <div>
                  <div className="font-medium">{p.title}</div>
                  <div className="text-xs text-stone-500">Sent {relativeDateISO(p.sent_at)} · {p.days_silent}d silent</div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-mono-num tnum text-stone-700">{inr(p.value)}</span>
                  <StatusPill status={p.status} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {/* Invoices */}
      <Section title="Invoices" count={invoices.length} testId="client-invoices">
        {invoices.length === 0 ? (
          <Empty>No invoices for this client.</Empty>
        ) : (
          <ul className="divide-y divide-stone-100">
            {invoices.map((i) => (
              <li key={i.id} className="py-3 flex items-center justify-between gap-4" data-testid={`client-invoice-${i.id}`}>
                <div>
                  <div className="font-medium font-mono-num">#{i.invoice_number}</div>
                  <div className="text-xs text-stone-500">Due {relativeDateISO(i.due_date)}{i.days_overdue ? ` · ${i.days_overdue}d overdue` : ""}</div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-mono-num tnum text-stone-700">{inr(i.amount)}</span>
                  <StatusPill status={i.status} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {/* Activity */}
      <Section title="Activity" count={activities.length} testId="client-activity">
        {activities.length === 0 ? (
          <Empty>No activity yet.</Empty>
        ) : (
          <ol className="relative border-l border-stone-200 ml-2 space-y-3 pt-1">
            {activities.map((a) => {
              const Icon = KIND_ICON[a.kind] || StickyNote;
              return (
                <li key={a.id} className="ml-4 relative" data-testid={`activity-${a.id}`}>
                  <span className="absolute -left-[26px] top-1 w-4 h-4 rounded-full bg-white border border-stone-200 grid place-items-center">
                    <Icon className="w-2.5 h-2.5 text-stone-600" />
                  </span>
                  <div className="text-sm">{a.summary}</div>
                  <div className="text-[11px] text-stone-500 mt-0.5">{relativeDateISO(a.created_at)} · <span className="uppercase tracking-wider">{a.kind}</span></div>
                </li>
              );
            })}
          </ol>
        )}
      </Section>
    </div>
  );
}

function Section({ title, count, children, testId }) {
  return (
    <section className="mt-8" data-testid={testId}>
      <div className="flex items-end justify-between mb-3">
        <h2 className="font-serif-display text-2xl">{title}</h2>
        <span className="text-[11px] uppercase tracking-[0.18em] text-stone-500">{count} item{count === 1 ? "" : "s"}</span>
      </div>
      <div className="revora-card p-5">{children}</div>
    </section>
  );
}

function Empty({ children }) {
  return <div className="text-sm text-stone-400 py-3">{children}</div>;
}
