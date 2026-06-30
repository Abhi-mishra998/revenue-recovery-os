# SPRINT — Revora × Raj Shamani Contest

**Owner**: Abhishek Mishra (ByteHubble)
**Goal**: 1st place — Raj Shamani × Emergent AI-Native Builder Contest
**Window**: 2026-06-29 → 2026-07-21
**Submission**: 2026-07-05 · **Shortlist**: 2026-07-15 · **Finale**: 2026-07-21

> Refined 2026-06-29 (two feedback rounds folded in). Locked names below override anything earlier.

---

## 0. The pitch (LOCKED — refined 2026-06-29)

> **Revora finds the revenue your spreadsheet is hiding. Upload your sheet — Revora gives you a Revenue Health report with what's at risk, why, and what to do today. Every number shows its evidence and confidence. You approve, it drafts, you send. It learns from what worked.**

Marketing tagline (X / LinkedIn / landing H1): **"Revora finds the revenue your spreadsheet is hiding."**

If a feature, screen, copy line, or post does not support that sentence — cut it.

**The four user-facing primitives** (this is what the UI says):
1. **Revenue Health** — a shareable report (Score · Do These Today · Risks · Expected Revenue Next 30 Days · If You Act Today · Strengths)
2. **Why?** — every risk score, every priority, every action has its reasons listed
3. **Confidence (labelled)** — every AI/probabilistic output shows a chip with label + basis ("High 91% · based on 12 interactions" or "Medium 62% · needs more data")
4. **Learning Loop** — 👍/👎 on every recommendation, accuracy aggregate on dashboard

Plus the **Revenue Visibility Score (0-100)** — composite metric with label (Poor/Fair/Good/Great) and delta arrow. Founders improve it over time.

**Locked names** (do not rename again without changing the product):
- Page title: **Revenue Health**
- Onboarding final step (now inside Revenue Health, Day 2 — not standalone): **Improve My Recommendations**
- Report section names in **display order**:
  1. **Revenue Visibility Score** — gauge + label + delta arrow
  2. **Do These Today** — top of report. The thing founders open the app for.
  3. **Risks** — with 🟢🟡🔴 traffic-light badges
  4. **Expected Revenue Next 30 Days**
  5. **If You Act Today** — two CSS bars (loss vs recovery)
  6. **Strengths** — last. Action beats analysis.
- Score name: **Revenue Visibility Score**
- Marketing line: **"Revora finds the revenue your spreadsheet is hiding."**

**The "5 engines" framing is INTERNAL ONLY.** Not in UI. Not in deck. Not in submission copy. Demo deck story is the 5-step founder narrative below (§12).

**Why this phrasing (not "AI CRM", not "Digital COO")**:
- "AI CRM" sounds like every me-too. Monaco ($35M, Founders Fund, led by Sam Blond), Reevo, Aurasell, Lightfield, Attio are spending real money to own that label — don't compete on their playing field with 6 days.
- "Digital COO" overpromises autonomy. Contest judges are SMB founders, not AI investors; vapor pitches lose to "I uploaded my Excel and recovered ₹8 L".
- "Revenue Health + Do These Today" is concrete, founder-language, and matches what the screen actually shows.

---

## 1. Research-grounded positioning (2026-06-29)

**Market check** — well-funded competitors already in this space:
- Monaco · Reevo · Aurasell · Lightfield · Attio (AI-native CRM / Revenue OS)
- KOGO (agent OS) · Richpanel (autonomous CX agents)
- Silicon Road Ventures ₹150 Cr India fund for B2B Agentic AI

**Contest signal** (from official launch posts, Storyboard18, CXO Digitalpulse, PNI):
- Raj Shamani himself built "real software for his own business" as the example shown.
- Target users named: manufacturers, traders, logistics, D2C, family-run businesses.
- Use cases highlighted: inventory, order management, workflow automation, lead tracking.
- Judging criterion #1 = "real business problem solved", #2 = upvotes, #3 = actual usage.

**Implication**: Win by being the most-used, most-loved real tool — not the most-architectural pitch.

---

## 2. Architecture — the hard split: AI vs Analytics

Most "wow" numbers in Revora are **math, not AI**. Founders trust math. Judges can't tell whether 30 hours of LLM plumbing produced a chart — they CAN tell when the score appears instantly and the actions are concrete.

| Layer | Endpoints | Compute |
|---|---|---|
| **Analytics (SQL/Python — no LLM)** | `/revenue-health`, `/today`, `/onboarding/state`, `/clients/{id}/memory`, `/impact`, `/learning/aggregate`, `/health/diff`, `/import/parse` | Pure queries + math. <500 ms p95. Cheap. Cannot fail on LLM outage. |
| **AI (LLM-backed)** | `/import/map`, `/brief/today`, `/followups/generate` | Schema-validated LLM call → Pydantic → guardrail. Confidence chip surfaces. Heuristic fallback for mapper. |

