# Revora — Architecture, in Plain English

Read this once and you'll know what every moving part in this codebase is for,
why it's there, and what would break if you removed it. No jargon without an
explanation.

---

## 1. The 30-second mental model

Revora is a normal web app, built like Linear or Stripe internally:

```
   ┌──────────────────────┐         ┌──────────────────────┐
   │   YOUR BROWSER       │  HTTP   │   THE BACKEND        │
   │   (React app)        │ ──────► │   (FastAPI server)   │
   │   "the frontend"     │ ◄────── │   "the API"          │
   └──────────────────────┘  JSON   └──────────┬───────────┘
                                                │
                                                │ SQL
                                                ▼
                                     ┌──────────────────────┐
                                     │   POSTGRES DATABASE  │
                                     │   (where everything  │
                                     │    is stored)        │
                                     └──────────────────────┘
```

That's it. Three boxes. Everything else in this document is detail about
what's *inside* those three boxes and the rules that keep them safe.

When you visit `localhost:3000`, you're talking to box 1 (React in your
browser). When that page needs data — "show me my proposals" — it sends an
HTTP request to box 2 (FastAPI). Box 2 reads/writes box 3 (Postgres) and
sends JSON back. That's the entire loop.

---

## 2. The frontend (what runs in your browser)

**Folder**: `frontend/`

This is the React app. Everything the user *sees* is here. Think of it like
the dashboard of a car — buttons, gauges, screens. It doesn't store anything
permanently; it just renders data that the backend gives it and sends
keystrokes / clicks back.

### The technologies, one by one

| Thing | What it actually does |
|---|---|
| **React 19** | The library that turns "I want a button here" into actual pixels on screen. Lets us think in components (a `<Button>`, a `<Card>`) instead of raw HTML. |
| **Create React App (CRA)** + **Craco** | CRA is the standard starter kit that bundles all your React code into a single optimized file the browser can load. Craco lets us tweak CRA's default behavior without ripping it apart — we use it for things like the `@/` import alias and a custom build health-check plugin. |
| **React Router v7** | Handles "which page am I on?" without doing a full page reload. When you click "Clients", it just swaps in the Clients component instead of fetching a whole new HTML page. |
| **Tailwind CSS** | A CSS framework where you write styles inline as utility classes (`className="text-zinc-900 p-4"`) instead of writing a separate `.css` file. Fast to iterate, no naming things. |
| **shadcn/ui** | A collection of ~46 pre-built UI components (dialogs, dropdowns, tabs) that we copy *into* our codebase and own outright. Not a dependency — actual files in `frontend/src/components/ui/`. Built on Radix primitives (accessibility-correct unstyled components). |
| **framer-motion** | Animation library. Used for the login page's animated counter, the live ledger that cycles, page transitions. |
| **lucide-react** | The icon set. Every `<Mail />`, `<Trash2 />`, `<ShieldCheck />` icon comes from here. ~1500 icons, all vectors. |
| **axios** | The HTTP client. When the frontend needs to talk to the backend, it uses axios. Wrapper around `fetch()` with nicer error handling and interceptors. |
| **@tanstack/react-query + swr** | Two libraries that handle "async data" — fetching from the backend, caching it, refetching when stale. We have both; mostly using direct axios calls right now. |
| **react-hook-form + zod** | Forms. `react-hook-form` manages "what did the user type" state efficiently. `zod` validates ("email must be a valid email"). |
| **sonner** | The little toast popups in the corner ("Client added", "Could not save"). |
| **recharts** | Charts (the donut on the Dashboard). |
| **yarn 1.22** | Package manager — installs libraries listed in `package.json`. We pin to yarn classic, not the newer yarn berry. |

### What lives where in the frontend

```
frontend/src/
├── pages/              # One file per route (Dashboard, Clients, Login, …)
├── components/         # Reusable building blocks
│   ├── Layout.jsx      # The sidebar + main content shell
│   ├── StatusPill.jsx  # The colored "active / cold / dead" badges
│   └── ui/             # shadcn primitives (we own them)
├── contexts/           # React Contexts — AuthContext holds login state
├── lib/                # api.js (the axios instance), format.js (₹ formatters)
├── App.jsx             # The router — maps URLs to pages
├── index.css           # Global styles + font imports
└── App.css             # The .revora-card, .cta-primary, .eyebrow-rule utility classes
```

