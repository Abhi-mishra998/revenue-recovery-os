# DEPLOY — Revora (Day 4)

> Total click time: ~25 minutes if everything goes right.
> Stack: Neon Postgres → Render backend → Vercel frontend → (optional) Cloudflare DNS.

---

## Step 0 — Pre-flight (you've done these)

- [x] Neon project created, DSN in hand
- [x] All four migrations applied to Neon (`0001 → 0004`)
- [x] Local secrets generated (see `backend/.env.production.example`)
- [x] `render.yaml` at repo root, `frontend/vercel.json` in place

If the repo isn't pushed yet, push it now — Render + Vercel both read from GitHub.

```bash
git add -A
git commit -m "deploy(D4): render + vercel configs + prod env template"
git push origin main
```

---

## Step 1 — Neon (apply schema, then verify)

Console: <https://console.neon.tech>

```bash
# One-shot migration runner — applies every .sql in db/sql/ in order.
# Idempotent — safe to re-run on a half-migrated DB.
cd backend
source .venv/bin/activate
POSTGRES_URL='postgresql://...' python -m scripts.apply_migrations

# Sanity check
psql "$POSTGRES_URL" -c '\dt'    # 12 tables expected
psql "$POSTGRES_URL" -c "SELECT pg_has_role(CURRENT_USER, 'revora_app', 'MEMBER')"  # t
```

**Why the role-membership check matters**: managed Postgres (Neon, RDS) gives
you a non-superuser as the connecting role. `SET LOCAL ROLE revora_app` for
RLS fails unless that user is a member. Migration `0005_grant_app_role.sql`
grants membership to whoever runs the migration — that's why the
`pg_has_role` query should return `t` after migrate.

---

## Step 2 — Render (backend)

Console: <https://dashboard.render.com>

1. **Sign in with GitHub.**
2. **New → Blueprint** → pick this repo, branch `main`. Render reads `render.yaml`.
3. **Approve the plan** — one web service named `revora-backend` on the free plan.
4. **Environment tab** — paste the values marked `sync: false`:

   | Key | Where it comes from |
   |---|---|
   | `POSTGRES_URL` | Neon console → Connection string |
   | `JWT_SECRET` | The 64-char value the secret-gen script printed |
   | `AUDIT_SIGNING_KEY` | The ed25519 base64 value from the same script |
   | `ADMIN_PASSWORD` | A real password you'll remember (≥12 chars) |
   | `EMERGENT_LLM_KEY` | Same value as in your local `backend/.env` |
   | `CORS_ORIGINS` | **Leave blank for now** — set after Vercel deploys |

5. **Deploy.** First build is ~3-4 minutes (pip install pandas/asyncpg/etc).
6. **Verify** — visit the Render URL (e.g. `https://revora-backend.onrender.com/api/`). Should return `{"app":"Revora","status":"ok"}`.

Copy the Render URL — you'll need it for Vercel and the smoke script.

---

## Step 3 — Vercel (frontend)

Console: <https://vercel.com/new>

1. **Sign in with GitHub.**
2. **Import** this repo. Vercel auto-detects Create React App via `frontend/vercel.json`.
3. **Root directory**: set to `frontend`.
4. **Environment Variables** → add:

   | Key | Value |
   |---|---|
   | `REACT_APP_BACKEND_URL` | The Render URL from Step 2 |
   | `CI` | `false` (CRA treats `CI=true` as warnings-are-errors) |

5. **Deploy.** First build is ~1-2 minutes.
6. **Verify** — visit the Vercel URL, sign up a fresh user, click "Use Demo Data", land on `/health`.

---

## Step 4 — Wire CORS back to the frontend domain

Render → `revora-backend` → Environment → set `CORS_ORIGINS` to the Vercel URL (no trailing slash, comma-separated if you have multiple). Manual deploy or push triggers redeploy.

---

## Step 5 — (Optional) Custom domain

If you want `revora.bytehubble.ai`:

1. **Vercel** → project → Domains → add `revora.bytehubble.ai`. Vercel shows you a CNAME.
2. **Cloudflare** (or wherever bytehubble.ai DNS lives) → add the CNAME pointing at Vercel.
3. **Update `REACT_APP_BACKEND_URL`** on Vercel to `https://revora.bytehubble.ai` (only if you also CNAME the backend). Skip this if Render's auto-domain is fine for the contest.
4. **Update `CORS_ORIGINS`** on Render to the new domain.

Skippable for v1 — `.vercel.app` + `.onrender.com` URLs are submission-grade.

---

## Step 6 — Production smoke

From your laptop:

```bash
cd backend
source .venv/bin/activate
python -m scripts.smoke_prod \
  --backend https://revora-backend.onrender.com \
  --admin-email founder@bytehubble.com \
  --admin-password 'YOUR_REAL_ADMIN_PASSWORD'
```

Expected output:

```
Smoke against: https://revora-backend.onrender.com/api
  ✓ backend reachable -> {'app': 'Revora', 'status': 'ok'}
  ✓ signup
  ✓ fresh onboarding state
  ✓ seed-demo -> {'clients': 12, 'proposals': 14, 'invoices': 10, ...}
  ✓ revenue-health renders
  ✓ do_these_today rows
  ✓ /today returns rows
  ✓ brief.source=llm
  ✓ brief has paragraph
  ✓ feedback up
  ✓ aggregate up=1
  ✓ impact returns shape
  ✓ audit chain verify (n=N)

=== SMOKE: GREEN ===
```

If any line fails, that's your gate — fix before Day 5.

---

## Troubleshooting

**Backend won't boot — `RuntimeError: JWT_SECRET is required`**
You set the env var on Render but didn't redeploy. Push any commit (or click "Manual Deploy → Clear build cache & deploy") to pick up new env values.

**Frontend logs in but routes 404 on `/health`**
SPA rewrites didn't take. Verify `frontend/vercel.json` has the wildcard rewrite to `/index.html`.

**CORS errors in browser console**
`CORS_ORIGINS` on Render must match the Vercel origin exactly, including scheme. No trailing slash. Comma-separated for multiple.

**LLM returns 503 / template_fallback constantly in prod**
Check `EMERGENT_LLM_KEY` is set on Render. The fallback is honest UX (the "AI brief — live" badge disappears) but you want the live path before recording the demo.

**Render free instance cold-start lag (~30s on first request)**
Expected on free tier. Pin a Render cron or UptimeRobot ping every 10 min during demo recording day so it stays warm.

**Audit chain verify returns ok=False**
This should never happen on a fresh prod DB. If it does, the most likely cause is a partial multi-process race during boot — single-replica Render free plan avoids this. Restart the service.
