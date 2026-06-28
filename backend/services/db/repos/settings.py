"""settings repo. Singleton row (id='global'). No RLS."""

from __future__ import annotations

from typing import Optional

from .. import is_postgres, pg
from . import _mongo


async def get_global() -> Optional[dict]:
    if is_postgres():
        async with pg.bypass_user() as conn:
            rec = await conn.fetchrow(
                "SELECT id, ai_killswitch, audit_signing_key FROM settings WHERE id = 'global'",
            )
        return dict(rec) if rec else None
    return await _mongo.db().settings.find_one({"id": "global"})


async def set_ai_killswitch(enabled: bool) -> None:
    if is_postgres():
        async with pg.bypass_user() as conn:
            await conn.execute(
                "INSERT INTO settings (id, ai_killswitch) VALUES ('global', $1) "
                "ON CONFLICT (id) DO UPDATE SET ai_killswitch = EXCLUDED.ai_killswitch",
                enabled,
            )
        return
    await _mongo.db().settings.update_one(
        {"id": "global"},
        {"$set": {"ai_killswitch": enabled}, "$setOnInsert": {"id": "global"}},
        upsert=True,
    )


async def set_audit_signing_key(key_b64: str) -> None:
    """Persist an auto-generated key on first start. Idempotent — won't overwrite."""
    if is_postgres():
        async with pg.bypass_user() as conn:
            await conn.execute(
                "INSERT INTO settings (id, audit_signing_key) VALUES ('global', $1) "
                "ON CONFLICT (id) DO UPDATE SET audit_signing_key = "
                "COALESCE(settings.audit_signing_key, EXCLUDED.audit_signing_key)",
                key_b64,
            )
        return
    await _mongo.db().settings.update_one(
        {"id": "global"},
        {"$setOnInsert": {"id": "global", "audit_signing_key": key_b64}},
        upsert=True,
    )
