"""
events repo. Append-only product analytics stream. Some reads filter on
metadata.client_id — natural in Mongo, jsonb path in Postgres.
"""
from __future__ import annotations

from typing import Optional

from .. import is_postgres, pg
from . import _mongo
from ._pg_serde import jsonb, rows_to_dicts


_COLS = ("id::text", "owner_id::text", "event_type", "entity_type", "entity_id::text",
         "prior_value", "new_value", "metadata", "source", "created_at")
_COLS_SQL = ", ".join(_COLS)


async def insert(doc: dict) -> None:
    if is_postgres():
        async with pg.with_user(doc["owner_id"]) as conn:
            await conn.execute(
                "INSERT INTO events (id, owner_id, event_type, entity_type, entity_id, "
                "prior_value, new_value, metadata, source, created_at) "
                "VALUES ($1::uuid, $2::uuid, $3, $4, $5::uuid, $6::jsonb, $7::jsonb, $8::jsonb, $9, $10)",
                doc["id"], doc["owner_id"], doc["event_type"],
                doc["entity_type"], doc["entity_id"],
                jsonb(doc.get("prior_value")), jsonb(doc.get("new_value")),
                jsonb(doc.get("metadata") or {}),
                doc.get("source", "system"), doc["created_at"],
            )
        return
    await _mongo.db().events.insert_one(dict(doc))


async def list_filtered(owner_id: str, *, entity_type: Optional[str] = None,
                         entity_id: Optional[str] = None,
                         event_type: Optional[str] = None,
                         limit: int = 200) -> list[dict]:
    if is_postgres():
        clauses, params = [], []
        if entity_type: clauses.append(f"entity_type = ${len(params)+1}"); params.append(entity_type)
        if entity_id:   clauses.append(f"entity_id = ${len(params)+1}::uuid"); params.append(entity_id)
        if event_type:  clauses.append(f"event_type = ${len(params)+1}"); params.append(event_type)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        sql = f"SELECT {_COLS_SQL} FROM events{where} ORDER BY created_at DESC LIMIT ${len(params)}"
        async with pg.with_user(owner_id) as conn:
            recs = await conn.fetch(sql, *params)
        return rows_to_dicts(recs)
    q: dict = {"owner_id": owner_id}
    if entity_type: q["entity_type"] = entity_type
    if entity_id:   q["entity_id"] = entity_id
    if event_type:  q["event_type"] = event_type
    cursor = _mongo.db().events.find(q, {"_id": 0}).sort("created_at", -1).limit(limit)
    return await cursor.to_list(limit)


async def list_outcomes_for_client(owner_id: str, client_id: str,
                                    types: tuple[str, ...], limit: int = 10) -> list[dict]:
    """Used by client_memory.recompute. Filters events by metadata.client_id."""
    if is_postgres():
        async with pg.with_user(owner_id) as conn:
            recs = await conn.fetch(
                f"SELECT {_COLS_SQL} FROM events "
                f"WHERE event_type = ANY($1::text[]) AND metadata->>'client_id' = $2 "
                f"ORDER BY created_at DESC LIMIT $3",
                list(types), client_id, limit,
            )
        return rows_to_dicts(recs)
    cursor = _mongo.db().events.find(
        {"owner_id": owner_id,
         "metadata.client_id": client_id,
         "event_type": {"$in": list(types)}},
        {"_id": 0},
    ).sort("created_at", -1).limit(limit)
    return await cursor.to_list(limit)
