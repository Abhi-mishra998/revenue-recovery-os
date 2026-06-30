# `submission/` — index

> Every artifact you need to record the demo, submit to emergent.sh, and
> publish to LinkedIn + X. Files are listed in the order you use them.

| When | File | What it is | Open with |
|---|---|---|---|
| **Day 5.4 record** | [`demo_script.md`](./demo_script.md) | 90-second beat-by-beat script. Numbers locked + pre-flighted against live prod. | any markdown viewer + your screen recorder |
| Day 5.4 record | [`sample_upload.csv`](./sample_upload.csv) | 15-row demo CSV for Beat 1 upload. 1 duplicate + 1 blank-name row trigger the "data quality" callouts. | drop into Welcome's "Upload CSV" |
| **Day 5.5 edit** | [`founder_story.md`](./founder_story.md) | 4-paragraph founder story (with real numbers from `/api/impact`) + LinkedIn post variant + X 6-tweet thread variant. | edit tone if you want, otherwise paste as-is |
| **Day 6.1 upload** | [`youtube_description.md`](./youtube_description.md) | Title (<60 chars), 198-word description with chapter markers, 12 tags, optional thumbnail brief. | paste into YouTube upload dialog (visibility = unlisted) |
| **Day 6.2 submit** | [`emergent_submission_form.md`](./emergent_submission_form.md) | Every field on app.emergent.sh/raj pre-pasted with character-count-compliant copy + 16-item tick-off checklist. | open <https://app.emergent.sh/raj> + paste field-by-field |
| **Day 6.3 publish** | [`founder_story.md`](./founder_story.md) sections "Public post (LinkedIn)" + "Tweet thread variant (X)" | Short-form posts ready to publish. Search-replace `[YOUTUBE_URL]` with the unlisted URL from Day 6.1. | paste into LinkedIn + X |
| **Day 7+ long-form** | [`linkedin_longform.md`](./linkedin_longform.md) | ~700-word LinkedIn article for post-submission distribution. Publish 24-72 hours after Day 6. | LinkedIn → Write Article |

---

## Field-by-field flow on submission day

```
Day 5.4  →  Record demo using demo_script.md + sample_upload.csv
            (founder@bytehubble.com / ByteHubble@2025 — pre-fill works)
            ↓
Day 5.5  →  Read founder_story.md, tweak voice if needed
            ↓
Day 6.1  →  YouTube → Upload → paste from youtube_description.md
            → Save unlisted URL
            ↓
Day 6.2  →  emergent.sh/raj → paste each field from emergent_submission_form.md
            → demo video URL = YouTube URL from above
            → Hit Submit
            ↓
Day 6.3  →  LinkedIn post + X 6-tweet thread (from founder_story.md)
            DM 10 founders you actually know
            ↓
Day 7    →  Publish linkedin_longform.md as a Native Article
            (24-72h after the short post)
            Run scripts/monitor_prod.py daily — fix only demo-path-breakers
```

---

## Production health monitor (Day 7+)

While the upvote phase is open (Days 7-15), run this hourly or behind a
cron so you catch demo-path regressions before judges do:

```bash
cd backend
source .venv/bin/activate
PROD_ADMIN_PASSWORD='ByteHubble@2025' \
  python -m scripts.monitor_prod -v
```

What it checks (silent unless something breaks):
1. Backend reachable inside 30 s (cold-start tolerant)
2. Admin login still works
3. Audit chain verifies clean
4. Morning brief still uses live Claude Haiku (not template fallback)

Exit code 1 means something regressed. Pipe into UptimeRobot, Pushover,
or a Discord webhook for free hourly alerting.

---

## Live URLs (canonical)

- Backend: <https://revora-backend-1in4.onrender.com>
- Frontend: <https://revenue-recovery-os1.vercel.app>
- DB: Neon `ep-dark-paper-atti4v7h.c-9.us-east-1.aws.neon.tech/neondb`
- Repo: <https://github.com/Abhi-mishra998/revenue-recovery-os>

## Demo credentials (founder seed tenant)

- Email: `founder@bytehubble.com`
- Password: `ByteHubble@2025`
- Has: 12 seed clients · 14 proposals · 10 invoices

## Real-data tenant (kept clean for your ByteHubble import)

- Email: `abhishek.mishra@bytehubble.ai`
- Password: `ByteHubble@2025` (same)
- Has: 0 rows — ready for the Day 5.1 real CSV upload (whenever you have it)
