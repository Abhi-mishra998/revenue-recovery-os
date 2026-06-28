import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { ShieldCheck, Activity, Power, Cpu, RefreshCw, Check, AlertTriangle, Hash } from "lucide-react";

export default function Admin() {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user?.is_admin) return <Navigate to="/" replace />;

  return (
    <div className="p-6 md:p-10 max-w-[1300px] mx-auto" data-testid="admin-page">
      <header className="mb-6">
        <div className="text-[11px] uppercase tracking-[0.08em] text-zinc-500 font-medium">Operator console</div>
        <h1 className="text-[28px] md:text-[32px] font-semibold mt-1 text-zinc-900 tracking-tight">Admin</h1>
        <p className="text-[13.5px] text-zinc-500 mt-1.5">
          Audit chain, AI kill-switch, and active model/prompt configuration.
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-5">
        <KillSwitchCard />
        <ChainVerifyCard />
        <AiConfigCard />
        <AuditLogCard />
      </div>
    </div>
  );
}

function Section({ icon: Icon, title, hint, children, testId }) {
  return (
    <div className="revora-card p-5" data-testid={testId}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2.5">
          <span className="w-8 h-8 rounded-md grid place-items-center text-zinc-600"
            style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}>
            <Icon className="w-4 h-4" strokeWidth={1.75} />
          </span>
          <div>
            <div className="text-[15px] font-semibold text-zinc-900">{title}</div>
            {hint && <div className="text-[11.5px] text-zinc-500 mt-0.5">{hint}</div>}
          </div>
        </div>
      </div>
      {children}
    </div>
  );
}

