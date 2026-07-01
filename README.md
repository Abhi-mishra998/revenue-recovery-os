<div align="center">

# Revora — Revenue Recovery OS

**The operating system for revenue you've already earned.**

Proposals, invoices, AI follow-ups, and recovery analytics for Indian B2B service businesses.

[![tests](https://github.com/Abhi-mishra998/revenue-recovery-os/actions/workflows/test.yml/badge.svg)](https://github.com/Abhi-mishra998/revenue-recovery-os/actions/workflows/test.yml)
[![lint](https://img.shields.io/badge/lint-ruff-D7FF64?logo=ruff)](backend/ruff.toml)
[![python](https://img.shields.io/badge/python-3.12-blue?logo=python)](backend/requirements.txt)
[![node](https://img.shields.io/badge/node-20-339933?logo=node.js)](frontend/package.json)
[![postgres](https://img.shields.io/badge/postgres-pgvector%2Fpg16-336791?logo=postgresql)](backend/db/sql/0001_initial.sql)
[![LLM](https://img.shields.io/badge/LLM-Claude%20Haiku%204.5-D97757)](backend/services/ai/client.py)

</div>

---

## System architecture

![Revora System Architecture](./diagram.png)

Six layers, one loop: browser → API → Postgres, with an AI service layer alongside, all wrapped in a shared observability + security surface. Deep-dive in [`archi.md`](./archi.md).

---

## Live deployment

| Surface | URL |
|---|---|
| Frontend (Vercel) | https://revenue-recovery-os1.vercel.app |
| Backend (Render)  | https://revora-backend-1in4.onrender.com |
| Database          | Neon Postgres 18 (us-east-1) |
| LLM               | Anthropic Claude Haiku 4.5 (`claude-haiku-4-5`) |

Demo login: `founder@bytehubble.com` / `<ADMIN_PASSWORD>`.

---

## Stack

| Layer | Choice |
|---|---|
| **Frontend** | React 19 · CRA + Craco · Tailwind · shadcn/ui · framer-motion · axios |
| **Backend**  | FastAPI · Uvicorn · Pydantic · asyncpg / motor (engine switch) |
| **Database** | PostgreSQL 16 + **pgvector** (prod) · MongoDB 7 (rollback path) |
| **AI**       | Provider-abstracted (Anthropic / OpenAI / Gemini) · versioned prompts · JSON-schema validation with retry · PII redact + rehydrate · output guardrails · value-tier model router |
| **Security** | Postgres RLS (per-tenant) · JWT with `tv` revocation · bcrypt · rate-limited auth + AI · ed25519-signed audit chain · admin kill-switch · CSP/HSTS headers |
| **Ops**      | Structured JSON logs · Sentry-optional · pytest matrix (mongo + postgres) in CI · Render blueprint · Vercel CI build |

---

## Quick start

```bash
# 1. Data layer (Postgres + pgvector; Mongo for rollback path)
docker compose up -d

# 2. Apply Postgres schema
docker exec -i revora-postgres psql -U revora -d revora \
  < backend/db/sql/0001_initial.sql

# 3. Backend
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env             # then edit: JWT_SECRET, ADMIN_PASSWORD, ANTHROPIC_API_KEY
uvicorn server:app --reload --port 8000

# 4. Frontend
cd ../frontend
yarn install
yarn start                        # http://localhost:3000
```

Default admin login: `founder@bytehubble.com` / whatever you set as `ADMIN_PASSWORD`.

---

## Environment

Minimum vars in `backend/.env`:

```env
DB_ENGINE=postgres
POSTGRES_URL=postgresql://revora:revora@localhost:5432/revora
JWT_SECRET=<64-char random>
ADMIN_EMAIL=founder@bytehubble.com
ADMIN_PASSWORD=<your password>
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

Full env table in [`archi.md` §16](./archi.md#16-environment-variables-the-configuration-knobs).

---

## Test + lint

```bash
cd backend && source .venv/bin/activate

# Full suite (parallel via pytest-xdist)
pytest tests/ -v --cov=services --cov=server

# Lint + format check
ruff check . && ruff format --check .

# Direct-DB RLS proof (Postgres only)
POSTGRES_URL=postgresql://revora:revora@localhost:5432/revora \
  pytest tests/test_pg_rls.py -v

# AI eval harness (dry-run — no LLM call)
python -m services.ai.eval --dry-run
```

CI runs the suite against both engines on every push — see [`.github/workflows/test.yml`](.github/workflows/test.yml).

---

## What makes Revora different

1. **Signed audit chain** — every write is ed25519-signed and hash-chained to the previous entry. Tamper is detectable, not just discouraged.
2. **Postgres RLS multi-tenancy** — the DB refuses cross-tenant reads even if the app forgets a `WHERE`.
3. **PII redact before LLM** — emails, phones, PAN, GSTIN, Aadhaar never leave your infra in cleartext.
4. **Value-tier model routing** — cheap proposals → Haiku; high-value proposals → stronger model. Cost stays proportional to stakes.
5. **AI kill-switch** — one admin toggle disables every LLM endpoint (outage / cost runaway / jailbreak).
6. **Dual-engine DB** — Postgres in prod, Mongo warm as rollback. Env-flip cutover.
7. **DPDP export + delete** — one-click data export and cascade-delete, both audit-signed.

Each buys real trust for a small tax in complexity — that's the project's character.

---

## Documentation

| Doc | What |
|---|---|
| [`archi.md`](./archi.md) | Architecture in plain English — every layer, every choice, why it exists |
| [`SETUP.md`](./SETUP.md) | Step-by-step setup + demo script |
| [`DEPLOY.md`](./DEPLOY.md) | Render + Vercel + Neon deploy playbook |
| [`docs/data-schema.md`](./docs/data-schema.md) | Every table, column, index, RLS policy |
| [`docs/runbook-pg-cutover.md`](./docs/runbook-pg-cutover.md) | Mongo → Postgres cutover + rollback |
| [`docs/production-readiness.md`](./docs/production-readiness.md) | 10-item go-live checklist |

---

## Repository layout

```
revenue-recovery-os/
├── backend/          FastAPI server, services (auth, audit, AI), Postgres schema, pytest suite
├── frontend/         React 19 app (CRA + Craco), Tailwind, shadcn/ui
├── docs/             Deep-dive docs (schema, runbooks, checklists)
├── docker-compose.yml    Postgres + Mongo containers (dev)
├── render.yaml       Render Blueprint (backend deploy)
├── archi.md          Architecture reference
├── SETUP.md          Setup + demo script
└── DEPLOY.md         Prod deploy playbook
```

---

<div align="center">

Built for the [Raj Shamani × Emergent](https://emergent.sh) contest.
Made in Bengaluru by [ByteHubble](https://bytehubble.ai).

</div>
