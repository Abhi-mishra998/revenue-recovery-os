-- Revora — let the connecting role assume the app role.
--
-- Migration 0001 creates `revora_app` for RLS to fire (the connecting role
-- is usually superuser, which bypasses RLS unconditionally — we drop to
-- revora_app per-request via SET LOCAL ROLE).
--
-- On local docker the connecting user IS a superuser, so the SET ROLE is
-- implicit and free. On managed Postgres (Neon, Supabase, RDS-IAM), the
-- connecting user is NOT a superuser, and SET ROLE fails with
-- "permission denied to set role" unless the connecting user has explicit
-- membership in the target role.
--
-- This migration grants that membership to whoever is running the
-- migration — works on Neon and on local docker without code changes.
--
-- Idempotent: GRANT ... TO ... is a no-op if the grant already exists.

DO $$
BEGIN
  EXECUTE format('GRANT revora_app TO %I', CURRENT_USER);
EXCEPTION WHEN OTHERS THEN
  -- If the connecting role is already a superuser, the grant is moot.
  RAISE NOTICE 'GRANT revora_app TO % skipped: %', CURRENT_USER, SQLERRM;
END $$;
