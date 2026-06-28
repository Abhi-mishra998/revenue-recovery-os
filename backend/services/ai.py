"""
Provider-abstracted AI layer.

The default for follow-up drafts is `gemini_emergent` (Gemini 2.5 Flash via the
Emergent Universal LLM key) — low-cost, fast, good enough for short B2B drafts.

Swapping providers (e.g. to a direct Gemini key from the user's settings, or to
Anthropic) is a one-file change: register a new entry in `PROVIDERS`.
"""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from typing import Callable, Awaitable, Dict, Optional

from emergentintegrations.llm.chat import LlmChat, UserMessage


# --- Provider registry -------------------------------------------------------
ProviderFn = Callable[[str, str, str, str], Awaitable[str]]


def _require_emergent_key() -> str:
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise NoApiKeyError("No AI API key configured. Please add an API key in settings.")
    return key


class NoApiKeyError(RuntimeError):
    """Raised when the active provider has no API key configured."""


async def _anthropic_via_emergent(model: str, system: str, user: str, session_id: str) -> str:
    api_key = _require_emergent_key()
    chat = (
        LlmChat(api_key=api_key, session_id=session_id, system_message=system)
        .with_model("anthropic", model)
    )
    text = await chat.send_message(UserMessage(text=user))
    return (text or "").strip()


async def _gemini_via_emergent(model: str, system: str, user: str, session_id: str) -> str:
    api_key = _require_emergent_key()
    chat = (
        LlmChat(api_key=api_key, session_id=session_id, system_message=system)
        .with_model("gemini", model)
    )
    text = await chat.send_message(UserMessage(text=user))
    return (text or "").strip()


# When user adds a direct Gemini/OpenAI key in settings, register here:
#
# async def _gemini_direct(model, system, user, session_id):
#     ...uses os.environ['GEMINI_API_KEY']...

PROVIDERS: Dict[str, ProviderFn] = {
    "anthropic_emergent": _anthropic_via_emergent,
    "gemini_emergent": _gemini_via_emergent,
}

DEFAULT_PROVIDER = os.environ.get("AI_PROVIDER", "gemini_emergent")
DEFAULT_MODEL = os.environ.get("AI_MODEL", "gemini-2.5-flash")


# --- Public API --------------------------------------------------------------
async def generate_text(
    system: str,
    user: str,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    session_id: Optional[str] = None,
) -> str:
    provider = provider or DEFAULT_PROVIDER
    model = model or DEFAULT_MODEL
    session_id = session_id or f"revora-{uuid.uuid4()}"
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown AI provider: {provider}. Registered: {list(PROVIDERS)}")
    return await PROVIDERS[provider](model, system, user, session_id)


# --- Proposal follow-up generator (dual output) -----------------------------
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


def _build_context(
    *, sender_name: str, recipient_contact: str, recipient_company: str,
    industry: Optional[str], title: str, value_inr: float, days_silent: int,
) -> str:
    industry_str = f", a {industry} business" if industry else ""
    return (
        f"Sender: {sender_name} (founder of an Indian B2B service agency)\n"
        f"Recipient: {recipient_contact} at {recipient_company}{industry_str}\n"
        f"Proposal title: \"{title}\"\n"
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
) -> dict:
    """
    Returns:
      {
        "whatsapp_text": str,
        "email_subject": str,
        "email_body": str,
      }
    """
    ctx = _build_context(
        sender_name=sender_name,
        recipient_contact=recipient_contact,
        recipient_company=recipient_company,
        industry=industry,
        title=title,
        value_inr=value_inr,
        days_silent=days_silent,
    )

    wa_task = generate_text(
        system=WA_SYSTEM,
        user=ctx + "\nWrite the WhatsApp message now.",
        provider=provider, model=model,
        session_id=f"wa-{uuid.uuid4()}",
    )
    em_task = generate_text(
        system=EMAIL_SYSTEM,
        user=ctx + "\nWrite the email now.",
        provider=provider, model=model,
        session_id=f"em-{uuid.uuid4()}",
    )
    wa_text, em_text = await asyncio.gather(wa_task, em_task)

    # Parse "Subject: ...\n\n<body>"
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
