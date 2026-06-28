"""
followups repo. Carries the full generation context (jsonb), prompt_ref,
route_ref, confidence, latency_ms, and a vector(1536) column reserved for
future semantic search (currently never written).
"""

from __future__ import annotations

from .. import is_postgres, pg
from . import _mongo
from ._pg_serde import jsonb, rows_to_dicts

_COLS = (
    "id::text",
    "owner_id::text",
    "proposal_id::text",
    "client_id::text",
    "generation_id::text",
    "channel",
    "draft_text",
    "context",
    "prompt_ref",
    "route_ref",
    "confidence::float8 AS confidence",
    "latency_ms",
    "created_at",
)
_COLS_SQL = ", ".join(_COLS)


async def list_for_proposal(proposal_id: str, owner_id: str, limit: int = 100) -> list[dict]:
    if is_postgres():
        async with pg.with_user(owner_id) as conn:
            recs = await conn.fetch(
                f"SELECT {_COLS_SQL} FROM followups "
                f"WHERE proposal_id = $1::uuid ORDER BY created_at DESC LIMIT $2",
                proposal_id,
                limit,
            )
        return rows_to_dicts(recs)
    cursor = (
        _mongo.db()
        .followups.find(
            {"owner_id": owner_id, "proposal_id": proposal_id},
            {"_id": 0},
        )
        .sort("created_at", -1)
        .limit(limit)
    )
    return await cursor.to_list(limit)


async def insert_many(docs: list[dict]) -> None:
    if not docs:
        return
    if is_postgres():
        # all docs in one generation share the same owner_id
        owner_id = docs[0]["owner_id"]
        async with pg.with_user(owner_id) as conn:
            await conn.executemany(
                "INSERT INTO followups (id, owner_id, proposal_id, client_id, generation_id, "
                "channel, draft_text, context, prompt_ref, route_ref, confidence, latency_ms, created_at) "
                "VALUES ($1::uuid, $2::uuid, $3::uuid, $4::uuid, $5::uuid, $6, $7, $8::jsonb, $9, $10, $11, $12, $13)",
                [
                    (
                        d["id"],
                        d["owner_id"],
                        d["proposal_id"],
                        d["client_id"],
                        d["generation_id"],
                        d["channel"],
                        d["draft_text"],
                        jsonb(d.get("context") or {}),
                        d.get("prompt_ref"),
                        d.get("route_ref"),
                        d.get("confidence"),
                        d.get("latency_ms"),
                        d["created_at"],
                    )
                    for d in docs
                ],
            )
        return
    await _mongo.db().followups.insert_many([dict(d) for d in docs])
