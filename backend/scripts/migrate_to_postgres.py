#!/usr/bin/env python3
"""
One-shot Mongo → Postgres migrator for Revora.

  python scripts/migrate_to_postgres.py --dry-run    # counts only, no writes
  python scripts/migrate_to_postgres.py              # copy everything
  python scripts/migrate_to_postgres.py --verify-only  # just count + chain check

Reads MONGO_URL + DB_NAME for the source; POSTGRES_URL for the target. The
Postgres schema (backend/db/sql/0001_initial.sql) must already be applied.

Order:
  users → clients → proposals, invoices, activities →
  followups → events → client_memory → audit_log (in seq order!) → settings.

Verification (always runs unless --no-verify):
  - per-table row counts match
  - audit chain on Postgres re-walked end-to-end; verify_chain ok=True
    (uses the same key loaded from env or settings — chain stays valid).

Idempotent: each insert uses ON CONFLICT DO NOTHING on the primary key, so a
half-finished run can be re-run without duplicates. Source DB is never modified.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

import asyncpg                                                    # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient                # noqa: E402

# Late imports so DB_ENGINE doesn't matter to the script — we explicitly
# bridge the two engines here.
from services.audit import load_signing_key, verify_chain         # noqa: E402


# Order matters — FK targets first.
TABLES = (
    "users",
    "clients",
    "proposals",
    "invoices",
    "activities",
    "followups",
    "events",
    "client_memory",
    "audit_log",
    "settings",
)


def _j(v):
    return json.dumps(v, default=str) if v is not None else None


# Per-table INSERTs. ON CONFLICT DO NOTHING on the primary key so re-runs are safe.
INSERT_SQL: dict[str, str] = {
    "users":
        "INSERT INTO users (id, email, name, auth_provider, password_hash, token_version, created_at) "
        "VALUES ($1::uuid, $2, $3, $4, $5, $6, $7) ON CONFLICT (id) DO NOTHING",
    "clients":
        "INSERT INTO clients (id, owner_id, company_name, contact_name, email, phone, whatsapp, "
        "industry, language, notes, created_at) "
        "VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11) ON CONFLICT (id) DO NOTHING",
    "proposals":
        "INSERT INTO proposals (id, owner_id, client_id, title, value_inr, sent_date, "
        "last_contact_date, stage, outcome_at, notes, created_at) "
        "VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9, $10, $11) ON CONFLICT (id) DO NOTHING",
    "invoices":
        "INSERT INTO invoices (id, owner_id, client_id, invoice_no, amount_inr, due_date, paid_date, "
        "issued_at, notes, created_at) "
        "VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9, $10) ON CONFLICT (id) DO NOTHING",
    "activities":
        "INSERT INTO activities (id, owner_id, client_id, related_type, related_id, channel, "
        "direction, summary, created_at) "
        "VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9) ON CONFLICT (id) DO NOTHING",
    "followups":
        "INSERT INTO followups (id, owner_id, proposal_id, client_id, generation_id, channel, "
        "draft_text, context, prompt_ref, route_ref, confidence, latency_ms, created_at) "
        "VALUES ($1::uuid, $2::uuid, $3::uuid, $4::uuid, $5::uuid, $6, $7, $8::jsonb, $9, $10, $11, $12, $13) "
        "ON CONFLICT (id) DO NOTHING",
    "events":
        "INSERT INTO events (id, owner_id, event_type, entity_type, entity_id, prior_value, "
        "new_value, metadata, source, created_at) "
        "VALUES ($1::uuid, $2::uuid, $3, $4, $5::uuid, $6::jsonb, $7::jsonb, $8::jsonb, $9, $10) "
        "ON CONFLICT (id) DO NOTHING",
    "client_memory":
        "INSERT INTO client_memory (id, owner_id, client_id, channel_preference, channel_counts, "
        "typical_response_days, response_rate, last_outcomes, recompute_count, updated_at) "
        "VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5::jsonb, $6, $7, $8::jsonb, $9, $10) "
        "ON CONFLICT (owner_id, client_id) DO NOTHING",
    "audit_log":
        "INSERT INTO audit_log (id, seq, actor_id, actor_email, action, resource_type, resource_id, "
        "payload_hash, prev_hash, record_hash, signature, public_key_fp, timestamp) "
        "VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13) ON CONFLICT (seq) DO NOTHING",
    "settings":
        "INSERT INTO settings (id, ai_killswitch, audit_signing_key) "
        "VALUES ($1, $2, $3) ON CONFLICT (id) DO NOTHING",
}


def row_to_params(table: str, doc: dict):
    """Bind a mongo doc to the positional params for the table's INSERT SQL."""
    if table == "users":
        return (doc["id"], doc["email"], doc.get("name", ""),
                doc.get("auth_provider", "email"), doc.get("password_hash"),
                int(doc.get("token_version", 0)), doc["created_at"])
    if table == "clients":
        return (doc["id"], doc["owner_id"], doc["company_name"], doc["contact_name"],
                doc.get("email"), doc.get("phone"), doc.get("whatsapp"), doc.get("industry"),
                doc.get("language") or "English", doc.get("notes"), doc["created_at"])
    if table == "proposals":
        return (doc["id"], doc["owner_id"], doc["client_id"], doc["title"],
                float(doc["value_inr"]), doc["sent_date"], doc["last_contact_date"],
                doc.get("stage", "sent"), doc.get("outcome_at"), doc.get("notes"), doc["created_at"])
    if table == "invoices":
        return (doc["id"], doc["owner_id"], doc["client_id"], doc["invoice_no"],
                float(doc["amount_inr"]), doc["due_date"], doc.get("paid_date"),
                doc.get("issued_at") or doc["created_at"], doc.get("notes"), doc["created_at"])
    if table == "activities":
        return (doc["id"], doc["owner_id"], doc["client_id"],
                doc.get("related_type"), doc.get("related_id") or None,
                doc["channel"], doc.get("direction", "outbound"),
                doc["summary"], doc["created_at"])
    if table == "followups":
        return (doc["id"], doc["owner_id"], doc["proposal_id"], doc["client_id"],
                doc.get("generation_id") or doc["id"],
                doc["channel"], doc["draft_text"],
                _j(doc.get("context") or {}),
                doc.get("prompt_ref"), doc.get("route_ref"),
                doc.get("confidence"), doc.get("latency_ms"), doc["created_at"])
    if table == "events":
        return (doc["id"], doc["owner_id"], doc["event_type"], doc["entity_type"],
                doc["entity_id"], _j(doc.get("prior_value")), _j(doc.get("new_value")),
                _j(doc.get("metadata") or {}), doc.get("source", "system"), doc["created_at"])
    if table == "client_memory":
        return (doc["id"], doc["owner_id"], doc["client_id"],
                doc.get("channel_preference"),
                _j(doc.get("channel_counts") or {}),
                doc.get("typical_response_days"),
                doc.get("response_rate"),
                _j(doc.get("last_outcomes") or []),
                int(doc.get("recompute_count") or 0),
                doc.get("updated_at") or doc.get("created_at") or "")
    if table == "audit_log":
        return (doc["id"], int(doc["seq"]), doc["actor_id"], doc["actor_email"],
                doc["action"], doc.get("resource_type"), doc.get("resource_id"),
                doc["payload_hash"], doc["prev_hash"], doc["record_hash"],
                doc["signature"], doc["public_key_fp"], doc["timestamp"])
    if table == "settings":
        return (doc["id"], bool(doc.get("ai_killswitch", False)),
                doc.get("audit_signing_key"))
    raise ValueError(f"unknown table: {table}")


