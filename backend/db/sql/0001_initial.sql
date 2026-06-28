-- Revora — Postgres schema v1.
--
-- Source of truth for collections is docs/data-schema.md. Every Mongo
-- collection has a 1:1 table here. Idempotent (IF NOT EXISTS) so this file
-- can be re-applied to a partially-initialised DB without harm.
--
-- Conventions:
--   * id uuid PRIMARY KEY                — string UUIDs everywhere, same as Mongo
--   * owner_id uuid REFERENCES users(id) ON DELETE CASCADE  — tenant scoping
--   * Free-form structures (context, metadata, channel_counts, last_outcomes)
--     ride in jsonb columns. Cheap to query, no schema lock-in.
--   * Timestamps stay text (ISO-8601 UTC strings) to match the Mongo wire format
--     byte-for-byte — keeps the API contract frozen during cutover. A future
--     migration can flip them to timestamptz once consumers don't care.
--
-- RLS — per-user row-level security
--   Every tenant-scoped table:
--     ENABLE ROW LEVEL SECURITY
--     FORCE  ROW LEVEL SECURITY   <- critical: without this, the table owner
--                                     bypasses RLS, so the app role (which owns
--                                     the schema in dev) would too.
--     POLICY using owner_id = current_setting('app.current_user_id')::uuid
--   The DAO layer wraps each request in BEGIN; SET LOCAL app.current_user_id;
--   so a buggy WHERE clause physically cannot leak across tenants.
--
-- audit_log keeps its unique seq + hash chain; no RLS — admin-only at the
-- application layer.

CREATE EXTENSION IF NOT EXISTS vector;       -- pgvector for followups.embedding
CREATE EXTENSION IF NOT EXISTS pgcrypto;     -- for gen_random_uuid() if we want server-side


-- =========================================================================
-- App role. The connecting user (POSTGRES_USER) is a superuser and bypasses
-- RLS unconditionally — so the request transaction SETs LOCAL ROLE to this
-- non-superuser, which IS subject to RLS. Admin paths (audit_log reads,
-- migration script, chain verify) skip the SET ROLE and run as superuser.
-- =========================================================================
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'revora_app') THEN
    CREATE ROLE revora_app NOLOGIN;
  END IF;
END $$;
GRANT USAGE ON SCHEMA public TO revora_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO revora_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO revora_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO revora_app;


-- =========================================================================
-- users — auth principals; not RLS-protected (auth uses it before user known)
-- =========================================================================
CREATE TABLE IF NOT EXISTS users (
  id              uuid PRIMARY KEY,
  email           text NOT NULL UNIQUE,
  name            text NOT NULL DEFAULT '',
  auth_provider   text NOT NULL DEFAULT 'email'
                   CHECK (auth_provider IN ('email', 'google')),
  password_hash   text,
  token_version   integer NOT NULL DEFAULT 0,
  created_at      text NOT NULL
);
CREATE INDEX IF NOT EXISTS users_email_lower_idx ON users (lower(email));


-- =========================================================================
-- clients
-- =========================================================================
CREATE TABLE IF NOT EXISTS clients (
  id              uuid PRIMARY KEY,
  owner_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  company_name    text NOT NULL,
  contact_name    text NOT NULL,
  email           text,
  phone           text,
  whatsapp        text,
  industry        text,
  language        text NOT NULL DEFAULT 'English',
  notes           text,
  created_at      text NOT NULL
);
CREATE INDEX IF NOT EXISTS clients_owner_company_idx ON clients (owner_id, company_name);

ALTER TABLE clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE clients FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS clients_owner ON clients;
CREATE POLICY clients_owner ON clients
  USING      (owner_id = current_setting('app.current_user_id', true)::uuid)
  WITH CHECK (owner_id = current_setting('app.current_user_id', true)::uuid);


