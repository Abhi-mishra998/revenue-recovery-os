# Production readiness review

Status: **GO with named caveats.** All ten gate items reviewed; what could be
fixed in code has been. Items that require deployment / operator action are
listed with concrete recommendations and owners.

Generated against commit at the head of `main` (sprint F commits).

| # | Item | Status | Receipts |
|---|------|--------|----------|
| 1 | Secrets management | ✅ PASS | `server.py:_validate_boot_secrets` (F.2) |
| 2 | HTTPS | ⚠️ DEPLOY | HSTS shipped; cert is operator-side |
| 3 | Database backups | ⚠️ DEPLOY | No code; runbook below |
| 4 | Input size limits | ✅ PASS | F.3 middleware + Pydantic per-field |
| 5 | Error handling | ✅ PASS | F.4 global handler; structured logs from C.* |
| 6 | Rate limits | ✅ PASS | auth + AI; recommendation for writes |
| 7 | Dependency vulns | ✅ PASS | F.5: backend 0 high; frontend 0 high |
| 8 | Session / cookie security | ⚠️ DESIGN | JWT in `localStorage` (intentional); upgrade path documented |
| 9 | DPDP basics | ✅ PASS | F.6 export + delete + audit-logged |
| 10 | AI threat model | ✅ PASS | Below; mitigations live in the code today |

Tests covering the gate: **193 passed, 1 skipped** (last run on
`DB_ENGINE=postgres`).

---

## 1. Secrets management — PASS

**Have:**
- All secrets in env (`JWT_SECRET`, `ADMIN_PASSWORD`, `MONGO_URL`,
  `POSTGRES_URL`, `AUDIT_SIGNING_KEY`).
- `.env` is `.gitignore`d; `.env.example` ships placeholders only.
- **Fail-fast at boot** when `ENV=production` is set
  (`server.py:_validate_boot_secrets`): `JWT_SECRET` must be ≥32 chars,
  must not start with `test-`/`ci-`/`dev-`/`changeme`, `CORS_ORIGINS`
  must be an explicit allowlist (no `*`).
- ed25519 audit signing key: env-first, then auto-generated and persisted
  in `db.settings` with a loud warning in `ENV=production`.

**Recommended next:**
- Move from env to a real secret store in prod
  (AWS Secrets Manager, GCP Secret Manager, Doppler, Vault).
- Rotate `JWT_SECRET` — when you rotate, every token instantly invalidates
  (good); plan a maintenance window or use `kid` headers for graceful
  rotation later.
- Rotate `AUDIT_SIGNING_KEY` requires a chain-break commit
  (`public_key_fp` will change). Plan annually + after any suspected leak.

## 2. HTTPS — DEPLOY (operator)

