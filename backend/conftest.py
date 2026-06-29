"""
Pytest bootstrap. The integration tests (test_audit, test_auth_edge, etc.) hit
the live backend over HTTP, but ALSO read env vars locally (JWT_SECRET to
forge tokens, DB_ENGINE to decide whether to peek at Postgres vs Mongo for
chain tamper tests). CI exports those explicitly; local dev relies on the
backend/.env file, which the test process does not auto-load.

Loading .env here keeps `pytest tests/` working both locally and in CI without
the dev having to remember to `export` anything.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