-- =========================================================================
-- proposals
-- =========================================================================
CREATE TABLE IF NOT EXISTS proposals (
  id                   uuid PRIMARY KEY,
  owner_id             uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  client_id            uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  title                text NOT NULL,
  value_inr            numeric NOT NULL,
  sent_date            text NOT NULL,
  last_contact_date    text NOT NULL,
  stage                text NOT NULL DEFAULT 'sent'
                        CHECK (stage IN ('sent', 'negotiating', 'won', 'lost')),
  outcome_at           text,        -- stamped when stage flips to won/lost
  notes                text,
  created_at           text NOT NULL
);
CREATE INDEX IF NOT EXISTS proposals_owner_idx       ON proposals (owner_id);
CREATE INDEX IF NOT EXISTS proposals_owner_client_idx ON proposals (owner_id, client_id);
CREATE INDEX IF NOT EXISTS proposals_owner_lcd_idx   ON proposals (owner_id, last_contact_date DESC);

ALTER TABLE proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE proposals FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS proposals_owner ON proposals;
CREATE POLICY proposals_owner ON proposals
  USING      (owner_id = current_setting('app.current_user_id', true)::uuid)
  WITH CHECK (owner_id = current_setting('app.current_user_id', true)::uuid);


-- =========================================================================
-- invoices
-- =========================================================================
CREATE TABLE IF NOT EXISTS invoices (
  id              uuid PRIMARY KEY,
  owner_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  client_id       uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  invoice_no      text NOT NULL,
  amount_inr      numeric NOT NULL,
  due_date        text NOT NULL,
  paid_date       text,             -- ML label
  issued_at       text NOT NULL,
  notes           text,
  created_at      text NOT NULL
);
CREATE INDEX IF NOT EXISTS invoices_owner_idx       ON invoices (owner_id);
CREATE INDEX IF NOT EXISTS invoices_owner_client_idx ON invoices (owner_id, client_id);
CREATE INDEX IF NOT EXISTS invoices_owner_due_idx    ON invoices (owner_id, due_date DESC);

ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS invoices_owner ON invoices;
CREATE POLICY invoices_owner ON invoices
  USING      (owner_id = current_setting('app.current_user_id', true)::uuid)
  WITH CHECK (owner_id = current_setting('app.current_user_id', true)::uuid);


-- =========================================================================
-- activities — user-curated touchpoints
-- =========================================================================
CREATE TABLE IF NOT EXISTS activities (
  id              uuid PRIMARY KEY,
  owner_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  client_id       uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  related_type    text CHECK (related_type IN ('proposal', 'invoice') OR related_type IS NULL),
  related_id      uuid,
  channel         text NOT NULL
                   CHECK (channel IN ('call', 'whatsapp', 'email', 'meeting', 'note')),
  direction       text NOT NULL DEFAULT 'outbound'
                   CHECK (direction IN ('inbound', 'outbound', 'internal')),
  summary         text NOT NULL,
  created_at      text NOT NULL
);
CREATE INDEX IF NOT EXISTS activities_owner_created_idx ON activities (owner_id, created_at DESC);
CREATE INDEX IF NOT EXISTS activities_owner_client_idx  ON activities (owner_id, client_id);

ALTER TABLE activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE activities FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS activities_owner ON activities;
CREATE POLICY activities_owner ON activities
  USING      (owner_id = current_setting('app.current_user_id', true)::uuid)
  WITH CHECK (owner_id = current_setting('app.current_user_id', true)::uuid);


-- =========================================================================
-- followups — AI drafts persisted with full generation context.
-- vector(1536) embedding ready for future semantic search (OpenAI dim).
-- =========================================================================
CREATE TABLE IF NOT EXISTS followups (
  id                uuid PRIMARY KEY,
  owner_id          uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  proposal_id       uuid NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
  client_id         uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  generation_id     uuid NOT NULL,
  channel           text NOT NULL CHECK (channel IN ('whatsapp', 'email')),
  draft_text        text NOT NULL,
  context           jsonb NOT NULL DEFAULT '{}'::jsonb,
  prompt_ref        text,
  route_ref         text,
  confidence        double precision,
  latency_ms        integer,
  embedding         vector(1536),
  created_at        text NOT NULL
);
CREATE INDEX IF NOT EXISTS followups_owner_prop_created_idx
  ON followups (owner_id, proposal_id, created_at DESC);
