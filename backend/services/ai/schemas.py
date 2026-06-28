"""
Structured outputs from the LLM. Each output type has a Pydantic schema —
the validator/retry layer in client.generate_json uses these to reject bad
output and steer the model on retry.

Adding a new structured output: define a Pydantic model here, point a
PromptTemplate.schema at it.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class FollowUpDraft(BaseModel):
    """One LLM call produces both channels. Bounded sizes — runaway output
    is rejected before it reaches the user."""
    whatsapp_text: str = Field(..., min_length=10, max_length=600,
                                description="3-5 line message, under 70 words, Indian English, no emojis.")
    email_subject: str = Field(..., min_length=3, max_length=140,
                                description="Single line subject. No 'Re:' prefixes from the model.")
    email_body: str = Field(..., min_length=20, max_length=2200,
                             description="2 short paragraphs, 110-180 words, signed off.")
