"""
PII redaction for outbound LLM payloads.

Why: a B2B follow-up needs recipient names and company names (so those stay),
but client-supplied free text (notes, titles) can leak emails, phone numbers,
tax IDs etc. Those get tokenised before any provider call. The guardrail
later checks that no token leaked back through.

API:
    redacted, token_map = redact(text)
    cleaned = rehydrate(text, token_map)   # rare — LLM output usually has none

Tokens are bracketed so they look nothing like normal template placeholders
({{ }}, %s, ${...}) — minimises the chance a model will 'helpfully' replace
them. Format: [REDACTED:KIND_N]
"""
from __future__ import annotations

import re
from typing import Pattern

# Order matters: more specific patterns first (PAN before generic digits).
_PATTERNS: list[tuple[str, Pattern[str]]] = [
    ("EMAIL",   re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")),
    ("GSTIN",   re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]\b")),
    ("PAN",     re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("AADHAAR", re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")),
    ("CC",      re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    # Phone last — broadest digit pattern, narrowed to Indian/international formats.
    ("PHONE",   re.compile(r"\+?(?:\d[\s-]?){10,14}")),
]

TOKEN_RE = re.compile(r"\[REDACTED:[A-Z]+_\d+\]")


def redact(text: str) -> tuple[str, dict[str, str]]:
    if not text:
        return text, {}
    counters: dict[str, int] = {}
    token_map: dict[str, str] = {}
    out = text
    for kind, pat in _PATTERNS:
        def _sub(m: re.Match) -> str:
            counters[kind] = counters.get(kind, 0) + 1
            tok = f"[REDACTED:{kind}_{counters[kind]}]"
            token_map[tok] = m.group(0)
            return tok
        out = pat.sub(_sub, out)
    return out, token_map


def rehydrate(text: str, token_map: dict[str, str]) -> str:
    if not text or not token_map:
        return text
    for tok, original in token_map.items():
        text = text.replace(tok, original)
    return text


def has_unrehydrated_tokens(text: str) -> bool:
    """Cheap check used by the guardrail to detect token leaks."""
    return bool(TOKEN_RE.search(text or ""))
