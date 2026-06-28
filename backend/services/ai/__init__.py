"""
AI layer — public API.

Business logic imports `generate_proposal_followup` and `NoApiKeyError` only.
Everything else (provider choice, prompt versioning, schema validation,
redaction, guardrails, model routing) is internal and swappable behind config.
"""
from __future__ import annotations

import asyncio
import re
import uuid
from typing import Optional

from .client import NoApiKeyError, generate_text  # re-exported  # noqa: F401


# Prompts kept inline for now — they move to services/ai/prompts.py in commit 2.
def _format_inr(n: float) -> str:
    digits = str(int(round(n)))
    if len(digits) <= 3:
        return "₹" + digits
    last3 = digits[-3:]
    rest = digits[:-3]
    groups = []
    while len(rest) > 2:
        groups.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.insert(0, rest)
    return "₹" + ",".join(groups) + "," + last3


def _build_context(*, sender_name, recipient_contact, recipient_company,
                   industry, title, value_inr, days_silent) -> str:
    industry_str = f", a {industry} business" if industry else ""
    return (
        f"Sender: {sender_name} (founder of an Indian B2B service agency)\n"
        f"Recipient: {recipient_contact} at {recipient_company}{industry_str}\n"
        f'Proposal title: "{title}"\n'
        f"Proposal value: {_format_inr(value_inr)}\n"
        f"Days since last contact: {days_silent}\n"
    )


WA_SYSTEM = (
    "You write polite, warm WhatsApp follow-ups for an Indian B2B service agency. "
    "Output a SHORT message of 3-5 lines, total under 70 words. "
    "Use natural Indian English. Reference the proposal title or the client's industry briefly so it feels specific. "
    "Use ₹ for currency. Do not use emojis. Sign off with the sender's first name only. "
    "No 'Subject:' line. Output ONLY the message text, nothing else."
)

EMAIL_SYSTEM = (
    "You write polite, slightly formal follow-up emails for an Indian B2B service agency. "
    "Output the email in EXACTLY this format:\n"
    "Subject: <single line subject>\n\n"
    "<body — 2 short paragraphs, 110-180 words total, sign off with sender name + 'Revora'>\n\n"
    "Use Indian English. Reference the proposal title and the client's industry where relevant. "
    "Use ₹ for currency. Do not use emojis. Output ONLY the email, nothing else."
)


async def generate_proposal_followup(
    *, sender_name: str, recipient_contact: str, recipient_company: str,
    industry: Optional[str], title: str, value_inr: float, days_silent: int,
    provider: Optional[str] = None, model: Optional[str] = None,
) -> dict:
    """Returns {whatsapp_text, email_subject, email_body}."""
    ctx = _build_context(
        sender_name=sender_name, recipient_contact=recipient_contact,
        recipient_company=recipient_company, industry=industry,
        title=title, value_inr=value_inr, days_silent=days_silent,
    )

    wa_task = generate_text(
        system=WA_SYSTEM, user=ctx + "\nWrite the WhatsApp message now.",
        provider=provider, model=model, session_id=f"wa-{uuid.uuid4()}",
    )
    em_task = generate_text(
        system=EMAIL_SYSTEM, user=ctx + "\nWrite the email now.",
        provider=provider, model=model, session_id=f"em-{uuid.uuid4()}",
    )
    wa_text, em_text = await asyncio.gather(wa_task, em_task)

    subject = ""
    body = (em_text or "").strip()
    m = re.match(r"^\s*Subject:\s*(.+?)\n\s*\n([\s\S]+)$", body, re.IGNORECASE)
    if m:
        subject = m.group(1).strip()
        body = m.group(2).strip()

    return {
        "whatsapp_text": (wa_text or "").strip(),
        "email_subject": subject,
        "email_body": body,
    }


__all__ = ["generate_proposal_followup", "NoApiKeyError"]
