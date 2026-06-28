"""
Provider-abstracted AI layer.

Why this exists
----------------
For the Emergent demo we use Claude Sonnet 4.5 via the Emergent Universal LLM key
(`anthropic_emergent` provider). When this repo is exported and refactored on Opus,
swapping to a direct Anthropic key, an OpenAI/Gemini provider, or a self-hosted
model is a one-file change: register a new entry in `PROVIDERS`.

The contract is intentionally narrow:

    text = await generate_text(provider, model, system, user_prompt, session_id)

Higher-level Revora drafting helpers compose business context (client name,
proposal value, days silent, tone) into a prompt and call `generate_text`.
"""

from __future__ import annotations

import os
import uuid
from typing import Callable, Awaitable, Dict, Optional

from emergentintegrations.llm.chat import LlmChat, UserMessage

# --- Provider registry -------------------------------------------------------

ProviderFn = Callable[[str, str, str, str], Awaitable[str]]


async def _anthropic_via_emergent(model: str, system: str, user: str, session_id: str) -> str:
    api_key = os.environ["EMERGENT_LLM_KEY"]
    chat = (
        LlmChat(api_key=api_key, session_id=session_id, system_message=system)
        .with_model("anthropic", model)
    )
    text = await chat.send_message(UserMessage(text=user))
    return (text or "").strip()


# When you export to Opus, add direct providers here, e.g.:
#
# async def _anthropic_direct(model, system, user, session_id):
#     ...uses os.environ['ANTHROPIC_API_KEY']...
#
# async def _openai_direct(model, system, user, session_id):
#     ...uses os.environ['OPENAI_API_KEY']...

PROVIDERS: Dict[str, ProviderFn] = {
    "anthropic_emergent": _anthropic_via_emergent,
}

# --- Defaults (config from env, sensible fallbacks) --------------------------

DEFAULT_PROVIDER = os.environ.get("AI_PROVIDER", "anthropic_emergent")
DEFAULT_MODEL = os.environ.get("AI_MODEL", "claude-sonnet-4-5-20250929")


# --- Public API --------------------------------------------------------------

async def generate_text(
    system: str,
    user: str,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    session_id: Optional[str] = None,
) -> str:
    """One-shot text completion. Provider-agnostic."""
    provider = provider or DEFAULT_PROVIDER
    model = model or DEFAULT_MODEL
    session_id = session_id or f"revora-{uuid.uuid4()}"
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown AI provider: {provider}. Registered: {list(PROVIDERS)}")
    return await PROVIDERS[provider](model, system, user, session_id)


# --- Revora-specific drafting --------------------------------------------------

TONE_GUIDE = {
    "gentle": "Warm, polite, casual but professional. Indian business etiquette. Start friendly.",
    "firm": "Direct and clear about the pending status. Still respectful but explicit about the need for an update.",
    "final": "Polite but final-warning tone. Acknowledge the long silence. Ask for a clear yes/no or a date.",
}


def _system_prompt(kind: str, tone: str) -> str:
    tone_line = TONE_GUIDE.get(tone, TONE_GUIDE["gentle"])
    if kind == "whatsapp":
        return (
            "You are an Indian B2B follow-up writing assistant for a service agency. "
            "Write a SHORT WhatsApp message (3 to 6 lines max, total under 80 words). "
            "No subject line. Use natural Indian English (e.g., 'Hi {name}', 'Just checking in'). "
            "Use ₹ for currency. Do not use emojis. Sign off with the sender's first name only. "
            f"Tone: {tone_line}"
        )
    if kind == "email":
        return (
            "You are an Indian B2B follow-up writing assistant for a service agency. "
            "Write a concise professional email (110-180 words). "
            "Format strictly as:\nSubject: <subject line>\n\n<email body>\n\n"
            "Body should have a greeting, 2 short paragraphs and a sign-off with sender name + company. "
            "Use ₹ for currency. No emojis. "
            f"Tone: {tone_line}"
        )
    # invoice_reminder
    return (
        "You are an Indian B2B accounts-receivable assistant. "
        "Write a polite invoice payment reminder email (100-160 words). "
        "Format strictly as:\nSubject: <subject line>\n\n<email body>\n\n"
        "Reference the invoice number and amount in ₹. Mention how many days it is past due. "
        "Offer to share invoice copy / answer questions. Sign off with sender name + company. No emojis. "
        f"Tone: {tone_line}"
    )


async def draft_followup(
    *,
    kind: str,           # "whatsapp" | "email" | "invoice_reminder"
    tone: str,           # "gentle" | "firm" | "final"
    sender_name: str,
    sender_company: str,
    recipient_name: str,
    recipient_company: str,
    subject_ref: str,    # short description: 'proposal "X" worth ₹...' OR 'invoice #...'
    days: int,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    system = _system_prompt(kind, tone)
    user = (
        f"Sender: {sender_name} from {sender_company}\n"
        f"Recipient: {recipient_name}"
        + (f" at {recipient_company}" if recipient_company else "")
        + "\n"
        f"Reference: {subject_ref}\n"
        f"Days since last contact / since due: {days}\n"
        f"Write the message now."
    )
    return await generate_text(
        system=system,
        user=user,
        provider=provider,
        model=model,
        session_id=f"draft-{uuid.uuid4()}",
    )
