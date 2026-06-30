import { useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const OUTCOMES = [
  { value: "replied", label: "Replied" },
  { value: "meeting_booked", label: "Meeting booked" },
  { value: "closed_won", label: "Closed won" },
  { value: "no_reply", label: "No reply" },
  { value: "closed_lost", label: "Closed lost" },
];

export default function ThumbsFeedback({ recommendationId, onSubmitted }) {
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(null);
  const [showOutcome, setShowOutcome] = useState(false);
  const [thumb, setThumb] = useState(null);

  async function send(thumbValue, outcome) {
    setSubmitting(true);
    try {
      await api.post(`/recommendations/${recommendationId}/feedback`, {
        thumb: thumbValue,
        outcome: outcome || null,
      });
      setSubmitted(thumbValue);
      setShowOutcome(false);
      onSubmitted?.(thumbValue, outcome);
      toast.success(thumbValue === "up" ? "Thanks — noted" : "Got it — we'll learn from this");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Could not save feedback");
    } finally {
      setSubmitting(false);
    }
  }

  function handleThumb(t) {
    setThumb(t);
    setShowOutcome(true);
  }

  if (submitted) {
    return (
      <div className="inline-flex items-center gap-1 text-[12px] text-zinc-500" data-testid="feedback-done">
        {submitted === "up" ? <ThumbsUp className="size-3.5 text-emerald-600" aria-hidden="true" /> : <ThumbsDown className="size-3.5 text-rose-600" aria-hidden="true" />}
        Feedback recorded
      </div>
    );
  }

  return (
    <div className="inline-flex items-center gap-2" data-testid="thumbs-feedback">
      {!showOutcome ? (
        <>
          <button
            type="button"
            disabled={submitting}
            onClick={() => handleThumb("up")}
            className="inline-flex items-center justify-center rounded-md border px-2 py-1 text-[12px] hover:bg-emerald-50 hover:border-emerald-300 focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:ring-offset-1 disabled:opacity-50 transition-colors"
            data-testid="thumb-up"
            aria-label="Mark this recommendation as helpful"
            title="This is a good recommendation"
          >
            <ThumbsUp className="size-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            disabled={submitting}
            onClick={() => handleThumb("down")}
            className="inline-flex items-center justify-center rounded-md border px-2 py-1 text-[12px] hover:bg-rose-50 hover:border-rose-300 focus:outline-none focus:ring-2 focus:ring-rose-400 focus:ring-offset-1 disabled:opacity-50 transition-colors"
            data-testid="thumb-down"
            aria-label="Mark this recommendation as missed"
            title="This recommendation missed the mark"
          >
            <ThumbsDown className="size-3.5" aria-hidden="true" />
          </button>
        </>
      ) : (
        <div className="inline-flex items-center gap-2">
          <span className="text-[12px] text-zinc-600">What happened?</span>
          <div className="min-w-[170px]">
            <Select disabled={submitting} onValueChange={(v) => send(thumb, v)}>
              <SelectTrigger className="h-8 text-[12px]" data-testid="outcome-select" aria-label="Outcome of the recommendation">
                <SelectValue placeholder="Optional outcome…" />
              </SelectTrigger>
              <SelectContent>
                {OUTCOMES.map((o) => (
                  <SelectItem key={o.value} value={o.value} className="text-[12.5px]">{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <button
            type="button"
            disabled={submitting}
            onClick={() => send(thumb, null)}
            className="text-[12px] text-zinc-500 hover:text-zinc-800 underline focus:outline-none focus:ring-2 focus:ring-zinc-400 rounded"
            data-testid="skip-outcome"
            aria-label="Skip outcome and submit feedback only"
          >
            skip
          </button>
        </div>
      )}
    </div>
  );
}
