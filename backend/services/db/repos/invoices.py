"""invoices repo. Tenant-scoped — owner_id required everywhere."""

from __future__ import annotations

from typing import Optional

from .. import is_postgres, pg
from . import _mongo
from ._pg_serde import row_to_dict, rows_to_dicts

_COLS = (
    "id::text",
    "owner_id::text",
    "client_id::text",
    "invoice_no",
    "amount_inr::float8 AS amount_inr",
    "due_date",
    "paid_date",
    "issued_at",
    "notes",
    "created_at",
)
_COLS_SQL = ", ".join(_COLS)


async def list_for_owner(owner_id: str) -> list[dict]:
    if is_postgres():
        async with pg.with_user(owner_id) as conn:
            recs = await conn.fetch(f"SELECT {_COLS_SQL} FROM invoices LIMIT 5000")
        return rows_to_dicts(recs)
    cursor = _mongo.db().invoices.find({"owner_id": owner_id}, {"_id": 0})
    return await cursor.to_list(5000)


async def get_for_owner(invoice_id: str, owner_id: str) -> Optional[dict]:
    if is_postgres():
        async with pg.with_user(owner_id) as conn:
            rec = await conn.fetchrow(f"SELECT {_COLS_SQL} FROM invoices WHERE id = $1::uuid", invoice_id)
        return row_to_dict(rec) if rec else None
    return await _mongo.db().invoices.find_one(
        {"id": invoice_id, "owner_id": owner_id},
        {"_id": 0},
    )


async def list_for_client_and_owner(client_id: str, owner_id: str, limit: int = 500) -> list[dict]:
    if is_postgres():
        async with pg.with_user(owner_id) as conn:
            recs = await conn.fetch(
                f"SELECT {_COLS_SQL} FROM invoices WHERE client_id = $1::uuid LIMIT $2",
                client_id,
                limit,
            )
        return rows_to_dicts(recs)
    cursor = _mongo.db().invoices.find(
        {"client_id": client_id, "owner_id": owner_id},
        {"_id": 0},
    )
    return await cursor.to_list(limit)


async def list_for_dashboard(owner_id: str) -> list[dict]:
    if is_postgres():
        async with pg.with_user(owner_id) as conn:
            recs = await conn.fetch(f"SELECT {_COLS_SQL} FROM invoices LIMIT 10000")
        return rows_to_dicts(recs)
    cursor = _mongo.db().invoices.find({"owner_id": owner_id}, {"_id": 0})
    return await cursor.to_list(10000)


async def insert(doc: dict) -> None:
    if is_postgres():
        async with pg.with_user(doc["owner_id"]) as conn:
            await conn.execute(
                "INSERT INTO invoices (id, owner_id, client_id, invoice_no, amount_inr, due_date, "
                "paid_date, issued_at, notes, created_at) "
                "VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9, $10)",
                doc["id"],
                doc["owner_id"],
                doc["client_id"],
                doc["invoice_no"],
                float(doc["amount_inr"]),
                doc["due_date"],
                doc.get("paid_date"),
                doc.get("issued_at") or doc["created_at"],
                doc.get("notes"),
                doc["created_at"],
            )
        return
    await _mongo.db().invoices.insert_one(dict(doc))


async def update_for_owner(invoice_id: str, owner_id: str, updates: dict) -> bool:
    if not updates:
        return False
    if is_postgres():
        sets, params = _build_set_clause(updates, start_index=3)
        async with pg.with_user(owner_id) as conn:
            res = await conn.execute(
                f"UPDATE invoices SET {sets} WHERE id = $1::uuid AND owner_id = $2::uuid",
                invoice_id,
                owner_id,
                *params,
            )
        return _parse_rowcount(res) > 0
    res = await _mongo.db().invoices.update_one(
        {"id": invoice_id, "owner_id": owner_id},
        {"$set": updates},
    )
    return res.matched_count > 0


async def delete_for_owner(invoice_id: str, owner_id: str) -> int:
    if is_postgres():
        async with pg.with_user(owner_id) as conn:
            res = await conn.execute(
                "DELETE FROM invoices WHERE id = $1::uuid AND owner_id = $2::uuid",
                invoice_id,
                owner_id,
            )
        return _parse_rowcount(res)
    res = await _mongo.db().invoices.delete_one({"id": invoice_id, "owner_id": owner_id})
    return res.deleted_count


_INV_UPDATE_COLS = {"invoice_no", "amount_inr", "due_date", "paid_date", "notes"}


def _build_set_clause(updates: dict, *, start_index: int) -> tuple[str, list]:
    parts: list[str] = []
    params: list = []
    i = start_index
    for k, v in updates.items():
        if k not in _INV_UPDATE_COLS:
            continue
        parts.append(f"{k} = ${i}")
        params.append(float(v) if k == "amount_inr" else v)
        i += 1
    if not parts:
        raise ValueError("no updatable columns in payload")
    return ", ".join(parts), params


def _parse_rowcount(status: str) -> int:
    try:
        return int(status.split()[-1])
    except (ValueError, IndexError):
        return 0
