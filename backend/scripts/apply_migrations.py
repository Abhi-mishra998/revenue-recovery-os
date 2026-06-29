"""Schema migration runner. Applies every .sql in db/sql/ to the target DB
in lexicographic order. Every migration is idempotent (`IF NOT EXISTS` /
`ON CONFLICT` / role-presence checks) so re-running is safe.

Usage:
    POSTGRES_URL=postgresql://... python -m scripts.apply_migrations
    python -m scripts.apply_migrations --dsn postgresql://...
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

import asyncpg

SQL_DIR = Path(__file__).resolve().parent.parent / "db" / "sql"


async def apply(dsn: str) -> None:
    files = sorted(SQL_DIR.glob("*.sql"))
    if not files:
        raise SystemExit(f"No migrations found in {SQL_DIR}")
    print(f"Connecting to {dsn.split('@')[-1].split('/')[0]} …")
    conn = await asyncpg.connect(dsn, timeout=30)
    try:
        for f in files:
            sql = f.read_text()
            print(f"→ {f.name} ({len(sql)} bytes)")
            await conn.execute(sql)
            print("  ✓ applied")
        # Sanity
        n = await conn.fetchval("SELECT COUNT(*) FROM pg_tables WHERE schemaname='public'")
        print(f"\npublic schema has {n} tables. Migrations complete.")
    finally:
        await conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=os.environ.get("POSTGRES_URL"))
    args = ap.parse_args()
    if not args.dsn:
        raise SystemExit("POSTGRES_URL not set; pass --dsn or export the env var")
    asyncio.run(apply(args.dsn))
