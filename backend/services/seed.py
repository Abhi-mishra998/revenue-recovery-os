"""
ByteHubble realistic demo seed.

Used in two places:
  1. server.py startup — idempotent (skips if owner already has clients).
  2. scripts/reset_demo.py — wipe & reseed in one command.

The seed paints a believable snapshot of an Indian dev agency 6-8 weeks into a
quarter: a few live deals, a chunk of cold proposals (the recoverable bucket),
a couple of dead ones, real-feeling overdue invoices, and an activity timeline.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import List


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ago(days: int) -> str:
    return (_now() - timedelta(days=days)).isoformat()


def _ahead(days: int) -> str:
    return (_now() + timedelta(days=days)).isoformat()


CLIENTS = [
    {"name": "Priya Sharma",     "company": "Nexora Retail",         "email": "priya@nexora.in",          "phone": "+91 98201 84421", "notes": "Founder. Wanted Shopify-to-custom migration."},
    {"name": "Rohan Mehta",      "company": "Trikon Labs",           "email": "rohan@trikonlabs.com",     "phone": "+91 98115 27384", "notes": "CTO. Tight on dev capacity, hiring ML engineers."},
    {"name": "Anjali Iyer",      "company": "Sundari Studios",       "email": "anjali@sundaristudios.in", "phone": "+91 99100 31102", "notes": "Boutique design house, slow decision cycle."},
    {"name": "Vikram Patel",     "company": "Patel & Associates CA", "email": "vp@patelca.in",            "phone": "+91 95605 88555", "notes": "Old-school CA firm in Ahmedabad. Price-sensitive."},
    {"name": "Kunal Desai",      "company": "FinKart",               "email": "kunal@finkart.io",         "phone": "+91 96320 41440", "notes": "Series A fintech, fast-moving. Decision-maker."},
    {"name": "Meera Krishnan",   "company": "Bloom Wellness",        "email": "meera@bloom.health",       "phone": "+91 91760 71008", "notes": "D2C wellness brand, founder-led."},
    {"name": "Arjun Reddy",      "company": "Hyderabad Heritage Hotels", "email": "arjun@hhhotels.in",    "phone": "+91 90080 22217", "notes": "Boutique hotel group, IT decisions through their CFO."},
    {"name": "Neha Kapoor",      "company": "Kapoor Legal LLP",      "email": "neha@kapoorlegal.in",      "phone": "+91 98180 47266", "notes": "Corporate law firm. Wanted client-portal."},
    {"name": "Siddharth Joshi",  "company": "Pixelmoss Games",       "email": "sid@pixelmoss.gg",         "phone": "+91 99023 19840", "notes": "Indie game studio. Cash-rich after Steam launch."},
    {"name": "Tanvi Bhatia",     "company": "Sahas Mobility",        "email": "tanvi@sahasmobility.com",  "phone": "+91 70459 33221", "notes": "Seed-stage EV-fleet startup, Bengaluru."},
    {"name": "Aditya Iyer",      "company": "Mantra Media",          "email": "aditya@mantramedia.in",    "phone": "+91 97000 11824", "notes": "Mid-size marketing agency, partner."},
    {"name": "Pooja Reddy",      "company": "Greenly Foods",         "email": "pooja@greenly.in",         "phone": "+91 99650 80112", "notes": "D2C foods, expanding to Tier-2."},
]

# (client_idx, title, value, sent_days_ago, last_days_ago, manual_status)
PROPOSALS = [
    # ---- Active (≤7 days silent)
    (4, "FinKart mobile app v2 — KYC + UPI flows",          620000,  5,  2, None),
    (5, "Bloom CRM customization + WhatsApp integration",   145000,  6,  3, None),
    (10, "Mantra analytics warehouse + dashboard",          295000,  4,  1, None),
    # ---- Cold (8-21 days silent) — the recoverable bucket
    (0,  "Nexora e-commerce platform rebuild (Next.js)",    450000, 18, 14, None),
    (1,  "ML inference pipeline (Phase 1)",                 285000, 12, 10, None),
    (2,  "Sundari brand identity + website",                180000, 16, 13, None),
    (6,  "Hotel booking engine + channel manager",          875000, 21, 17, None),
    (8,  "Pixelmoss web companion app",                     210000, 14, 12, None),
    (11, "Greenly D2C site speed + checkout overhaul",      155000, 13,  9, None),
    # ---- Dead (>21 days silent OR manually marked)
    (3,  "Internal tax-portal MVP",                         320000, 40, 32, None),
    (7,  "Kapoor Legal client-portal v1",                   240000, 55, 30, None),
    (9,  "Sahas dispatcher dashboard (paused)",             140000, 38, 24, "dead"),
    # ---- Won (closed deals — show the wins)
    (4,  "FinKart admin panel — phase 1",                   280000, 70, 45, "won"),
    (10, "Mantra Media WordPress speedup",                   85000, 60, 35, "won"),
    # ---- Lost
    (3,  "Patel CA — internal HR portal",                   195000, 80, 50, "lost"),
]

# (client_idx, invoice_number, amount, issued_days_ago, due_days_ago OR +days_ahead via "ahead", paid)
INVOICES = [
    # ---- Paid
    (4,  "BH-2025-011", 310000, 50, ("ago", 20), True),
    (10, "BH-2025-013", 85000,  40, ("ago", 10), True),
    # ---- Due (not yet overdue)
    (5,  "BH-2025-021",  72500, 12, ("ahead", 10), False),
    (4,  "BH-2025-022", 155000,  8, ("ahead", 7),  False),
    # ---- Overdue (1-14 days past)
    (0,  "BH-2025-014", 225000, 35, ("ago", 5),  False),
    (8,  "BH-2025-020",  90000, 30, ("ago", 6),  False),
    # ---- Critical (>14 days past)
    (1,  "BH-2025-016", 142500, 50, ("ago", 20), False),
    (3,  "BH-2025-009",  95000, 75, ("ago", 45), False),
    (6,  "BH-2025-007", 425000, 95, ("ago", 65), False),
    (7,  "BH-2025-005", 180000, 110, ("ago", 80), False),
]

# Extra colour activities to make the timeline feel lived-in
EXTRA_ACTIVITIES = [
    # (client_idx, kind, summary, days_ago)
    (0, "whatsapp", "Pinged Priya on WhatsApp — she asked for revised timeline doc",  10),
    (0, "call",     "Quick call: Priya said internal review pending with co-founder",  7),
    (1, "email",    "Sent Phase-1 SOW + cost breakdown",                              11),
    (1, "meeting",  "Discovery call (45 min) on inference scale targets",             20),
    (4, "call",     "Kickoff call with FinKart product team",                          5),
    (5, "whatsapp", "Meera confirmed she wants to start next sprint",                  3),
    (6, "email",    "Sent channel-manager comparison sheet",                          15),
    (7, "note",     "Neha mentioned partner change — re-pitching post-March",         30),
    (10,"meeting",  "Quarterly review with Mantra — pipeline looks healthy",           4),
    (11,"email",    "Pooja shared current site analytics CSV",                        10),
]


async def reset_demo_data_for_owner(db, owner_id: str) -> dict:
    """Delete ALL ByteHubble demo data for this owner_id. Returns counts."""
    r_clients = await db.clients.delete_many({"owner_id": owner_id})
    r_proposals = await db.proposals.delete_many({"owner_id": owner_id})
    r_invoices = await db.invoices.delete_many({"owner_id": owner_id})
    r_activities = await db.activities.delete_many({"owner_id": owner_id})
    return {
        "clients_deleted": r_clients.deleted_count,
        "proposals_deleted": r_proposals.deleted_count,
        "invoices_deleted": r_invoices.deleted_count,
        "activities_deleted": r_activities.deleted_count,
    }


async def seed_demo_for_owner(db, owner_id: str, *, force: bool = False) -> dict:
    """Insert the realistic seed for owner_id. Idempotent unless force=True."""
    if not force:
        existing = await db.clients.count_documents({"owner_id": owner_id})
        if existing > 0:
            return {"skipped": True, "reason": "existing data present"}

    # Clients
    client_ids: List[str] = []
    for idx, c in enumerate(CLIENTS):
        cid = str(uuid.uuid4())
        await db.clients.insert_one({
            **c, "id": cid, "owner_id": owner_id,
            "created_at": _ago(60 - idx),
        })
        client_ids.append(cid)

    # Proposals + 'sent' activity for each
    for (client_idx, title, value, sent_d, last_d, manual_status) in PROPOSALS:
        pid = str(uuid.uuid4())
        cid = client_ids[client_idx]
        await db.proposals.insert_one({
            "id": pid, "owner_id": owner_id, "client_id": cid,
            "title": title, "value": value,
            "sent_at": _ago(sent_d),
            "last_contact_at": _ago(last_d),
            "manual_status": manual_status, "notes": "",
            "created_at": _ago(sent_d),
        })
        await db.activities.insert_one({
            "id": str(uuid.uuid4()), "owner_id": owner_id, "client_id": cid, "proposal_id": pid,
            "kind": "email", "summary": f"Sent proposal: {title}",
            "created_at": _ago(sent_d),
        })

    # Invoices + 'raised' activity for each
    for (client_idx, number, amount, issued_d, due, paid) in INVOICES:
        cid = client_ids[client_idx]
        due_iso = _ahead(due[1]) if due[0] == "ahead" else _ago(due[1])
        iid = str(uuid.uuid4())
        await db.invoices.insert_one({
            "id": iid, "owner_id": owner_id, "client_id": cid,
            "invoice_number": number, "amount": amount,
            "issued_at": _ago(issued_d),
            "due_date": due_iso,
            "paid_at": _ago(2) if paid else None,
            "notes": "", "created_at": _ago(issued_d),
        })
        await db.activities.insert_one({
            "id": str(uuid.uuid4()), "owner_id": owner_id, "client_id": cid, "invoice_id": iid,
            "kind": "note",
            "summary": ("Invoice #" + number + " raised") + (" · marked PAID" if paid else ""),
            "created_at": _ago(issued_d),
        })

    # Extra colour activities
    for (client_idx, kind, summary, days_ago) in EXTRA_ACTIVITIES:
        cid = client_ids[client_idx]
        await db.activities.insert_one({
            "id": str(uuid.uuid4()), "owner_id": owner_id, "client_id": cid,
            "kind": kind, "summary": summary, "created_at": _ago(days_ago),
        })

    return {
        "clients": len(CLIENTS),
        "proposals": len(PROPOSALS),
        "invoices": len(INVOICES),
        "extra_activities": len(EXTRA_ACTIVITIES),
    }
