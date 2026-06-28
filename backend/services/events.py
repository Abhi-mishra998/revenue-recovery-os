"""
Append-only event log for product analytics + ML feature engineering.

Distinct from audit.py (which is signed and tamper-evident, for security
forensics) — this collection is denormalised, indexed for query, and freely
readable by tenants.

Append-only by convention: no PATCH/DELETE endpoint exists. If you need to
retract, append a corrective event instead.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .db.repos import events as events_repo

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def emit_event(
    db=None,
    *,
    owner_id: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    prior_value: Any = None,
    new_value: Any = None,
    metadata: Optional[dict] = None,
    source: str = "system",
) -> dict:
    """Insert one event row. Never raises in normal flow — failure is logged,
    not bubbled, because losing one analytics event must not break the user's
    action. (Audit log already gives us hard durability for security claims.)
    The `db` arg is kept for back-compat; the repo dispatches on DB_ENGINE."""
    rec = {
        "id": str(uuid.uuid4()),
        "owner_id": owner_id,
        "event_type": event_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "prior_value": prior_value,
        "new_value": new_value,
        "metadata": metadata or {},
        "source": source,
        "created_at": _now_iso(),
    }
    try:
        await events_repo.insert(rec)
    except Exception:
        logger.exception("emit_event failed (event_type=%s entity_id=%s) — swallowing", event_type, entity_id)
    return rec
