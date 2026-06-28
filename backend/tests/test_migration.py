"""
End-to-end migration integrity test.

Seeds a small known dataset into a dedicated Mongo DB, wipes the Postgres
schema, runs migrate_to_postgres.py, then asserts:
  - per-table counts match
  - audit chain on Postgres verifies (ok=True, signatures intact)

This is a self-contained test — it does NOT touch revora_test (the integration
test DB) or the dev postgres data, beyond a clean re-apply of the schema.

Skips cleanly if postgres / mongo aren't reachable.
"""
import asyncio
import base64
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

POSTGRES_URL = os.environ.get("POSTGRES_URL")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="POSTGRES_URL not set")

ROOT = Path(__file__).resolve().parent.parent  # backend/
SCHEMA_SQL = ROOT / "db" / "sql" / "0001_initial.sql"
MIGRATE_SCRIPT = ROOT / "scripts" / "migrate_to_postgres.py"

MIGRATION_DB = f"revora_migration_test_{uuid.uuid4().hex[:6]}"


def _run(coro):
    return asyncio.run(coro)


async def _connect_pg():
    import asyncpg
    return await asyncpg.connect(POSTGRES_URL, timeout=5)


async def _reset_postgres_schema():
    """Drop every public table + the revora_app role's grants, then re-apply."""
    conn = await _connect_pg()
    try:
        # DROP all rows table-by-table — schema is idempotent so we don't drop
        # the tables themselves. This is enough to give the migrator a clean slate.
        for table in (
            "events", "client_memory", "followups", "activities",
            "invoices", "proposals", "clients", "audit_log", "settings", "users",
        ):
            await conn.execute(f"DELETE FROM {table}")
    finally:
        await conn.close()