**Have in code:**
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` on every
  response (`server.py:add_security_headers`).
- `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy`, `Permissions-Policy` set.

**Deploy must do:**
- Terminate TLS at the load balancer (ALB/Cloudflare/Caddy/nginx).
- Set `X-Forwarded-Proto` and configure FastAPI / uvicorn with
  `--proxy-headers --forwarded-allow-ips=<lb_cidr>` so the app sees
  `request.url.scheme == "https"`.
- Don't expose port 8000/8765 to the public.
- Auto-renew certs (Let's Encrypt / Cloudflare-managed).

**Not done by us; not blockable from code.**

## 3. Database backups — DEPLOY (operator)

**Have in code:** none. There is no in-app backup process — that's a deploy
responsibility on the managed DB (or a sidecar cron).

**Recommended runbook:**

| DB | Provider | Action |
|---|---|---|
| Postgres | RDS / Supabase / Neon | Enable automated daily snapshots + 7-day PITR window. Snapshots encrypted at rest. |
| Postgres | Self-hosted | `pg_dumpall \| gzip > backup-$(date +%F).sql.gz`, cron daily, rotate to S3 with lifecycle policy. |
| Mongo (rollback only) | — | `mongodump` weekly while still warm; delete the DB once postgres has been load-bearing for 30 days. |

**Test the restore monthly** — backups you've never restored aren't backups,
they're hope.

## 4. Input size limits — PASS

**Have:**
- Per-field: Pydantic `Field(max_length=…)` on every string body field in
  `server.py:127-243` (NAME_LEN=120, NOTES_LEN=4000, money capped at 1T).
- Per-request: `enforce_max_body_size` middleware (F.3) — default 5MB,
  env `MAX_REQUEST_BYTES`. Returns 413 with stable error code
  `request_too_large`.

**Test proof:** `test_prodgrade.py::TestMaxBodySize` (6MB rejected; normal
POST unaffected).

## 5. Error handling — PASS

**Have:**
- Global `_internal_error_handler` (F.4) catches every unhandled `Exception`,
  logs full traceback server-side with `request_id`, returns safe shape:
  `{detail: {code: "internal_error", message: "...", request_id: "..."}}`.
- HTTPException paths use stable shape `{detail: {code, message}}` for
  AI/body-limit errors; legacy string-only `detail` retained on auth paths.
- All `print()` replaced with structured `logger.info/.warning/.exception`
  (sprint C). JSON-formatted, request_id-tagged.
- Sentry hook backend (`init_sentry`, sprint C) and frontend
  (`initSentry`, sprint F.7) — both opt-in via env, both no-op silently
  when SDK or DSN is absent.

## 6. Rate limits — PASS

**Have (`server.py` decorators):**

| Endpoint | Limit | Key |
|---|---|---|
| `POST /auth/login` | 30/min | per IP |
| `POST /auth/register` | 10/min | per IP |
| `POST /auth/google/session` | 30/min | per IP |
| `POST /proposals/{id}/generate-followup` | 10/hour | **per user** (custom key_func decodes JWT sub) |

`RATE_LIMIT_ENABLED=false` disables limits for shared-IP CI runs.

**Recommended next:**
- Add a generic per-user rate limit on `POST/PATCH/DELETE` writes
  (~300/min/user) as a backstop. Not currently a problem because every
  authed write is owner-scoped and the user pays for their own DB time,
  but cheap insurance.
- The current limits are in-memory (slowapi default) — multi-process
  deploys need a Redis backend for slowapi so limits aren't per-process.

## 7. Dependency vulnerabilities — PASS

**Backend** (`pip-audit` on the active venv): **0 known vulnerabilities.**
F.5 bumped `fastapi` 0.110.1 → ≥0.138.1, pulling `starlette` ≥1.3.1 which
closes 8 advisories (PYSEC-2026-161/248/249, CVE-2024-47874, CVE-2025-54121,
CVE-2026-48817/48818).

**Frontend** (`yarn audit`):
- 0 high (was 5)
- 12 moderate, 1 low

All remaining moderate are **transitive deps of `react-scripts`** (jest,
jsdom, etc.) — dev/test toolchain only, never reach the production bundle.
CRA hasn't been maintained for 3+ years; permanent fix is migrating off
CRA to Vite (out of scope for this gate).

`form-data` and `ws` resolutions added in F.5 to close the high-severity ones.

## 8. Session / cookie security — DESIGN CHOICE

**Have:**
- JWT bearer tokens in `localStorage`, sent as `Authorization: Bearer …`.
  No cookies, no CSRF surface.
- Tokens carry `tv` (`token_version`); `POST /auth/logout` bumps the user's
  `token_version`, invalidating every outstanding token for that user
  across all devices in O(1). Verified by
  `test_auth_edge.py::test_logout_revokes_other_tokens_for_same_user`.
- 7-day expiry, no refresh tokens.

**Known trade-off:** localStorage is XSS-reachable. The mitigations:
- `X-Frame-Options: DENY` + tight CORS allowlist reduce XSS vectors.
- React 19 auto-escapes interpolated content; we don't use the unsafe-HTML
  injection escape hatch anywhere — `grep` for that API name in
  `frontend/src` returns zero hits.
- No third-party scripts on the auth-protected pages.

**Upgrade path (not blocked, ~half-day refactor):**
- Move JWT to `HttpOnly + SameSite=Strict + Secure` cookie set on
  `/auth/login`.
- Add CSRF middleware (synchronizer-token pattern in a `__csrf` cookie +
  `X-CSRF-Token` header on writes).
- Frontend stops touching the token — browser sends it automatically.
- Token-revocation logic (`tv` claim) unchanged.

## 9. DPDP basics — PASS

**Have (F.6):**

| Requirement | Where |
|---|---|
| Consent for stored contact data | Implicit on `POST /auth/register` — the user creates their own account. For client data they upload, they're the data fiduciary. |
| Data minimisation | Pydantic schemas reject any field not in the explicit `_CLIENT_UPDATE_COLS` / `_PROP_UPDATE_COLS` / `_INV_UPDATE_COLS` whitelist. No PII goes to LLM providers — `services/ai/redact.py` tokenises emails/phones/PAN/GSTIN/Aadhaar before any external call. |
| Right to access (export) | `GET /api/me/data` — full JSON dump of clients, proposals, invoices, activities, followups, events, client_memory. Frontend Settings page → "Download my data (JSON)". |
| Right to erasure (delete) | `DELETE /api/me` — cascade-deletes the user and every owned record (Postgres FK cascades; Mongo per-collection). Frontend Settings page with two-step confirm. |
| Audit trail of consent/erasure | Every export and deletion is signed into the audit chain as `me.data.export` / `me.account.delete` (the deletion fact survives even though the user row is gone). |
| Breach notification | Operator responsibility — runbook should include a Sentry alert routing rule when uncaught exception rate > N/min. |

**Test proof:** `test_prodgrade.py::TestExportMyData`,
`TestDeleteMyAccount` (4 tests).

**Recommended next:**
- Add a data-retention policy (e.g. auto-delete `audit_log` entries
  >7 years old per DPDP record-keeping limits).
- Add a "Privacy policy" link on /login + /register pages with a
  consent checkbox; copy lives outside this repo.
- If you accept payment/billing later, add a separate consent flag for
  marketing emails (DPDP requires granular consent for non-essential use).

## 10. AI endpoint threat model — PASS

The only LLM-touching surface is `POST /proposals/{id}/generate-followup`.

| Threat | Vector | Mitigation | Receipt |
|---|---|---|---|
| **Prompt injection echoing back to user** | Malicious text in `proposal.title` or `client.notes` makes the model output "ignore previous instructions" / "you are now…" | Output guardrail (`services/ai/guardrail.py`) blocks blacklist phrases and PII-token leaks before the draft reaches the user. | `test_ai_e2e.py::TestGuardrailIntegration` |
| **PII leak to LLM provider** | Email/phone/PAN/GSTIN/Aadhaar in proposal title gets shipped to OpenAI/Anthropic/Gemini | `services/ai/redact.py` tokenises every pattern before the prompt is rendered. Rehydrate happens server-side after validation; if the model echoes a token, the guardrail catches it. | `test_ai_e2e.py::TestPiiRedaction` (3) |
| **Cost amplification / runaway spend** | Authed user spams the endpoint, racks up LLM credits | Per-user rate limit 10/hour (key extracted from JWT); kill-switch (`POST /admin/killswitch`) blocks every outbound call in <1s (cached state); retry capped at `LLM_MAX_ATTEMPTS=3` with exponential backoff (~15s total wall time before 503). | `test_audit.py::TestKillSwitch` (3), `test_ai_e2e.py::TestProviderRetry` (2) |
| **Malformed output crashes server / leaks raw** | Model returns prose / fences / partial JSON | `client.generate_json` strips fences, runs `_extract_json`, validates against Pydantic schema; one corrective retry; otherwise `MalformedOutputError` → 502 with safe shape. | `test_ai_validator.py` (8) |
| **Provider downtime takes the app down** | LLM provider 500s for 10 minutes | Exponential-backoff retry (F.5 sprint E); on exhaustion `LLMProviderUnavailable` → 503 with `code='llm_unavailable'`. Frontend shows calm "AI busy, try again" panel with Retry button instead of red toast. | `test_ai_e2e.py::TestProviderRetry::test_raises_llm_unavailable_after_all_attempts_fail` |
| **Auto-send to recipient** | Bug / future feature turns a draft into an actual send | **Architectural rule**: Revora never auto-sends. Drafts return as text + a `mailto:` / `wa.me:` link; the human user clicks. Guardrail module's docstring documents this as a hard rule. | Code-review enforcement; no SMTP / WhatsApp Cloud API client in the codebase. |
| **Audit-chain tampering** | Operator with DB access edits a row | Chain is hash-linked and ed25519-signed; `GET /admin/audit-log/verify` walks every record and reports tampering. Postgres `audit_log` has no RLS — admin-only at app layer — but the signing key is the gate. | `test_audit.py::TestTamperDetection` (4) |
| **Embedding-based data exfiltration (future)** | Once `followups.embedding` is populated, an attacker could reconstruct PII from embeddings | Not yet a problem: no vectors are written. When semantic search is wired in, run redaction BEFORE embedding too; reuse `services/ai/redact.py`. Documented in `docs/data-schema.md`. | Future. |

**Kill-switch reasoning**: One env var (`ai_killswitch` in `db.settings`) or
one admin click and every LLM call returns 503 in <1s. Use it when:
- LLM provider is having a regional outage and retries make it worse.
- Cost-bound alert fires (cost-per-tenant > threshold).
- Vendor sends a suspicious model update and outputs go weird.

After the cause is resolved: flip back. The cached state invalidates on the
toggle endpoint (in-process only — multi-process deploys need a Redis
pub/sub or short TTL; documented in `server.py`).

---

## What broke during this review (and got fixed in F.*)

| Sprint | Finding | Fix |
|---|---|---|
| F.2 | `JWT_SECRET` length not validated; placeholder secrets could ship to prod | Boot-time validation; fail-fast in `ENV=production` |
| F.3 | No body-size cap; 100MB POST would allocate before Pydantic rejected | `enforce_max_body_size` middleware, 5MB default + env knob |
| F.4 | Uncaught exceptions returned FastAPI's default 500 with path info | `_internal_error_handler` → safe shape, traceback logged server-side only |
| F.5 | 8 starlette CVEs (via FastAPI 0.110); 5 high-severity frontend transitive | Bumped FastAPI; resolutions tightened for `form-data` + `ws` |
| F.6 | No DPDP export, no account-deletion endpoint | `GET /api/me/data`, `DELETE /api/me`, audit-logged + frontend Settings page |
| F.7 | Frontend had no Sentry hook | Opt-in `initSentry()` with lazy import; bundle unaffected when DSN absent |

---

## Open items (not blocking go-live, but get them in flight)

| Priority | Item | Owner |
|---|---|---|
| P0 | Set up automated DB backups + restore drill (item 3) | DevOps |
| P0 | Terminate TLS at load balancer; configure forwarded-proto headers (item 2) | DevOps |
| P1 | Move secrets to a real secret manager (item 1, "next") | DevOps |
| P1 | Distributed rate limiter (Redis-backed slowapi) once multi-process | Backend |
| P2 | JWT → HttpOnly cookie migration + CSRF (item 8, "upgrade path") | Backend |
| P2 | Migrate frontend off CRA to Vite (eliminates the 12 moderate transitive vulns) | Frontend |
| P3 | Data-retention job for `audit_log` (DPDP record-keeping limits) | Backend |
| P3 | Multi-admin role system (today: single `ADMIN_EMAIL`) | Backend |

---

**Sign-off** — this branch is safe to deploy with the DEPLOY-tagged items
above handled by whoever owns the prod environment.