**Three LLM endpoints. That's it.** Mapper (one-time per import), Morning Brief (1 call / founder / day, cached), Follow-up draft (on-demand). Everything else is deterministic.

**Internal engine map** (this stays internal; UI never names them, deck never names them):

| Internal engine | What it is in code | Already built? | Day 1-3 work |
|---|---|---|---|
| Understanding | Upload CSV/Excel → AI mapper → repo writes | Repos ✅ · AI client ✅ | Wizard + mapper endpoint (Day 1) |
| Memory | `services/memory.py` recomputes `client_memory` on every event | ✅ | Surface via Why? chips (Day 2) |
| Risk | `services/data/predict_close_probability.py` + scoring | ✅ math works | Wire into Revenue Health (Day 2) |
| Strategy | Morning Brief paragraph | ❌ NEW | Day 3 |
| Execution | AI follow-up generator (router → redact → guardrail → drafts) | ✅ | Confidence chip + 👍/👎 (Day 2-3) |

---

## 3. Two accounts (decided)

- `abhishek.mishra@bytehubble.ai` — real ByteHubble data, real usage account.
- `founder@bytehubble.com` — seeded clean-demo admin, kept for demo video recording.
- Backend: `ADMIN_EMAILS` env (comma-separated) → both admin. Backward compat with old `ADMIN_EMAIL`.

---

## 4. Flagship workflow — three beats, 90-second demo

**Beat 1 — Upload + Instant Value + Revenue Health (45 s)**

Signup → 3 cards: **[Upload CSV]** **[Upload Excel · Day 2]** **[Use Demo Data]** → drop file → **within 3 seconds**, parse completes and screen shows:

> We found in your file:
> ✓ 52 customers
> ✓ ₹1.8 Cr pipeline
> ✓ 14 inactive deals
> ✓ 7 overdue invoices
>
> *(computed by heuristic — no AI yet)*

→ AI column mapper shows `Customer → client_name`, `Deal Amount → value_inr` with per-row confidence chips → confirm with row counts → **Revenue Health report** loads (pure SQL, <500 ms):

> **Revenue Health · ByteHubble**
>
> **Revenue Visibility 42 / 100 · Poor · ↑ +9 since Jun 22**
> *Here's why ▾* (missing follow-ups · invoice delays · pipeline concentration · 4 silent clients)
> *Benchmark unavailable — coming after 100 companies.*
>
> **Do These Today · 3 actions · ~14 minutes**
> 1. 🔴 **Call Rahul (FinKart)** — recover ₹6.2 L · **High 89% · based on 12 interactions** · 5 min
> 2. 🟡 **WhatsApp Bloom Wellness** — ₹4.1 L · **Medium 76% · based on 7 interactions** · 3 min
> 3. 🟡 **Email Nexora** — ₹2.5 L · **Medium 62% · needs more data** · 6 min
> 👍/👎 per row · Why? chevron per row
>
> **[⬇ Download Revenue Health as PDF]**
>
> **Risks** *(each line with Why? chevron)*
> 🔴 4 clients silent 14+ days · ₹14.2 L exposed
> 🔴 2 invoices overdue · ₹3.1 L stuck
> 🟡 Pipeline concentrated — top 2 deals = 60% of total
>
> **Expected Revenue Next 30 Days**
> ₹32 L · Medium 81% · Biggest risk: Bloom · Biggest opportunity: FinKart
>
> **If You Act Today**
> `████████████` Do nothing → ₹11.2 L lost
> `████████████████` Act today → ₹8.4 L recovered
>
> **Strengths**
> ✓ High close rate on enterprise deals (3 of last 4)
> ✓ Fast first reply (median 1.2 d)
>
> ─── inline card, first visit only ───
> **Improve My Recommendations · 30 seconds**
> Help Revora get sharper on what to do today.
> 1) Which channel usually gets replies first? ○ WhatsApp ○ Email ○ Phone
> 2) After how many days do you usually follow up? ○ 3 ○ 7 ○ 14
> 3) What matters more to you? ○ Recover cash ○ Close deals ○ Customer relationships
> [Save → Do These Today re-ranks]

**Beat 2 — Trust proof (15 s) — audit lives in the MIDDLE, never the closer**
Admin → "Run verify" → `ok=True` → caption: "Every AI action signed and chained. Auditable."

**Beat 3 — Daily ritual + emotional close (30 s)**
Login → **Morning Brief** pinned card:
> "Good morning Abhishek. ₹12.8 L at risk today. Three to act on: Rahul (FinKart) — High 89%; Bloom — Medium 76%; Nexora — Medium 62%. Everything else is fine."

→ **What Changed Since Last Upload** card:
> Since Jun 22
> +2 clients replied · -1 invoice overdue · +₹3.8 L recovered
> Visibility 42 → 51

→ Click Rahul's row → Why? evidence → Generate Follow-Up → drafts with confidence chip → **Copy to WhatsApp** → 👍 → "Accuracy week-to-date: 78%."

