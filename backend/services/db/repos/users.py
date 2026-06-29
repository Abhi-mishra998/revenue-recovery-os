"""
users repo.

Methods callers actually need:
  get_by_email, get_by_id, insert, bump_token_version,
  set_password_hash, count_for_email
"""

from __future__ import annotations

from typing import Optional

from .. import is_postgres, pg
from . import _mongo
from ._pg_serde import row_to_dict

# ---------- public surface ----------


async def get_by_email(email: str) -> Optional[dict]:
    if is_postgres():
        return await _pg_get_by_email(email)
    return await _mongo.db().users.find_one({"email": email})


async def get_by_id(user_id: str) -> Optional[dict]:
    if is_postgres():
        return await _pg_get_by_id(user_id)
    return await _mongo.db().users.find_one({"id": user_id})


async def insert(doc: dict) -> None:
    if is_postgres():
        return await _pg_insert(doc)
    await _mongo.db().users.insert_one(dict(doc))


async def bump_token_version(user_id: str) -> None:
    if is_postgres():
        return await _pg_bump_token_version(user_id)
    await _mongo.db().users.update_one({"id": user_id}, {"$inc": {"token_version": 1}})


async def set_password_hash(user_id: str, password_hash: str) -> None:
    if is_postgres():
        return await _pg_set_password_hash(user_id, password_hash)
    await _mongo.db().users.update_one({"id": user_id}, {"$set": {"password_hash": password_hash}})


async def get_tenant_profile(user_id: str) -> Optional[dict]:
    """Return the per-user JSON profile written by /api/personalize. Postgres only."""
    if not is_postgres():
        return None
    async with pg.bypass_user() as conn:
        row = await conn.fetchval("SELECT tenant_profile FROM users WHERE id = $1::uuid", user_id)
    if not row:
        return None
    if isinstance(row, str):
        import json

        try:
            return json.loads(row)
        except Exception:
            return None
    return dict(row)


async def get_daily_brief(user_id: str) -> Optional[dict]:
    """Cached Morning Brief jsonb. Postgres only."""
    if not is_postgres():
        return None
    async with pg.bypass_user() as conn:
        row = await conn.fetchval("SELECT daily_brief FROM users WHERE id = $1::uuid", user_id)
    if not row:
        return None
    if isinstance(row, str):
        import json

        try:
            return json.loads(row)
        except Exception:
            return None
    return dict(row)


async def set_daily_brief(user_id: str, brief: dict) -> None:
    if not is_postgres():
        return
    import json

    async with pg.bypass_user() as conn:
        await conn.execute(
            "UPDATE users SET daily_brief = $1::jsonb WHERE id = $2::uuid",
            json.dumps(brief),
            user_id,
        )


async def set_tenant_profile(user_id: str, profile: dict) -> None:
    if not is_postgres():
        return
    import json

    async with pg.bypass_user() as conn:
        await conn.execute(
            "UPDATE users SET tenant_profile = $1::jsonb WHERE id = $2::uuid",
            json.dumps(profile),
            user_id,
        )


async def delete_user_cascade(user_id: str) -> None:
    """Delete the user + every row that references them.
    Postgres: FK ON DELETE CASCADE handles it in one DELETE.
    Mongo: explicit delete_many per collection (no FKs)."""
    if is_postgres():
        async with pg.bypass_user() as conn:
            await conn.execute("DELETE FROM users WHERE id = $1::uuid", user_id)
        return
    mdb = _mongo.db()
    for coll in (
        "client_memory",
        "events",
        "followups",
        "activities",
        "invoices",
        "proposals",
        "clients",
    ):
        await mdb[coll].delete_many({"owner_id": user_id})
    await mdb.users.delete_one({"id": user_id})


# ---------- postgres impls (admin / cross-tenant — bypass RLS) ----------


async def _pg_get_by_email(email: str) -> Optional[dict]:
    async with pg.bypass_user() as conn:
        rec = await conn.fetchrow(
            "SELECT id::text, email, name, auth_provider, password_hash, token_version, created_at "
            "FROM users WHERE email = $1",
            email,
        )
    return row_to_dict(rec) if rec else None


async def _pg_get_by_id(user_id: str) -> Optional[dict]:
    async with pg.bypass_user() as conn:
        rec = await conn.fetchrow(
            "SELECT id::text, email, name, auth_provider, password_hash, token_version, created_at "
            "FROM users WHERE id = $1::uuid",
            user_id,
        )
    return row_to_dict(rec) if rec else None


async def _pg_insert(doc: dict) -> None:
    async with pg.bypass_user() as conn:
        await conn.execute(
            "INSERT INTO users (id, email, name, auth_provider, password_hash, token_version, created_at) "
            "VALUES ($1::uuid, $2, $3, $4, $5, $6, $7)",
            doc["id"],
            doc["email"],
            doc.get("name", ""),
            doc.get("auth_provider", "email"),
            doc.get("password_hash"),
            int(doc.get("token_version", 0)),
            doc["created_at"],
        )


async def _pg_bump_token_version(user_id: str) -> None:
    async with pg.bypass_user() as conn:
        await conn.execute(
            "UPDATE users SET token_version = token_version + 1 WHERE id = $1::uuid",
            user_id,
        )


async def _pg_set_password_hash(user_id: str, password_hash: str) -> None:
    async with pg.bypass_user() as conn:
        await conn.execute(
            "UPDATE users SET password_hash = $2 WHERE id = $1::uuid",
            user_id,
            password_hash,
        )
