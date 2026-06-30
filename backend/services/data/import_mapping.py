"""
Importer column mapper. Two halves:
  * TARGET_FIELDS: minimum set of fields per target table the founder needs
    to upload.
  * heuristic_mapping(): pure-Python guess via synonyms + difflib ratio.
    Always computed, always returned alongside the LLM suggestion so /map
    never hard-blocks on an LLM outage.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Optional

# Day 1 lightweight schema per SPRINT.md §5 Day 1 cut/skip.
# Each entry: (target_field, required, [synonyms])
TARGET_FIELDS: dict[str, list[tuple[str, bool, list[str]]]] = {
    "clients": [
        (
            "company_name",
            True,
            [
                "company",
                "client",
                "customer",
                "business",
                "account",
                "name",
                "client name",
                "customer name",
                "company name",
                "organization",
                "business name",
            ],
        ),
        (
            "contact_name",
            False,
            [
                "contact name",
                "contact person",
                "person",
                "buyer",
                "decision maker",
                "owner",
                "primary contact",
                "poc",
            ],
        ),
        ("email", False, ["email", "e-mail", "email id", "email address", "mail"]),
        ("phone", False, ["phone", "phone number", "mobile", "tel", "telephone", "contact number"]),
        ("whatsapp", False, ["whatsapp", "whats app", "wa", "whatsapp number"]),
        (
            "preferred_channel",
            False,
            ["preferred channel", "channel", "contact channel", "preferred contact", "pref channel"],
        ),
    ],
    "proposals": [
        (
            "client_name",
            True,
            ["client", "customer", "company", "client name", "customer name", "account", "business"],
        ),
        ("title", False, ["title", "deal", "deal name", "opportunity", "project", "subject", "proposal"]),
        (
            "value_inr",
            True,
            [
                "value",
                "deal value",
                "amount",
                "revenue",
                "price",
                "deal size",
                "₹",
                "inr",
                "total",
                "deal amount",
            ],
        ),
        ("stage", False, ["stage", "status", "state", "pipeline stage", "pipeline"]),
        ("sent_date", False, ["sent", "sent date", "date sent", "created", "issued", "start date"]),
        (
            "last_contact_date",
            False,
            ["last contact", "last contact date", "last touch", "last activity", "updated", "last talk"],
        ),
    ],
    "invoices": [
        ("client_name", True, ["client", "customer", "company", "client name", "customer name", "business"]),
        (
            "invoice_no",
            True,
            ["invoice no", "invoice number", "invoice", "inv", "inv no", "bill no", "bill number"],
        ),
        ("amount_inr", True, ["amount", "value", "total", "₹", "inr", "billed"]),
        ("due_date", True, ["due", "due date", "deadline", "payment due", "pay by"]),
        ("status", False, ["status", "state", "paid", "payment status"]),
    ],
}

_NORM_RE = re.compile(r"[^a-z0-9]+")


def _norm(s: str) -> str:
    return _NORM_RE.sub(" ", s.lower()).strip()


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def heuristic_mapping(headers: list[str], target: str) -> list[dict]:
    """Return [{target_field, source_header|None, confidence}] for every target
    field. Two-pass: exact normalized matches first (so 'Deal Value' goes to
    value_inr before title even though title's synonyms contain 'deal'); then
    substring/fuzzy for whatever's left."""
    spec = TARGET_FIELDS.get(target)
    if spec is None:
        raise ValueError(f"unknown target: {target}")

    results: dict[str, dict] = {
        f[0]: {"target_field": f[0], "source_header": None, "confidence": 0.0} for f in spec
    }
    used_headers: set[str] = set()
    norm_headers = {h: _norm(h) for h in headers}

    # Pass 1 — exact normalized match in synonym list
    for field, _required, synonyms in spec:
        synonym_norms = {_norm(s) for s in (synonyms + [field])}
        for h, h_norm in norm_headers.items():
            if h in used_headers:
                continue
            if h_norm in synonym_norms:
                results[field] = {"target_field": field, "source_header": h, "confidence": 1.0}
                used_headers.add(h)
                break

    # Pass 2 — substring + fuzzy for unmapped fields
    for field, _required, synonyms in spec:
        if results[field]["source_header"]:
            continue
        synonym_norms = [_norm(s) for s in (synonyms + [field])]
        best_header, best_score = None, 0.0
        for h, h_norm in norm_headers.items():
            if h in used_headers:
                continue
            if any(s and (s in h_norm or h_norm in s) for s in synonym_norms):
                if best_score < 0.9:
                    best_header, best_score = h, 0.9
                continue
            r = max(_ratio(h, s) for s in synonyms + [field])
            if r > best_score and r >= 0.6:
                best_header, best_score = h, round(r, 2)
        if best_header:
            results[field] = {"target_field": field, "source_header": best_header, "confidence": best_score}
            used_headers.add(best_header)

    return [results[f[0]] for f in spec]


def llm_user_prompt(target: str, headers: list[str], sample_rows: list[dict]) -> str:
    """Compact prompt for the schema-validated LLM call."""
    field_lines = []
    for field, required, synonyms in TARGET_FIELDS[target]:
        tag = "REQUIRED" if required else "optional"
        field_lines.append(f"- {field} ({tag}) — typical names: {', '.join(synonyms[:5])}")
    rows_preview = sample_rows[:3]  # keep prompt small
    return (
        f"Target table: {target}\n\n"
        f"Source CSV headers (verbatim): {headers}\n\n"
        f"Sample rows (first 3):\n{rows_preview}\n\n"
        f"Target fields the founder must map:\n" + "\n".join(field_lines) + "\n\n"
        "For EVERY target field above, return one mapping object with "
        "(target_field, source_header, confidence 0-1). Use source_header=null "
        "when no source column fits. Be conservative: confidence < 0.6 means "
        "'I'm guessing — show the dropdown override'. Do not invent column names."
    )


LLM_SYSTEM = (
    "You map columns from an uploaded CRM CSV onto a known target schema. "
    "You return STRICT JSON matching the MappingSuggestion schema — a list of "
    "FieldMapping objects under the 'mappings' key. No prose, no code fences."
)
