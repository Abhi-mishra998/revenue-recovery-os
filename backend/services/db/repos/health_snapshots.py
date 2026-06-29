"""
health_snapshots repo. One snapshot per owner per day (UNIQUE (owner_id,
snapshot_date)). Powers the visibility-score delta arrow and the "What
Changed Since Last Upload" card on Day 3.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from .. import is_postgres, pg
from ._pg_serde import jsonb


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode(rec) -> Optional[dict]:
    if rec is None:
        return None
    d = dict(rec)
    if isinstance(d.get("payload"), str):
        try:
            d["payload"] = json.loads(d["payload"])
        except Exception:
            pass
    return d


def _require_pg() -> None:
    if not is_postgres():
        raise RuntimeError("health_snapshots requires DB_ENGINE=postgres")


def _as_date(d) -> date:
    return d if isinstance(d, date) else date.fromisoformat(str(d))


async def upsert_today(owner_id: str, payload: dict) -> str:
    """One snapshot per owner per UTC date. Conflict updates payload + id stays."""
    _require_pg()
    today = date.today()
    async with pg.with_user(owner_id) as conn:
        rec = await conn.fetchrow(
            "INSERT INTO health_snapshots (id, owner_id, snapshot_date, payload, created_at) "
            "VALUES ($1::uuid, $2::uuid, $3, $4::jsonb, $5) "
            "ON CONFLICT (owner_id, snapshot_date) DO UPDATE SET payload = EXCLUDED.payload "
            "RETURNING id::text",
            str(uuid.uuid4()),
            owner_id,
            today,
            jsonb(payload),
            _now_iso(),
        )
    return rec["id"]


async def latest_before(owner_id: str, before_date) -> Optional[dict]:
    """Returns the most recent snapshot strictly before the given date, or None."""
    _require_pg()
    async with pg.with_user(owner_id) as conn:
        rec = await conn.fetchrow(
            "SELECT id::text, owner_id::text, snapshot_date, payload, created_at "
            "FROM health_snapshots WHERE snapshot_date < $1 "
            "ORDER BY snapshot_date DESC LIMIT 1",
            _as_date(before_date),
        )
    return _decode(rec)


async def get_for_date(owner_id: str, snapshot_date) -> Optional[dict]:
    _require_pg()
    async with pg.with_user(owner_id) as conn:
        rec = await conn.fetchrow(
            "SELECT id::text, owner_id::text, snapshot_date, payload, created_at "
            "FROM health_snapshots WHERE snapshot_date = $1 LIMIT 1",
            _as_date(snapshot_date),
        )
    return _decode(rec)
