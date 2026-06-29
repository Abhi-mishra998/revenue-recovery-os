-- Revora — daily_brief cache on users (Day 3).
--
-- One row per founder per UTC date is enough — Morning Brief regenerates
-- only when the cached date != today. JSONB shape:
--   {date: 'YYYY-MM-DD', brief: BriefDraft, recommendation_ids: [uuid],
--    generated_at: iso, source: 'llm' | 'template_fallback'}
--
-- Idempotent. No new table — fewer files, fewer migrations.

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS daily_brief jsonb;
