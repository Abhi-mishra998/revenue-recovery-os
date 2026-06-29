"""
Structured outputs from the LLM. Each output type has a Pydantic schema —
the validator/retry layer in client.generate_json uses these to reject bad
output and steer the model on retry.

Adding a new structured output: define a Pydantic model here, point a
PromptTemplate.schema at it.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class FieldMapping(BaseModel):
    """One column mapping suggestion. source_header is None when the LLM can't
    find a plausible match — UI shows 'unmapped' rather than guessing."""

    target_field: str = Field(..., min_length=1, max_length=64)
    source_header: Optional[str] = Field(default=None, max_length=200)
    confidence: float = Field(..., ge=0.0, le=1.0)


class MappingSuggestion(BaseModel):
    """LLM-proposed column mapping. The endpoint also returns a heuristic
    mapping computed locally; the UI picks whichever the founder confirms."""

    mappings: list[FieldMapping] = Field(..., min_length=1, max_length=32)


class BriefDraft(BaseModel):
    """Morning Brief output. 60-120 words, names up to 3 clients with reasons
    and one-line actions. Bounded sizes so a runaway model can't drown the UI."""

    headline: str = Field(..., min_length=5, max_length=120)
    paragraph: str = Field(..., min_length=40, max_length=900)
    confidence: float = Field(..., ge=0.0, le=1.0)


class FollowUpDraft(BaseModel):
    """One LLM call produces both channels. Bounded sizes — runaway output
    is rejected before it reaches the user."""

    whatsapp_text: str = Field(
        ...,
        min_length=10,
        max_length=600,
        description="3-5 line message, under 70 words, Indian English, no emojis.",
    )
    email_subject: str = Field(
        ...,
        min_length=3,
        max_length=140,
        description="Single line subject. No 'Re:' prefixes from the model.",
    )
    email_body: str = Field(
        ..., min_length=20, max_length=2200, description="2 short paragraphs, 110-180 words, signed off."
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Self-reported 0-1: how well the draft fits the context. "
        "Nullable so v1/v2 outputs (no confidence ask) still validate.",
    )
