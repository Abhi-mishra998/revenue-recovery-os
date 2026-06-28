"""
Output guardrail.

Runs *after* schema validation and rehydration, *before* the draft is returned
to the user. Cheap structural and content checks — anything that would make
a B2B founder look bad if they pasted it.

Caller decides whether to block (raise) or warn (log + return).

Hard rule: even if checks pass, the system never sends the draft itself.
A human still copies and sends. The guardrail is one more belt over the
"copy-only" suspenders.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from .redact import has_unrehydrated_tokens
from .schemas import FollowUpDraft

logger = logging.getLogger(__name__)


# Phrases that should never appear in a polite B2B follow-up. Detection is
# case-insensitive, substring-based. False-positive cost is low (the user
# regenerates); false-negative cost is high (founder sends garbage).
_BLACKLIST = (
    "as an ai",
    "i am an ai",
    "as a language model",
    "i cannot",
    "i can't help",
    "i'm sorry, but i",
    "ignore previous instructions",
    "ignore the above",
    "system prompt",
    "you are now",
    "<|endoftext|>",
    "<|im_start|>",
    "[[redacted",  # any redaction-marker leak
)


class GuardrailViolation(RuntimeError):
    """One or more guardrail checks failed. .issues holds the list."""
    def __init__(self, issues: list[str]):
        super().__init__("; ".join(issues))
        self.issues = issues


@dataclass
class GuardrailResult:
    ok: bool
    issues: list[str]


def check_followup_draft(draft: FollowUpDraft) -> GuardrailResult:
    issues: list[str] = []

    for field, text in (("whatsapp_text", draft.whatsapp_text),
                        ("email_subject", draft.email_subject),
                        ("email_body",    draft.email_body)):
        text = text or ""
        if has_unrehydrated_tokens(text):
            issues.append(f"{field}: leaked redaction token")
        low = text.lower()
        for bad in _BLACKLIST:
            if bad in low:
                issues.append(f"{field}: contains blacklisted phrase ({bad!r})")
                break  # one issue per field is enough

    # WhatsApp word count (schema bounds chars, not words)
    wa_words = len(re.findall(r"\S+", draft.whatsapp_text or ""))
    if wa_words > 110:  # 70 target with headroom
        issues.append(f"whatsapp_text: too long ({wa_words} words; target <70)")

    # Email body looks like an email (some line breaks)
    if "\n" not in (draft.email_body or ""):
        issues.append("email_body: single line — likely not a real email")

    return GuardrailResult(ok=not issues, issues=issues)


def enforce_followup(draft: FollowUpDraft) -> None:
    """Raise GuardrailViolation if the draft fails checks. Caller can catch."""
    r = check_followup_draft(draft)
    if not r.ok:
        logger.warning("guardrail blocked follow-up draft: %s", r.issues)
        raise GuardrailViolation(r.issues)