### How the frontend talks to the backend

Every API call goes through `frontend/src/lib/api.js` — an axios instance
that automatically attaches the JWT token from `localStorage` to every
request. If the backend says "401 unauthorized", the interceptor kicks the
user back to `/login`.

The backend URL is configured via `REACT_APP_BACKEND_URL` (env var, defaults
to `http://localhost:8000`). All API routes start with `/api/`.

---

## 3. The backend (the API server)

**Folder**: `backend/`

This is the brain. It receives HTTP requests from the frontend, reads/writes
the database, calls AI providers when needed, enforces security rules, and
sends JSON back.

### The technologies, one by one

| Thing | What it actually does |
|---|---|
| **Python 3.12** | The language. We use modern Python (async/await, type hints everywhere). |
| **FastAPI** | The web framework. You define functions like `async def list_proposals(...)` and decorate them with `@app.get("/api/proposals")`. FastAPI handles the HTTP plumbing, request validation, and auto-generates OpenAPI docs at `/docs`. Fast because it's async (handles many requests concurrently on a single thread). |
| **Uvicorn** | The actual web server process. FastAPI is just the "shape" of the app; Uvicorn is what listens on a port and accepts TCP connections. You run `uvicorn server:app`. |
| **Pydantic** | Schema validation. Every request body and response is defined as a Pydantic class. If a request comes in with a missing field or wrong type, Pydantic rejects it *before* your code runs. |
| **asyncpg** | The Postgres driver. Talks to Postgres over the wire. Async = doesn't block while waiting for the database. |
| **motor** | The MongoDB async driver. Used only when `DB_ENGINE=mongo` (legacy / rollback path — see §5). |
| **PyJWT** | Issues + verifies the JWT login tokens. |
| **bcrypt** | Hashes passwords. We never store plaintext passwords — only the bcrypt hash. |
| **cryptography (ed25519)** | The crypto library used to sign the audit log entries (see §8). |
| **slowapi** | Rate limiting. "Max 30 logins/minute per IP", "max 10 AI generations/hour per user". |
| **emergentintegrations** | A wrapper SDK around multiple LLM providers (OpenAI / Anthropic / Google). One key (`EMERGENT_LLM_KEY`) instead of three. |
| **pandas, numpy** | Used in the data-features layer for proposal scoring math. |
| **ruff** | The linter. Catches dead code, bad imports, style issues. Also runs as a formatter. |
| **pytest** | The test runner (see §10). |

### What lives where in the backend

```
backend/
├── server.py                  # All HTTP endpoints (~48 routes, 1500 lines)
├── db/
│   ├── pg.py                  # Postgres connection pool + helpers
│   ├── mongo.py               # Mongo client (legacy)
│   └── sql/0001_initial.sql   # The schema (tables, indexes, RLS policies)
├── services/
│   ├── auth.py                # Login, JWT issue/verify
│   ├── audit.py               # The ed25519-signed audit chain
│   ├── memory.py              # Derives "client memory" signals from activity
│   ├── obs.py                 # Structured logging + Sentry
│   ├── seed.py                # Demo data (12 clients, 14 proposals…)
│   ├── db/repos/              # One file per table (clients.py, proposals.py…)
│   │                          # All SQL lives here. server.py never writes SQL.
│   ├── ai/
│   │   ├── client.py          # Provider-agnostic LLM caller + retry
│   │   ├── prompts.py         # Versioned prompt templates
│   │   ├── router.py          # Picks the model based on proposal value
│   │   ├── redact.py          # Strips PII before sending to AI
│   │   ├── guardrail.py       # Checks AI output isn't garbage
│   │   └── schemas.py         # Pydantic schemas for AI response shape
│   └── data/
│       ├── extract_proposal_features.py  # Turns a proposal into ML inputs
│       └── predict_close_probability.py  # The simple win-rate model
├── tests/                     # 186 tests
├── scripts/                   # One-off scripts (migrate_to_postgres.py)
└── requirements.txt           # Python dependencies
```

### The "endpoint" pattern

Every URL the frontend can call is a function in `server.py`. Example:

```python
@api_router.get("/clients")
async def list_clients(user = Depends(get_current_user)):
    return await client_repo.list_for_owner(user.id)
```

That single line gives you:
- A GET `/api/clients` endpoint
- Auto auth check (`Depends(get_current_user)` — fails with 401 if no valid JWT)
- Auto JSON serialization of the return value
- Auto entry in the OpenAPI docs at `/docs`

