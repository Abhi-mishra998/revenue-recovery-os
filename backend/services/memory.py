"""
Per-client derived features. Recomputed (not incrementally patched) from
current state on every relevant action — guarantees the doc never drifts
from reality.

Reads the canonical state (activities, events) and writes one document per
(owner_id, client_id) into the `client_memory` collection.

Used by:
  - UI (Client Detail will surface preferred channel, response cadence)
  - Future personalisation models (training feature)

Performance: rebuild for ONE client is bounded by that client's activity +
event count — typically tens of rows, sub-millisecond. There is no global
rebuild path on purpose.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from statistics import median
from typing import Optional

logger = logging.getLogger(__name__)

OUTCOME_EVENT_TYPES = ("proposal.won", "proposal.lost", "invoice.payment_received")
RESPONSE_WINDOW_DAYS = 14
RESPONSE_PAIR_MAX_DAYS = 30  # ignore deltas longer than this when computing median


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse(iso: Optional[str]) -> Optional[datetime]:
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(iso)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _derive_response_metrics(activities: list[dict]) -> tuple[Optional[float], Optional[float]]:
    """Returns (typical_response_days, response_rate). None when not enough data."""
    activities = sorted(activities, key=lambda a: a.get("created_at") or "")
    outbound = [a for a in activities if a.get("direction") == "outbound"]
    if not outbound:
        return None, None

    deltas: list[float] = []
    answered = 0
    for ob in outbound:
        ob_t = _parse(ob.get("created_at"))
        if not ob_t:
            continue
        # Earliest inbound after this outbound within window
        for ib in activities:
            if ib.get("direction") != "inbound":
                continue
            ib_t = _parse(ib.get("created_at"))
            if not ib_t or ib_t <= ob_t:
                continue
            delta_days = (ib_t - ob_t).total_seconds() / 86400.0
            if delta_days <= RESPONSE_PAIR_MAX_DAYS:
                deltas.append(delta_days)
                if delta_days <= RESPONSE_WINDOW_DAYS:
                    answered += 1
            break  # first inbound only

    typical = round(median(deltas), 2) if deltas else None
    rate = round(answered / len(outbound), 3) if outbound else None
    return typical, rate


async def recompute_client_memory(db, *, owner_id: str, client_id: str) -> dict:
    activities = await db.activities.find(
        {"owner_id": owner_id, "client_id": client_id}, {"_id": 0},
    ).to_list(2000)

    channel_counts: dict[str, int] = {}
    for a in activities:
        if a.get("direction") == "inbound":
            ch = a.get("channel")
            if ch:
                channel_counts[ch] = channel_counts.get(ch, 0) + 1
    channel_preference = max(channel_counts, key=channel_counts.get) if channel_counts else None

    typical, rate = _derive_response_metrics(activities)

    outcomes_cursor = db.events.find(
        {"owner_id": owner_id,
         "metadata.client_id": client_id,
         "event_type": {"$in": list(OUTCOME_EVENT_TYPES)}},
        {"_id": 0},
    ).sort("created_at", -1).limit(10)
    last_outcomes = [
        {"type": e["event_type"], "id": e["entity_id"], "at": e["created_at"]}
        async for e in outcomes_cursor
    ]

    res = await db.client_memory.find_one_and_update(
        {"owner_id": owner_id, "client_id": client_id},
        {
            "$set": {
                "channel_preference": channel_preference,
                "channel_counts": channel_counts,
                "typical_response_days": typical,
                "response_rate": rate,
                "last_outcomes": last_outcomes,
                "updated_at": _now_iso(),
            },
            "$inc": {"recompute_count": 1},
            "$setOnInsert": {
                "id": __import__("uuid").uuid4().__str__(),
                "owner_id": owner_id,
                "client_id": client_id,
            },
        },
        upsert=True,
        return_document=True,
    )
    if res is not None:
        res.pop("_id", None)
    return res or {}


async def get_or_compute_client_memory(db, *, owner_id: str, client_id: str) -> dict:
    """Return cached memory; recompute if missing."""
    doc = await db.client_memory.find_one({"owner_id": owner_id, "client_id": client_id}, {"_id": 0})
    if doc:
        return doc
    return await recompute_client_memory(db, owner_id=owner_id, client_id=client_id)