function KillSwitchCard() {
  const [enabled, setEnabled] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const { data } = await api.get("/admin/killswitch");
    setEnabled(data.ai_killswitch);
  };
  useEffect(() => { load(); }, []);

  const toggle = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/admin/killswitch", { enabled: !enabled });
      setEnabled(data.ai_killswitch);
      toast.success(`AI ${data.ai_killswitch ? "disabled" : "enabled"}`);
    } catch {
      toast.error("Could not toggle kill-switch");
    } finally { setBusy(false); }
  };

  return (
    <Section
      icon={Power}
      title="AI kill-switch"
      hint="Blocks every outbound LLM call when on. Returns 503 to clients."
      testId="killswitch-card"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm">
          Status:{" "}
          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border
            ${enabled ? "bg-red-50 text-red-700 border-red-200" : "bg-green-50 text-green-700 border-green-200"}`}
            data-testid="killswitch-state">
            {enabled === null ? "—" : enabled ? "blocking AI" : "AI enabled"}
          </span>
        </div>
        <button onClick={toggle} disabled={busy || enabled === null}
          className={enabled ? "cta-primary" : "cta-danger"}
          data-testid="killswitch-toggle">
          {busy ? "Saving…" : enabled ? "Re-enable AI" : "Disable AI now"}
        </button>
      </div>
    </Section>
  );
}

function ChainVerifyCard() {
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  const verify = async () => {
    setBusy(true); setResult(null);
    try {
      const { data } = await api.get("/admin/audit-log/verify");
      setResult(data);
    } catch (e) {
      toast.error("Verify failed: " + (e.response?.data?.detail || e.message));
    } finally { setBusy(false); }
  };

  return (
    <Section
      icon={ShieldCheck}
      title="Audit chain integrity"
      hint="Recomputes every record hash and signature. Catches tampering."
      testId="chain-card"
    >
      <div className="flex items-center justify-between gap-3">
        <button onClick={verify} disabled={busy} className="cta-primary" data-testid="chain-verify-btn">
          <RefreshCw className={`w-3.5 h-3.5 ${busy ? "animate-spin" : ""}`} />
          {busy ? "Verifying…" : "Run verify"}
        </button>
        {result && (
          <div className="text-sm flex items-center gap-2" data-testid="chain-verify-result">
            {result.ok
              ? <><Check className="w-4 h-4 text-green-700" />
                  <span className="text-green-700 font-medium">OK</span></>
              : <><AlertTriangle className="w-4 h-4 text-red-700" />
                  <span className="text-red-700 font-medium">{result.issues.length} issue(s)</span></>}
            <span className="text-zinc-500 tnum">· {result.records_checked} records</span>
          </div>
        )}
      </div>
      {result?.public_key_fp && (
        <div className="mt-3 text-[11px] text-zinc-500 inline-flex items-center gap-1">
          <Hash className="w-3 h-3" /> key fp <span className="font-mono">{result.public_key_fp}</span>
        </div>
      )}
      {result && !result.ok && (
        <ul className="mt-3 text-xs text-red-700 bg-red-50 border border-red-100 rounded-md p-2 space-y-0.5 max-h-32 overflow-auto">
          {result.issues.map((i, idx) => <li key={idx}>{i}</li>)}
        </ul>
      )}
    </Section>
  );
}

function AiConfigCard() {
  const [cfg, setCfg] = useState(null);
  useEffect(() => {
    api.get("/admin/ai/config").then((r) => setCfg(r.data)).catch(() => {});
  }, []);
  if (!cfg) return (
    <Section icon={Cpu} title="Active AI configuration" hint="Prompts + routing table." testId="ai-config-card">
      <div className="text-sm text-zinc-400">Loading…</div>
    </Section>
  );
  return (
    <Section icon={Cpu} title="Active AI configuration" hint="Prompts + routing table — read-only." testId="ai-config-card">
      <div className="space-y-3 text-sm">
        <Row label="Active prompts">
          {Object.entries(cfg.active_prompts).map(([k, v]) => (
            <div key={k} className="flex justify-between gap-2 text-xs py-0.5">
              <span className="text-zinc-600">{k}</span>
              <span className="font-mono text-zinc-900">{v.ref}</span>
            </div>
          ))}
        </Row>
        <Row label={`Routing (≥ ₹${(cfg.high_value_threshold_inr/100000).toFixed(0)}L → complex)`}>
          <div className="text-xs text-zinc-900 py-0.5">
            <div className="flex justify-between"><span className="text-zinc-600">simple</span>
              <span className="font-mono">{cfg.routes_default.simple.provider}/{cfg.routes_default.simple.model}</span></div>
            <div className="flex justify-between"><span className="text-zinc-600">complex</span>
              <span className="font-mono">{cfg.routes_default.complex.provider}/{cfg.routes_default.complex.model}</span></div>
          </div>
        </Row>
        <Row label="Prompt versions in registry">
          <div className="flex flex-wrap gap-1.5 mt-1">
            {Object.keys(cfg.prompt_versions).map((ref) => (
              <span key={ref} className="text-[11px] px-2 py-0.5 rounded-full border border-zinc-200 bg-white font-mono">
                {ref}
              </span>
            ))}
          </div>
        </Row>
      </div>
    </Section>
  );
}

function Row({ label, children }) {
  return (
    <div>
      <div className="field-label">{label}</div>
      <div className="mt-1">{children}</div>
    </div>
  );
}

function AuditLogCard() {
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async (p = page) => {
    setBusy(true);
    try {
      const { data } = await api.get(`/admin/audit-log?page=${p}&page_size=25`);
      setData(data);
    } finally { setBusy(false); }
  };
  useEffect(() => { load(1); }, []);

  return (
    <div className="revora-card p-5 lg:col-span-2" data-testid="audit-log-card">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2.5">
          <span className="w-8 h-8 rounded-md grid place-items-center text-zinc-600"
            style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}>
            <Activity className="w-4 h-4" strokeWidth={1.75} />
          </span>
          <div>
            <div className="text-[15px] font-semibold text-zinc-900">Audit log</div>
            <div className="text-[11.5px] text-zinc-500 mt-0.5">
              Newest first · {data?.total ?? "—"} total records
            </div>
          </div>
        </div>
        <button onClick={() => load(page)} className="cta-ghost" data-testid="audit-refresh">
          <RefreshCw className={`w-3.5 h-3.5 ${busy ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[700px]">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-[0.16em] text-slate-500 border-b border-slate-200 font-semibold">
              <th className="px-3 py-2 w-12">Seq</th>
              <th className="px-3 py-2">Action</th>
              <th className="px-3 py-2">Resource</th>
              <th className="px-3 py-2">Actor</th>
              <th className="px-3 py-2">Time</th>
            </tr>
          </thead>
          <tbody>
            {(data?.records || []).map((r) => (
              <tr key={r.id} className="border-b last:border-0 border-slate-100" data-testid={`audit-row-${r.seq}`}>
                <td className="px-3 py-2 tnum text-slate-500">{r.seq}</td>
                <td className="px-3 py-2 font-mono text-[12.5px] text-slate-900">{r.action}</td>
                <td className="px-3 py-2 text-[12px] text-slate-600">
                  {r.resource_type ? `${r.resource_type}/${(r.resource_id || "").slice(0, 8)}…` : "—"}
                </td>
                <td className="px-3 py-2 text-[12px] text-slate-600 truncate max-w-[180px]">{r.actor_email}</td>
                <td className="px-3 py-2 text-[11.5px] text-slate-500 tnum">{new Date(r.timestamp).toLocaleString()}</td>
              </tr>
            ))}
            {data?.records?.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-8 text-center text-slate-400">No records yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between mt-3">
        <span className="text-xs text-zinc-500">Page {data?.page ?? 1}</span>
        <div className="flex items-center gap-2">
          <button disabled={busy || (data?.page ?? 1) <= 1}
            onClick={() => { setPage(page - 1); load(page - 1); }}
            className="cta-ghost text-xs" data-testid="audit-prev">Prev</button>
          <button disabled={busy || !data || data.page * data.page_size >= data.total}
            onClick={() => { setPage(page + 1); load(page + 1); }}
            className="cta-ghost text-xs" data-testid="audit-next">Next</button>
        </div>
      </div>
    </div>
  );
}