The actual SQL lives in `client_repo` (a repository file). Endpoints stay
thin; repos hold the database queries. This separation means we can swap
Postgres for Mongo by swapping the repo, not the endpoint.

---

## 4. The database (where everything is stored)

**Engine**: PostgreSQL 16 + the **pgvector** extension (so we can store
1536-dimension embeddings for future semantic search of AI drafts).

### The tables

There are 10 of them. Plain-English purpose:

| Table | What it stores |
|---|---|
| `users` | Login accounts — email, hashed password, name |
| `clients` | The companies you work with (FinKart, Bloom Wellness, …) |
| `proposals` | The deals you've sent to those clients ("Brand identity rebuild — ₹6.2 L") |
| `invoices` | Bills you've issued (paid / unpaid / overdue) |
| `activities` | A log of "I called Bloom on Tuesday", "they replied on Friday" |
| `followups` | The AI-generated draft messages, with model name + confidence |
| `events` | An append-only stream of "something happened" markers — used for analytics & memory derivation |
| `client_memory` | Derived facts: "this client prefers WhatsApp, replies within 3 days" |
| `audit_log` | The tamper-proof signed log (see §8) |
| `settings` | App-wide config: the kill-switch, signing keys |

### The owner_id pattern (multi-tenancy)

Every table except `users` has an `owner_id` column. This is the user that
owns the record. Two founders using Revora can never see each other's
clients because every query filters by `owner_id = me`.

Postgres takes this one step further with **Row-Level Security (RLS)** — see
§8.

### The dual-engine thing (Postgres OR Mongo)

The app supports two databases. You flip via the `DB_ENGINE` env var:

- `DB_ENGINE=postgres` — production
- `DB_ENGINE=mongo` — fallback / rollback path

This sounds weird but the reason is real: we migrated from Mongo to Postgres
and kept Mongo as a "panic button" in case Postgres misbehaves in
production. Both schemas are kept in sync. The cutover playbook is in
`docs/runbook-pg-cutover.md`.

In normal operation you'll never touch Mongo. It's a parachute.

---

## 5. Docker (how the databases run locally)

**File**: `docker-compose.yml`

Docker is a way to run software in isolated little boxes called containers.
Instead of installing Postgres on your laptop directly, we run it inside a
Docker container. Same for Mongo. They share your laptop's CPU and memory
but their files, configs, and ports are sandboxed.

When you run `docker compose up -d`, two containers start:

| Container | What it is | Port |
|---|---|---|
| `revora-postgres` | Postgres 16 with pgvector extension pre-installed (image: `pgvector/pgvector:pg16`) | 5432 |
| `revora-mongo` | MongoDB 7 (image: `mongo:7`) | 27017 |

Each one mounts a Docker volume so the data survives `docker compose down`.

The backend (FastAPI) does **not** run in Docker — it runs natively with
`uvicorn`. Same for the frontend (`yarn start`). Only the databases are
containerised, because they're the things you don't want to install
manually.

Why this matters: if you nuke your laptop and clone the repo on a new one,
`docker compose up -d && yarn && pip install -r requirements.txt` and you're
running. No "install Postgres, configure pg_hba.conf, run initdb…".

---

## 6. Authentication (how login works)

The flow:

1. User submits email + password to `POST /api/auth/login`.
2. Backend looks up the user, checks `bcrypt.verify(password, user.password_hash)`.
3. If OK, backend signs a **JWT** (JSON Web Token) — a base64-encoded blob
   containing `{user_id, token_version, expiry}` signed with `JWT_SECRET`.
4. Frontend stores the JWT in `localStorage`.
5. Every subsequent request includes `Authorization: Bearer <jwt>`.
6. The backend's `get_current_user` dependency decodes the JWT, looks up
   the user, and passes them to the endpoint.

### Why `token_version`

When you log out (or change your password), we want to invalidate all your
existing JWTs immediately — not wait for them to expire. We do this by
bumping `users.token_version` in the DB. The JWT contains the version it
was signed with; if the current DB version is higher, the JWT is rejected.

### Google OAuth

There's also a "Sign in with Google" path via `auth.emergentagent.com` — a
hosted Emergent OAuth proxy. After Google confirms identity, it redirects
back to our frontend with a token, which we exchange for our own JWT. Same
end state.