**Demo final card** (fade to black, logo):
> **Today's Opportunity**
> **₹12.4 L**
> 3 actions · ~14 minutes

End on opportunity. Audit is the proof in the middle. Revenue is the story.

---

## 5. Day-by-day plan

> Dates are 2026. Each day has one **must-ship** and a **stop-condition**. Hit a blocker → cut, not slip.

### Day 1 — Mon 2026-06-29 — Importer pipeline + Demo Data + Onboarding wizard

**Engineering does not block on ByteHubble's real file.** The mapper exists precisely because headers are unknown. Demo data unblocks Day 1 today.

**Backend**
- [ ] `ADMIN_EMAILS` env (CSV). Loop existing `seed_admin()` over the list. Backward compat with old `ADMIN_EMAIL`.
- [ ] `import_jobs` table migration: `(file_id PK, owner_id, stage, headers jsonb, sample_rows jsonb, mapping jsonb, stats jsonb, created_at)`. RLS by owner_id. Repo in `services/db/repos/`. **Stage-based: each endpoint reads/writes this row, no re-upload on mapping failure.**
- [ ] `POST /api/import/parse` — accepts CSV today (`.xlsx` Day 2). **Single pandas pass** produces three derived blocks:
  ```
  {
    file_id, headers, sample_rows,
    column_types: { money: [...], date: [...], status: [...], identifier: [...] },
    data_quality: { rows, duplicates, blank_dates, blank_names, currency },
    quick_signals: { silent_clients, overdue_invoices, pipeline_inr, inactive_deals }
  }
  ```
  Frontend uses `quick_signals + data_quality` for the 4-line "We found" teaser within 3 s — **before** the LLM mapper runs.
