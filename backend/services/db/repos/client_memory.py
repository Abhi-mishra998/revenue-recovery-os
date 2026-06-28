"""client_memory repo. Singleton per (owner_id, client_id)."""

from __future__ import annotations

import uuid
from typing import Optional

from .. import is_postgres, pg
from . import _mongo
from ._pg_serde import jsonb, row_to_dict

_COLS = (
    "id::text",
    "owner_id::text",
    "client_id::text",
    "channel_preference",
    "channel_counts",
    "typical_response_days::float8 AS typical_response_days",
    "response_rate::float8 AS response_rate",
    "last_outcomes",
    "recompute_count",
    "updated_at",
)
_COLS_SQL = ", ".join(_COLS)


async def list_for_owner(owner_id: str, limit: int = 10000) -> list[dict]:
    """Used by /me/data export."""
    if is_postgres():
        async with pg.with_user(owner_id) as conn:
            recs = await conn.fetch(f"SELECT {_COLS_SQL} FROM client_memory LIMIT $1", limit)
        return [row_to_dict(r) for r in recs]
    cursor = _mongo.db().client_memory.find({"owner_id": owner_id}, {"_id": 0}).limit(limit)
    return await cursor.to_list(limit)


async def get(owner_id: str, client_id: str) -> Optional[dict]:
    if is_postgres():
        async with pg.with_user(owner_id) as conn:
            rec = await conn.fetchrow(
                f"SELECT {_COLS_SQL} FROM client_memory WHERE client_id = $1::uuid",
                client_id,
            )
        return row_to_dict(rec) if rec else None
    return await _mongo.db().client_memory.find_one(
        {"owner_id": owner_id, "client_id": client_id},
        {"_id": 0},
    )


async def upsert(owner_id: str, client_id: str, fields: dict) -> dict:
    """Atomic upsert. Returns the row after the update."""
    if is_postgres():
        async with pg.with_user(owner_id) as conn:
            row_id = str(uuid.uuid4())
            rec = await conn.fetchrow(
                f"""
                INSERT INTO client_memory (id, owner_id, client_id,
                    channel_preference, channel_counts, typical_response_days,
                    response_rate, last_outcomes, recompute_count, updated_at)
                VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5::jsonb, $6, $7, $8::jsonb, 1, $9)
                ON CONFLICT (owner_id, client_id) DO UPDATE SET
                    channel_preference    = EXCLUDED.channel_preference,
                    channel_counts        = EXCLUDED.channel_counts,
                    typical_response_days = EXCLUDED.typical_response_days,
                    response_rate         = EXCLUDED.response_rate,
                    last_outcomes         = EXCLUDED.last_outcomes,
                    recompute_count       = client_memory.recompute_count + 1,
                    updated_at            = EXCLUDED.updated_at
                RETURNING {_COLS_SQL}
                """,
                row_id,
                owner_id,
                client_id,
                fields.get("channel_preference"),
                jsonb(fields.get("channel_counts") or {}),
                fields.get("typical_response_days"),
                fields.get("response_rate"),
                jsonb(fields.get("last_outcomes") or []),
                fields.get("updated_at"),
            )
        return row_to_dict(rec) or {}
    res = await _mongo.db().client_memory.find_one_and_update(
        {"owner_id": owner_id, "client_id": client_id},
        {
            "$set": {
                "channel_preference": fields.get("channel_preference"),
                "channel_counts": fields.get("channel_counts") or {},
                "typical_response_days": fields.get("typical_response_days"),
                "response_rate": fields.get("response_rate"),
                "last_outcomes": fields.get("last_outcomes") or [],
                "updated_at": fields.get("updated_at"),
            },
            "$inc": {"recompute_count": 1},
            "$setOnInsert": {
                "id": str(uuid.uuid4()),
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


async def delete_for_client(owner_id: str, client_id: str) -> int:
    if is_postgres():
        async with pg.with_user(owner_id) as conn:
            res = await conn.execute(
                "DELETE FROM client_memory WHERE client_id = $1::uuid",
                client_id,
            )
        try:
            return int(res.split()[-1])
        except (ValueError, IndexError):
            return 0
    res = await _mongo.db().client_memory.delete_many(
        {"owner_id": owner_id, "client_id": client_id},
    )
    return res.deleted_count
