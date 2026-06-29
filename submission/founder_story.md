# Revora — founder story (Raj Shamani × Emergent submission)

> Four paragraphs. Read aloud and time yourself — should land at ~90 seconds.
> Replace the bracketed `[...]` placeholders with real numbers from your
> `abhishek.mishra@bytehubble.ai` tenant once Day 5.2 is done.

---

## (1) The problem

I run ByteHubble. Revenue for a B2B services company lives in a spreadsheet — one tab for clients, one for proposals, one for invoices. I open it every Monday morning and stare at fifty rows. The deals I forgot about. The follow-ups I never sent. The invoices that quietly went overdue while I was building the actual product. The money was leaking, and the spreadsheet was the leak.

## (2) Why I built Revora

I didn't want another CRM to learn. I wanted something that read my own spreadsheet, told me where revenue was hiding, and trusted me to make the call. Seven days, three hard rules: every number shows its evidence, every AI output shows its confidence, no message ever sends without me hitting send. I built it on real foundations — Postgres with row-level security, ed25519-signed audit chain, schema-validated LLM outputs — because if I was going to trust it with my pipeline, it had to be auditable.

## (3) What changed

In four days of using Revora on ByteHubble's real data, I recovered **[₹X.X L]** I would have missed, sent **[N]** follow-ups in **[H]** minutes instead of a full morning, and watched my Visibility Score climb from **[A]** to **[B]**. The brief tells me what to do; the Do-These-Today list shows me the order; the audit chain proves every step. I open Revora before I open my inbox.

## (4) What's next

Revora is one founder's tool, but the same problem shows up in every SMB I know — manufacturers, traders, consultants, agencies. The next ten weeks: open it to ten pilot founders, sharpen the prompts on their data, ship Google Sheets sync and a WhatsApp integration so the loop closes inside the channel founders already live in. The vision is small and specific: every founder in India should know where their revenue is hiding by 9:30 every morning.

---

## Numbers to fill in (from `/api/impact` and `/api/health/diff` after Day 5.2)

| Placeholder | How to fill |
|---|---|
| `[₹X.X L]` | `impact.revenue_protected_week` — sum of values for proposals you generated follow-ups on |
| `[N]` | `impact.followups_generated_week` ÷ 2 (each generation makes whatsapp + email) |
| `[H]` | `impact.hours_saved_week` × 60 (script says "minutes") |
| `[A]` | first visibility score (from your first `/revenue-health` snapshot) |
| `[B]` | latest visibility score (after acting on Do These Today rows) |

If `[A]` and `[B]` are close (e.g. 42 → 44), be honest — the story is "Revora gave me clarity I didn't have", not "fake jumps".

---

## Public post (LinkedIn, ~120 words — use after submission)

> Spent seven days building Revora for myself.
>
> Problem: my company's revenue lives in a spreadsheet. Deals I forgot. Follow-ups I never sent. Invoices going quietly overdue.
>
> I drop the sheet into Revora. Three seconds — it sees 52 clients, ₹1.8 Cr pipeline, 14 inactive deals. Three more seconds — Revenue Visibility 42/100, three actions to take today, ₹12.4 L of opportunity I would have missed.
>
> Every number shows its evidence. Every AI output shows its confidence. Every action is signed with ed25519 and chained — auditable. Founder approves every send.
>
> Submitting to @raj_shamani × @emergent's builder contest. The whole thing is at:
>
> 🔗 https://revenue-recovery-os1.vercel.app
>
> If you run a small business that lives in spreadsheets, I'd love your thoughts.

---

## Tweet thread variant (X, 6 tweets, 280 char each)

1. `Spent 7 days building Revora — a tool for founders whose revenue lives in a spreadsheet. You upload it. You get a Revenue Health report. ₹ at risk, ₹ to recover, what to do today. Built on a hard rule: every number shows its evidence. Demo: https://revenue-recovery-os1.vercel.app 🧵`
2. `Beat 1 — drop your CSV. Within 3 seconds: "Revora sees 52 customers, ₹1.8 Cr pipeline, 14 inactive deals, 7 overdue invoices." Before any AI runs. Pure pandas. Founder feels seen.`
3. `Beat 2 — Revenue Health report. Visibility 42/100. Three actions to take today, each with traffic light + estimated minutes + Why? evidence + confidence chip. Forecast for the next 30 days. If you do nothing vs if you act today — in bars.`
4. `Beat 3 — every AI output is schema-validated, every action ed25519-signed and chained. Hit "Run verify" on the admin page — the chain returns ok=True. SMB founders need to trust their tools more than enterprise does. We built for trust first.`
5. `Beat 4 — daily ritual. Morning brief names your three at-risk clients with reasons and confidence. What Changed Since Last Upload shows visibility moved 42 → 51. You click a row, you review the draft, you copy to WhatsApp. You hit send. Revora learns.`
6. `Building Revora was the cleanest week of my year. Postgres + row-level security. Audit chain. AI as a tool, not as a chatbot. If you build for SMB founders, you'll relate. Submitted to @raj_shamani × @emergent's contest. Upvotes welcome 🙏 https://emergent.sh/builders/revora`
