"""
import_jobs repo. Stage-based import pipeline storage (parse → map → commit).
Tenant-scoped via RLS (with_user). Postgres only — pre-cutover Mongo path is
not supported because the importer was introduced after the Postgres flip.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from .. import is_postgres, pg
from ._pg_serde import jsonb

_JSON_KEYS = ("headers", "sample_rows", "raw_rows", "stats", "mapping")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(rec) -> Optional[dict]:
    if rec is None:
        return None
    d = dict(rec)
    for k in _JSON_KEYS:
        if isinstance(d.get(k), str):
            try:
                d[k] = json.loads(d[k])
            except Exception:
                pass
    return d


def _require_pg() -> None:
    if not is_postgres():
        raise RuntimeError("import_jobs requires DB_ENGINE=postgres")


async def create(
    owner_id: str,
    *,
    headers: list[str],
    sample_rows: list[dict],
    raw_rows: list[dict],
    stats: dict,
) -> str:
    """Insert a parsed-stage row. Returns file_id."""
    _require_pg()
    file_id = str(uuid.uuid4())
    async with pg.with_user(owner_id) as conn:
        await conn.execute(
            "INSERT INTO import_jobs "
            "(id, owner_id, stage, headers, sample_rows, raw_rows, stats, created_at) "
            "VALUES ($1::uuid, $2::uuid, 'parsed', $3::jsonb, $4::jsonb, $5::jsonb, $6::jsonb, $7)",
            file_id,
            owner_id,
            jsonb(headers),
            jsonb(sample_rows),
            jsonb(raw_rows),
            jsonb(stats),
            _now_iso(),
        )
    return file_id


async def get(file_id: str, owner_id: str) -> Optional[dict]:
    _require_pg()
    async with pg.with_user(owner_id) as conn:
        rec = await conn.fetchrow(
            "SELECT id::text, owner_id::text, stage, target, headers, sample_rows, "
            "raw_rows, stats, mapping, created_at "
            "FROM import_jobs WHERE id = $1::uuid",
            file_id,
        )
    return _row(rec)


async def set_mapping(file_id: str, owner_id: str, *, mapping: dict, target: str) -> None:
    _require_pg()
    async with pg.with_user(owner_id) as conn:
        result = await conn.execute(
            "UPDATE import_jobs SET stage = 'mapped', mapping = $1::jsonb, target = $2 WHERE id = $3::uuid",
            jsonb(mapping),
            target,
            file_id,
        )
    if result.endswith(" 0"):
        raise LookupError(f"import_job {file_id} not found for owner")


async def mark_committed(file_id: str, owner_id: str) -> None:
    _require_pg()
    async with pg.with_user(owner_id) as conn:
        await conn.execute(
            "UPDATE import_jobs SET stage = 'committed' WHERE id = $1::uuid",
            file_id,
        )
