"""
Shared (de)serialisation helpers between the postgres rows and the dict shape
the API has always returned. Goal: callers see the same keys/types they did
on the mongo path.
"""
from __future__ import annotations

import json
from typing import Any


def row_to_dict(record) -> dict:
    """asyncpg Record -> plain dict. jsonb columns are returned by asyncpg as
    strings; decode them here so callers see real dicts/lists."""
    if record is None:
        return None  # type: ignore[return-value]
    d = dict(record)
    for k, v in list(d.items()):
        if isinstance(v, str) and k in ("context", "metadata", "prior_value",
                                         "new_value", "channel_counts", "last_outcomes"):
            try:
                d[k] = json.loads(v)
            except Exception:
                pass
    return d


def rows_to_dicts(records) -> list[dict]:
    return [row_to_dict(r) for r in records]


def jsonb(value: Any) -> str | None:
    """Encode a Python value for a jsonb parameter."""
    if value is None:
        return None
    return json.dumps(value, default=str)