### Demo credentials

On first boot, if `ADMIN_EMAIL` and `ADMIN_PASSWORD` env vars are set, the
backend creates that user automatically. That's the `founder@bytehubble.com`
account you see pre-filled on the login page.

---

## 7. RLS — Row-Level Security (Postgres tenant isolation)

This is what you wrote as "RLA". RLS = Row-Level Security. It's a Postgres
feature that enforces "you can only see your own rows" at the *database*
level, not in application code.

### Why it matters

In application code, every `SELECT` should filter by `WHERE owner_id = me`.
But humans write buggy code. One missing `WHERE` clause and Bob suddenly
sees Alice's clients.

RLS removes the option of the bug:

1. We create a special Postgres role `revora_app` (not a superuser).
2. Every connection from the backend runs as `revora_app`.
3. On every request, the backend issues `SET LOCAL app.current_user_id = '<uuid>'`.
4. Every tenant table has a policy:
   `CREATE POLICY t ON clients USING (owner_id = current_setting('app.current_user_id')::uuid);`
5. From that point on, **Postgres physically refuses to return any row where
   `owner_id` doesn't match**, even if the SQL has no `WHERE` clause.

It's belt + braces. Application code still adds `WHERE owner_id = me`
defensively, but RLS catches the bugs the app doesn't.

This is tested in `backend/tests/test_pg_rls.py` — we connect as Alice, try
to read Bob's rows, assert nothing comes back.

---

## 8. The audit chain (the trust story)

**File**: `backend/services/audit.py`

Every write operation (create client, update proposal, generate AI draft,
delete account) is recorded in the `audit_log` table. But it's not just
recorded — it's *cryptographically signed* so nobody (not even a malicious
admin with database access) can edit history without it showing.

### How the chain works

Each row has:
- `seq` — a monotonic number (1, 2, 3, …)
- `prev_hash` — the hash of the previous row
- `record_hash` — `sha256(this row's fields)`
- `signature` — that hash signed with our private **ed25519** key
- `public_key_fp` — fingerprint of the public key used (so you can rotate keys)

If anyone changes a row in the middle of the chain:
- The row's `record_hash` no longer matches its contents
- Or the next row's `prev_hash` no longer matches the modified row's hash
- The chain "breaks" and the `/audit/verify` endpoint flags exactly where

This is the same idea as a blockchain, minus the consensus / mining — we're
the only writer.

### The ed25519 key

ed25519 is a public-key signature scheme. Fast, tiny keys (32 bytes),
modern crypto. The key is either:
- Loaded from `AUDIT_SIGNING_KEY` env var (base64-encoded), or
- Auto-generated on first boot and stored in `settings.audit_signing_key`
  (with a log warning telling you to copy it to env for real production)

The login page shows the first 16 hex chars of the public key fingerprint
(`5277·9747·1b6b·0905`) as the "live audit chain" indicator. That's not
decoration — it's pulled from the actual key in this codebase.

### What gets logged

Examples of action strings:
- `client.create`, `client.update`, `client.delete`
- `proposal.create`, `proposal.update`, `proposal.delete`
- `ai.followup.generate`
- `user.delete` (the DPDP cascade — see §9)
- `auth.login`, `auth.logout`

If you ever need to prove to a regulator "here is everything we did with
client X's data", the audit log is the answer.

---

## 9. DPDP — Indian data privacy law

DPDP = Digital Personal Data Protection Act, 2023. The Indian equivalent of
GDPR. Two endpoints we built to comply:

### Export

`GET /api/me/data` — returns a JSON blob containing every record this user
owns (their user row, all clients, proposals, invoices, activities,
followups, events, client_memory). User downloads it, has their data.

### Delete

`DELETE /api/me` — cascade-deletes the user and *every* record they own. Run
in a transaction. Before the delete commits, we write a final audit entry
(`user.delete`) signed into the chain — so even after the user is gone,
there's tamper-proof proof we deleted them at time T.

After delete: their existing JWT is dead (no user row to look up).

These are tested end-to-end in `backend/tests/test_prodgrade.py` — Alice
deletes herself; we verify Bob's data is untouched and Alice's records are
all gone.

---

## 10. The AI layer

**Folder**: `backend/services/ai/`

This is where the "Generate Follow-Up" button gets its drafts.

### The provider abstraction

