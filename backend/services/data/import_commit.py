"""
Row-to-doc builders for the importer. Pure functions — the SQL inserts and
transaction live in the /api/import/commit endpoint so a single with_user
context wraps the whole import (atomic per /commit call).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

_VALID_STAGES = {"sent", "negotiating", "won", "lost"}
_STAGE_ALIASES = {
    # initial outreach
    "open": "sent",
    "new": "sent",
    "active": "sent",
    "cold": "sent",
    "proposal sent": "sent",
    "proposal_sent": "sent",
    # mid-pipeline / actively engaged
    "in progress": "negotiating",
    "in_progress": "negotiating",
    "negotiation": "negotiating",
    "follow-up": "negotiating",
    "follow up": "negotiating",
    "followup": "negotiating",
    "decision pending": "negotiating",
    "decision_pending": "negotiating",
    "qualified": "negotiating",
    # outcomes
    "closed won": "won",
    "closed_won": "won",
    "closed": "won",
    "lost": "lost",
    "closed lost": "lost",
    "closed_lost": "lost",
    "dead": "lost",
    "dropped": "lost",
}
_PAID_TOKENS = {"paid", "complete", "completed", "settled"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _g(row: dict, mapping: dict, field: str) -> Optional[str]:
    """Read row[mapping[field]] safely; return None if unmapped/empty."""
    src = mapping.get(field)
    if not src or src not in row:
        return None
    v = row[src]
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _to_money(v: Optional[str]) -> Optional[float]:
    if v is None:
        return None
    s = re.sub(r"[^\d.\-]", "", v)
    if not s or s in ("-", ".", "-."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_date(v: Optional[str]) -> Optional[str]:
    """Parse a date string; return ISO string or None."""
    if not v:
        return None
    parsed = pd.to_datetime(v, errors="coerce", dayfirst=False, format="mixed")
    if pd.isna(parsed):
        parsed = pd.to_datetime(v, errors="coerce", dayfirst=True, format="mixed")
    if pd.isna(parsed):
        return None
    return parsed.isoformat()


def _normalize_stage(v: Optional[str]) -> str:
    if not v:
        return "sent"
    s = v.lower().strip()
    if s in _VALID_STAGES:
        return s
    return _STAGE_ALIASES.get(s, "sent")


def build_client_doc(row: dict, mapping: dict, owner_id: str) -> Optional[dict]:
    company = _g(row, mapping, "company_name")
    if not company:
        return None
    return {
        "id": str(uuid.uuid4()),
        "owner_id": owner_id,
        "company_name": company,
        "contact_name": _g(row, mapping, "contact_name") or "",
        "email": _g(row, mapping, "email"),
        "phone": _g(row, mapping, "phone"),
        "whatsapp": None,
        "industry": None,
        "language": "English",
        "notes": None,
        "created_at": _now_iso(),
    }


def build_proposal_doc(row: dict, mapping: dict, owner_id: str, client_id: str) -> Optional[dict]:
    value = _to_money(_g(row, mapping, "value_inr"))
    if value is None:
        return None
    now = _now_iso()
    return {
        "id": str(uuid.uuid4()),
        "owner_id": owner_id,
        "client_id": client_id,
        "title": _g(row, mapping, "title") or "Imported deal",
        "value_inr": value,
        "sent_date": _to_date(_g(row, mapping, "sent_date")) or now,
        "last_contact_date": _to_date(_g(row, mapping, "last_contact_date")) or now,
        "stage": _normalize_stage(_g(row, mapping, "stage")),
        "outcome_at": None,
        "notes": None,
        "created_at": now,
    }


def build_invoice_doc(row: dict, mapping: dict, owner_id: str, client_id: str) -> Optional[dict]:
    inv_no = _g(row, mapping, "invoice_no")
    amount = _to_money(_g(row, mapping, "amount_inr"))
    due = _to_date(_g(row, mapping, "due_date"))
    if not inv_no or amount is None or not due:
        return None
    now = _now_iso()
    status = (_g(row, mapping, "status") or "").lower().strip()
    paid_date = now if status in _PAID_TOKENS else None
    return {
        "id": str(uuid.uuid4()),
        "owner_id": owner_id,
        "client_id": client_id,
        "invoice_no": inv_no,
        "amount_inr": amount,
        "due_date": due,
        "paid_date": paid_date,
        "issued_at": now,
        "notes": None,
        "created_at": now,
    }
