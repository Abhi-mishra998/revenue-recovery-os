"""
ByteHubble realistic demo seed — schema v2 (locked-in field names).

Used in two places:
  1. server.py startup — idempotent (skips if owner already has clients).
  2. scripts/reset_demo.py — wipe & reseed in one command.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ago(days: int) -> str:
    return (_now() - timedelta(days=days)).isoformat()


def _ahead(days: int) -> str:
    return (_now() + timedelta(days=days)).isoformat()


CLIENTS = [
    {"company_name": "Nexora Retail",            "contact_name": "Priya Sharma",     "email": "priya@nexora.in",          "phone": "+91 98201 84421", "whatsapp": "+91 98201 84421", "industry": "E-commerce",        "language": "English", "notes": "Founder. Wanted Shopify-to-custom migration."},
    {"company_name": "Trikon Labs",              "contact_name": "Rohan Mehta",      "email": "rohan@trikonlabs.com",     "phone": "+91 98115 27384", "whatsapp": "+91 98115 27384", "industry": "ML / AI",           "language": "English", "notes": "CTO. Tight on dev capacity, hiring ML engineers."},
    {"company_name": "Sundari Studios",          "contact_name": "Anjali Iyer",      "email": "anjali@sundaristudios.in", "phone": "+91 99100 31102", "whatsapp": "+91 99100 31102", "industry": "Design",            "language": "English", "notes": "Boutique design house, slow decision cycle."},
    {"company_name": "Patel & Associates CA",    "contact_name": "Vikram Patel",     "email": "vp@patelca.in",            "phone": "+91 95605 88555", "whatsapp": "+91 95605 88555", "industry": "Chartered Accounting","language": "English", "notes": "Old-school CA firm in Ahmedabad. Price-sensitive."},
    {"company_name": "FinKart",                  "contact_name": "Kunal Desai",      "email": "kunal@finkart.io",         "phone": "+91 96320 41440", "whatsapp": "+91 96320 41440", "industry": "Fintech",           "language": "English", "notes": "Series A fintech, fast-moving. Decision-maker."},
    {"company_name": "Bloom Wellness",           "contact_name": "Meera Krishnan",   "email": "meera@bloom.health",       "phone": "+91 91760 71008", "whatsapp": "+91 91760 71008", "industry": "D2C Wellness",      "language": "English", "notes": "D2C wellness brand, founder-led."},
    {"company_name": "Hyderabad Heritage Hotels","contact_name": "Arjun Reddy",      "email": "arjun@hhhotels.in",        "phone": "+91 90080 22217", "whatsapp": "+91 90080 22217", "industry": "Hospitality",       "language": "English", "notes": "Boutique hotel group; IT through CFO."},
    {"company_name": "Kapoor Legal LLP",         "contact_name": "Neha Kapoor",      "email": "neha@kapoorlegal.in",      "phone": "+91 98180 47266", "whatsapp": "+91 98180 47266", "industry": "Legal",             "language": "English", "notes": "Corporate law firm. Wanted client-portal."},
    {"company_name": "Pixelmoss Games",          "contact_name": "Siddharth Joshi",  "email": "sid@pixelmoss.gg",         "phone": "+91 99023 19840", "whatsapp": "+91 99023 19840", "industry": "Gaming",            "language": "English", "notes": "Indie game studio. Cash-rich after Steam launch."},
    {"company_name": "Sahas Mobility",           "contact_name": "Tanvi Bhatia",     "email": "tanvi@sahasmobility.com",  "phone": "+91 70459 33221", "whatsapp": "+91 70459 33221", "industry": "EV / Mobility",     "language": "English", "notes": "Seed-stage EV-fleet startup, Bengaluru."},
    {"company_name": "Mantra Media",             "contact_name": "Aditya Iyer",      "email": "aditya@mantramedia.in",    "phone": "+91 97000 11824", "whatsapp": "+91 97000 11824", "industry": "Marketing",         "language": "English", "notes": "Mid-size marketing agency, partner."},
    {"company_name": "Greenly Foods",            "contact_name": "Pooja Reddy",      "email": "pooja@greenly.in",         "phone": "+91 99650 80112", "whatsapp": "+91 99650 80112", "industry": "D2C Foods",         "language": "English", "notes": "D2C foods, expanding to Tier-2."},
]

# (client_idx, title, value_inr, sent_days_ago, last_days_ago, stage)
PROPOSALS = [
    # active stage with recent contact
    (4,  "FinKart mobile app v2 — KYC + UPI flows",          620000,  5,  2,  "negotiating"),
    (5,  "Bloom CRM customization + WhatsApp integration",   145000,  6,  3,  "sent"),
    (10, "Mantra analytics warehouse + dashboard",           295000,  4,  1,  "negotiating"),
    # cold — recoverable bucket
    (0,  "Nexora e-commerce platform rebuild (Next.js)",     450000, 18, 14, "sent"),
    (1,  "ML inference pipeline (Phase 1)",                  285000, 12, 10, "negotiating"),
    (2,  "Sundari brand identity + website",                 180000, 16, 13, "sent"),
    (6,  "Hotel booking engine + channel manager",           875000, 21, 17, "negotiating"),
    (8,  "Pixelmoss web companion app",                      210000, 14, 12, "sent"),
    (11, "Greenly D2C site speed + checkout overhaul",       155000, 13,  9, "negotiating"),
    # dead — silent >21d
    (3,  "Internal tax-portal MVP",                          320000, 40, 32, "sent"),
    (7,  "Kapoor Legal client-portal v1",                    240000, 55, 30, "sent"),
    # closed
    (4,  "FinKart admin panel — phase 1",                    280000, 70, 45, "won"),
    (10, "Mantra Media WordPress speedup",                    85000, 60, 35, "won"),
    (3,  "Patel CA — internal HR portal",                    195000, 80, 50, "lost"),
]

# (client_idx, invoice_no, amount_inr, issued_days_ago, due (("ago"|"ahead", days)), paid_days_ago_or_None)
INVOICES = [
    # paid
    (4,  "BH-2025-011", 310000, 50, ("ago", 20),   18),
    (10, "BH-2025-013",  85000, 40, ("ago", 10),    8),
    # unpaid (not yet overdue)
    (5,  "BH-2025-021",  72500, 12, ("ahead", 10), None),
    (4,  "BH-2025-022", 155000,  8, ("ahead", 7),  None),
    # overdue
    (0,  "BH-2025-014", 225000, 35, ("ago", 5),    None),
    (8,  "BH-2025-020",  90000, 30, ("ago", 6),    None),
    (1,  "BH-2025-016", 142500, 50, ("ago", 20),   None),
    (3,  "BH-2025-009",  95000, 75, ("ago", 45),   None),
    (6,  "BH-2025-007", 425000, 95, ("ago", 65),   None),
    (7,  "BH-2025-005", 180000, 110, ("ago", 80),  None),
]

# Extra colour activities (related_type=proposal|invoice|None, related_id resolved later)
EXTRA_ACTIVITIES = [
    # (client_idx, channel, direction, summary, days_ago)
    (0,  "whatsapp", "outbound", "Pinged Priya on WhatsApp — she asked for revised timeline doc", 10),
    (0,  "call",     "outbound", "Quick call: Priya said internal review pending with co-founder", 7),
    (1,  "email",    "outbound", "Sent Phase-1 SOW + cost breakdown",                              11),
    (1,  "meeting",  "internal", "Discovery call (45 min) on inference scale targets",             20),
    (4,  "call",     "outbound", "Kickoff call with FinKart product team",                          5),
    (5,  "whatsapp", "inbound",  "Meera confirmed she wants to start next sprint",                  3),
    (6,  "email",    "outbound", "Sent channel-manager comparison sheet",                          15),
    (7,  "note",     "internal", "Neha mentioned partner change — re-pitching post-March",         30),
    (10, "meeting",  "internal", "Quarterly review with Mantra — pipeline looks healthy",           4),
    (11, "email",    "inbound",  "Pooja shared current site analytics CSV",                        10),
]


async def reset_demo_data_for_owner(db, owner_id: str) -> dict:
    r_c = await db.clients.delete_many({"owner_id": owner_id})
    r_p = await db.proposals.delete_many({"owner_id": owner_id})
    r_i = await db.invoices.delete_many({"owner_id": owner_id})
    r_a = await db.activities.delete_many({"owner_id": owner_id})
    return {
        "clients_deleted": r_c.deleted_count,
        "proposals_deleted": r_p.deleted_count,
        "invoices_deleted": r_i.deleted_count,
        "activities_deleted": r_a.deleted_count,
    }


async def seed_demo_for_owner(db, owner_id: str, *, force: bool = False) -> dict:
    if not force:
        existing = await db.clients.count_documents({"owner_id": owner_id})
        if existing > 0:
            return {"skipped": True, "reason": "existing data present"}

    client_ids = []
    for idx, c in enumerate(CLIENTS):
        cid = str(uuid.uuid4())
        await db.clients.insert_one({
            **c, "id": cid, "owner_id": owner_id,
            "created_at": _ago(60 - idx),
        })
        client_ids.append(cid)

    for (client_idx, title, value_inr, sent_d, last_d, stage) in PROPOSALS:
        pid = str(uuid.uuid4())
        cid = client_ids[client_idx]
        await db.proposals.insert_one({
            "id": pid, "owner_id": owner_id, "client_id": cid,
            "title": title, "value_inr": value_inr,
            "sent_date": _ago(sent_d),
            "last_contact_date": _ago(last_d),
            "stage": stage, "notes": "",
            "created_at": _ago(sent_d),
        })
        await db.activities.insert_one({
            "id": str(uuid.uuid4()), "owner_id": owner_id, "client_id": cid,
            "related_type": "proposal", "related_id": pid,
            "channel": "email", "direction": "outbound",
            "summary": f"Sent proposal: {title}",
            "created_at": _ago(sent_d),
        })

    for (client_idx, invoice_no, amount_inr, issued_d, due, paid_days) in INVOICES:
        cid = client_ids[client_idx]
        due_iso = _ahead(due[1]) if due[0] == "ahead" else _ago(due[1])
        iid = str(uuid.uuid4())
        await db.invoices.insert_one({
            "id": iid, "owner_id": owner_id, "client_id": cid,
            "invoice_no": invoice_no, "amount_inr": amount_inr,
            "issued_at": _ago(issued_d),
            "due_date": due_iso,
            "paid_date": _ago(paid_days) if paid_days is not None else None,
            "notes": "", "created_at": _ago(issued_d),
        })
        await db.activities.insert_one({
            "id": str(uuid.uuid4()), "owner_id": owner_id, "client_id": cid,
            "related_type": "invoice", "related_id": iid,
            "channel": "note", "direction": "internal",
            "summary": "Invoice #" + invoice_no + " raised" + (" · marked PAID" if paid_days is not None else ""),
            "created_at": _ago(issued_d),
        })

    for (client_idx, channel, direction, summary, days_ago) in EXTRA_ACTIVITIES:
        cid = client_ids[client_idx]
        await db.activities.insert_one({
            "id": str(uuid.uuid4()), "owner_id": owner_id, "client_id": cid,
            "related_type": None, "related_id": None,
            "channel": channel, "direction": direction,
            "summary": summary, "created_at": _ago(days_ago),
        })

    return {
        "clients": len(CLIENTS),
        "proposals": len(PROPOSALS),
        "invoices": len(INVOICES),
        "extra_activities": len(EXTRA_ACTIVITIES),
    }