We use `emergentintegrations` — a small SDK that sits in front of OpenAI,
Anthropic, and Google Gemini. One API key (`EMERGENT_LLM_KEY`) talks to all
three providers, so we can route requests to whichever is cheaper or more
appropriate.

We can also bypass it and use direct provider keys (`OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`) if needed.

### Model routing by value

`services/ai/router.py` picks the model based on the proposal's `value_inr`:

- **Simple tier** (default, low-value deals) → Gemini Flash (fast, cheap)
- **Complex tier** (high-value deals) → Claude Sonnet (better reasoning)

Why: we don't need a frontier model to write "Hey Rohit, just following up
on last week's note". We *do* want it on a ₹50 L proposal.

### PII redaction (before)

`services/ai/redact.py` runs before every LLM call. It finds and replaces:
- Email addresses → `[EMAIL_0]`
- Phone numbers → `[PHONE_0]`
- PAN numbers, GSTIN, Aadhaar → tokens

After the LLM responds, `rehydrate()` puts the real values back. The LLM
provider never sees the customer's real PII.

### Output guardrails (after)

`services/ai/guardrail.py` checks the LLM output for:
- Refusal patterns ("As an AI…", "I cannot…") — retry
- Leaked redaction tokens (the LLM forgot to use real names) — retry
- Schema violations (wrong JSON shape) — retry once with a corrective message

### Schema validation

The LLM is asked to return JSON in a specific shape (`FollowUpDraft` Pydantic
model with `whatsapp` and `email` fields). We validate it; if invalid, one
corrective retry; if still bad, hard error.

### The kill-switch

In `settings`, there's a `kill_switch_enabled` boolean. Admin-only. When ON,
every AI endpoint returns 503 instantly with no LLM call. Use it if:
- A provider is having an outage (avoid timeouts)
- You suspect a cost runaway (avoid surprise bills)
- A jailbreak is being attempted

### Tests with no real LLM calls

All AI tests use `StubProvider` — a fake LLM that returns canned responses.
So our test suite never hits OpenAI / Anthropic / Gemini. Fast, free,
deterministic.

---

## 11. Rate limiting

**Library**: `slowapi`

Two limits enforced today:

| Endpoint | Limit | Why |
|---|---|---|
| `POST /api/auth/login` | 30/min per IP | Brute-force protection |
| `POST /api/followups/generate` | 10/hour per user | Cost containment |

Toggle off with `RATE_LIMIT_ENABLED=false` (useful in tests).

When you hit the limit, the API responds 429 with a Retry-After header.

---

## 12. Middleware (the request pipeline)

When a request hits the server, it passes through several layers before
reaching your endpoint code:

```
HTTP request
  │
  ├─► 1. enforce_max_body_size        (reject if > 5 MB)
  ├─► 2. add_security_headers         (X-Frame-Options: DENY, HSTS, etc.)
  ├─► 3. request_context_and_access_log (assign X-Request-ID, log)
  ├─► 4. CORSMiddleware               (check origin allowed)
  ├─► 5. slowapi rate limiter         (check rate limits)
  ▼
your endpoint function
```

Each layer can short-circuit the request. The 5 MB cap prevents someone
uploading a 10 GB file to crash the server. The security headers prevent
clickjacking, MIME sniffing, etc.

---

## 13. Structured logging + observability

**File**: `backend/services/obs.py`

Every log line is a JSON object:
```json
{"ts": "...", "level": "INFO", "request_id": "abc123", "user_id": "...", "msg": "..."}
```

JSON logs are machine-parseable — you can pipe them into Datadog, Grafana
Loki, CloudWatch, etc., and run queries like "show me all 500 errors for
user X in the last hour".

**Sentry integration**: if `SENTRY_DSN` is set, exceptions are auto-reported
to Sentry. Same for the frontend (`REACT_APP_SENTRY_DSN`).

Every request gets a unique `X-Request-ID` — if a user reports a bug, ask
for that ID and you can grep the logs.

---

## 14. CI/CD (GitHub Actions)

**File**: `.github/workflows/test.yml`

Every push to the repo triggers 4 jobs that run in parallel on GitHub's
servers:

