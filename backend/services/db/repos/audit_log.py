"""
audit_log repo. No RLS — admin-only at the application layer (require_admin
dep in server.py). Postgres path uses bypass_user (superuser) so the audit
chain stays readable for cross-tenant verify + admin listing.
"""

from __future__ import annotations

from typing import Optional

from .. import is_postgres, pg
from . import _mongo
from ._pg_serde import row_to_dict, rows_to_dicts

_COLS = (
    "id::text",
    "seq",
    "actor_id",
    "actor_email",
    "action",
    "resource_type",
    "resource_id",
    "payload_hash",
    "prev_hash",
    "record_hash",
    "signature",
    "public_key_fp",
    "timestamp",
)
_COLS_SQL = ", ".join(_COLS)


async def latest_seq_and_hash() -> Optional[dict]:
    """Returns the most recent {seq, record_hash} for chain linking, or None."""
    if is_postgres():
        async with pg.bypass_user() as conn:
            rec = await conn.fetchrow(
                "SELECT seq, record_hash FROM audit_log ORDER BY seq DESC LIMIT 1",
            )
        return dict(rec) if rec else None
    return await _mongo.db().audit_log.find_one(
        {},
        sort=[("seq", -1)],
        projection={"record_hash": 1, "seq": 1},
    )


async def insert(rec: dict) -> None:
    if is_postgres():
        async with pg.bypass_user() as conn:
            await conn.execute(
                "INSERT INTO audit_log (id, seq, actor_id, actor_email, action, "
                "resource_type, resource_id, payload_hash, prev_hash, record_hash, "
                "signature, public_key_fp, timestamp) "
                "VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)",
                rec["id"],
                int(rec["seq"]),
                rec["actor_id"],
                rec["actor_email"],
                rec["action"],
                rec.get("resource_type"),
                rec.get("resource_id"),
                rec["payload_hash"],
                rec["prev_hash"],
                rec["record_hash"],
                rec["signature"],
                rec["public_key_fp"],
                rec["timestamp"],
            )
        return
    await _mongo.db().audit_log.insert_one(dict(rec))


async def iter_in_order():
    """Async iterator over the chain in seq-ascending order — for verify."""
    if is_postgres():
        async with pg.bypass_user() as conn:
            async for r in conn.cursor(f"SELECT {_COLS_SQL} FROM audit_log ORDER BY seq ASC"):
                yield row_to_dict(r)
        return
    cursor = _mongo.db().audit_log.find({}, sort=[("seq", 1)])
    async for r in cursor:
        r.pop("_id", None)
        yield r


async def count() -> int:
    if is_postgres():
        async with pg.bypass_user() as conn:
            return int(await conn.fetchval("SELECT count(*) FROM audit_log"))
    return await _mongo.db().audit_log.count_documents({})


async def list_paginated(page: int, page_size: int) -> list[dict]:
    skip = (page - 1) * page_size
    if is_postgres():
        async with pg.bypass_user() as conn:
            recs = await conn.fetch(
                f"SELECT {_COLS_SQL} FROM audit_log ORDER BY seq DESC LIMIT $1 OFFSET $2",
                page_size,
                skip,
            )
        return rows_to_dicts(recs)
    cursor = _mongo.db().audit_log.find({}, {"_id": 0}).sort("seq", -1).skip(skip).limit(page_size)
    return await cursor.to_list(page_size)
