"""
Feature extraction from raw collections into the dict shape consumed by
predict.py. Kept dumb and pure — easy to call from anywhere, easy to mock.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def _days_since(iso: Optional[str]) -> Optional[int]:
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(iso)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - d).days
    except Exception:
        return None


def extract_proposal_features(*, proposal: dict, memory: Optional[dict] = None) -> dict:
    """
    Stable feature names — schemas downstream depend on them. If you add one,
    add it to the schema doc and (eventually) the training set definition.
    """
    memory = memory or {}
    return {
        "stage": proposal.get("stage"),
        "value_inr": float(proposal.get("value_inr") or 0.0),
        "days_silent": _days_since(proposal.get("last_contact_date")),
        "days_since_sent": _days_since(proposal.get("sent_date")),
        "industry": (proposal.get("client_industry") or None),
        "response_rate": memory.get("response_rate"),
        "typical_response_days": memory.get("typical_response_days"),
        "channel_preference": memory.get("channel_preference"),
        "outcome_count": len(memory.get("last_outcomes") or []),
    }
