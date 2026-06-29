"""
Tiered model router.

Simple follow-up drafts go to the cheap tier (Gemini Flash by default).
Frontier tier (Claude Sonnet / GPT-4o) is reserved for cases where the
extra cost is justified — large-ticket proposals, retry after a failed
attempt, or an explicit override.

Routing table is defined in code (sensible defaults) and overridable per
deployment via env vars:

  AI_ROUTE_<TASK>_<TIER>_PROVIDER
  AI_ROUTE_<TASK>_<TIER>_MODEL

e.g. AI_ROUTE_PROPOSAL_FOLLOWUP_COMPLEX_MODEL=claude-sonnet-4-6
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Optional


class Tier(StrEnum):
    SIMPLE = "simple"
    COMPLEX = "complex"


@dataclass(frozen=True)
class ModelChoice:
    tier: Tier
    provider: str
    model: str

    @property
    def ref(self) -> str:
        return f"{self.tier.value}:{self.provider}/{self.model}"


@dataclass
class RouteSignals:
    task: str = "proposal_followup"
    value_inr: Optional[float] = None
    previous_attempt_failed: bool = False
    override_tier: Optional[Tier] = None


# Default routing table. (task, tier) -> ModelChoice
#
# Production default is Claude Haiku 4.5 (both tiers) because:
#   1. The emergent_* providers depend on the private `emergentintegrations`
#      wheel which isn't installable on Render / public deploy targets, so
#      they fail with ModuleNotFoundError at runtime there.
#   2. Haiku is cheap (~$1/M input, $5/M output) — keeping COMPLEX on Haiku
#      avoids accidental Sonnet 4.6 spend on the (rare) >₹50L proposal path.
#
# Env overrides still work — set AI_ROUTE_PROPOSAL_FOLLOWUP_{SIMPLE,COMPLEX}_
# {PROVIDER,MODEL} on a deploy that has emergent_* available and you can flip
# back. CI matrix uses these env overrides to test alternate providers.
_DEFAULTS: dict[tuple[str, Tier], ModelChoice] = {
    ("proposal_followup", Tier.SIMPLE): ModelChoice(
        Tier.SIMPLE,
        "anthropic",
        "claude-haiku-4-5-20251001",
    ),
    ("proposal_followup", Tier.COMPLEX): ModelChoice(
        Tier.COMPLEX,
        "anthropic",
        "claude-haiku-4-5-20251001",
    ),
}

# Value above which a proposal qualifies for the frontier tier by default.
# ₹50 lakh — premium-segment dealmaking, worth the extra LLM cost.
HIGH_VALUE_THRESHOLD_INR = 50_00_000


def _env_override(task: str, tier: Tier, default: ModelChoice) -> ModelChoice:
    prefix = f"AI_ROUTE_{task.upper()}_{tier.value.upper()}"
    provider = os.environ.get(f"{prefix}_PROVIDER") or default.provider
    model = os.environ.get(f"{prefix}_MODEL") or default.model
    return ModelChoice(tier=tier, provider=provider, model=model)


def pick_tier(signals: RouteSignals) -> Tier:
    if signals.override_tier:
        return signals.override_tier
    if signals.previous_attempt_failed:
        return Tier.COMPLEX
    if signals.value_inr is not None and signals.value_inr >= HIGH_VALUE_THRESHOLD_INR:
        return Tier.COMPLEX
    return Tier.SIMPLE


def route(signals: RouteSignals) -> ModelChoice:
    tier = pick_tier(signals)
    key = (signals.task, tier)
    base = _DEFAULTS.get(key) or _DEFAULTS[("proposal_followup", tier)]
    return _env_override(signals.task, tier, base)
