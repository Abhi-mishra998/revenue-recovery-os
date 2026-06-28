"""
Tamper-evident append-only audit log.

Each record:
  seq           monotonic int (1, 2, 3 ...)
  actor_id      user id who triggered the action (or "system")
  actor_email   their email at the time
  action        identifier ("client.create", "ai.followup.generate", ...)
  resource_type "client" | "proposal" | "invoice" | "activity" | None
  resource_id   uuid string or None
  payload_hash  sha256 of canonical-JSON payload
  prev_hash     record_hash of seq-1 (64 zeros for seq=1)
  timestamp     ISO-8601 UTC
  record_hash   sha256 of canonical-JSON of the above 9 fields
  signature     base64 ed25519 sig of record_hash bytes
  public_key_fp first 16 hex chars of sha256(public key bytes) — diagnostic

Signing key resolution order:
  1. AUDIT_SIGNING_KEY env (base64, 32 bytes) — preferred for prod.
  2. settings.audit_signing_key in Mongo — auto-generated on first start,
     with a loud WARNING. Convenient for dev, not for prod.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .db.repos import audit_log as audit_log_repo
from .db.repos import settings as settings_repo

logger = logging.getLogger(__name__)

ZERO_HASH = "0" * 64
SETTINGS_DOC_ID = "global"

# ponytail: process-level lock — multi-process deploy needs a distributed lock
# (Mongo findAndModify on a sequence doc with retry, or Redis SETNX).
_append_lock = asyncio.Lock()
_signing_key: Optional[Ed25519PrivateKey] = None
_public_key_fp: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _payload_hash(payload: Any) -> str:
    if payload is None:
        return _sha256_hex(b"")
    return _sha256_hex(_canonical_json(payload))


def _record_blob(rec: dict) -> dict:
    return {k: rec[k] for k in (
        "seq", "actor_id", "actor_email", "action",
        "resource_type", "resource_id", "payload_hash",
        "prev_hash", "timestamp",
    )}


def _key_fingerprint(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return _sha256_hex(raw)[:16]


async def load_signing_key(db=None) -> None:
    """Load ed25519 key from env, else from settings doc, else generate+persist.
    The `db` arg is kept for backward compat; the settings repo dispatches on
    DB_ENGINE itself."""
    global _signing_key, _public_key_fp
    env_key = os.environ.get("AUDIT_SIGNING_KEY")
    if env_key:
        raw = base64.b64decode(env_key)
        _signing_key = Ed25519PrivateKey.from_private_bytes(raw)
        _public_key_fp = _key_fingerprint(_signing_key.public_key())
        logger.info("Audit key loaded from AUDIT_SIGNING_KEY env (fp=%s)", _public_key_fp)
        return

    doc = await settings_repo.get_global()
    if doc and doc.get("audit_signing_key"):
        raw = base64.b64decode(doc["audit_signing_key"])
        _signing_key = Ed25519PrivateKey.from_private_bytes(raw)
        _public_key_fp = _key_fingerprint(_signing_key.public_key())
        logger.info("Audit key loaded from settings doc (fp=%s)", _public_key_fp)
        return

    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    await settings_repo.set_audit_signing_key(base64.b64encode(raw).decode("ascii"))
    _signing_key = key
    _public_key_fp = _key_fingerprint(key.public_key())
    logger.warning(
        "AUDIT_SIGNING_KEY not set — generated and persisted to db.settings. "
        "For production, set AUDIT_SIGNING_KEY env to a base64-encoded "
        "32-byte ed25519 secret. fp=%s",
        _public_key_fp,
    )


def get_public_key_fp() -> str:
    return _public_key_fp or ""


async def append_audit(
    db=None,
    *,
    action: str,
    actor_id: str,
    actor_email: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    payload: Any = None,
) -> dict:
    """Append a record. Raises on signing/insert failure — caller must let it
    bubble so a missing audit row never silently masks an action.
    The `db` arg is kept for back-compat; the repo dispatches on DB_ENGINE."""
    if _signing_key is None:
        raise RuntimeError("audit signing key not loaded — call load_signing_key first")
    async with _append_lock:
        last = await audit_log_repo.latest_seq_and_hash()
        seq = (last["seq"] + 1) if last else 1
        prev_hash = last["record_hash"] if last else ZERO_HASH
        rec = {
            "id": str(uuid.uuid4()),
            "seq": seq,
            "actor_id": actor_id,
            "actor_email": actor_email,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "payload_hash": _payload_hash(payload),
            "prev_hash": prev_hash,
            "timestamp": _now_iso(),
        }
        rec["record_hash"] = _sha256_hex(_canonical_json(_record_blob(rec)))
        rec["signature"] = base64.b64encode(
            _signing_key.sign(rec["record_hash"].encode("utf-8"))
        ).decode("ascii")
        rec["public_key_fp"] = _public_key_fp
        await audit_log_repo.insert(rec)
        return rec


async def verify_chain(db=None, limit: Optional[int] = None) -> dict:
    """Walk the chain start to end. Returns ok/issues/records_checked.
    `db` arg kept for back-compat."""
    if _signing_key is None:
        raise RuntimeError("audit signing key not loaded")
    public_key = _signing_key.public_key()
    prev_hash = ZERO_HASH
    seq_expected = 1
    issues: list[str] = []
    count = 0
    async for r in audit_log_repo.iter_in_order():
        if limit is not None and count >= limit:
            break
        if r["seq"] != seq_expected:
            issues.append(f"seq gap: expected {seq_expected}, got {r['seq']}")
        if r["prev_hash"] != prev_hash:
            issues.append(f"prev_hash mismatch at seq {r['seq']}")
        recomputed = _sha256_hex(_canonical_json(_record_blob(r)))
        if recomputed != r["record_hash"]:
            issues.append(f"record_hash mismatch at seq {r['seq']}")
        try:
            public_key.verify(
                base64.b64decode(r["signature"]),
                recomputed.encode("utf-8"),
            )
        except InvalidSignature:
            issues.append(f"bad signature at seq {r['seq']}")
        except Exception as e:
            issues.append(f"signature error at seq {r['seq']}: {e}")
        prev_hash = r["record_hash"]
        seq_expected = r["seq"] + 1
        count += 1
    return {
        "ok": not issues,
        "records_checked": count,
        "issues": issues,
        "public_key_fp": _public_key_fp,
    }
