"""
asyncpg pool + RLS-aware session helper.

Lifecycle:
  init_pool()   — call from FastAPI startup when DB_ENGINE=postgres
  close_pool()  — call from FastAPI shutdown
  pool()        — accessor; raises if not initialised

RLS-aware request scoping:
  async with with_user(user_id) as conn:
      rows = await conn.fetch("SELECT * FROM clients WHERE …")
  Inside the block, every statement runs in a transaction with
  app.current_user_id SET LOCAL, so RLS policies on tenant tables fire.
  Admin paths use bypass_user() which sets a marker SETting that policies
  treat as 'no tenant scope' (used for audit_log reads, the migration
  script, and chain verify).
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def init_pool() -> asyncpg.Pool:
    """Create the global pool. Idempotent — safe to call twice."""
    global _pool
    if _pool is not None:
        return _pool
    dsn = os.environ.get("POSTGRES_URL")
    if not dsn:
        raise RuntimeError("POSTGRES_URL is required when DB_ENGINE=postgres")
    _pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=int(os.environ.get("PG_POOL_MIN", "1")),
        max_size=int(os.environ.get("PG_POOL_MAX", "10")),
        command_timeout=30,
    )
    logger.info("postgres pool initialised (max_size=%s)", _pool.get_max_size())
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("postgres pool closed")


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("postgres pool not initialised — call init_pool first")
    return _pool


_APP_ROLE = "revora_app"


@asynccontextmanager
async def with_user(user_id: str):
    """
    Acquire a connection and pin app.current_user_id for the duration of a
    single transaction. RLS policies on tenant tables read this setting to
    decide visibility.

    Critical: also SET LOCAL ROLE revora_app — the connecting role is a
    superuser (postgres default) which bypasses RLS unconditionally. Dropping
    to revora_app for the transaction body makes the policies actually fire.
    """
    async with pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL ROLE {_APP_ROLE}")
            await conn.execute("SELECT set_config('app.current_user_id', $1, true)", str(user_id))
            yield conn


@asynccontextmanager
async def bypass_user():
    """
    Acquire a connection without setting app.current_user_id — for admin
    paths (audit log reads, migration, chain verify). RLS policies that
    require the setting will block reads, so use only on tables without
    RLS (audit_log, users, settings).
    """
    async with pool().acquire() as conn:
        async with conn.transaction():
            yield conn
