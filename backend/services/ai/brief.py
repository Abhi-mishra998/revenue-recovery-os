"""
Morning Brief — one LLM call per founder per day, schema-validated.

Inputs are the same rows that back /api/today + the founder's tenant_profile
(set via /api/personalize) + each client's memory. Output is a BriefDraft;
the endpoint persists it to users.daily_brief so subsequent reads same-day
short-circuit (no LLM cost).

Template fallback fires when the LLM is unavailable so the dashboard never
shows a blank brief — UI distinguishes the two via the `source` field.
"""

from __future__ import annotations

import logging
from typing import Any

from .client import generate_json
from .schemas import BriefDraft

logger = logging.getLogger(__name__)

BRIEF_SYSTEM = (
    "You write a 60-90 word morning brief for an SMB founder. Tone: calm, "
    "specific, no hype. Always name the clients (verbatim). One reason and "
    "one action per client. Mention ₹ at risk in words ('₹6.2 L'). End with "
    "one reassurance line.\n\n"
    "Return STRICT JSON with EXACTLY these keys — no others, no nesting:\n"
    '  {"headline": "<one short greeting line, ≤120 chars>",\n'
    '   "paragraph": "<60-90 words covering the 3 actions>",\n'
    '   "confidence": <float 0-1 — how solid the brief feels given the inputs>}\n'
    "No prose outside the JSON. No code fences. No `brief` or `brief_content` keys."
)


def _format_actions(actions: list[dict], clients_map: dict) -> str:
    lines = []
    for a in actions[:3]:
        client = clients_map.get(a.get("target_client_id"), {})
        name = client.get("company_name") or a.get("action") or "?"
        why = "; ".join((a.get("why") or [])[:2])
        prob = a.get("close_probability")
        prob_str = f" (close p={prob:.2f})" if isinstance(prob, (int, float)) else ""
        lines.append(
            f"- {name}: action='{a.get('action')}' value=₹{int(a.get('value_inr') or 0):,}"
            f" status={a.get('status')} confidence={(a.get('confidence') or {}).get('label')}"
            f" why={why}{prob_str}"
        )
    return "\n".join(lines) or "- (no open actions today)"


def build_brief_prompt(
    *,
    actions: list[dict],
    clients_map: dict,
    tenant_profile: dict | None,
    founder_name: str,
) -> str:
    profile_line = ""
    if tenant_profile:
        profile_line = (
            f"\nFounder preferences: channel={tenant_profile.get('preferred_channel')}, "
            f"follow_up_days={tenant_profile.get('follow_up_days')}, "
            f"priority={tenant_profile.get('priority')}\n"
        )
    return (
        f"Founder: {founder_name or 'there'}\n"
        f"Top actions today (already ranked by the analytics layer — DO NOT reorder):\n"
        f"{_format_actions(actions, clients_map)}\n"
        f"{profile_line}\n"
        "Write the brief now. 60-90 words. Open with 'Good morning {name}.'"
    )


async def generate_brief(
    *,
    actions: list[dict],
    clients_map: dict,
    tenant_profile: dict | None,
    founder_name: str,
) -> BriefDraft:
    """Schema-validated LLM call. Raises on LLM unavailable/malformed — caller
    catches and falls back to template_fallback()."""
    prompt = build_brief_prompt(
        actions=actions,
        clients_map=clients_map,
        tenant_profile=tenant_profile,
        founder_name=founder_name,
    )
    return await generate_json(
        system=BRIEF_SYSTEM,
        user=prompt,
        schema=BriefDraft,
        max_tokens=400,
    )


def template_fallback(*, actions: list[dict], clients_map: dict, founder_name: str) -> dict[str, Any]:
    """Pure-Python fallback when the LLM is unavailable. Returns the same
    shape as BriefDraft.model_dump() for caller convenience."""
    if not actions:
        return {
            "headline": f"Good morning {founder_name or 'there'}.",
            "paragraph": "Nothing at risk today — your pipeline is quiet. Use the gap to set up next week's follow-ups.",
            "confidence": 0.4,
        }
    total = sum(int(a.get("value_inr") or 0) for a in actions[:3])
    names = []
    for a in actions[:3]:
        c = clients_map.get(a.get("target_client_id"), {})
        names.append(c.get("company_name") or "an unnamed client")
    name_list = ", ".join(names[:-1]) + (f" and {names[-1]}" if len(names) > 1 else names[0])
    paragraph = (
        f"₹{total:,} at risk today across {name_list}. "
        f"Three to act on: {name_list}. "
        "Each row in Do These Today has its reason and a confidence chip — start with the top one."
    )
    return {
        "headline": f"Good morning {founder_name or 'there'}.",
        "paragraph": paragraph,
        "confidence": 0.5,
    }