CREATE INDEX IF NOT EXISTS followups_owner_generation_idx
  ON followups (owner_id, generation_id);
-- HNSW index on embedding is intentionally NOT created here — empty index
-- on an empty column is wasteful; build it once we start writing vectors.

ALTER TABLE followups ENABLE ROW LEVEL SECURITY;
ALTER TABLE followups FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS followups_owner ON followups;
CREATE POLICY followups_owner ON followups
  USING      (owner_id = current_setting('app.current_user_id', true)::uuid)
  WITH CHECK (owner_id = current_setting('app.current_user_id', true)::uuid);


-- =========================================================================
-- events — append-only product analytics stream
-- =========================================================================
CREATE TABLE IF NOT EXISTS events (
  id              uuid PRIMARY KEY,
  owner_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event_type      text NOT NULL,
  entity_type     text NOT NULL,
  entity_id       uuid NOT NULL,
  prior_value     jsonb,            -- nullable; stage flips carry old/new here
  new_value       jsonb,
  metadata        jsonb NOT NULL DEFAULT '{}'::jsonb,
  source          text NOT NULL DEFAULT 'system'
                   CHECK (source IN ('user', 'system')),
  created_at      text NOT NULL
);
CREATE INDEX IF NOT EXISTS events_owner_entity_created_idx
  ON events (owner_id, entity_id, created_at DESC);
CREATE INDEX IF NOT EXISTS events_owner_type_created_idx
  ON events (owner_id, event_type, created_at DESC);

ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE events FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS events_owner ON events;
CREATE POLICY events_owner ON events
  USING      (owner_id = current_setting('app.current_user_id', true)::uuid)
  WITH CHECK (owner_id = current_setting('app.current_user_id', true)::uuid);


-- =========================================================================
-- client_memory — derived features, recomputed (not patched)
-- =========================================================================
CREATE TABLE IF NOT EXISTS client_memory (
  id                      uuid PRIMARY KEY,
  owner_id                uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  client_id               uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  channel_preference      text,
  channel_counts          jsonb NOT NULL DEFAULT '{}'::jsonb,
  typical_response_days   double precision,
  response_rate           double precision,
  last_outcomes           jsonb NOT NULL DEFAULT '[]'::jsonb,
  recompute_count         integer NOT NULL DEFAULT 0,
  updated_at              text NOT NULL,
  UNIQUE (owner_id, client_id)
);

ALTER TABLE client_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE client_memory FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS client_memory_owner ON client_memory;
CREATE POLICY client_memory_owner ON client_memory
  USING      (owner_id = current_setting('app.current_user_id', true)::uuid)
  WITH CHECK (owner_id = current_setting('app.current_user_id', true)::uuid);


-- =========================================================================
-- audit_log — signed hash-chained log; admin-only at the app layer, no RLS
-- =========================================================================
CREATE TABLE IF NOT EXISTS audit_log (
  id              uuid PRIMARY KEY,
  seq             integer NOT NULL UNIQUE,
  actor_id        text NOT NULL,           -- text (not uuid) — system events use 'system'
  actor_email     text NOT NULL,
  action          text NOT NULL,
  resource_type   text,
  resource_id     text,
  payload_hash    text NOT NULL,
  prev_hash       text NOT NULL,
  record_hash     text NOT NULL,
  signature       text NOT NULL,
  public_key_fp   text NOT NULL,
  timestamp       text NOT NULL
);
CREATE INDEX IF NOT EXISTS audit_log_actor_ts_idx  ON audit_log (actor_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS audit_log_action_ts_idx ON audit_log (action, timestamp DESC);


-- =========================================================================
-- settings — global singleton (id='global')
-- =========================================================================
CREATE TABLE IF NOT EXISTS settings (
  id                   text PRIMARY KEY,                -- 'global'
  ai_killswitch        boolean NOT NULL DEFAULT false,
  audit_signing_key    text                              -- nullable; ed25519 base64
);
