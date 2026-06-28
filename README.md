# Revora — Revenue Recovery OS

[![tests](https://github.com/Abhi-mishra998/revenue-recovery-os/actions/workflows/test.yml/badge.svg)](https://github.com/Abhi-mishra998/revenue-recovery-os/actions/workflows/test.yml)
[![lint](https://img.shields.io/badge/lint-ruff-D7FF64?logo=ruff)](backend/ruff.toml)
[![python](https://img.shields.io/badge/python-3.12-blue?logo=python)](backend/requirements.txt)
[![node](https://img.shields.io/badge/node-20-339933?logo=node.js)](frontend/package.json)
[![postgres](https://img.shields.io/badge/postgres-pgvector%2Fpg16-336791?logo=postgresql)](backend/db/sql/0001_initial.sql)

The operating system for revenue you've already earned — proposals, invoices,
AI follow-ups, and recovery analytics for Indian B2B service businesses.

## Stack

- **Backend**: FastAPI · asyncpg / motor (DB_ENGINE switch) · Postgres+pgvector
  (prod) or MongoDB (rollback)
- **Frontend**: React 19 · CRA + Craco · Tailwind · shadcn/ui
- **AI**: provider-abstracted (Emergent gateway / OpenAI / Anthropic / Gemini),
  versioned prompts, JSON schema validation with retry, PII redaction,
  output guardrails, tiered model router
- **Security**: per-tenant RLS (Postgres) · JWT with `tv` revocation ·
  bcrypt · rate-limited auth & AI · ed25519-signed audit chain · admin
  kill-switch · CSP/HSTS headers
- **Observability**: pytest (174 tests, mongo+pg matrix in CI) · structured
  logs · request tracing (Sprint C)

## Quick start

```bash
# 1. data layer (mongo + postgres+pgvector)
docker compose up -d

# 2. apply postgres schema
docker exec -i revora-postgres psql -U revora -d revora \
  < backend/db/sql/0001_initial.sql

# 3. backend
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# optional: pip install -r requirements-runtime.txt   # private LLM SDKs
cp .env.example .env
# edit .env: JWT_SECRET, ADMIN_PASSWORD, DB_ENGINE (mongo | postgres)
uvicorn server:app --reload --port 8000

# 4. frontend
cd ../frontend
yarn install
yarn start   # http://localhost:3000
```

Default admin login (set in `.env`): `founder@bytehubble.com` / your
`ADMIN_PASSWORD`.

## Test + lint

```bash
cd backend && source .venv/bin/activate

# Full suite (against a running backend on either engine)
pytest tests/ -v --cov=services --cov=server

# Lint + format check (no backend needed)
ruff check . && ruff format --check .

# Direct-DB RLS proof (Postgres only — skips if POSTGRES_URL unset)
POSTGRES_URL=postgresql://revora:revora@localhost:5432/revora \
  pytest tests/test_pg_rls.py -v

# AI eval harness (dry-run prints prompts without calling the LLM)
python -m services.ai.eval --dry-run
```

## Architecture docs

| Doc | What |
|---|---|
| [`docs/data-schema.md`](docs/data-schema.md) | Every collection / table — fields, indexes, RLS, ML labels |
| [`docs/runbook-pg-cutover.md`](docs/runbook-pg-cutover.md) | Mongo → Postgres cutover + rollback playbook |
| [`memory/PRD.md`](memory/PRD.md) | Product brief and locked-in architecture rules |

## Cutover & rollback

The data layer ships two engines wired in. `DB_ENGINE=mongo` (default) or
`DB_ENGINE=postgres`. Rollback is an env flip + redeploy — Mongo stays warm
during cutover. Full playbook in [`docs/runbook-pg-cutover.md`](docs/runbook-pg-cutover.md).

## CI

`.github/workflows/test.yml` runs three jobs on every push and PR:

| Job | What |
|---|---|
| **lint** | `ruff check` + `ruff format --check` on `backend/` |
| **pytest (engine=mongo)** | Full suite against a fresh mongo:7 service container |
| **pytest (engine=postgres)** | Full suite against pgvector/pg16 with schema applied |
| **frontend (build)** | `yarn install --frozen-lockfile` + `yarn build` |

Coverage XML + junit XML uploaded as artefacts per matrix.
