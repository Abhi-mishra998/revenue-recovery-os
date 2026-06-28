"""
AI layer — public API.

Business logic imports `generate_proposal_followup` and `NoApiKeyError` only.
Everything else (provider choice, prompt versioning, schema validation,
redaction, guardrails, model routing) is internal and swappable behind config.
"""
from __future__ import annotations

import uuid
from typing import Optional

from .client import NoApiKeyError, MalformedOutputError, generate_json, generate_text  # noqa: F401
from . import prompts
from .schemas import FollowUpDraft


def _format_inr(n: float) -> str:
    digits = str(int(round(n)))
    if len(digits) <= 3:
        return "₹" + digits
    last3, rest = digits[-3:], digits[:-3]
    groups = []
    while len(rest) > 2:
        groups.insert(0, rest[-2:]); rest = rest[:-2]
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


async def generate_proposal_followup(
    *, sender_name: str, recipient_contact: str, recipient_company: str,
    industry: Optional[str], title: str, value_inr: float, days_silent: int,
    provider: Optional[str] = None, model: Optional[str] = None,
    prompt_ref: Optional[str] = None,
) -> dict:
    """Returns {whatsapp_text, email_subject, email_body, prompt_ref}.

    Single LLM call returns a JSON object matching FollowUpDraft. Malformed
    output triggers one corrective retry inside generate_json; second failure
    bubbles MalformedOutputError to the caller (server returns 502).
    """
    template = prompts.get_ref(prompt_ref) if prompt_ref else prompts.get("proposal_followup")
    context = _build_context(
        sender_name=sender_name, recipient_contact=recipient_contact,
        recipient_company=recipient_company, industry=industry,
        title=title, value_inr=value_inr, days_silent=days_silent,
    )
    system, user = template.render(context=context)

    draft: FollowUpDraft = await generate_json(
        system=system, user=user, schema=template.schema,
        provider=provider, model=model, session_id=f"fu-{uuid.uuid4()}",
    )
    return {
        "whatsapp_text": draft.whatsapp_text.strip(),
        "email_subject": draft.email_subject.strip(),
        "email_body": draft.email_body.strip(),
        "prompt_ref": template.ref,
    }


__all__ = ["generate_proposal_followup", "NoApiKeyError", "MalformedOutputError"]
