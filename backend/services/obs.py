"""
Observability: JSON-structured logs, request-id propagation, optional Sentry.

No third-party logging library — stdlib Formatter + Filter cover the same
ground in ~50 lines. Sentry is opt-in: SENTRY_DSN env activates it, missing
SDK degrades to a warning instead of crashing the boot.

Usage from server.py:
    from services.obs import init_logging, init_sentry, request_id_ctx
    init_logging()
    init_sentry()
    # middleware wired in server.py: sets request_id_ctx + emits access log
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional

# Per-request context. Middleware sets these on entry; the log filter reads
# them so every emitted line carries the request_id/user_id of its caller.
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
user_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="")


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line. Stable field order via dict
    construction; extras are merged in if the caller passed `extra={...}`."""

    _STANDARD_FIELDS = (
        # Names that LogRecord always has — never write them as 'extra'.
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "taskName",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = request_id_ctx.get()
        uid = user_id_ctx.get()
        if rid:
            payload["request_id"] = rid
        if uid:
            payload["user_id"] = uid
        # Merge any caller-supplied extras (e.g. method/route/status/latency_ms).
        # Skip empty strings — request_id/user_id contextvars default to '' so
        # the filter sets them on every record, but we don't want them in the
        # JSON unless they're actually populated.
        for k, v in record.__dict__.items():
            if k in self._STANDARD_FIELDS or k.startswith("_"):
                continue
            if k in payload:
                continue
            if v == "" or v is None:
                continue
            payload[k] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class _ContextFilter(logging.Filter):
    """Attach request_id/user_id to records that other handlers might emit."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        record.user_id = user_id_ctx.get()
        return True


def init_logging(level: Optional[str] = None) -> None:
    """Reconfigure the root logger with JsonFormatter on stdout.
    Idempotent — safe to call from a startup hook that may re-run."""
    lvl = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()

    root = logging.getLogger()
    # Drop pre-existing handlers (uvicorn installs a basic one).
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(_ContextFilter())
    root.addHandler(handler)
    root.setLevel(lvl)

    # Quiet down chatty libs unless DEBUG explicitly asked.
    for noisy in ("uvicorn.access", "uvicorn.error"):
        logging.getLogger(noisy).setLevel("WARNING" if lvl != "DEBUG" else "DEBUG")


def init_sentry() -> bool:
    """Activate Sentry if SENTRY_DSN is set AND sentry-sdk is installed.
    Returns True if active. Missing SDK degrades to a warning — never crashes.
    """
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return False
    try:
        import sentry_sdk  # type: ignore
        from sentry_sdk.integrations.fastapi import FastApiIntegration  # type: ignore
    except ImportError:
        logging.getLogger(__name__).warning(
            "SENTRY_DSN set but sentry-sdk not installed — skipping Sentry init. "
            "pip install sentry-sdk"
        )
        return False
    sentry_sdk.init(
        dsn=dsn,
        integrations=[FastApiIntegration()],
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        environment=os.environ.get("SENTRY_ENVIRONMENT", "development"),
        release=os.environ.get("SENTRY_RELEASE"),
    )
    logging.getLogger(__name__).info(
        "Sentry initialised", extra={"env": os.environ.get("SENTRY_ENVIRONMENT")}
    )
    return True
