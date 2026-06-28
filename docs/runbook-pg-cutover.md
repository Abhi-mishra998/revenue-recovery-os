# Postgres cutover & rollback runbook

The data layer ships with two engines wired in: **mongo** (legacy, default)
and **postgres** (target). Selection is one env var — `DB_ENGINE` — so
rollback is an env flip + redeploy, not a code change.

The repo layer at `backend/services/db/repos/*` dispatches on `DB_ENGINE`
inside every method. API responses are byte-identical between engines; the
frontend doesn't change.

---

## Pre-flight (do once, before scheduling the cutover)

1. **Bring up the Postgres container** alongside the existing Mongo:
   ```bash
   docker compose up -d
   ```
   This starts `revora-postgres` on `localhost:5432` with the `pgvector/pgvector:pg16`
   image. The `pg_data` volume persists across container restarts.

2. **Apply the schema**:
   ```bash
   docker exec -i revora-postgres psql -U revora -d revora \
     < backend/db/sql/0001_initial.sql
   ```
   Idempotent — safe to re-apply. Creates 10 tables, FKs, indexes, the
   `revora_app` non-superuser role, RLS policies on every tenant table, and
   the `vector`/`pgcrypto` extensions.

3. **Set `POSTGRES_URL` in `backend/.env`** (leave `DB_ENGINE=mongo` for now):
   ```
   POSTGRES_URL=postgresql://revora:revora@localhost:5432/revora
   ```
   In production: use a non-superuser, non-`revora_app` connecting role
   that's a **member** of `revora_app`, with `BYPASSRLS=false`. That way
   even a forgotten `SET LOCAL ROLE` call wouldn't escape the policies.

4. **Verify pre-flight with the RLS tests**:
   ```bash
   POSTGRES_URL=postgresql://revora:revora@localhost:5432/revora \
     pytest backend/tests/test_pg_rls.py -v
   ```
   Should be 5/5 green. If it isn't, RLS is broken — fix before cutover.

---

## Cutover (the actual move)

5. **Dry-run the migrator** to see what would be copied:
   ```bash
   cd backend
   python scripts/migrate_to_postgres.py --dry-run
   ```
   Prints per-table Mongo vs Postgres counts. `pg_before` should be 0 for
   every row.

6. **Pause writes** (deploy a maintenance banner / 503 on POST/PATCH/DELETE
   if your front end supports it; or accept ~5 min of double-writes you'll
   lose). Read-only access can stay.

7. **Run the migration**:
   ```bash
   python scripts/migrate_to_postgres.py
   ```
   Per-table progress prints as it goes. The script verifies on its own at
   the end:
   - counts match Mongo
   - audit chain re-walks on Postgres and `ok=True`

   The exit code is non-zero if verification fails.

8. **Flip the engine**: set `DB_ENGINE=postgres` in the backend's env and
   redeploy / restart the FastAPI process. On startup the logs print
   `Revora ready (engine=postgres, audit key fp=...)`. Fingerprint should
   match the pre-cutover value (same key persists across the move).

9. **Run the integration tests against the new backend**:
   ```bash
   pytest backend/tests/ -v
   ```
   115/115 green = good.

10. **Re-enable writes**.

---

## Rollback

The rollback path is **env flip + redeploy**:

1. Set `DB_ENGINE=mongo` in the backend env.
2. Redeploy / restart the FastAPI process.
3. Confirm `engine=mongo` in startup logs.

That's it — Mongo wasn't touched during the migration. Any writes accepted
on Postgres between cutover and rollback are lost (they're not in Mongo).
That's the cost of one-shot cutover; if you can't afford it, the dual-write
phase below.

### Dual-write (optional, lower-risk variant)

Not currently implemented — would add a write wrapper that fans out to both
engines for the duration of the transition. Cleaner rollback (no data loss
either direction), at the cost of more moving parts. Plumb in a new commit
when needed.

---

## Cleanup (once you're confident — typically 2 weeks after cutover)

1. Drop the Mongo container + its volume:
   ```bash
   docker compose stop mongo
   docker compose rm -f mongo
   docker volume rm revenue-recovery-os_mongo_data
   ```
2. Remove the mongo branches from the repo layer (a follow-up commit; until
   then they're harmless dead code behind `is_mongo()`).
3. Drop `motor`, `pymongo` from `backend/requirements.txt`.

---

## Things that should NOT change during cutover

- **Frozen API contract**: every endpoint returns the same JSON shape on
  either engine. The frontend doesn't change.
- **`audit_log.seq`** stays a strictly increasing integer; the migration
  copies in seq-ascending order and the chain re-verifies on Postgres.
- **`AUDIT_SIGNING_KEY`** — if you set it via env, the same key signs
  records on both engines. If you let the server auto-generate it, the
  migrated `settings.audit_signing_key` row keeps the same key.

## Things that DO change subtly

- **`SET LOCAL ROLE revora_app`** is the load-bearing isolation step on
  Postgres. If a future patch adds a new repo method that calls
  `bypass_user()` instead of `with_user(owner_id)`, RLS is bypassed —
  caught by `tests/test_pg_rls.py` and code review.
- **`outcome_at`** is an explicit column on Postgres; on Mongo it's only
  present on proposals that have transitioned to won/lost since the
  feature shipped. Retroactive backfill is out of scope.
