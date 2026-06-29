-- Revora — import_jobs (Day 1 of the contest sprint).
--
-- Stage-based importer: /parse writes the row, /map fills mapping,
-- /commit drains raw_rows into clients/proposals/invoices. If any later
-- stage fails the founder re-calls the same stage with the same file_id —
-- no re-upload.
--
-- Idempotent (IF NOT EXISTS), tenant-scoped via RLS, same pattern as 0001.

CREATE TABLE IF NOT EXISTS import_jobs (
  id            uuid PRIMARY KEY,
  owner_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  stage         text NOT NULL DEFAULT 'parsed'
                CHECK (stage IN ('parsed','mapped','committed')),
  target        text
                CHECK (target IS NULL OR target IN ('clients','proposals','invoices')),
  headers       jsonb NOT NULL,
  sample_rows   jsonb NOT NULL,
  raw_rows      jsonb NOT NULL,
  stats         jsonb NOT NULL DEFAULT '{}'::jsonb,
  mapping       jsonb,
  created_at    text NOT NULL
);

ALTER TABLE import_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE import_jobs FORCE  ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE schemaname = 'public'
                                AND tablename = 'import_jobs'
                                AND policyname = 'import_jobs_owner'
  ) THEN
    CREATE POLICY import_jobs_owner ON import_jobs
      USING      (owner_id = current_setting('app.current_user_id', true)::uuid)
      WITH CHECK (owner_id = current_setting('app.current_user_id', true)::uuid);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS import_jobs_owner_created_idx
  ON import_jobs (owner_id, created_at DESC);
