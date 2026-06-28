# Revora — Revenue Recovery OS — PRD

## Original problem statement
B2B service businesses in India (consultants, IT/dev agencies, CA firms, design studios)
lose money when proposal & invoice follow-up slips into WhatsApp threads + Excel.
ByteHubble is the first user. We need a daily operator console that surfaces what's
going cold, what to chase today, how much ₹ is recoverable, plus AI-drafted (copy-only)
WhatsApp + email follow-ups, an invoice tracker with AI reminders, and a client
activity log.

## Architecture decisions
- Backend: FastAPI + MongoDB (motor) + JWT bearer auth + bcrypt
- AI: Claude Sonnet 4.5 via Emergent Universal LLM key (emergentintegrations)
- Frontend: React + react-router + axios + shadcn/ui + sonner + lucide-react
- Fonts: Cormorant Garamond (display) + Outfit (UI) + JetBrains Mono (numbers)
- INR formatting: Indian numbering system (1,00,000 lakhs / 1,25,00,000 crores) + compact ₹ L / ₹ Cr for hero
- Auth model: single-user-per-tenant; all data scoped by owner_id

## User personas
- Founder/Operator at a 5-30 person Indian agency (primary)
- AR/finance assistant who chases invoices (secondary)

## Core requirements (static)
1. Proposal dashboard with auto status
2. Status logic: Active (≤7d), Cold (≤21d), Dead (>21d) by days-since-contact
3. AI follow-up drafts (WhatsApp + Email) — copy to clipboard only
4. Revenue-at-Risk view + Recoverable ₹
5. Today's Action List (ranked by value × days-silent)
6. Invoice tracker + AI reminder
7. Client activity log

## Implemented (2026-02-XX)
- JWT email/password auth with bcrypt, /api/auth/login, /api/auth/me, /api/auth/register
- Seed admin user founder@bytehubble.com + 12 demo clients, 15 proposals, 10 invoices, ~35 activities
- Proposals CRUD + touch (mark followed-up) + auto status
- Invoices CRUD + mark-paid + auto status (due/overdue/critical/paid)
- Dashboard summary + ranked Today's Action List with urgency scoring
- AI draft endpoint (Claude Sonnet 4.5 via Emergent key): WhatsApp, Email, Invoice-reminder × 3 tones (gentle/firm/final)
- Activity timeline per client (auto-logged on every action)
- Beautiful editorial-fintech UI: cream paper bg + serif hero numbers + status pills + warm Indian-business voice
- 14/14 backend pytest passing; 100% frontend critical flows passing

## Architecture shims for Opus export (2026-02-XX, scope-locked)
- `backend/services/ai.py` — provider-abstracted AI layer. `PROVIDERS` dict maps name → handler. Default `anthropic_emergent` (uses EMERGENT_LLM_KEY). Swap providers by adding entries — no other code changes needed.
- `backend/services/seed.py` — extracted realistic ByteHubble seed (12 clients across verticals, 15 proposals, 10 invoices, varied activities). `reset_demo_data_for_owner()` + `seed_demo_for_owner()` are reusable.
- `backend/scripts/reset_demo.py` — one-command wipe + reseed (or `--wipe-only`). Preserves the user account; touches only demo content for the target owner.

## P0 backlog (next)
- Real ₹ recovered counter (when cold proposal moves to active/won)
- Daily summary email digest of today's action list

## P1 backlog
- Multi-user / team support
- Per-client custom follow-up cadence
- CSV import for existing proposals / invoices
- Drag-and-drop reorder on action list

## P2 backlog
- Native WhatsApp Cloud API send (currently copy-only)
- Predictive likelihood-to-close ML
- Meeting transcription / call notes
- Multi-currency support

## Next action items
- Validate with ByteHubble for 1 week, capture ₹ actually recovered
- Build the daily email digest + the "₹ recovered this month" tracker for the contest demo
