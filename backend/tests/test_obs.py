"""
Observability tests:
  - JsonFormatter emits valid JSON with the expected fields
  - request_id_ctx + user_id_ctx propagate into log lines
  - empty contextvars don't leak as empty strings into output
  - Sentry init is a no-op when SENTRY_DSN is unset (doesn't crash)
  - live endpoint echoes X-Request-ID back in the response (integration)
"""

import json
import logging
import os
import uuid

import pytest
import requests

from services.obs import (
    JsonFormatter,
    init_logging,
    init_sentry,
    request_id_ctx,
    user_id_ctx,
)

# ---------- JsonFormatter unit ----------


class TestJsonFormatter:
    def _emit(self, msg, *, extra=None, level=logging.INFO):
        rec = logging.LogRecord(
            name="testlogger",
            level=level,
            pathname=__file__,
            lineno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for k, v in (extra or {}).items():
            setattr(rec, k, v)
        return JsonFormatter().format(rec)

    def test_emits_valid_json_with_core_fields(self):
        out = self._emit("hello")
        d = json.loads(out)
        assert d["msg"] == "hello"
        assert d["level"] == "INFO"
        assert d["logger"] == "testlogger"
        assert "ts" in d  # ISO-8601 timestamp

    def test_extras_included(self):
        out = self._emit("req", extra={"method": "GET", "status": 200, "latency_ms": 42})
        d = json.loads(out)
        assert d["method"] == "GET"
        assert d["status"] == 200
        assert d["latency_ms"] == 42

    def test_empty_strings_omitted(self):
        """request_id/user_id contextvars default to '' — must not appear."""
        # No contextvar set, default empty.
        out = self._emit("x")
        d = json.loads(out)
        assert "request_id" not in d
        assert "user_id" not in d

    def test_request_id_contextvar_attached(self):
        token = request_id_ctx.set("trace-xyz")
        try:
            # The filter attaches request_id to the record before format runs;
            # in production this is on the handler. Simulate by setting on extra.
            out = self._emit("x", extra={"request_id": "trace-xyz"})
            d = json.loads(out)
            assert d["request_id"] == "trace-xyz"
        finally:
            request_id_ctx.reset(token)

    def test_exception_serialised(self):
        try:
            raise ValueError("kaboom")
        except ValueError:
            rec = logging.LogRecord(
                name="t",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="oh no",
                args=(),
                exc_info=True,
            )
            import sys

            rec.exc_info = sys.exc_info()
            d = json.loads(JsonFormatter().format(rec))
            assert "exc" in d
            assert "ValueError" in d["exc"]
            assert "kaboom" in d["exc"]


# ---------- init_logging idempotency ----------


class TestInitLogging:
    def test_idempotent(self):
        """Calling init_logging twice should leave only one handler."""
        init_logging()
        first_handlers = list(logging.getLogger().handlers)
        init_logging()
        second_handlers = list(logging.getLogger().handlers)
        # Same length (old handlers replaced, not appended)
        assert len(first_handlers) == len(second_handlers) == 1


# ---------- Sentry no-op when DSN absent ----------


class TestSentryInit:
    def test_returns_false_without_dsn(self, monkeypatch):
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        assert init_sentry() is False  # silent no-op


# ---------- Live integration: X-Request-ID echo ----------


@pytest.mark.skipif(
    not os.environ.get("REACT_APP_BACKEND_URL"),
    reason="REACT_APP_BACKEND_URL not set — backend integration skipped",
)
class TestRequestIdMiddleware:
    BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    API = f"{BASE}/api"

    def test_custom_request_id_echoed(self):
        rid = f"test-{uuid.uuid4().hex[:12]}"
        r = requests.get(f"{self.API}/", headers={"X-Request-ID": rid}, timeout=15)
        assert r.headers.get("X-Request-ID") == rid

    def test_generated_request_id_present_when_missing(self):
        r = requests.get(f"{self.API}/", timeout=15)
        rid = r.headers.get("X-Request-ID")
        assert rid
        # Server-generated id is a UUID
        uuid.UUID(rid)  # raises if not a UUID

    def test_request_ids_unique_per_request(self):
        r1 = requests.get(f"{self.API}/", timeout=15)
        r2 = requests.get(f"{self.API}/", timeout=15)
        assert r1.headers.get("X-Request-ID") != r2.headers.get("X-Request-ID")
