"""
clients repo. All methods are tenant-scoped — owner_id is required and the
postgres path runs inside with_user(owner_id) so RLS enforces it physically.
"""

from __future__ import annotations

from typing import Optional

from .. import is_postgres, pg
from . import _mongo
from ._pg_serde import row_to_dict, rows_to_dicts

_COLS = (
    "id::text",
    "owner_id::text",
    "company_name",
    "contact_name",
    "email",
    "phone",
    "whatsapp",
    "industry",
    "language",
    "notes",
    "created_at",
)
_COLS_SQL = ", ".join(_COLS)


# ---------- public surface ----------


async def list_for_owner(owner_id: str) -> list[dict]:
    if is_postgres():
        async with pg.with_user(owner_id) as conn:
            recs = await conn.fetch(f"SELECT {_COLS_SQL} FROM clients ORDER BY company_name ASC LIMIT 2000")
        return rows_to_dicts(recs)
    cursor = _mongo.db().clients.find({"owner_id": owner_id}, {"_id": 0}).sort("company_name", 1)
    return await cursor.to_list(2000)


async def get_for_owner(client_id: str, owner_id: str) -> Optional[dict]:
    if is_postgres():
        async with pg.with_user(owner_id) as conn:
            rec = await conn.fetchrow(f"SELECT {_COLS_SQL} FROM clients WHERE id = $1::uuid", client_id)
        return row_to_dict(rec) if rec else None
    return await _mongo.db().clients.find_one({"id": client_id, "owner_id": owner_id}, {"_id": 0})


async def exists_for_owner(client_id: str, owner_id: str) -> bool:
    if is_postgres():
        async with pg.with_user(owner_id) as conn:
            v = await conn.fetchval("SELECT 1 FROM clients WHERE id = $1::uuid LIMIT 1", client_id)
        return v is not None
    return (
        await _mongo.db().clients.find_one(
            {"id": client_id, "owner_id": owner_id},
            {"_id": 1},
        )
        is not None
    )


async def insert(doc: dict) -> None:
    if is_postgres():
        async with pg.with_user(doc["owner_id"]) as conn:
            await conn.execute(
                "INSERT INTO clients (id, owner_id, company_name, contact_name, email, phone, whatsapp, "
                "industry, language, notes, created_at) "
                "VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11)",
                doc["id"],
                doc["owner_id"],
                doc["company_name"],
                doc["contact_name"],
                doc.get("email"),
                doc.get("phone"),
                doc.get("whatsapp"),
                doc.get("industry"),
                doc.get("language") or "English",
                doc.get("notes"),
                doc["created_at"],
            )
        return
    await _mongo.db().clients.insert_one(dict(doc))


async def update_for_owner(client_id: str, owner_id: str, updates: dict) -> bool:
    """Returns True if a row was updated, False otherwise."""
    if not updates:
        return False
    if is_postgres():
        sets, params = _build_set_clause(updates, start_index=3)
        async with pg.with_user(owner_id) as conn:
            res = await conn.execute(
                f"UPDATE clients SET {sets} WHERE id = $1::uuid AND owner_id = $2::uuid",
                client_id,
                owner_id,
                *params,
            )
        return _parse_rowcount(res) > 0
    res = await _mongo.db().clients.update_one(
        {"id": client_id, "owner_id": owner_id},
        {"$set": updates},
    )
    return res.matched_count > 0


async def delete_for_owner(client_id: str, owner_id: str) -> int:
    if is_postgres():
        async with pg.with_user(owner_id) as conn:
            res = await conn.execute(
                "DELETE FROM clients WHERE id = $1::uuid AND owner_id = $2::uuid",
                client_id,
                owner_id,
            )
        return _parse_rowcount(res)
    res = await _mongo.db().clients.delete_one({"id": client_id, "owner_id": owner_id})
    return res.deleted_count


# ---------- internal helpers ----------

_CLIENT_UPDATE_COLS = {
    "company_name",
    "contact_name",
    "email",
    "phone",
    "whatsapp",
    "industry",
    "language",
    "notes",
}


def _build_set_clause(updates: dict, *, start_index: int) -> tuple[str, list]:
    """Build a parameterised SET clause whitelisted against known columns."""
    parts: list[str] = []
    params: list = []
    i = start_index
    for k, v in updates.items():
        if k not in _CLIENT_UPDATE_COLS:
            continue  # silently drop unknown fields — Pydantic should have rejected first
        parts.append(f"{k} = ${i}")
        params.append(v)
        i += 1
    if not parts:
        raise ValueError("no updatable columns in payload")
    return ", ".join(parts), params


def _parse_rowcount(status: str) -> int:
    """asyncpg execute() returns strings like 'DELETE 1' or 'UPDATE 0'."""
    try:
        return int(status.split()[-1])
    except (ValueError, IndexError):
        return 0
