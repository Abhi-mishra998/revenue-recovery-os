# Revora — 90-second demo script

**Goal**: judges remember three things — (1) Upload your spreadsheet → instant Revenue Health report, (2) Every AI action is signed and verifiable, (3) Today's Opportunity in rupees.

**Recording setup** (one-time, before take 1):
- Browser: Chrome, incognito, zoom 100 %, 1440 × 900 window.
- Tab 1: `https://revenue-recovery-os1.vercel.app` (logged in as `founder@bytehubble.com` — demo seed is already there).
- Tab 2: `https://revenue-recovery-os1.vercel.app/admin` (audit page, ready to click "Verify chain").
- Voice: calm, slightly slower than normal. Aim 165 words ≈ 90 s at this pace.
- One take per beat — if a beat goes wrong, redo only that beat and stitch.

---

## Beat 1 — Upload + Instant Value + Revenue Health (45 s · 80 words)

[**Open**: `/welcome` — three cards visible]

> "I run a B2B services company. Like every founder, revenue lives in a spreadsheet."

[**Click**: `Upload CSV` card. Drop the file. Within 3 seconds, the instant-value teaser shows.]

> "I drop my client file. Within three seconds, Revora already sees fifty-two customers, ₹1.8 crore in pipeline, fourteen inactive deals, and seven overdue invoices — before any AI runs."

[**Click**: `Continue → Map columns`. AI mapping shows with confidence chips. Click `Import 52 rows`.]

[**Wait** ~1 s for `/health` to load.]

> "And here's Revenue Health. Visibility forty-two out of a hundred — 'Poor'. Three actions to take today. Risks with traffic lights. Expected revenue next thirty days. If I do nothing, ₹11 lakh leaks. If I act today, ₹8 lakh recovers."

[**Slow scroll** down to bars + Strengths.]

---

## Beat 2 — Trust proof (15 s · 30 words)

[**Switch to Tab 2**: `/admin` — audit page already loaded.]

[**Click**: `Run verify`. Wait for `ok=True` and the record count.]

> "Every single AI action is signed with ed25519 and chained, so the founder can prove what the system did and when. Auditable by design."

[**Hover**: the public-key fingerprint — `fp=f330d80b…`.]

---

## Beat 3 — Daily ritual + emotional close (30 s · 55 words)

[**Switch to Tab 1**: refresh `/` (Dashboard).]

> "This is what I open every morning. The brief — three clients at risk today, named, with reasons and confidence. What changed since last upload — visibility forty-two to fifty-one, two clients replied. Impact this week — six hours saved, ₹3.8 lakh protected."

[**Click**: top row in `Do These Today` → drafts open → `Copy to WhatsApp`.]

> "I review the draft, copy it, send it from my own WhatsApp. I tap thumbs-up. Revora learns."

[**Fade card** in foreground]:

> **Today's Opportunity**
> **₹12.4 L**
> 3 actions · ~14 minutes

[**Fade to black** → Revora wordmark → end.]

---

## Captions to overlay (lower third, 18 px, white on 60 % black)

| Timestamp | Caption |
|---|---|
| 0:03 | "Upload your spreadsheet" |
| 0:08 | "Instant: 52 customers · ₹1.8 Cr pipeline" |
| 0:22 | "AI mapping with confidence" |
| 0:35 | "Revenue Health — Visibility 42 / 100" |
| 0:45 | "Every action signed · ed25519" |
| 1:00 | "Morning Brief · live AI" |
| 1:10 | "What changed: 42 → 51" |
| 1:20 | "Copy to WhatsApp — founder approves every send" |
| 1:28 | "Today's Opportunity ₹12.4 L" |

---

## Common re-take triggers

- **Beat 1**: parse takes longer than 4 s — cold-start Render. Wait 30 s, refresh, restart.
- **Beat 1**: mapping table shows `null` for a required field — fix synonyms in `import_mapping.py` BEFORE recording, re-deploy, retake.
- **Beat 2**: `ok=False` on verify — chain broken (a Render env change). Wipe + re-seed via Day 4 procedure.
- **Beat 3**: brief shows `template_fallback` badge — `EMERGENT_LLM_KEY` not set on Render. Set it, redeploy, retake.

---

## Demo dataset

Recording uses the demo seed on `founder@bytehubble.com`:
- 12 clients · 14 proposals · 10 invoices
- Visibility lands ~27 / Poor on the cold demo seed (sometimes ~42 if recent demo activity)
- Top 3 actions: Patel & Associates CA (₹6.2 L), Hyderabad Heritage Hotels (₹4.1 L), Kapoor Legal LLP (₹2.5 L)

If you want different numbers in the recording, use the real ByteHubble data on `abhishek.mishra@bytehubble.ai` instead — that's the Day 5 pivot.

---

## Distribution-ready alt clip (for X / LinkedIn, 30 s)

If 90 s feels long for social, cut a 30 s version that's Beat 1 only ending on Revenue Health. Save the audit + ritual for the longer submission video.