| Job | What it does |
|---|---|
| **frontend** | `yarn install --frozen-lockfile && yarn build` — make sure the React app still builds |
| **lint** | `ruff check && ruff format --check` — Python style + dead-code checks |
| **pytest (mongo)** | Spins up Mongo 7, runs all 186 backend tests against it |
| **pytest (postgres)** | Spins up Postgres 16 + pgvector, runs the same 186 tests against it |

If anything fails, GitHub shows a red ✗ next to the commit and refuses to
merge into `main` (if branch protection is on). Coverage reports + JUnit
results are saved as artifacts.

---

## 15. Tests (186 of them)

**Folder**: `backend/tests/`

Each file targets one concern. Notable ones:

| File | What it proves |
|---|---|
| `test_revora_api.py` | Every endpoint returns the documented shape |
| `test_audit.py` | The ed25519 chain detects tampering |
| `test_pg_rls.py` | Alice physically cannot read Bob's rows |
| `test_isolation.py` | Cross-tenant safety at the application level |
| `test_ai_e2e.py` | Generate-follow-up works end-to-end with a stub LLM |
| `test_ai_router.py` | Low-value proposals → simple model, high-value → complex |
| `test_ai_validator.py` | Bad JSON from the LLM is retried once, then rejected |
| `test_ai_redact_guardrail.py` | Emails/phones never leak to the LLM |
| `test_prodgrade.py` | 5 MB body limit, DPDP export shape, delete cascade |
| `test_migration.py` | Data survives a Mongo → Postgres migration |
| `test_dashboard_math.py` | "Revenue at risk", "overdue" numbers are correct |
| `test_obs.py` | JSON log lines have the right fields |

The frontend has no automated tests — we rely on TypeScript-style ESLint
checks + the build step catching errors.

---

## 16. Environment variables (the configuration knobs)

Defined in `backend/.env` (not checked into git):

| Var | Purpose |
|---|---|
| `DB_ENGINE` | `postgres` or `mongo` |
| `POSTGRES_URL` | Connection string for Postgres |
| `MONGO_URL` | Connection string for Mongo |
| `DB_NAME` | Database name |
| `JWT_SECRET` | Used to sign login tokens (≥ 32 chars in prod) |
| `AUDIT_SIGNING_KEY` | Base64 ed25519 key for the audit chain (auto-generates if absent) |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Seed founder account on first boot |
| `CORS_ORIGINS` | Comma-separated list of allowed frontend origins |
| `RATE_LIMIT_ENABLED` | `true` / `false` |
| `EMERGENT_LLM_KEY` | The LLM gateway key |
| `AI_PROVIDER`, `AI_ROUTE_*` | Override which model gets used where |
| `SENTRY_DSN` | Optional — error reporting |
| `ENV` | `production` enables stricter checks |

Frontend env (in `frontend/.env`):

| Var | Purpose |
|---|---|
| `REACT_APP_BACKEND_URL` | Where the React app sends API calls |
| `REACT_APP_SENTRY_DSN` | Frontend error reporting |

---

## 17. The directory map (what's in the repo)

```
revenue-recovery-os/
├── archi.md                    ← you are here
├── README.md                   ← short project intro
├── SETUP.md                    ← step-by-step setup + demo script
├── docker-compose.yml          ← Postgres + Mongo container definitions
├── .github/workflows/test.yml  ← CI pipeline definition
├── .gitignore                  ← what git ignores (node_modules, .env, etc.)
│
├── backend/                    ← FastAPI server
│   ├── server.py               ← all HTTP routes
│   ├── db/                     ← Postgres + Mongo client wiring
│   ├── services/               ← business logic + AI + audit
│   ├── tests/                  ← 186 pytest tests
│   ├── scripts/                ← one-off scripts (mongo→pg migrator)
│   ├── requirements.txt        ← Python deps
│   ├── pytest.ini              ← test config (parallel workers)
│   └── ruff.toml               ← linter config
│
├── frontend/                   ← React app
│   ├── src/                    ← all UI code
│   ├── package.json            ← JS deps
│   ├── craco.config.js         ← CRA tweaks
│   ├── tailwind.config.js      ← Tailwind config
│   └── plugins/                ← custom Webpack health-check plugin
│
├── docs/                       ← deeper docs
│   ├── data-schema.md          ← every table, every column
│   ├── runbook-pg-cutover.md   ← Mongo → Postgres migration playbook
│   └── production-readiness.md ← 10-item go-live checklist
│
├── memory/                     ← PRD + project context (not a database)
└── test_reports/               ← Saved test runs for evidence
```

