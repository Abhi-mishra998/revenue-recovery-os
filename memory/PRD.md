# Revora — Revenue Recovery OS — PRD

## Original problem statement (prompt 1)
Build a Revenue Recovery OS for Indian B2B service businesses (consultants, agencies, CA firms, design studios). First user = ByteHubble. React + FastAPI + MongoDB. Google login (Emergent playbook) + email/password fallback. Every user sees only their own data.

## Locked-in models (prompt 1 — schema v2)
- **User**: name, email, auth_provider
- **Client**: company_name, contact_name, email, phone, whatsapp, industry, language (default "English"), notes
- **Proposal**: client_id, title, value_inr, sent_date, last_contact_date, status (auto active/cold/dead), stage (sent/negotiating/won/lost), notes
- **Invoice**: client_id, invoice_no, amount_inr, due_date, paid_date, status (auto paid/unpaid/overdue), days_overdue (auto), notes
- **Activity**: client_id, related_type, related_id, channel, direction, summary, created_at

**Rule**: status + days_overdue are computed from dates, never typed by the user.

## Architecture rules (prompt 1, locked)
1. Don't change DB/framework/auth after prompt 1
2. Don't rename models
3. Don't touch code outside the named feature
4. One feature per prompt
5. Backward-compatible
6. Copy-to-send only (no auto-send anywhere)
7. Stop for review after each prompt

## Implemented (prompt 1 — 2026-02)

### Auth
- Google OAuth (Emergent playbook): /login → "Continue with Google" → emergentagent → /?session_id=… → POST /api/auth/google/session → JWT bearer
- Email/password fallback: /api/auth/login, /api/auth/register, /api/auth/me
- JWT bearer in localStorage as `revora_token`
- Seed admin: founder@bytehubble.com / ByteHubble@2025

### Backend (FastAPI + MongoDB)
- All endpoints scoped by owner_id (per-user authorization on every query)
- CRUD: /api/clients, /api/proposals, /api/invoices, /api/activities
- /api/dashboard/summary returns the 4 dashboard metrics
- Auto status compute: active ≤7d, cold ≤21d, dead >21d (proposals); paid/unpaid/overdue (invoices)
- One-time legacy field migration runs on startup (renames v1 fields to v2 idempotently)
- Reset/reseed: `python scripts/reset_demo.py`

### Frontend (React + react-router 7)
- Indigo #4338ca primary, Teal #0d9488 accent, light theme, card-based
- 5 screens: Dashboard, Proposals (+ detail), Clients (+ detail), Invoices
- Status badges: green=active/paid, amber=cold, red=dead/overdue
- ₹ with Indian commas (1,00,000 / 1.25 Cr compact)
- Responsive sidebar → hamburger drawer on mobile (<768px)

### Seed (12 clients / 14 proposals / 10 invoices / 10 activities)
- Realistic Indian B2B mix across verticals
- Dashboard reads: ₹37.75 L pipeline · 6 cold · 6 overdue (₹11.57 L) · ₹27.15 L at risk

### Tests
- 15/15 backend pytest pass — auth, data isolation, dashboard math, CRUD, status compute, Google session 401
- 100% frontend Playwright pass on critical flows
- Test file: /app/backend/tests/test_revora_api.py

## Optional polish flagged by testing agent (NOT applied — awaiting your direction)
1. Map upstream Emergent failure on Google session to 401 instead of 502 (cosmetic)
2. Split server.py (~628 LOC) into routes/{auth,clients,proposals,invoices}.py
3. Use IST day boundaries for status flips (India-first product)
4. Dev-only React `<span>` in `<option>` warning from Emergent's visual-editor instrumentation (not a real bug)

## Out of scope (deliberately not built — awaiting future prompts)
- AI follow-up drafts (drafts WERE in earlier iteration, removed for prompt 1 scope)
- Today's Action List
- Activity timeline UI on client detail
- FollowUp model persistence
- Bulk actions, CSV import, audit log, ML

## Backlog
- **P0**: ₹ Recovered counter, FollowUp model + persistence, AI draft generation
- **P1**: CSV import, daily email digest, IST-aware status, dark mode
- **P2**: WhatsApp Cloud API send, predictive ML
