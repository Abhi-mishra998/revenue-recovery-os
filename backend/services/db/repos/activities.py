"""activities repo."""

from __future__ import annotations

from .. import is_postgres, pg
from . import _mongo
from ._pg_serde import rows_to_dicts

_COLS = (
    "id::text",
    "owner_id::text",
    "client_id::text",
    "related_type",
    "related_id::text",
    "channel",
    "direction",
    "summary",
    "created_at",
)
_COLS_SQL = ", ".join(_COLS)


async def list_for_owner(owner_id: str, limit: int = 200) -> list[dict]:
    if is_postgres():
        async with pg.with_user(owner_id) as conn:
            recs = await conn.fetch(
                f"SELECT {_COLS_SQL} FROM activities ORDER BY created_at DESC LIMIT $1",
                limit,
            )
        return rows_to_dicts(recs)
    cursor = (
        _mongo.db().activities.find({"owner_id": owner_id}, {"_id": 0}).sort("created_at", -1).limit(limit)
    )
    return await cursor.to_list(limit)


async def list_for_client_and_owner(client_id: str, owner_id: str, limit: int = 2000) -> list[dict]:
    """Used by client_memory.recompute — needs full per-client history."""
    if is_postgres():
        async with pg.with_user(owner_id) as conn:
            recs = await conn.fetch(
                f"SELECT {_COLS_SQL} FROM activities WHERE client_id = $1::uuid LIMIT $2",
                client_id,
                limit,
            )
        return rows_to_dicts(recs)
    cursor = _mongo.db().activities.find(
        {"owner_id": owner_id, "client_id": client_id},
        {"_id": 0},
    )
    return await cursor.to_list(limit)


async def insert(doc: dict) -> None:
    if is_postgres():
        async with pg.with_user(doc["owner_id"]) as conn:
            await conn.execute(
                "INSERT INTO activities (id, owner_id, client_id, related_type, related_id, "
                "channel, direction, summary, created_at) "
                "VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9)",
                doc["id"],
                doc["owner_id"],
                doc["client_id"],
                doc.get("related_type"),
                _opt_uuid(doc.get("related_id")),
                doc["channel"],
                doc.get("direction", "outbound"),
                doc["summary"],
                doc["created_at"],
            )
        return
    await _mongo.db().activities.insert_one(dict(doc))


def _opt_uuid(v):
    """Avoid asyncpg type coercion of NULLs to text."""
    return v if v else None