---

## 18. A typical request, end-to-end

So you understand how the pieces talk:

1. You click **"New proposal"** on `localhost:3000/proposals`.
2. React renders the dialog. You fill it in and click **Create**.
3. The form handler calls `api.post('/proposals', body)`.
4. Axios attaches your JWT to the request header.
5. The request hits Uvicorn, then enters FastAPI's middleware pipeline:
   body-size check → security headers → request-ID stamp → CORS → rate limit.
6. FastAPI routes the request to `create_proposal()` in `server.py`.
7. `Depends(get_current_user)` decodes your JWT, looks you up in `users`,
   confirms `token_version` matches. If yes, you're attached to the request
   as `user`.
8. `create_proposal()` calls `proposal_repo.create(owner_id=user.id, ...)`.
9. The repo runs an `INSERT ... RETURNING *` against Postgres. RLS confirms
   the `owner_id` matches `app.current_user_id`.
10. We also write an `audit_log` row, signed with ed25519, chained to the
    previous row.
11. The new row is returned to `create_proposal()`, serialized to JSON, sent
    back to the browser.
12. React's `onSaved` callback fires, the dialog closes, the proposals list
    refetches and re-renders.

Total elapsed: ~50 ms locally.

---

## 19. Glossary (jargon, deciphered)

| Term | Plain meaning |
|---|---|
| **API** | An HTTP service. Frontend asks it for data. |
| **JWT** | A signed login token. Lives in the browser, sent with every request. |
| **RLS** | Postgres "row-level security" — DB-enforced "you can only see your own rows". |
| **bcrypt** | The algorithm we hash passwords with. Slow on purpose so brute-forcing is expensive. |
| **ed25519** | Modern crypto signature scheme. Used to sign the audit log. |
| **CORS** | Browser security: "is this frontend origin allowed to call this API?". |
| **Pydantic** | Python schema-validation library. Defines request/response shapes. |
| **Async / await** | Python keywords that let one process handle many requests at once without threads. |
| **shadcn/ui** | A pattern of *owning* (not importing) your UI components. |
| **Radix** | Unstyled, accessibility-correct UI primitives (the engine under shadcn). |
| **Tailwind** | CSS-as-utility-classes framework. |
| **CRA** | Create React App — the "official" React starter. |
| **Craco** | Wrapper that lets you tweak CRA without forking it. |
| **Uvicorn** | The Python web server process that runs FastAPI. |
| **pgvector** | A Postgres extension that lets you store + search vector embeddings. |
| **Mongo** | A document-oriented database. We kept it as a fallback. |
| **DPDP** | India's Digital Personal Data Protection Act, 2023. |
| **PII** | Personally Identifiable Information (email, phone, PAN, Aadhaar). |
| **kill-switch** | Admin toggle to disable AI endpoints instantly. |
| **slowapi** | The rate-limiting library. |
| **Sentry** | Error-reporting service. Optional. |
| **Docker container** | A sandboxed process. We use it to run Postgres + Mongo locally. |
| **GitHub Actions** | CI service that runs tests on every push. |
| **Repo (repository)** | In our code, a file with all SQL for one table. Not "GitHub repo". |
| **Middleware** | Code that runs on every request before/after the endpoint. |

---

## 20. What makes this project different from a generic SaaS

If you're comparing Revora to a starter template, here's what is *not*
boilerplate and worth understanding:

1. **The audit chain** — most apps log to a normal table; we sign each entry
   and chain them. You can prove what happened.
2. **Postgres RLS** — most apps trust application code to filter rows; we
   make Postgres enforce it.
3. **PII redaction before LLM** — most "AI features" send raw customer data
   to OpenAI. We mask it first.
4. **Model routing by deal value** — most apps use one model for everything;
   we route cheap proposals to a cheap model.
5. **Kill-switch** — most apps have no escape hatch when an AI bill goes
   crazy or a provider melts down.
6. **Dual-engine DB** — most apps pick one database and live with it; we
   kept Mongo as a rollback path for the Postgres migration.
7. **DPDP export + delete** — most apps "add it later"; we built it on day
   one and tested it.

Each of these costs a small amount of complexity and buys real trust /
safety. That's the project's character.

---

*Last updated: 2026-06-28. If a file or library here got renamed since,
trust the codebase, not this document — but tell me so I can fix it.*
