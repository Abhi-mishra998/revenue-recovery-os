# Revora — Setup, Demo, and How It Works

This guide gets a new dev (or you, on a new laptop) from `git clone` to a
working app in **~5 minutes**, walks through a **12-minute client demo**
script, and explains the system in plain English so you can answer any
question on a sales call without scrambling.

> **Should I deploy to cloud yet?** No. Run locally, share with clients via
> a tunnel ([§5](#5-sharing-with-a-client-without-deploying)), get pilot
> signal first. Deploy when at least one pilot user is asking you to.
> Deployment options are in [§7](#7-when-youre-ready-to-deploy).

---

## 1. What you need installed

| Tool | Why | Install |
|---|---|---|
| **Docker Desktop** | runs Postgres + Mongo locally without touching system | https://docker.com/products/docker-desktop |
| **Python 3.12** | backend — newer 3.13/3.14 work but 3.12 matches CI | `brew install python@3.12` |
| **Node 20** | frontend | `brew install node@20` |
| **Yarn 1.x** | frontend package manager (declared in `package.json`) | `npm install -g yarn` |
| **Git** | obviously | already there |

That's it. No system-wide Postgres, no system-wide Mongo, no globally
installed Python deps.

---

## 2. Five-minute first boot

From the repo root:

```bash
# 2.1  Start both databases
docker compose up -d
#      → revora-postgres (pgvector/pg16) + revora-mongo

# 2.2  Apply the Postgres schema (idempotent — safe to re-run)
docker exec -i revora-postgres psql -U revora -d revora \
  < backend/db/sql/0001_initial.sql

# 2.3  Backend
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
#      → edit .env: pick DB_ENGINE=postgres (recommended) OR mongo
#                   set JWT_SECRET (any random 32+ char string)
#                   set ADMIN_PASSWORD (your first-time login password)
python -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(48))"
#      → use the output for JWT_SECRET if you don't have one yet

uvicorn server:app --reload --port 8000
#      → logs print 'Revora ready (engine=postgres, audit key fp=...)'
```

In a **second terminal**:

```bash
# 2.4  Frontend
cd frontend
yarn install
# point the React app at the local backend:
echo "REACT_APP_BACKEND_URL=http://localhost:8000" > .env
yarn start
#      → opens http://localhost:3000 automatically
```

**Login**: `founder@bytehubble.com` / whatever you set as `ADMIN_PASSWORD`.

The admin user is seeded on first boot with a realistic dataset (12 clients,
14 proposals, 10 invoices, plus 7 days of activity) — you'll see real numbers
on the dashboard immediately, no empty state.

---

## 3. What you should see

After login, every page has data:

| Page | What's there |
|---|---|
| **Dashboard** | ₹37.75 L pipeline, 6 cold proposals, ₹11.57 L overdue, ₹27.15 L at risk — all live from the seed |
| **Proposals** | 14 proposals across clients like Nexora, FinKart, Sundari Studios; status pills (active/cold/dead) auto-computed from `last_contact_date` |
| **Proposal detail** | Click any cold one — you'll see the AI follow-up panel, generation history, and a close-likelihood badge with reasons in the tooltip |
| **Clients** | 12 Indian B2B clients with industries; click into one to see their proposals + invoices + the "Client memory" card (preferred channel, response rate) |
| **Invoices** | 10 invoices, mix of paid / unpaid / overdue |
| **Settings** | Export-my-data + Delete-my-account (DPDP gates) |
| **Admin** (visible only to founder@) | Kill-switch, chain verify, audit log, active AI config |

---

## 4. The 12-minute client demo

Order matters. The first 90 seconds are the hook — show value before
explaining anything.

### Setup before the call (30 seconds)
1. `docker compose up -d` (if not already running)
2. Backend + frontend running
3. **Log in fresh** — close existing tab, log in. Don't demo on a stale tab.
4. Have this script open on a second monitor.

### Minute 0-1 — The hook
> "This is the dashboard. ₹27 lakh in revenue at risk, ₹11.5 lakh in overdue
> invoices, 6 cold proposals. We compute all of this from your existing data.
> No manual status entry."

- Point at **Revenue at Risk** card.
- Point at **Top 5 proposals at risk** — say "ranked by value × days silent,
  so the urgent ones float up."
- Hover the **close-likelihood** badge somewhere — say "we already do live
  inference today on what's worth chasing."

### Minute 1-4 — Cold proposal → AI follow-up
1. Click into **FinKart KYC + UPI flows** (or any cold one).
2. Point at the badges:
   > "14 days silent, ₹6.2 L. Likelihood badge is amber because the response
   > history is mixed."
3. Click **Generate Follow-Up**.
4. ~1 second later, two drafts appear (WhatsApp + Email side by side).
5. Point at the badges below the button:
   > "AI confidence is 82%. Generated with prompt `proposal_followup@v3`,
   > simple tier → Gemini Flash, in 850ms. Every generation is tracked."
6. Scroll to **Generation history** — show that the drafts are stored.
7. Click **Send on WhatsApp** or **Copy** — say:
   > "We never auto-send. The user always copies and sends manually.
   > That's a hard architectural rule, not a setting you can toggle."

### Minute 4-6 — Per-client memory
1. Back to **Clients** → click **FinKart**.
2. Scroll to the **Client memory** card.
3. Point at:
   - Preferred channel (e.g. "WhatsApp")
   - Typical response time (e.g. "~3.5d")
   - Response rate (e.g. "75%")
4. Say:
   > "We derive these signals from your activity. They're the seed data for
   > a real ML model later — right now the close-probability uses a heuristic
   > so we can train on real outcomes once the data is big enough."

### Minute 6-9 — Tamper-evident audit + kill-switch
1. Click into **Admin** (sidebar — only visible to the founder).
2. Click **Run verify** on the chain card.
   > "Every state change — create, update, delete, AI draft, login — is signed
   > with ed25519 and hash-linked. We can prove the log wasn't tampered with."
3. Show **Audit log** — scroll through the recent entries.
4. Toggle **kill-switch** on:
   > "If we suspect a cost runaway or the LLM provider is having issues, one
   > click here and every AI call returns 503 instantly."
5. Toggle it back off.

### Minute 9-11 — DPDP (matters for Indian B2B / regulated clients)
1. Click **Settings**.
2. Click **Download my data (JSON)** — show the file download in the corner.
   > "DPDP Act compliance. Every byte we store about a tenant, on demand,
   > as a JSON export."
3. Point at the **Delete account** card (don't click it):
   > "Cascade-deletes the user and every owned record. Signed into the audit
   > chain before the delete, so the deletion fact is permanently recorded."

### Minute 11-12 — Close
> "It runs locally for you today on the same code path that runs in
> production. Postgres with row-level security, JWT auth, ed25519-signed
> audit log, rate limits, structured logging, full test suite.
> What questions do you have?"

---

## 5. Sharing with a client without deploying

You don't need cloud for client demos. Use a tunnel.

### Option A — Cloudflare tunnel (free, no signup needed for quick demos)

```bash
# install
brew install cloudflared

# tunnel your local backend
cloudflared tunnel --url http://localhost:8000
#      → prints a https://<random>.trycloudflare.com URL

# update the frontend to point at it
echo "REACT_APP_BACKEND_URL=https://<that-url>" > frontend/.env
# rebuild + serve the frontend, or push to Vercel/Netlify free tier

# OR: tunnel the frontend too
cloudflared tunnel --url http://localhost:3000
```

### Option B — ngrok (free tier, easier)

```bash
brew install ngrok
ngrok http 8000  # backend
# in another terminal:
ngrok http 3000  # frontend
```

Share the frontend URL with the client. Login still works because the JWT
auth doesn't care about hostname.

**Caveat**: tunnel sessions die when you `Ctrl+C`. Fine for live demos,
not for "let me email you a link to play with for a week."

---

## 6. How the system works (architecture in plain English)

### Request flow (a single API call)

```
Client (React)
   ↓ HTTPS + Bearer JWT
Reverse proxy (in prod: Cloudflare/ALB/nginx)
   ↓
FastAPI (uvicorn)
   ├─ Middleware 1: enforce_max_body_size      ← rejects >5MB before parse
   ├─ Middleware 2: security_headers           ← HSTS, X-Frame-Options, …
   ├─ Middleware 3: request_context+access_log ← stamps X-Request-ID,
   │                                              JSON log per request
   ├─ Middleware 4: CORSMiddleware             ← allowlist
   ├─ Middleware 5: slowapi rate limiter       ← 30/min login, 10/h AI
   ↓
Endpoint handler (server.py)
   ├─ get_current_user dep   ← JWT decode, token_version check
   ├─ assert_owns_client     ← cross-tenant safety
   ├─ repo call               ← services/db/repos/*
   │     ├─ MONGO path: motor query
   │     └─ POSTGRES path: with_user(uid) → SET LOCAL ROLE revora_app
   │                       + set_config('app.current_user_id', uid)
   │                       → every query runs under RLS
   ├─ append_audit (if state change)  ← ed25519-signed, hash-chained
   ├─ emit_event (if state change)    ← append-only analytics stream
   └─ return JSON
```

### Data lives in three places

| Store | What's in it | Why |
|---|---|---|
| **Postgres + pgvector** (prod) | Everything: users, clients, proposals, invoices, activities, followups (with `vector(1536)` for future semantic search), events, client_memory, audit_log, settings | Real FKs, RLS at the DB level, ed25519-signed audit chain |
| **Mongo** (legacy / rollback) | Same shapes (no FKs) | `DB_ENGINE=mongo` flips back to it in seconds if Postgres misbehaves |
| **In-process** | Kill-switch state (5-min cache, invalidated on toggle); JWT signing key (env or settings doc); audit signing key (env or settings doc) | Single DB read per process boot, then fast |

### The AI layer

```
generate_proposal_followup(proposal, client)
   ↓
1. router.route() picks tier (simple/complex) by value_inr
2. redact.redact(context) tokenises email/phone/PAN/GSTIN/Aadhaar
3. prompts.get('proposal_followup') → active template (v3)
4. client.generate_json(...)
     ├─ _call_with_retry: 3 attempts, exp backoff
     │   └─ provider.generate_text  ← Gemini Flash | Claude Sonnet | ...
     ├─ _extract_json: strip ```fences``` and prose
     └─ schema.model_validate: 1 corrective retry on bad JSON
5. redact.rehydrate(draft) restores PII tokens
6. guardrail.enforce(draft) blocks "as an AI", leaked tokens, single-line emails
7. Return + persist to followups + audit + emit_event
```

Each step has tests; if a future hire breaks one, CI catches it.

### Security model

| Layer | What it does |
|---|---|
| JWT bearer in localStorage | Stateless auth; `tv` claim invalidates all tokens on logout |
| `assert_owns_client` etc. | Every write checks the client/proposal belongs to caller |
| Postgres RLS + non-superuser role | Even a buggy `WHERE` clause physically can't leak across tenants |
| Rate limits (slowapi) | 30/min login per IP, 10/hour AI per user |
| ed25519 audit chain | Operator with DB access can't silently edit a row — verify endpoint catches it |
| PII redactor | Email/phone/PAN/GSTIN/Aadhaar tokenised before any LLM call |
| Output guardrail | "As an AI", prompt-injection echo, single-line emails — blocked |
| Kill-switch | One click stops every outbound AI call in <1s |
| CSP-equivalent headers | HSTS, X-Frame-Options DENY, Referrer-Policy, Permissions-Policy |

---

## 7. When you're ready to deploy

**Tier 1 — Cheapest, fastest (one-person SaaS)**

| Component | Provider | Cost | Why |
|---|---|---|---|
| Backend (FastAPI) | **Render** or **Railway** or **Fly.io** | ~$10-25/mo | One-click Docker deploy; free TLS; auto-redeploy on git push |
| Frontend (React build) | **Vercel** or **Netlify** | $0 free tier | CDN, free TLS, deploy preview per PR |
| Postgres + pgvector | **Neon** (serverless) or **Supabase** | $0-25/mo | pgvector available on both; automated backups; PITR included |

Total: **$0-50/mo** for the first 50 users. Sign up, point env vars, push.

**Tier 2 — Once you have ≥10 paying tenants**

| Component | Provider | Why upgrade |
|---|---|---|
| Backend | **AWS Fargate** / **GCP Cloud Run** behind ALB | autoscale, multi-region |
| Frontend | **CloudFront + S3** | tighter control, custom error pages |
| Postgres | **RDS Aurora** / **Cloud SQL** | replicas, point-in-time recovery |
| Secrets | **AWS Secrets Manager** / **GCP Secret Manager** | rotation, audit |
| Observability | **Sentry** + **Datadog** / **Grafana Cloud** | already wired in code, just add the DSNs |

### Pre-deploy checklist (from `docs/production-readiness.md`)

- [ ] Set `ENV=production` (turns on fail-fast secret validation)
- [ ] `JWT_SECRET` ≥32 random chars, from a real secret manager
- [ ] `ADMIN_PASSWORD` set; rotate after first login
- [ ] `AUDIT_SIGNING_KEY` set in env (not auto-generated) for prod
- [ ] `CORS_ORIGINS` = your real frontend URL only (no `*`)
- [ ] `DB_ENGINE=postgres`, `POSTGRES_URL` points at managed Postgres
- [ ] `RATE_LIMIT_ENABLED=true`
- [ ] Optional: `SENTRY_DSN` + `REACT_APP_SENTRY_DSN` for error tracking
- [ ] Optional: `EMERGENT_LLM_KEY` (or `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` for direct providers)
- [ ] Run the schema: `psql -f backend/db/sql/0001_initial.sql`
- [ ] First boot creates the admin user; verify you can log in
- [ ] Visit `/admin` → Run verify → audit chain shows `ok=True`

---

## 8. Common issues + fixes

| Symptom | Cause | Fix |
|---|---|---|
| Login fails immediately with 401 | `ADMIN_PASSWORD` env not set on first boot → admin user never created | Set `ADMIN_PASSWORD` in `.env`, drop and re-init the DB or call `seed_admin()` |
| `RuntimeError: JWT_SECRET must be ≥32 chars in production` | You set `ENV=production` with a short secret | Generate one: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| Dashboard shows 0 of everything | You logged in as a non-admin user (your own register) — they don't get seeded data | Either log in as `founder@bytehubble.com` or create some clients/proposals via the UI |
| `pip install` fails on `emergentintegrations` | It's a private package | It's optional. Tests + UI work without it. Install via `pip install -r requirements-runtime.txt` only if you have Emergent's index credentials |
| AI follow-up returns 400 "No AI API key configured" | No LLM provider credentials | Either set `EMERGENT_LLM_KEY`, or `pip install openai && export OPENAI_API_KEY=...` and `AI_PROVIDER=openai` |
| Frontend says "Network error" on every call | `REACT_APP_BACKEND_URL` wrong / backend not running | Check `frontend/.env`; check `curl http://localhost:8000/api/` |
| `docker compose up` fails — port already in use | You have a system Postgres or Mongo running | `lsof -i :5432` or `lsof -i :27017`, kill it, or change ports in `docker-compose.yml` |
| `403 Admin only` on `/admin` | Logged-in email != `ADMIN_EMAIL` env | Set `ADMIN_EMAIL` to your email + restart, or log in as the founder |

---

## 9. Where to dig deeper

| Doc | What |
|---|---|
| [`README.md`](README.md) | Project summary + CI status |
| [`docs/data-schema.md`](docs/data-schema.md) | Every collection / table — fields, indexes, RLS |
| [`docs/runbook-pg-cutover.md`](docs/runbook-pg-cutover.md) | Mongo → Postgres migration playbook |
| [`docs/production-readiness.md`](docs/production-readiness.md) | 10-item go-live gate + AI threat model |
| [`memory/PRD.md`](memory/PRD.md) | Original product brief, locked architecture rules |
