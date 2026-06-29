"""
Pre-mapping heuristics for the importer. One pandas pass produces:
column_types, data_quality, and quick_signals — used by the onboarding
'We found N customers · ₹X pipeline · ...' teaser BEFORE the LLM mapper runs.

Everything here is intentionally crude. The LLM mapper + the real Revenue
Health analytics are the source of truth. These numbers exist to show the
founder the system understands the file inside 3 seconds.
"""

from __future__ import annotations

import io
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import pandas as pd

_MONEY_RE = re.compile(r"^[\s₹$€£]?[\d][\d,.\s]*$")
_CURRENCY_SYMBOLS = {"₹": "INR", "$": "USD", "€": "EUR", "£": "GBP"}
_OVERDUE_TOKENS = {"overdue", "unpaid", "late", "past due", "past_due", "due"}
_MAX_ROWS = 10_000  # ponytail: cap rows in jsonb; switch to object storage if breached


def _is_money(v: str) -> bool:
    return bool(v) and bool(_MONEY_RE.match(v.strip()))


def _parse_dates(series: pd.Series) -> pd.Series:
    """Try day-first then month-first; merge. Returns tz-naive datetime64 (UTC assumed)."""
    out = pd.to_datetime(series, errors="coerce", dayfirst=False, format="mixed")
    if out.isna().any():
        alt = pd.to_datetime(series, errors="coerce", dayfirst=True, format="mixed")
        out = out.fillna(alt)
    return out


def _classify(values: list[str]) -> str:
    nonempty = [v.strip() for v in values if v and v.strip()]
    if not nonempty:
        return "empty"
    n = len(nonempty)
    if sum(1 for v in nonempty if _is_money(v)) / n >= 0.7:
        return "money"
    parsed = _parse_dates(pd.Series(nonempty))
    if parsed.notna().sum() / n >= 0.7:
        return "date"
    uniq = len(set(nonempty))
    if uniq >= 3 and uniq / n >= 0.8:
        return "identifier"
    if 2 <= uniq <= max(5, int(n * 0.3)):
        return "status"
    return "text"


def _detect_currency(df: pd.DataFrame, money_cols: list[str]) -> str:
    counts: Counter = Counter()
    for col in money_cols:
        for v in df[col].astype(str):
            for sym, code in _CURRENCY_SYMBOLS.items():
                if sym in v:
                    counts[code] += 1
                    break
    return counts.most_common(1)[0][0] if counts else "INR"


def _money_sum(series: pd.Series) -> int:
    def to_num(v: Any) -> float:
        s = re.sub(r"[^\d.\-]", "", str(v))
        try:
            return float(s) if s and s not in ("-", ".", "-.") else 0.0
        except ValueError:
            return 0.0

    return int(series.apply(to_num).sum())


def _read_xlsx(file_bytes: bytes) -> pd.DataFrame:
    """Read an .xlsx file. Single-sheet only for v1 — multi-sheet uploads
    raise so the founder explicitly picks which sheet to import (Day 3+)."""
    with pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl") as xf:
        if len(xf.sheet_names) > 1:
            raise ValueError(f"Multi-sheet workbooks not supported yet (found {len(xf.sheet_names)} sheets)")
        return xf.parse(xf.sheet_names[0], dtype=str, keep_default_na=False)


def analyze_file(file_bytes: bytes, filename: str = "") -> dict:
    """Single-pass analysis. Dispatches on extension; falls back to CSV."""
    name = (filename or "").lower()
    try:
        if name.endswith((".xlsx", ".xlsm")):
            df = _read_xlsx(file_bytes)
        else:
            df = pd.read_csv(io.BytesIO(file_bytes), dtype=str, keep_default_na=False)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Could not read file: {e}") from e
    return _analyze_df(df)


def analyze_csv(file_bytes: bytes) -> dict:
    """Back-compat alias. Prefer analyze_file()."""
    return analyze_file(file_bytes, filename="file.csv")


def _analyze_df(df: pd.DataFrame) -> dict:
    if df.empty or not list(df.columns):
        raise ValueError("File has no rows or no columns")
    if len(df) > _MAX_ROWS:
        raise ValueError(f"File exceeds {_MAX_ROWS} rows (got {len(df)})")

    df = df.fillna("")
    headers = list(df.columns)

    buckets: dict[str, list[str]] = {
        "money": [],
        "date": [],
        "status": [],
        "identifier": [],
        "text": [],
        "empty": [],
    }
    for col in headers:
        buckets[_classify(df[col].astype(str).tolist())].append(col)

    total_rows = len(df)
    duplicates = int(df.duplicated().sum())
    name_col = buckets["identifier"][0] if buckets["identifier"] else (headers[0] if headers else None)
    blank_names = int((df[name_col].astype(str).str.strip() == "").sum()) if name_col else 0
    blank_dates = (
        int(df[buckets["date"]].apply(lambda s: s.astype(str).str.strip() == "").any(axis=1).sum())
        if buckets["date"]
        else 0
    )
    currency = _detect_currency(df, buckets["money"]) if buckets["money"] else "INR"

    data_quality = {
        "rows": total_rows,
        "duplicates": duplicates,
        "blank_dates": blank_dates,
        "blank_names": blank_names,
        "currency": currency,
    }

    silent_clients = inactive_deals = overdue_invoices = 0
    pipeline_inr = 0

    if buckets["date"]:
        last_date_col = buckets["date"][-1]
        parsed = _parse_dates(df[last_date_col].astype(str))
        now_naive = pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None))
        try:
            days = (now_naive - parsed).dt.days
        except TypeError:
            # parsed has tz info; strip
            days = (now_naive - parsed.dt.tz_localize(None)).dt.days
        silent_clients = int((days > 14).sum())
        inactive_deals = int((days > 30).sum())

    if buckets["money"]:
        pipeline_inr = _money_sum(df[buckets["money"][0]])

    if buckets["status"]:
        vals = df[buckets["status"][0]].astype(str).str.lower().str.strip()
        overdue_invoices = int(vals.isin(_OVERDUE_TOKENS).sum())

    quick_signals = {
        "silent_clients_count": silent_clients,
        "inactive_deals_count": inactive_deals,
        "overdue_invoices_count": overdue_invoices,
        "pipeline_inr": pipeline_inr,
    }

    column_types = {k: v for k, v in buckets.items() if v}
    sample_rows = df.head(5).to_dict(orient="records")
    raw_rows = df.to_dict(orient="records")

    return {
        "headers": headers,
        "sample_rows": sample_rows,
        "raw_rows": raw_rows,
        "column_types": column_types,
        "data_quality": data_quality,
        "quick_signals": quick_signals,
    }