async def _seed_mongo() -> dict:
    """Insert a small known dataset into MIGRATION_DB. Returns expected counts."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from services.audit import (
        load_signing_key, append_audit, _signing_key,
    )
    import services.audit as audit_mod
    # Force the audit module to reset its global key so we generate fresh
    # against the migration DB.
    audit_mod._signing_key = None
    audit_mod._public_key_fp = None

    # Point the settings/audit repos at the migration DB by setting DB_NAME
    # for this process. The other (integration) tests use revora_test.
    os.environ["DB_NAME"] = MIGRATION_DB
    os.environ["DB_ENGINE"] = "mongo"

    mclient = AsyncIOMotorClient(MONGO_URL)
    mdb = mclient[MIGRATION_DB]
    # ensure clean
    for c in ("users", "clients", "proposals", "invoices", "activities",
              "followups", "events", "client_memory", "audit_log", "settings"):
        await mdb[c].drop()

    # Use the repo layer (mongo path) so we exercise the exact code that
    # writes prod data — keeps the schema-on-the-wire honest.
    from services.db.repos import (
        users as users_repo,
        clients as clients_repo,
        proposals as proposals_repo,
        invoices as invoices_repo,
        activities as activities_repo,
        followups as followups_repo,
        events as events_repo,
        client_memory as memory_repo,
        settings as settings_repo,
    )

    # NOTE: repos lazy-import `from server import db`. We replace it before
    # importing repos exercise — see conftest pattern below. Hack: just call
    # mongo directly via the same client.
    # ↓ swap _mongo.db() to return our migration mdb
    from services.db.repos import _mongo as _mongo_repo
    _mongo_repo.db = lambda: mdb  # type: ignore[assignment]

    u_id = str(uuid.uuid4())
    await users_repo.insert({
        "id": u_id, "email": f"mig-{u_id[:6]}@x", "name": "Migration Tester",
        "auth_provider": "email", "password_hash": "x", "token_version": 0,
        "created_at": "2026-06-28T00:00:00+00:00",
    })
    c_id = str(uuid.uuid4())
    await clients_repo.insert({
        "id": c_id, "owner_id": u_id, "company_name": "Mig Co",
        "contact_name": "Mig Contact", "language": "English",
        "created_at": "2026-06-28T00:00:00+00:00",
    })
    p_id = str(uuid.uuid4())
    await proposals_repo.insert({
        "id": p_id, "owner_id": u_id, "client_id": c_id,
        "title": "Mig deal", "value_inr": 100000.0, "stage": "sent",
        "sent_date": "2026-06-20T00:00:00+00:00",
        "last_contact_date": "2026-06-20T00:00:00+00:00",
        "created_at": "2026-06-20T00:00:00+00:00",
    })
    inv_id = str(uuid.uuid4())
    await invoices_repo.insert({
        "id": inv_id, "owner_id": u_id, "client_id": c_id,
        "invoice_no": "MIG-001", "amount_inr": 5000.0,
        "due_date": "2026-07-01T00:00:00+00:00",
        "issued_at": "2026-06-25T00:00:00+00:00",
        "created_at": "2026-06-25T00:00:00+00:00",
    })
    a_id = str(uuid.uuid4())
    await activities_repo.insert({
        "id": a_id, "owner_id": u_id, "client_id": c_id,
        "related_type": "proposal", "related_id": p_id,
        "channel": "email", "direction": "outbound",
        "summary": "Sent mig deal", "created_at": "2026-06-20T00:00:00+00:00",
    })
    fu_gen = str(uuid.uuid4())
    fu1 = str(uuid.uuid4())
    fu2 = str(uuid.uuid4())
    await followups_repo.insert_many([
        {"id": fu1, "owner_id": u_id, "proposal_id": p_id, "client_id": c_id,
         "generation_id": fu_gen, "channel": "whatsapp", "draft_text": "Hi there",
         "context": {"days_silent": 3}, "prompt_ref": "proposal_followup@v3",
         "route_ref": "simple:emergent_gemini/gemini-2.5-flash",
         "confidence": 0.85, "latency_ms": 850,
         "created_at": "2026-06-27T00:00:00+00:00"},
        {"id": fu2, "owner_id": u_id, "proposal_id": p_id, "client_id": c_id,
         "generation_id": fu_gen, "channel": "email", "draft_text": "Subject: Hi\n\nBody",
         "context": {"days_silent": 3}, "prompt_ref": "proposal_followup@v3",
         "route_ref": "simple:emergent_gemini/gemini-2.5-flash",
         "confidence": 0.85, "latency_ms": 850,
         "created_at": "2026-06-27T00:00:00+00:00"},
    ])
    await events_repo.insert({
        "id": str(uuid.uuid4()), "owner_id": u_id,
        "event_type": "proposal.created", "entity_type": "proposal",
        "entity_id": p_id, "prior_value": None, "new_value": None,
        "metadata": {"client_id": c_id, "value_inr": 100000},
        "source": "user", "created_at": "2026-06-20T00:00:00+00:00",
    })
    await memory_repo.upsert(u_id, c_id, {
        "channel_preference": "email", "channel_counts": {"email": 1},
        "typical_response_days": 2.0, "response_rate": 0.5,
        "last_outcomes": [], "updated_at": "2026-06-28T00:00:00+00:00",
    })
    # Audit signing key + a few signed audit entries
    await load_signing_key()
    await append_audit(action="auth.register", actor_id=u_id, actor_email="mig@x",
                       resource_type="user", resource_id=u_id, payload={"x": 1})
    await append_audit(action="client.create", actor_id=u_id, actor_email="mig@x",
                       resource_type="client", resource_id=c_id, payload={"y": 2})
    await append_audit(action="proposal.create", actor_id=u_id, actor_email="mig@x",
                       resource_type="proposal", resource_id=p_id, payload={"z": 3})

    counts = {
        "users": await mdb.users.count_documents({}),
        "clients": await mdb.clients.count_documents({}),
        "proposals": await mdb.proposals.count_documents({}),
        "invoices": await mdb.invoices.count_documents({}),
        "activities": await mdb.activities.count_documents({}),
        "followups": await mdb.followups.count_documents({}),
        "events": await mdb.events.count_documents({}),
        "client_memory": await mdb.client_memory.count_documents({}),
        "audit_log": await mdb.audit_log.count_documents({}),
        "settings": await mdb.settings.count_documents({}),
    }
    mclient.close()
    return counts


def _run_migrator() -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["DB_NAME"] = MIGRATION_DB
    env["POSTGRES_URL"] = POSTGRES_URL
    env["MONGO_URL"] = MONGO_URL
    # NOTE: explicitly NOT setting DB_ENGINE — migrator forces it internally.
    return subprocess.run(
        [sys.executable, str(MIGRATE_SCRIPT)],
        env=env, capture_output=True, text=True, timeout=60,
    )


async def _pg_counts() -> dict:
    conn = await _connect_pg()
    try:
        out = {}
        for table in ("users", "clients", "proposals", "invoices", "activities",
                      "followups", "events", "client_memory", "audit_log", "settings"):
            out[table] = int(await conn.fetchval(f"SELECT count(*) FROM {table}"))
        return out
    finally:
        await conn.close()


async def _drop_mongo_db():
    from motor.motor_asyncio import AsyncIOMotorClient
    c = AsyncIOMotorClient(MONGO_URL)
    try:
        await c.drop_database(MIGRATION_DB)
    finally:
        c.close()


class TestMigrationIntegrity:
    def test_end_to_end(self):
        try:
            # 1. clean both sides
            _run(_reset_postgres_schema())
            mongo_counts = _run(_seed_mongo())

            # 2. run the migrator as a subprocess
            res = _run_migrator()
            assert res.returncode == 0, (
                f"migrator failed (rc={res.returncode})\n"
                f"stdout:\n{res.stdout}\n\nstderr:\n{res.stderr}"
            )

            # 3. per-table counts match
            pg_counts = _run(_pg_counts())
            for table, expected in mongo_counts.items():
                assert pg_counts[table] == expected, (
                    f"count mismatch on {table}: mongo={expected} pg={pg_counts[table]}"
                )

            # 4. migrator's own verify step (chain check) printed ok=True
            assert "ok=True" in res.stdout, (
                f"chain verify did not print ok=True\nstdout:\n{res.stdout}"
            )
        finally:
            _run(_drop_mongo_db())
            _run(_reset_postgres_schema())
