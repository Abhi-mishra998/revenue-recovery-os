"""
Versioned prompt templates — ONE place.

Every template carries an id and a version. Bump the version when you change
either the system instruction or the user template; old versions stay in the
registry so eval runs can A/B them. The active template is whichever PROMPTS
points at; eval can target a specific id+version pair.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Type

from pydantic import BaseModel

from .schemas import FollowUpDraft


@dataclass(frozen=True)
class PromptTemplate:
    id: str
    version: int
    description: str
    system: str
    user_template: str          # str.format with named keys
    schema: Type[BaseModel]
    output_format: str = "json"  # "json" | "text"

    def render(self, **kwargs) -> tuple[str, str]:
        return self.system, self.user_template.format(**kwargs)

    @property
    def ref(self) -> str:
        return f"{self.id}@v{self.version}"


# ---------- Follow-up draft ----------
_FOLLOWUP_USER_V1 = (
    "Context:\n{context}\n\n"
    "Write a single JSON object with three string fields:\n"
    '  whatsapp_text: 3-5 line WhatsApp follow-up under 70 words, polite Indian English,\n'
    "    no emojis, signed off with the sender's first name only, no 'Subject:' line.\n"
    "  email_subject: a single line subject (no 'Re:' prefix).\n"
    "  email_body: 2 short paragraphs (110-180 words total), signed off with the\n"
    "    sender's name + 'Revora', no emojis, Indian English.\n"
    "Use ₹ for currency. Reference the proposal title or industry briefly so each\n"
    "draft feels specific. Output the JSON object only — no prose, no fences."
)

_FOLLOWUP_SYSTEM_V1 = (
    "You draft polite, warm B2B follow-ups for an Indian service agency. "
    "You return a single JSON object matching the requested schema. "
    "You never invent facts not in the context (no fake calls, meetings, or commitments). "
    "You never include 'as an AI' disclaimers or instructions about yourself."
)


_FOLLOWUP_SYSTEM_V2 = (
    "You draft polite, warm B2B follow-ups for an Indian service agency. "
    "Output strictly a JSON object matching the requested schema — no prose around it, "
    "no code fences, no commentary. "
    "Do not invent past calls, meetings, agreed timelines, or promised features. "
    "Use only facts present in the context. "
    "If a fact is missing, write around it rather than fabricating. "
    "Never include 'as an AI', 'I am an AI', 'as a language model', or self-references."
)


FOLLOWUP_V1 = PromptTemplate(
    id="proposal_followup",
    version=1,
    description="Original single-prompt draft (text → regex parse).",
    system=_FOLLOWUP_SYSTEM_V1,
    user_template=_FOLLOWUP_USER_V1,
    schema=FollowUpDraft,
    output_format="json",
)


FOLLOWUP_V2 = PromptTemplate(
    id="proposal_followup",
    version=2,
    description="Tighter anti-hallucination guardrails; same schema as v1.",
    system=_FOLLOWUP_SYSTEM_V2,
    user_template=_FOLLOWUP_USER_V1,
    schema=FollowUpDraft,
    output_format="json",
)


_FOLLOWUP_USER_V3 = (
    "Context:\n{context}\n\n"
    "Return a single JSON object with these fields:\n"
    '  whatsapp_text: 3-5 line WhatsApp follow-up under 70 words, polite Indian English,\n'
    "    no emojis, signed off with the sender's first name only, no 'Subject:' line.\n"
    "  email_subject: a single line subject (no 'Re:' prefix).\n"
    "  email_body: 2 short paragraphs (110-180 words total), signed off with the\n"
    "    sender's name + 'Revora', no emojis, Indian English.\n"
    "  confidence: a number between 0 and 1 — your honest self-assessment of how well\n"
    "    these drafts fit the context. Low when the context is thin/contradictory;\n"
    "    high when you reference specific facts from the context confidently.\n"
    "Use ₹ for currency. Reference the proposal title or industry briefly so each\n"
    "draft feels specific. Output the JSON object only — no prose, no fences."
)


FOLLOWUP_V3 = PromptTemplate(
    id="proposal_followup",
    version=3,
    description="v2 anti-hallucination + asks for self-reported confidence.",
    system=_FOLLOWUP_SYSTEM_V2,
    user_template=_FOLLOWUP_USER_V3,
    schema=FollowUpDraft,
    output_format="json",
)


# Active template per id. Bump here when promoting a new version.
ACTIVE: dict[str, PromptTemplate] = {
    "proposal_followup": FOLLOWUP_V3,
}

# All versions, addressable by ref ("proposal_followup@v1") — used by eval harness.
ALL: dict[str, PromptTemplate] = {
    t.ref: t for t in (FOLLOWUP_V1, FOLLOWUP_V2, FOLLOWUP_V3)
}


def get(id_: str) -> PromptTemplate:
    return ACTIVE[id_]


def get_ref(ref: str) -> PromptTemplate:
    return ALL[ref]