async def fetch_mongo(mdb, collection: str, *, batch_size: int = 1000):
    cursor = mdb[collection].find({}, {"_id": 0})
    if collection == "audit_log":
        cursor = cursor.sort("seq", 1)
    while True:
        batch = await cursor.to_list(batch_size)
        if not batch:
            break
        for doc in batch:
            yield doc


async def migrate(*, dry_run: bool) -> dict:
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    pg_url = os.environ["POSTGRES_URL"]

    mclient = AsyncIOMotorClient(mongo_url)
    mdb = mclient[db_name]
    pg = await asyncpg.create_pool(dsn=pg_url, min_size=1, max_size=4)

    summary: dict[str, dict] = {}
    try:
        async with pg.acquire() as conn:
            for table in TABLES:
                mongo_count = await mdb[table].count_documents({})
                if dry_run:
                    pg_count = await conn.fetchval(f"SELECT count(*) FROM {table}")
                    summary[table] = {"mongo": mongo_count, "pg_before": int(pg_count), "inserted": 0}
                    print(f"[dry-run] {table:14s}  mongo={mongo_count:6d}  pg_before={int(pg_count):6d}")
                    continue

                inserted = 0
                pg_before = int(await conn.fetchval(f"SELECT count(*) FROM {table}"))
                async with conn.transaction():
                    async for doc in fetch_mongo(mdb, table):
                        params = row_to_params(table, doc)
                        await conn.execute(INSERT_SQL[table], *params)
                        inserted += 1
                pg_after = int(await conn.fetchval(f"SELECT count(*) FROM {table}"))
                summary[table] = {
                    "mongo": mongo_count, "pg_before": pg_before,
                    "pg_after": pg_after, "inserted": inserted,
                }
                print(f"{table:14s}  mongo={mongo_count:6d}  pg_after={pg_after:6d}  inserted={inserted}")
    finally:
        await pg.close()
        mclient.close()

    return summary


