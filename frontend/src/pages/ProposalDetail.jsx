import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { inr, dateShort } from "@/lib/format";
import { StatusBadge, StageBadge } from "@/components/StatusPill";
import { ArrowLeft, Pencil, Trash2, Sparkles, Copy, Check, Send, Mail, MessageSquare, KeyRound, Cpu, Hash, Gauge, History, TrendingUp } from "lucide-react";
import { toast } from "sonner";
import { ProposalDialog } from "@/pages/Proposals";

export default function ProposalDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [client, setClient] = useState(null);
  const [clients, setClients] = useState([]);
  const [editing, setEditing] = useState(false);

  // AI follow-up state
  const [genLoading, setGenLoading] = useState(false);
  const [drafts, setDrafts] = useState(null);   // { whatsapp: {id,text}, email: {id,subject,body} }
  const [meta, setMeta] = useState(null);       // { prompt_ref, route_ref, confidence, latency_ms, ... }
  const [history, setHistory] = useState([]);
  const [genError, setGenError] = useState(null);

  const load = async () => {
    const { data: p } = await api.get(`/proposals/${id}`);
    setData(p);
    const cl = await api.get(`/clients/${p.client_id}`);
    setClient(cl.data.client);
    const all = await api.get("/clients");
    setClients(all.data);
    try {
      const h = await api.get(`/proposals/${id}/followups`);
      setHistory(h.data || []);
    } catch { /* tolerate empty history */ }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  const remove = async () => {
    if (!confirm("Delete this proposal?")) return;
    await api.delete(`/proposals/${id}`);
    toast.success("Proposal deleted");
    nav("/proposals");
  };

  const generate = async () => {
    setGenLoading(true);
    setGenError(null);
    try {
      const { data: r } = await api.post(`/proposals/${id}/generate-followup`);
      setDrafts({ whatsapp: r.whatsapp, email: r.email });
      setMeta(r.meta || null);
      // Refresh history so the new generation appears
      try {
        const h = await api.get(`/proposals/${id}/followups`);
        setHistory(h.data || []);
      } catch { /* tolerate */ }
      toast.success("Drafts ready");
    } catch (e) {
      const detail = e.response?.data?.detail;
      const msg = typeof detail === "string" ? detail : "Could not generate drafts";
      setGenError(msg);
      toast.error(msg);
    } finally {
      setGenLoading(false);
    }
  };

  if (!data) return <div className="p-8 text-slate-500">Loading…</div>;

  return (
    <div className="p-6 md:p-10 max-w-[1000px] mx-auto" data-testid={`proposal-detail-${id}`}>
      <Link to="/proposals" className="inline-flex items-center text-[12px] text-zinc-500 hover:text-zinc-800 gap-1 mb-4" data-testid="back-to-proposals">
        <ArrowLeft className="w-3.5 h-3.5" /> All proposals
      </Link>

      {/* Proposal summary card */}
      <div className="revora-card p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-[22px] md:text-[26px] font-semibold text-zinc-900 tracking-tight">{data.title}</h1>
            {client && (
              <Link to={`/clients/${client.id}`} className="text-[13px] text-zinc-700 hover:text-zinc-900 mt-1 inline-block underline-offset-4 hover:underline">
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
          {data.prediction && <Field label="Close likelihood" value={<PredictionBadge p={data.prediction} />} />}
          {data.outcome_at && <Field label="Closed" value={dateShort(data.outcome_at)} />}
        </div>

        {data.notes && (
          <div className="mt-6">
            <div className="field-label">Notes</div>
            <div className="text-sm text-slate-700 mt-1 whitespace-pre-wrap">{data.notes}</div>
          </div>
        )}
      </div>

      {/* AI follow-up section */}
      <section className="mt-6" data-testid="ai-followup-section">
        <div className="revora-card p-5 md:p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <span className="w-7 h-7 rounded-md bg-teal-50 border border-teal-100 text-teal-700 grid place-items-center">
                  <Sparkles className="w-4 h-4" />
                </span>
                <h2 className="text-lg font-semibold text-slate-900">AI Follow-Up</h2>
              </div>
              <p className="text-sm text-slate-500 mt-1.5">
                Generates a short WhatsApp message + a slightly formal email from this proposal&apos;s context.
                Copy &amp; send manually — Revora never auto-sends.
              </p>
            </div>
            <button
              onClick={generate}
              disabled={genLoading}
              className="cta-primary"
              data-testid="generate-followup-btn"
            >
              <Sparkles className="w-4 h-4" />
              {genLoading ? "Drafting…" : (drafts ? "Regenerate" : "Generate Follow-Up")}
            </button>
          </div>

          {genError && (
            <div className="mt-4 p-3 rounded-md border border-amber-200 bg-amber-50 text-sm text-amber-900 flex items-start gap-2" data-testid="genfollowup-error">
              <KeyRound className="w-4 h-4 mt-0.5 shrink-0" />
              <div>
                <div className="font-medium">{genError}</div>
                <div className="text-xs text-amber-800 mt-1">
                  Add an API key (Gemini, OpenAI or Anthropic) in settings to enable AI drafts.
                </div>
              </div>
            </div>
          )}

          {!drafts && !genError && !genLoading && (
            <div className="mt-4 text-sm text-slate-400 italic" data-testid="genfollowup-idle">
              Click <span className="font-medium text-slate-600">Generate Follow-Up</span> to draft a WhatsApp and email follow-up tailored to {client?.company_name || "this client"}.
            </div>
          )}

          {drafts && (
            <>
              {meta && <MetaBadges meta={meta} />}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mt-5" data-testid="genfollowup-drafts">
                <WhatsAppDraft text={drafts.whatsapp.text} client={client} />
                <EmailDraft subject={drafts.email.subject} body={drafts.email.body} client={client} />
              </div>
            </>
          )}
        </div>
      </section>

      {history.length > 0 && (
        <GenerationHistory history={history} />
      )}

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

function CopyButton({ text, testId }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      toast.success("Copied");
      setTimeout(() => setCopied(false), 1600);
    } catch {
      toast.error("Could not copy");
    }
  };
  return (
    <button onClick={copy} className="cta-ghost text-xs" data-testid={testId}>
      {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function waLink(phone, text) {
  if (!phone) return null;
  const digits = (phone || "").replace(/\D/g, "");
  if (!digits) return null;
  return `https://wa.me/${digits}?text=${encodeURIComponent(text)}`;
}

function WhatsAppDraft({ text, client }) {
  const phone = client?.whatsapp || client?.phone;
  const link = waLink(phone, text);
  return (
    <div className="revora-card p-4 border-slate-200" data-testid="draft-whatsapp">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <span className="w-6 h-6 rounded-md bg-green-50 border border-green-100 text-green-700 grid place-items-center">
            <MessageSquare className="w-3.5 h-3.5" />
          </span>
          <div className="text-sm font-semibold text-slate-900">WhatsApp · short &amp; warm</div>
        </div>
        <CopyButton text={text} testId="draft-whatsapp-copy" />
      </div>
      <div className="bg-green-50/40 border border-green-100 rounded-md p-3 text-sm text-slate-800 whitespace-pre-wrap" data-testid="draft-whatsapp-text">
        {text}
      </div>
      <div className="mt-3 flex items-center gap-2">
        {link ? (
          <a
            href={link}
            target="_blank"
            rel="noopener noreferrer"
            className="cta-accent text-sm"
            data-testid="send-on-whatsapp"
          >
            <Send className="w-3.5 h-3.5" /> Send on WhatsApp
          </a>
        ) : (
          <span className="text-xs text-slate-500" data-testid="send-on-whatsapp-disabled">
            Add a phone or WhatsApp number to this client to enable Send on WhatsApp.
          </span>
        )}
        <span className="text-[11px] text-slate-400 ml-auto">Never auto-sent</span>
      </div>
    </div>
  );
}

function PredictionBadge({ p }) {
  const pct = Math.round((p.probability ?? 0) * 100);
  const tone =
    pct >= 70 ? { bg: "#DCFCE7", fg: "#166534", border: "#86EFAC" } :
    pct >= 40 ? { bg: "#FEF3C7", fg: "#92400E", border: "#FCD34D" } :
                { bg: "#FEE2E2", fg: "#991B1B", border: "#FCA5A5" };
  const reasons = (p.reasons || []).join(" · ");
  return (
    <span
      title={`${p.model_ref} · signal ${(p.confidence * 100).toFixed(0)}% · ${reasons}`}
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border tnum"
      style={{ background: tone.bg, color: tone.fg, borderColor: tone.border }}
      data-testid="proposal-prediction-badge"
    >
      <TrendingUp className="w-3 h-3" /> {pct}%
    </span>
  );
}

function Pill({ icon: Icon, label, value, tone = "default", testId }) {
  const palette = tone === "good"
    ? { bg: "#DCFCE7", fg: "#166534", border: "#86EFAC" }
    : tone === "warn"
    ? { bg: "#FEF3C7", fg: "#92400E", border: "#FCD34D" }
    : { bg: "#F4F4F5", fg: "#3F3F46", border: "#E4E4E7" };
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border"
      style={{ background: palette.bg, color: palette.fg, borderColor: palette.border }}
      data-testid={testId}
      title={label}>
      {Icon && <Icon className="w-3 h-3" />} {value}
    </span>
  );
}

function MetaBadges({ meta }) {
  const conf = meta.confidence == null ? null : Math.round(meta.confidence * 100);
  const confTone = conf == null ? "default" : conf >= 70 ? "good" : conf >= 40 ? "warn" : "default";
  return (
    <div className="flex flex-wrap items-center gap-1.5 mt-4" data-testid="genfollowup-meta">
      {conf != null && <Pill icon={Gauge} label="AI confidence" value={`AI conf ${conf}%`} tone={confTone} testId="meta-confidence" />}
      {meta.prompt_ref && <Pill icon={Hash} label="Prompt" value={meta.prompt_ref} testId="meta-prompt" />}
      {meta.route_ref && <Pill icon={Cpu} label="Model route" value={meta.route_ref} testId="meta-route" />}
      {meta.latency_ms != null && <Pill label="Latency" value={`${meta.latency_ms} ms`} testId="meta-latency" />}
    </div>
  );
}

function GenerationHistory({ history }) {
  // Group by generation_id so the WA + email rows from one call land together.
  const byGen = new Map();
  for (const f of history) {
    const key = f.generation_id || f.id;
    if (!byGen.has(key)) byGen.set(key, { created_at: f.created_at, rows: [], meta: f });
    byGen.get(key).rows.push(f);
  }
  const groups = Array.from(byGen.values()).sort(
    (a, b) => (b.created_at || "").localeCompare(a.created_at || "")
  );
  return (
    <section className="mt-6" data-testid="genfollowup-history">
      <div className="revora-card p-5 md:p-6">
        <div className="flex items-center gap-2 mb-3">
          <span className="w-7 h-7 rounded-md bg-zinc-100 border border-zinc-200 text-zinc-600 grid place-items-center">
            <History className="w-4 h-4" strokeWidth={1.75} />
          </span>
          <h2 className="text-lg font-semibold text-slate-900">Generation history</h2>
          <span className="text-[11px] text-zinc-500 ml-1">{groups.length} run{groups.length === 1 ? "" : "s"}</span>
        </div>
        <ul className="divide-y divide-slate-100">
          {groups.map((g) => {
            const m = g.meta || {};
            return (
              <li key={g.created_at + (g.rows[0]?.id || "")} className="py-3" data-testid={`history-${g.created_at}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-[12px] text-slate-500 tnum">{new Date(g.created_at).toLocaleString()}</div>
                  <div className="flex flex-wrap gap-1.5">
                    {m.confidence != null && <Pill icon={Gauge} value={`AI conf ${Math.round(m.confidence*100)}%`} />}
                    {m.prompt_ref && <Pill icon={Hash} value={m.prompt_ref} />}
                    {m.route_ref && <Pill icon={Cpu} value={m.route_ref} />}
                    {m.latency_ms != null && <Pill value={`${m.latency_ms} ms`} />}
                  </div>
                </div>
                <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-3">
                  {g.rows.map((r) => (
                    <details key={r.id} className="text-sm" data-testid={`history-row-${r.id}`}>
                      <summary className="cursor-pointer text-[12.5px] text-slate-700 inline-flex items-center gap-1.5">
                        {r.channel === "whatsapp" ? <MessageSquare className="w-3.5 h-3.5" /> : <Mail className="w-3.5 h-3.5" />}
                        <span className="capitalize font-medium">{r.channel}</span>
                        <span className="text-slate-400">· {(r.draft_text || "").slice(0, 60)}…</span>
                      </summary>
                      <pre className="mt-2 text-[12px] whitespace-pre-wrap text-slate-700 bg-slate-50 border border-slate-100 rounded p-2 max-h-56 overflow-auto">
{r.draft_text}
                      </pre>
                    </details>
                  ))}
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}

function EmailDraft({ subject, body, client }) {
  const fullText = subject ? `Subject: ${subject}\n\n${body}` : body;
  const mailto = client?.email
    ? `mailto:${encodeURIComponent(client.email)}?subject=${encodeURIComponent(subject || "")}&body=${encodeURIComponent(body)}`
    : null;
  return (
    <div className="revora-card p-4 border-slate-200" data-testid="draft-email">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <span className="w-6 h-6 rounded-md bg-indigo-50 border border-indigo-100 text-indigo-700 grid place-items-center">
            <Mail className="w-3.5 h-3.5" />
          </span>
          <div className="text-sm font-semibold text-slate-900">Email · slightly formal</div>
        </div>
        <CopyButton text={fullText} testId="draft-email-copy" />
      </div>
      {subject && (
        <div className="mb-2">
          <div className="field-label">Subject</div>
          <div className="text-sm text-slate-900 mt-1" data-testid="draft-email-subject">{subject}</div>
        </div>
      )}
      <div className="bg-indigo-50/40 border border-indigo-100 rounded-md p-3 text-sm text-slate-800 whitespace-pre-wrap" data-testid="draft-email-body">
        {body}
      </div>
      <div className="mt-3 flex items-center gap-2">
        {mailto ? (
          <a href={mailto} className="cta-ghost text-xs" data-testid="open-in-mail">
            <Mail className="w-3 h-3" /> Open in mail app
          </a>
        ) : (
          <span className="text-xs text-slate-500">No client email on file.</span>
        )}
        <span className="text-[11px] text-slate-400 ml-auto">Never auto-sent</span>
      </div>
    </div>
  );
}
