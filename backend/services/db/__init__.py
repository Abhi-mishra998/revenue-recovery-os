"""
Engine-aware data-access entry point.

The application code talks to repos (services/db/repos/*) which dispatch on
the active engine. This module owns the engine-selection knob.

DB_ENGINE env:
  mongo     — default; the legacy motor path keeps working untouched.
  postgres  — repos route to asyncpg + RLS-aware sessions (services/db/pg.py).
"""
from __future__ import annotations

import os


def active_engine() -> str:
    return (os.environ.get("DB_ENGINE") or "mongo").strip().lower()


def is_postgres() -> bool:
    return active_engine() == "postgres"


def is_mongo() -> bool:
    return active_engine() == "mongo"
