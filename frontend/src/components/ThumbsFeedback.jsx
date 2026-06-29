import { useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { ThumbsUp, ThumbsDown } from "lucide-react";

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
        {submitted === "up" ? <ThumbsUp className="size-3.5 text-emerald-600" /> : <ThumbsDown className="size-3.5 text-rose-600" />}
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
            className="inline-flex items-center justify-center rounded-md border px-2 py-1 text-[12px] hover:bg-emerald-50 hover:border-emerald-300 disabled:opacity-50"
            data-testid="thumb-up"
            title="This is a good recommendation"
          >
            <ThumbsUp className="size-3.5" />
          </button>
          <button
            type="button"
            disabled={submitting}
            onClick={() => handleThumb("down")}
            className="inline-flex items-center justify-center rounded-md border px-2 py-1 text-[12px] hover:bg-rose-50 hover:border-rose-300 disabled:opacity-50"
            data-testid="thumb-down"
            title="This recommendation missed the mark"
          >
            <ThumbsDown className="size-3.5" />
          </button>
        </>
      ) : (
        <div className="inline-flex items-center gap-2">
          <span className="text-[12px] text-zinc-500">What happened?</span>
          <select
            disabled={submitting}
            onChange={(e) => send(thumb, e.target.value)}
            defaultValue=""
            className="text-[12px] border rounded-md px-1.5 py-1"
            data-testid="outcome-select"
          >
            <option value="" disabled>Optional outcome…</option>
            {OUTCOMES.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <button
            type="button"
            disabled={submitting}
            onClick={() => send(thumb, null)}
            className="text-[12px] text-zinc-500 hover:text-zinc-800 underline"
            data-testid="skip-outcome"
          >
            skip
          </button>
        </div>
      )}
    </div>
  );
}
