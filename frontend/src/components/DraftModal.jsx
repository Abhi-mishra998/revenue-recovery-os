import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Copy, RefreshCw, Sparkles, Check } from "lucide-react";
import { toast } from "sonner";

const TONES = [
  { id: "gentle", label: "Gentle" },
  { id: "firm", label: "Firm" },
  { id: "final", label: "Final nudge" },
];

export default function DraftModal({ open, onOpenChange, context }) {
  // context: { mode: 'proposal'|'invoice', id, label }
  const [tab, setTab] = useState("whatsapp");
  const [tone, setTone] = useState("gentle");
  const [drafts, setDrafts] = useState({}); // key=kind|tone -> text
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const key = `${tab}-${tone}`;
  const currentText = drafts[key];

  useEffect(() => {
    if (open && context) {
      setDrafts({});
      setTab(context.mode === "invoice" ? "email" : "whatsapp");
      setTone("gentle");
    }
  }, [open, context]);

  useEffect(() => {
    if (!open || !context) return;
    if (drafts[key]) return;
    generate();
    // eslint-disable-next-line
  }, [tab, tone, open]);

  const generate = async () => {
    if (!context) return;
    setLoading(true);
    try {
      const kind = context.mode === "invoice" ? (tab === "whatsapp" ? "whatsapp" : "invoice_reminder") : tab;
      const body = {
        kind,
        tone,
        proposal_id: context.mode === "proposal" ? context.id : undefined,
        invoice_id: context.mode === "invoice" ? context.id : undefined,
      };
      const { data } = await api.post("/ai/draft", body);
      setDrafts((d) => ({ ...d, [key]: data.text }));
    } catch (e) {
      toast.error("Could not generate draft. " + (e.response?.data?.detail || ""));
    } finally {
      setLoading(false);
    }
  };

  const copy = async () => {
    if (!currentText) return;
    await navigator.clipboard.writeText(currentText);
    setCopied(true);
    toast.success("Copied to clipboard");
    if (context?.id && context?.mode === "proposal") {
      api.post("/activities", { client_id: context.client_id, proposal_id: context.id, kind: "draft_copied", summary: `Copied ${tab} draft (${tone})` }).catch(() => {});
    }
    if (context?.id && context?.mode === "invoice") {
      api.post("/activities", { client_id: context.client_id, invoice_id: context.id, kind: "draft_copied", summary: `Copied ${tab} draft (${tone})` }).catch(() => {});
    }
    setTimeout(() => setCopied(false), 1800);
  };

  if (!context) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl bg-[#FAF9F6] border-stone-200">
        <DialogHeader>
          <DialogTitle className="font-serif-display text-2xl flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-amber-600" />
            AI Follow-up Draft
          </DialogTitle>
          <DialogDescription className="text-stone-500">
            For <span className="text-stone-700 font-medium">{context.label}</span> · drafts are copy-to-send only.
          </DialogDescription>
        </DialogHeader>

        <Tabs value={tab} onValueChange={setTab} className="mt-2">
          <TabsList className="bg-stone-100" data-testid="draft-channel-tabs">
            <TabsTrigger value="whatsapp" data-testid="draft-tab-whatsapp">WhatsApp</TabsTrigger>
            <TabsTrigger value="email" data-testid="draft-tab-email">
              {context.mode === "invoice" ? "Email reminder" : "Email"}
            </TabsTrigger>
          </TabsList>

          <div className="mt-4 flex items-center gap-2 flex-wrap" data-testid="tone-selector">
            <span className="text-[11px] uppercase tracking-[0.18em] text-stone-500 mr-1">Tone</span>
            {TONES.map((t) => (
              <button
                key={t.id}
                onClick={() => setTone(t.id)}
                data-testid={`tone-${t.id}`}
                className={`text-xs px-3 py-1.5 rounded-full border transition ${
                  tone === t.id
                    ? "bg-stone-900 text-amber-50 border-stone-900"
                    : "bg-white border-stone-200 text-stone-700 hover:bg-stone-50"
                }`}
              >
                {t.label}
              </button>
            ))}
            <button
              onClick={generate}
              data-testid="draft-regenerate"
              className="ml-auto text-xs px-3 py-1.5 rounded-full border border-stone-200 bg-white hover:bg-stone-50 inline-flex items-center gap-1.5"
            >
              <RefreshCw className="w-3 h-3" /> Regenerate
            </button>
          </div>

          <TabsContent value="whatsapp" className="mt-4">
            <DraftBody loading={loading} text={currentText} testId="draft-output-whatsapp" />
          </TabsContent>
          <TabsContent value="email" className="mt-4">
            <DraftBody loading={loading} text={currentText} testId="draft-output-email" />
          </TabsContent>
        </Tabs>

        <div className="mt-4 flex justify-end">
          <button
            onClick={copy}
            disabled={!currentText || loading}
            data-testid="draft-copy-btn"
            className="cta-primary disabled:opacity-50"
          >
            {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            {copied ? "Copied" : "Copy to clipboard"}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function DraftBody({ loading, text, testId }) {
  if (loading) {
    return (
      <div className="draft-output text-stone-400" data-testid={`${testId}-loading`}>
        Drafting with Claude…
      </div>
    );
  }
  return (
    <div className="draft-output" data-testid={testId}>{text || "—"}</div>
  );
}
