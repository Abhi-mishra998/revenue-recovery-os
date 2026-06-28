"""
AI layer — public API.

Business logic imports `generate_proposal_followup` and `NoApiKeyError` only.
Everything else (provider choice, prompt versioning, schema validation,
redaction, guardrails, model routing) is internal and swappable behind config.
"""

from __future__ import annotations

import uuid
from typing import Optional

from . import prompts
from . import redact as redact_mod
from .client import MalformedOutputError, NoApiKeyError, generate_json, generate_text  # noqa: F401
from .guardrail import GuardrailViolation, enforce_followup  # noqa: F401
from .router import RouteSignals, Tier, route  # noqa: F401
from .schemas import FollowUpDraft


def _format_inr(n: float) -> str:
    digits = str(int(round(n)))
    if len(digits) <= 3:
        return "₹" + digits
    last3, rest = digits[-3:], digits[:-3]
    groups = []
    while len(rest) > 2:
        groups.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.insert(0, rest)
    return "₹" + ",".join(groups) + "," + last3


def _build_context(
    *, sender_name, recipient_contact, recipient_company, industry, title, value_inr, days_silent
) -> str:
    industry_str = f", a {industry} business" if industry else ""
    return (
        f"Sender: {sender_name} (founder of an Indian B2B service agency)\n"
        f"Recipient: {recipient_contact} at {recipient_company}{industry_str}\n"
        f'Proposal title: "{title}"\n'
        f"Proposal value: {_format_inr(value_inr)}\n"
        f"Days since last contact: {days_silent}\n"
    )


async def generate_proposal_followup(
    *,
    sender_name: str,
    recipient_contact: str,
    recipient_company: str,
    industry: Optional[str],
    title: str,
    value_inr: float,
    days_silent: int,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    prompt_ref: Optional[str] = None,
    tier_override: Optional[Tier] = None,
) -> dict:
    """Returns {whatsapp_text, email_subject, email_body, prompt_ref, route_ref}.

    Single LLM call returns a JSON object matching FollowUpDraft. Malformed
    output triggers one corrective retry inside generate_json; second failure
    bubbles MalformedOutputError to the caller (server returns 502).

    Model selection goes through the router: SIMPLE tier (Gemini Flash) by
    default; COMPLEX tier (Claude Sonnet) for ≥ ₹50L proposals or when
    tier_override is set. Caller can also pin a specific provider/model
    bypassing the router.
    """
    template = prompts.get_ref(prompt_ref) if prompt_ref else prompts.get("proposal_followup")
    choice = route(
        RouteSignals(
            task="proposal_followup",
            value_inr=value_inr,
            override_tier=tier_override,
        )
    )
    eff_provider = provider or choice.provider
    eff_model = model or choice.model

    context = _build_context(
        sender_name=sender_name,
        recipient_contact=recipient_contact,
        recipient_company=recipient_company,
        industry=industry,
        title=title,
        value_inr=value_inr,
        days_silent=days_silent,
    )
    redacted_context, token_map = redact_mod.redact(context)
    system, user = template.render(context=redacted_context)

    draft: FollowUpDraft = await generate_json(
        system=system,
        user=user,
        schema=template.schema,
        provider=eff_provider,
        model=eff_model,
        session_id=f"fu-{uuid.uuid4()}",
    )

    # Rehydrate PII first, then guardrail-check the user-visible version.
    rehydrated = FollowUpDraft(
        whatsapp_text=redact_mod.rehydrate(draft.whatsapp_text, token_map).strip(),
        email_subject=redact_mod.rehydrate(draft.email_subject, token_map).strip(),
        email_body=redact_mod.rehydrate(draft.email_body, token_map).strip(),
    )
    enforce_followup(rehydrated)  # raises GuardrailViolation on bad content

    return {
        "whatsapp_text": rehydrated.whatsapp_text,
        "email_subject": rehydrated.email_subject,
        "email_body": rehydrated.email_body,
        "confidence": draft.confidence,
        "prompt_ref": template.ref,
        "route_ref": choice.ref,
    }


__all__ = ["generate_proposal_followup", "NoApiKeyError", "MalformedOutputError"]