async def verify(summary: dict | None = None) -> bool:
    """Compare per-table counts + re-walk the audit chain on Postgres."""
    pg_url = os.environ["POSTGRES_URL"]
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]

    mclient = AsyncIOMotorClient(mongo_url)
    mdb = mclient[db_name]
    pg = await asyncpg.create_pool(dsn=pg_url, min_size=1, max_size=2)
    ok = True
    try:
        async with pg.acquire() as conn:
            print("\n--- count verification ---")
            for table in TABLES:
                mc = await mdb[table].count_documents({})
                pc = int(await conn.fetchval(f"SELECT count(*) FROM {table}"))
                status = "OK" if mc == pc else "MISMATCH"
                print(f"{table:14s}  mongo={mc:6d}  pg={pc:6d}  {status}")
                if mc != pc:
                    ok = False

        # Re-walk the chain on Postgres. The signing key needs to be loaded;
        # load_signing_key() reads from env first, then settings doc (which we
        # just migrated). Force DB_ENGINE=postgres for this verify-only step.
        os.environ["DB_ENGINE"] = "postgres"
        # Lazy-init the global pg pool from services.db.pg so verify_chain works.
        from services.db import pg as pgmod
        await pgmod.init_pool()
        try:
            await load_signing_key()
            chain = await verify_chain()
            print("\n--- audit chain on postgres ---")
            print(f"records_checked={chain['records_checked']}  ok={chain['ok']}  fp={chain['public_key_fp']}")
            if chain.get("issues"):
                for i in chain["issues"][:10]:
                    print(f"  - {i}")
                ok = False
        finally:
            await pgmod.close_pool()
    finally:
        await pg.close()
        mclient.close()

    return ok


async def main():
    p = argparse.ArgumentParser(description="Mongo → Postgres migrator for Revora.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print counts without writing to Postgres.")
    p.add_argument("--verify-only", action="store_true",
                   help="Skip migration; just verify counts + audit chain.")
    p.add_argument("--no-verify", action="store_true",
                   help="Skip verification after migration (not recommended).")
    args = p.parse_args()

    if args.verify_only:
        ok = await verify()
        return 0 if ok else 2

    summary = await migrate(dry_run=args.dry_run)
    if args.dry_run or args.no_verify:
        return 0
    ok = await verify(summary)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
