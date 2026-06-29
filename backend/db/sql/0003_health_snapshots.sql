-- Revora — health_snapshots (Day 2) + tenant_profile on users.
--
-- One snapshot per tenant per day, payload jsonb stores the full
-- /revenue-health response. Powers the "What changed since last upload"
-- card on Day 3 and the delta arrow on the visibility score.
--
-- tenant_profile lives on users (single column, no new table) — it's
-- per-tenant config, not global, so it can't live on settings.
--
-- Idempotent (IF NOT EXISTS), tenant-scoped via RLS, same pattern as 0001.

CREATE TABLE IF NOT EXISTS health_snapshots (
  id              uuid PRIMARY KEY,
  owner_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  snapshot_date   date NOT NULL,
  payload         jsonb NOT NULL,
  created_at      text NOT NULL,
  UNIQUE (owner_id, snapshot_date)
);

ALTER TABLE health_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE health_snapshots FORCE  ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE schemaname = 'public'
                                AND tablename = 'health_snapshots'
                                AND policyname = 'health_snapshots_owner'
  ) THEN
    CREATE POLICY health_snapshots_owner ON health_snapshots
      USING      (owner_id = current_setting('app.current_user_id', true)::uuid)
      WITH CHECK (owner_id = current_setting('app.current_user_id', true)::uuid);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS health_snapshots_owner_date_idx
  ON health_snapshots (owner_id, snapshot_date DESC);

-- tenant_profile is per-user JSON: {preferred_channel, follow_up_days, priority}.
-- Read by /revenue-health to steer Do These Today ranking + by Brief prompts (Day 3).
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS tenant_profile jsonb;