- [ ] `POST /api/import/map` — body `{ file_id }`. Reads sample_rows from `import_jobs`. Calls Gemini Flash via `services/ai/client.py` with strict `MappingSuggestion` Pydantic schema → `{ field_name: source_header, confidence }`. **Heuristic fallback (header synonyms + Levenshtein) always shown alongside** so LLM is never a hard blocker. Confidence chip per field. Writes mapping back to `import_jobs`.
- [ ] `POST /api/import/commit` — body `{ file_id }`. Reads mapping from `import_jobs`. Streams rows through `client_repo.create_bulk` / `proposal_repo.create_bulk` / `invoice_repo.create_bulk` (add bulk variants — single transaction). RLS + audit fire automatically.
- [ ] `GET /api/onboarding/state` — `{ has_data, has_personalized, clients_count, proposals_count, invoices_count }`.
- [ ] **Demo data seeder**: `POST /api/import/seed-demo` (admin or any tenant on first-time use). 40 clients / 60 proposals / 25 invoices, distribution realistic for the four primitives to render. Lives at `services/demo/seed.py`. Idempotent (clears the tenant's rows first, confirms via flag).
- [ ] Audit events: `import.parse`, `import.map`, `import.commit`, `import.seed_demo` with row counts only (no PII in metadata).

**Personalize is NOT in Day 1.** Moved to Day 2 as an inline card inside Revenue Health (post-diagnosis).

**Frontend**
- [ ] `<OnboardingWizard />` at `/welcome`. Three cards: **Upload CSV**, **Upload Excel** ("Day 2" badge), **Use Demo Data** (calls `/import/seed-demo` then redirects to Revenue Health).
- [ ] **4-step flow** (down from 5 — Personalize moved out):
  1. Drop file
  2. **Instant-value teaser** — 4 lines from `data_quality + quick_signals` rendered the moment `/parse` returns ("We found 52 customers · ₹1.8 Cr pipeline · 14 inactive deals · 7 overdue invoices")
  3. Mapping table (AI + dropdown override · per-row confidence chip)
  4. Confirm with row counts → progress → redirect `/health`
- [ ] `App.jsx` — if `onboarding/state.has_data === false`, route to `/welcome` after login.

**Cut/skip**
- Excel parsing → Day 2 (single dep `openpyxl`, already transitive via pandas).
- `/api/import/validate` as a separate endpoint → **folded into `/parse`'s `data_quality` block**. Same UI moment ("Revora also cleaned your data"), one fewer endpoint to authorize/audit/rate-limit.
- Email/PDF ingestion → not this week.
- Personalize endpoint → Day 2.

**Stop-condition**: AI mapping flaky → ship heuristic fallback only. Mapping UI still lets founder override. AI mapping is the delight, not the blocker.

---

### Day 2 — Tue 2026-06-30 — Revenue Health (SQL-only) + snapshots + PDF + Improve My Recommendations

**Backend — Analytics layer (NO LLM calls in any of these endpoints)**
- [ ] `.xlsx` support in `/api/import/parse` via `openpyxl`. Single-sheet only for v1; multi-sheet → founder picks.
- [ ] `_context_for_client(client_id)` helper — joins client + proposals + invoices + activities + memory into one dict. Used by every LLM prompt that mentions a client (Day 3).
- [ ] `health_snapshots` table: `(id, owner_id, snapshot_date date, payload jsonb, created_at)`. Index on `(owner_id, snapshot_date desc)`. RLS.
- [ ] `GET /api/revenue-health` — pure SQL/Python. Single payload backing the report:
  - `visibility_score: { score, label: 'Poor'|'Fair'|'Good'|'Great', breakdown: { active_clients_pct, non_silent_proposals_pct, paid_invoices_pct, concentration_pct }, delta: { arrow: '↑'|'↓'|'→', value, since_date } | null, reasons: [str] }` — composite weighted score. `# ponytail: equal weights for v1, tune when usage data lands`. Delta filled from `health_snapshots` if a prior snapshot exists.
  - `benchmark: { available: false, message: 'Coming after 100 companies' }` — honest placeholder until we have data.
  - `do_these_today: [{ id (uuid), action, target_client_id, value_inr, status: 'red'|'amber'|'green', estimated_minutes, confidence: { score, label, basis }, why: [evidence_strings] }]` — top-3 from existing scoring. **Renamed from Action Plan.** Re-ranks based on `tenant_profile.priority` (cash → value × days × (1-p); close → value × p; relationship → relationship_score). Confidence here is data-sufficiency-based (interaction count), no LLM.
  - `risks: [{ statement, value_inr, status: 'red'|'amber'|'green', why }]` — silent clients + overdue invoices + pipeline concentration. **Traffic-light status from thresholds:** 🟢 silent <7d & no overdue / 🟡 7-14d or 1 overdue / 🔴 >14d or 2+ overdue.
  - `expected_revenue_30d: { amount_inr, confidence: { score, label, basis }, biggest_risk_client, biggest_opportunity_client }` — `amount = Σ value × close_probability`; `biggest_risk = max(value × (1-p))`; `biggest_opportunity = max(value × p)`. Confidence based on `N proposals` data-sufficiency.
  - `if_you_act_today: { do_nothing_loss_inr, act_recovery_inr, model_note: 'Model estimate · 15% uplift from acting' }` — `do_nothing = Σ value × (1-p)`; `act = Σ value × p × 1.15`. **Renamed from Counterfactual.** Hides if <5 active proposals.
  - `strengths: [{ statement, evidence }]` — derived from `client_memory` aggregates.
  - `estimated_total_minutes: int` — sum of estimated_minutes across `do_these_today`. `# ponytail: stake 5 min/call, 3 min/whatsapp, 6 min/email — tune from real timings`.
- [ ] **Snapshot on every `/revenue-health` call** IF the latest snapshot for this owner is >24 h old. Writes the same `payload` to `health_snapshots`. 1 row/day max.
- [ ] `GET /api/health/diff?since=YYYY-MM-DD` — returns `{ visibility: {from, to, delta}, replied_delta, overdue_delta, recovered_inr_delta }`. Default `since` = most recent prior snapshot.
- [ ] `GET /api/today` — top-N at-risk: `{ value_inr, days_silent, likelihood, status, estimated_minutes, confidence: { score, label, basis }, why }`. Ranking same as `do_these_today`.
- [ ] `POST /api/personalize` (now triggered from inside Revenue Health, not onboarding) — body `{ preferred_channel, follow_up_days, priority }`. Writes to `settings.tenant_profile`. Triggers `do_these_today` re-rank on next `/revenue-health` call. **Three questions that actually move ranking.**
- [ ] `GET /api/clients/{id}/memory` to surface `client_memory` in client detail.
- [ ] **Confidence chip scope** (scoped down from the earlier "every endpoint" plan): only on LLM endpoints (mapper, brief, drafts) AND probabilistic endpoints (forecast, do_these_today rows where the score comes from `close_probability`). Pure-SQL Visibility/Risks/If-You-Act-Today show evidence, not a chip.

**Frontend**
- [ ] `<RevenueHealthReport />` at `/health` — single-scroll page. **Display order**: Score → **Do These Today** → Risks → Expected Revenue Next 30 Days → If You Act Today → Strengths. Print-friendly CSS for PDF.
- [ ] `<VisibilityScoreCard />` — gauge 0-100 + label (Poor/Fair/Good/Great) + ↑/↓ arrow with snapshot delta (`↑ +9 since Jun 22`). "Here's why" expander shows breakdown reasons. Benchmark line below: "Coming after 100 companies."
- [ ] `<DoTheseTodayList />` — **at the top of the report under the score.** Strip header: "3 actions · ~14 minutes". Each row: 🟢/🟡/🔴 badge · client + action · value · estimated time · `<LabelledConfidenceChip />` · `<WhyChevron />` · `<ThumbsFeedback />`.
- [ ] `<RiskBadge status="red|amber|green" />` reusable — 🟢 Healthy / 🟡 Watch / 🔴 Immediate Action.
- [ ] `<ExpectedRevenueBlock />` — 4 numbers: expected revenue, confidence chip, biggest risk client, biggest opportunity client.
- [ ] `<IfYouActTodayBars />` — two horizontal CSS bars. Red bar = do_nothing loss · green bar = act recovery. Width proportional. No chart library.
- [ ] `<WhyChevron />` reusable — expandable taking `why: string[]`, renders bullets. Used across the report, Today's list, follow-up cards, client detail.
- [ ] `<LabelledConfidenceChip />` reusable — `{ score, label, basis }` → "High 91% · based on 12 interactions". Used only where AI/probabilistic output appears.
- [ ] `<ImproveMyRecommendationsCard />` — inline card at the bottom of `<DoTheseTodayList />`, **first visit only** (after that, hidden behind a "Update preferences" link). 3 questions, 30 s pitch. Save → re-rank.
- [ ] `<DownloadPDFButton />` — top-right of Revenue Health page. Triggers `window.print()`. Print CSS hides nav/header/CTAs. **No PDF library.**
- [ ] Client detail: `client_memory` surface (preferred channel chip, response cadence, response rate gauge). No "agent" label anywhere.
- [ ] Remove all "Agent" labels from the UI — language is "Revenue Health / Why? / Confidence / Do These Today".

**Stop-condition**: `client_memory` sparse (cold tenant) → "Still learning your clients — more signal arrives with each follow-up" empty state. If You Act Today hides if <5 active proposals.

---

### Day 3 — Wed 2026-07-01 — Morning Brief + Learning Loop + What Changed + Impact

**Morning Brief (the ONLY new LLM endpoint this day)**
- [ ] `GET /api/brief/today` — computed once per founder per day, cached in `settings.daily_brief` (jsonb keyed by date). Computation:
  1. Pull top-3 from `/api/today` (includes Why? evidence per row).
  2. Pull `client_memory` for each + `tenant_profile`.
  3. One Gemini Flash call (~400 tokens out): "Write a 60-word morning brief for the founder. Mention ₹ at risk. Name the three clients. One-line reason and action each. Confidence on each. End with one reassurance line."
  4. Schema-validated. Guardrail rejects refusals.
  5. Output includes overall `confidence: { score, label, basis }`.
- [ ] `<MorningBrief />` card pinned top of dashboard. Refresh rate-limited 3/day via slowapi. Confidence chip on the card.

**Learning Loop**
- [ ] `POST /api/recommendations/{recommendation_id}/feedback` — body `{ thumb: "up"|"down", outcome?: "replied"|"meeting_booked"|"closed_won"|"no_reply"|"closed_lost" }`. Writes `recommendation.feedback` event. No new table.
- [ ] Recommendation IDs: every row returned from `/api/today`, `/api/revenue-health`, `/api/brief/today`, `/api/followups/generate` includes a stable `id` (uuid).
- [ ] `GET /api/learning/aggregate` — `{ thumbs_up_count, thumbs_down_count, accuracy_pct, recent_examples }`.
- [ ] `<ThumbsFeedback recommendationId={id} />` reusable. Appears next to every recommendation, brief, and follow-up draft.
- [ ] `<LearningCard />` on dashboard.

**What Changed Since Last Upload (snapshot payoff)**
- [ ] `<WhatChangedCard />` on dashboard. Uses `/api/health/diff`. Pinned when ≥2 snapshots exist. Hidden otherwise. Shows: `+N clients replied · -M invoices overdue · +₹X.X L recovered · Visibility 42 → 51`.

**Impact dashboard**
- [ ] `GET /api/impact`:
  - `followups_generated_week` — count from `followups` this week
  - `hours_saved_week` — `× 15 min / 60` (`# ponytail: 15 min/follow-up is a stake, refine when usage data lands`)
  - `revenue_protected_week` — sum `proposals.value_inr` where any followup generated this week and still active
  - `response_rate_week` — from `client_memory`
- [ ] `<ImpactCard />` dashboard. Zeros are honest UX.
- [ ] `followup.copied` event when Copy/Send clicked → usage telemetry.

**Polish**
- [ ] Onboarding error states: bad file, mapping mismatch, partial import.
- [ ] `founder@bytehubble.com` seed refreshed so demo recording works without real data if needed.

**Stop-condition**:
- Brief LLM call slow/flaky → template-string fallback ("3 clients at risk today: …"); "AI brief — live" badge only when LLM succeeded.
- Learning aggregate computation slow → cache per-day in `settings.learning_aggregate`.

---

### Day 4 — Thu 2026-07-02 — Deploy

**Must ship**
- [ ] Backend → **Render** or **Fly.io**. Env: `ENV=production`, real `JWT_SECRET`, real `AUDIT_SIGNING_KEY`, `CORS_ORIGINS` = frontend domain only, `RATE_LIMIT_ENABLED=true`, `ADMIN_EMAILS=abhishek.mishra@bytehubble.ai,founder@bytehubble.com`.
- [ ] Postgres → **Neon** with pgvector. Run `0001_initial.sql` + new migrations for `import_jobs`, `health_snapshots`.
- [ ] Frontend → **Vercel** with `REACT_APP_BACKEND_URL`.
- [ ] Custom domain (`revora.bytehubble.ai` suggested). Cloudflare DNS, automatic TLS.
- [ ] LLM keys: `EMERGENT_LLM_KEY` (or direct provider keys). Confirm Gemini Flash + Claude Sonnet both reachable.
- [ ] Smoke test: signup → upload sample CSV → AI maps → import → Revenue Health renders → generate follow-up → audit verifies → PDF download works.

**Skipped on purpose**: AWS Fargate/RDS/Secrets Manager. Tier-2 problem.

---

### Day 5 — Fri 2026-07-03 — Real use + demo recording

- [ ] Abhishek uploads ByteHubble's real CSV/Excel into `abhishek.mishra@bytehubble.ai` on prod.
- [ ] Sends **3 real follow-ups** to real ByteHubble clients. Logs outcomes.
- [ ] Screen-record 90 s demo (audit in the **middle**, opportunity at the **end**):
  - **Beat 1 (45 s)**: Onboarding → instant-value teaser (4 lines, 3 s) → mapping → Revenue Health report (Score → Do These Today at top → Risks → Forecast → If You Act Today bars → Strengths). PDF download click for half a second.
  - **Beat 2 (15 s)**: Admin → Run verify → `ok=True`. Audit is proof in the middle, not the closing emotion.
  - **Beat 3 (30 s)**: Login → Morning Brief → **What Changed Since Last Upload** → click row → drafts → Copy to WhatsApp → 👍 → "Accuracy week-to-date: 78%" → **fade out on "Today's Opportunity · ₹12.4 L · 3 actions · ~14 minutes"** final card.
- [ ] Before/after screenshots: actual Excel chaos vs Revora dashboard.
- [ ] Founder story (4 short paragraphs): problem at ByteHubble, why Revora, what changed, next.

**Stop-condition**: 3 follow-ups not possible on a Friday → 2 real + 1 with a friendly client clearly labelled "with permission".

---

### Day 6 — Sat 2026-07-04 — Submit + first promote

- [ ] Submit on https://app.emergent.sh/raj: live URL, 90 s demo, founder story, before/after screenshots, evidence pack (audit log entries showing real `ai.followup.generate`).
- [ ] Submission headline = §0 sentence. Architecture in one line, not paragraphs.
- [ ] X + LinkedIn post: video + URL + upvote ask.
- [ ] Share in 3 founder/B2B groups Abhishek is genuinely in. No spam.

---

### Day 7 — Sun 2026-07-05 — Buffer + critical fixes only

- [ ] Watch Sentry / logs. Fix only demo-path-breakers.
- [ ] No new features. Resist.
- [ ] LinkedIn long-form: founder-story extended.

**Stretch (only if Days 1-6 finished early — NOT promised)**:
- "Ask Revora" — `GET /api/ask` with structured-data-only prompt. One LLM call per question, schema-validated. Risky: a wrong answer in front of judges is a contest-killer. Ship ONLY if confidence is high after manual testing on ByteHubble's real data.

---

## 6. Days 8-22 — Upvote engine + shortlist prep

After 2026-07-05 the build is locked. Distribution + proving real usage.

**Daily until 2026-07-15**
- Use Revora for ≥1 real follow-up at ByteHubble.
- One public post: build update, screen clip, customer reaction, metric (use **What Changed** card as the visual — it's the daily story machine).
- Reply personally to every comment / DM.

**Once mid-week**
- DM 10 founders Abhishek knows. Get them on the upload flow. Permissioned screenshots of their dashboards.

**For shortlist (2026-07-15)**
- 5-min extended demo for finale.
- Evidence pack v2: ≥3 real ByteHubble follow-ups → outcomes table; audit log screenshots; **snapshot diff over 14 days** (Visibility 42 → 61 story); impact dashboard delta; ≥2 external founders' import → insight screenshots.

---

## 7. What we are explicitly NOT doing

| Skipped | Why | When to revisit |
|---|---|---|
| 6 separate agents as separate processes / "agent" labels in UI | Demo fragility + judges don't care. UI says Revenue Health / Why? / Confidence / Do These Today. | Post-contest if user signal demands it |
| "5 engines" framing in the deck or submission copy | Nobody outside builders cares. Deck story is Problem → Spreadsheet → Revenue Health → Actions → Recovered Revenue (§12). | Never as customer-facing copy |
| Standalone Knowledge Graph layer | FKs in Postgres are the graph. `_context_for_client()` helper (Day 2) is the same outcome in 20 lines. | Never |
| Hourly background observer / cron workers | Cost + complexity + no contest value. Compute on first-login-of-day instead. | After 100 active tenants |
| AI auto-send to customers | Violates no-auto-send rule. SMB trust killer. Architectural NO. | Never as default; opt-in only, post-pilot |
| Memory Evolution diff view / "Business Memory" aggregate | `health_snapshots` + `/api/health/diff` + `<WhatChangedCard />` IS the diff. Same outcome, smaller. | — |
| Confidence chip on pure-SQL outputs (Score, Risks, If You Act Today) | Reserved for LLM + probabilistic outputs (mapper, brief, drafts, forecast, do_these_today rows). Pure analytics show evidence, not a chip. | Never — labelling deterministic numbers as "AI confidence" is dishonest |
| Separate `/api/import/validate` endpoint | Same heuristic pass already produces `data_quality` in `/api/import/parse`. Same UI moment, one fewer endpoint. | Never |
| PDF library (jspdf, pdfmake, react-pdf) | `window.print()` + print CSS produces a clean Revenue Health PDF for free. | After custom branding is requested |
| Chart library (recharts, chart.js, victory) | One gauge (SVG) + two horizontal bars (CSS) is all the report needs. | After a chart-heavy feature is requested |
| Industry benchmark backend | Honest placeholder UI ("Coming after 100 companies") until data exists. Never invent comparisons. | After 100 tenants |
| "Ask Revora" conversational endpoint | A wrong answer in front of judges is a contest-killer. | Day 7 stretch only or post-shortlist |
| AI Timeline narration view | UI rework only — data already exists in `activities` + `events`. | Post-shortlist polish |
| Email/PDF/WhatsApp ingestion | One ingestion path (CSV/Excel) is enough. | Post-contest |
| Web scraping company websites | Marketing site has no CRM data. | Likely never |
| Google Sheets / HubSpot / Zoho integrations | CSV export from any of them works today. | Post-shortlist if a judge asks |
| Native mobile app | Web is mobile-responsive. | PWA only if needed |
| More security / middleware / docs / DB tuning | Foundation enough. Judges don't grade this. | Post-contest |
| AWS Fargate / RDS migration | Render + Neon fine for ≤50 users. | After 10 paying tenants |
| Frontend test suite | Manual + ESLint catches enough this week. | After shortlist |
| Marketing site | The app IS the marketing. | Post-contest |

---

## 8. Risks (named, with mitigations)

| Risk | Mitigation |
|---|---|
| AI mapping returns nonsense | Heuristic fallback (header synonyms + Levenshtein) always shown alongside; founder confirms before commit. |
| LLM API outage on demo day | Revenue Health, Today, Score, Forecast, Counterfactual are **pure SQL** — they cannot fail on LLM outage. Only Brief + Drafts depend on LLM, both have template fallbacks. Demo recorded Day 5; live failure can't tank submission. |
| Real ByteHubble data messy | AI mapper exists specifically for unknown headers. Founder can override any mapping. |
| Morning Brief LLM call slow | Cached daily. Template-string fallback. "AI brief — live" badge only when LLM succeeded. |
| Visibility Score formula gives unintuitive numbers | Tune weights against ByteHubble's real data Day 5 before recording. `# ponytail: equal weights v1, tune from usage`. |
| Low upvote count | Daily public posts from Day 1. **What Changed** card gives a daily visual to post. Personal DMs Day 6. No silent build. |
| Abhishek forgets to use it ("real usage" hollow) | 9 AM calendar block — "Open Revora, send today's follow-ups." 5-min ritual. |
| Deploy eats more than a day | Render + Neon + Vercel ≤ 2 hrs with prepared env vars. Prep Day 3. |
| LLM cost surprise | Three LLM endpoints only (mapper, brief, drafts). Rate limit (10/hr/user) + kill-switch already in place. Set billing alerts Day 4. |
| Re-import corrupts existing data | All writes through repos → audit logged → reversible. "Re-import" flow deletes existing rows from owner first, with confirmation. |
| Compared to Monaco / Reevo by a judge who knows the space | Counter-pitch: "Built in 7 days by the founder using it daily on his own business. Most numbers here are math, not LLM guesses." |

---

## 9. Definition of done — submission-ready

- [ ] Public URL works, loads <3 s
- [ ] Fresh signup → "Use Demo Data" → AI maps → Revenue Health → Do These Today visible — all under 60 s
- [ ] Revenue Health renders in order: **Score · Do These Today · Risks · Expected Revenue Next 30 Days · If You Act Today · Strengths**
- [ ] Revenue Visibility Score shows label (Poor/Fair/Good/Great) and snapshot delta arrow when ≥2 snapshots exist
- [ ] Industry benchmark line reads "Coming after 100 companies" (never invented)
- [ ] Do These Today is at the **top** of the report, shows traffic-light badges, estimated minutes strip ("3 actions · ~14 minutes"), Why?, Labelled Confidence chip
- [ ] If You Act Today shows two CSS bars (loss vs recovery), no chart library
- [ ] Every LLM/probabilistic output has Why? evidence list AND Labelled Confidence chip (label + basis, not bare number)
- [ ] Pure-SQL outputs (Score, Risks, If You Act Today) show evidence — no fake confidence chip
- [ ] PDF export works via `window.print()`; print CSS hides nav/header
- [ ] `abhishek.mishra@bytehubble.ai` tenant has real ByteHubble data + ≥3 real follow-ups + ≥3 👍/👎 entries + real audit entries
- [ ] Morning Brief renders on dashboard, names real clients, has a real ₹ figure + confidence chip
- [ ] **What Changed Since Last Upload** card renders on dashboard when ≥2 snapshots exist
- [ ] Learning card on dashboard shows accuracy aggregate from real 👍/👎
- [ ] Impact dashboard shows ≥1 non-zero metric from real usage
- [ ] Audit chain verifies (`ok=True`) on prod
- [ ] 90 s demo video uploaded — three beats clear, audit in middle (proof), ends on **"Today's Opportunity · ₹12.4 L · 3 actions · ~14 minutes"** final card
- [ ] Founder story written, includes ₹ + hours numbers
- [ ] Submitted on app.emergent.sh/raj
- [ ] Public post live with submission URL + upvote ask + tagline "Revora finds the revenue your spreadsheet is hiding"
- [ ] Onboarding shows instant-value teaser (4 lines) within 3 seconds of file upload, before mapping

---

## 10. What I need from Abhishek to start Day 1

**Demo data unblocks engineering. Day 1 starts NOW.**

1. **Confirm**: `ADMIN_EMAILS=abhishek.mishra@bytehubble.ai,founder@bytehubble.com` — both admin.
2. **ByteHubble real file by EOD Day 4** — for Day 5 real-usage demo recording. **NOT a Day 1 blocker.** Header row + 2 rows in chat is enough when you have it.
3. **Daily 5-min check-in** — same time every day so public posts stay consistent.

---

## 11. Honest caveats

- 1st place is not guaranteed. ~Thousands of submissions. We're optimising the criteria judges actually scored on — not certainty.
- The biggest single risk is **upvote distribution**, not the product. Reach is the variable.
- If by Day 4 ByteHubble has 0 real follow-ups generated, the "real usage" claim is weak. We manufacture real usage by Day 5 or the story doesn't hold.
- The architecture description above (3 LLM endpoints, rest SQL) is true. Don't overstate it — calling Revora "autonomous" is the lie a judge will catch.
- Monaco / Reevo / Aurasell exist. If a judge brings them up, the answer is: "They're building for enterprise sales teams with $35M and a year. I built this in 7 days for myself as a founder. Most of what you see is math, not an LLM guess. That's the whole point of the contest."

---

## 12. Pitch deck story (5 slides, no "agent" word)

1. **Problem** — Founders run revenue from a spreadsheet. Most of the money is hiding in cells nobody re-opened.
2. **Spreadsheet** — Show actual chaos. Highlight 4 silent clients, 7 overdue invoices the founder hadn't noticed.
3. **Revenue Health** — Upload → 3 seconds → Visibility 42/100, Do These Today, traffic-light Risks, Expected Revenue, If You Act Today bars.
4. **Actions** — Click row → Why? → Generate Follow-Up → Copy to WhatsApp → 👍. Audit-signed. The founder approved every send.
5. **Recovered revenue** — What Changed Since Last Upload: Visibility 42 → 61. ₹3.8 L recovered. 3 follow-ups, 2 replies, 1 closed.

Five slides. No "agent". No "five engines". The product IS the deck.

---

## Sources (research from 2026-06-29)

- [Raj Shamani × Emergent ₹1 Crore Builder's Challenge — Emergent](https://emergent.sh/news/raj-shamani-emergent-one-crore-builders-challenge-for-indian-business-owners)
- [Storyboard18 — Raj Shamani, Emergent ₹1 crore challenge launch](https://www.storyboard18.com/digital/raj-shamani-emergent-launch-%E2%82%B91-crore-challenge-to-help-indian-businesses-build-with-ai-102425.htm)
- [CXO Digitalpulse — Drive AI adoption among Indian businesses](https://www.cxodigitalpulse.com/emergent-and-raj-shamani-launch-%E2%82%B91-crore-challenge-to-drive-ai-adoption-among-indian-businesses/)
- [Reevo — AI-Native CRM 2026 guide](https://reevo.ai/blog/ai-native-crm-guide)
- [SaaStr — Which CRM Should You Use in 2026/2027? Follow the Agents](https://www.saastr.com/which-crm-should-you-use-in-2026-2027-follow-the-agents/)
- [The Wire — Silicon Road Ventures ₹150 Cr India fund for B2B Agentic AI](https://thewire.in/article/ptiprnews/usa-based-silicon-road-ventures-launches-india-focused-aif-to-back-b2b-agentic-ai-commerce-tech-startups)
- [MindStudio — Six-Layer Agentic Operating System stack](https://www.mindstudio.ai/blog/what-is-agentic-operating-system)
- [Inc42 — Indian AI Startup Tracker 2026](https://inc42.com/startups/indian-ai-startup-tracker/)
