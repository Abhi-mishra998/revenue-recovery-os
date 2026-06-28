"""
Audit log + kill-switch tests.

Tamper tests reach into the audit_log storage directly to mutate a record,
then expect the chain-verify endpoint to detect the tampering. Engine-aware
storage helper handles both Mongo and Postgres so this works on either
DB_ENGINE.
"""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "founder@bytehubble.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ByteHubble@2025")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "revora_test")
POSTGRES_URL = os.environ.get("POSTGRES_URL")
DB_ENGINE = (os.environ.get("DB_ENGINE") or "mongo").lower()


def _login(email: str, password: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _register(prefix: str) -> tuple[str, dict]:
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "password": "Pw1234!!XY", "name": prefix.title()},
                      timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]


def _session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _session(_login(ADMIN_EMAIL, ADMIN_PASSWORD))


class _AuditStorage:
    """Engine-aware test helper for poking audit_log records directly.
    On Mongo, wraps the audit_log collection (so existing tests keep working).
    On Postgres, wraps a synchronous psycopg-free helper that uses asyncpg
    inside asyncio.run."""

    def __init__(self):
        self._mongo_client = None
        if DB_ENGINE == "mongo":
            self._mongo_client = MongoClient(MONGO_URL)
            self.audit_log = self._mongo_client[DB_NAME].audit_log
        else:
            import asyncio
            import asyncpg

            class _PgAudit:
                """Subset of the motor Collection API we use in tests."""
                def find_one(_self, filt=None, sort=None):  # noqa: N805
                    filt = filt or {}
                    async def _run():
                        conn = await asyncpg.connect(POSTGRES_URL, timeout=5)
                        try:
                            params, where = [], []
                            for k, v in filt.items():
                                params.append(v)
                                col = "resource_id" if k == "resource_id" else k
                                where.append(f"{col} = ${len(params)}")
                            sql = "SELECT * FROM audit_log"
                            if where:
                                sql += " WHERE " + " AND ".join(where)
                            order = "seq DESC" if sort and sort[0][0] == "seq" and sort[0][1] == -1 else "seq ASC"
                            sql += f" ORDER BY {order} LIMIT 1"
                            row = await conn.fetchrow(sql, *params)
                            if not row:
                                return None
                            d = dict(row)
                            d["_id"] = str(d["id"])  # mongo-style key for compatibility
                            return d
                        finally:
                            await conn.close()
                    return asyncio.run(_run())

                def update_one(_self, filt, update):
                    set_clause = update.get("$set") or {}
                    async def _run():
                        conn = await asyncpg.connect(POSTGRES_URL, timeout=5)
                        try:
                            params, sets, where = [], [], []
                            for k, v in set_clause.items():
                                params.append(v); sets.append(f"{k} = ${len(params)}")
                            for k, v in filt.items():
                                col = "id::uuid" if k == "_id" else k
                                params.append(str(v) if k == "_id" else v)
                                where.append(f"id = ${len(params)}::uuid" if k == "_id" else f"{col} = ${len(params)}")
                            sql = f"UPDATE audit_log SET {', '.join(sets)} WHERE {' AND '.join(where)}"
                            await conn.execute(sql, *params)
                        finally:
                            await conn.close()
                    asyncio.run(_run())
            self.audit_log = _PgAudit()

    def close(self):
        if self._mongo_client:
            self._mongo_client.close()


@pytest.fixture(scope="module")
def mongo_db():
    s = _AuditStorage()
    try:
        yield s
    finally:
        s.close()


class TestChainHappyPath:
    def test_verify_returns_ok_on_a_clean_chain(self, admin_session):
        r = admin_session.get(f"{API}/admin/audit-log/verify", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True, d
        assert d["records_checked"] >= 1
        assert d["public_key_fp"]
        assert d["issues"] == []

    def test_state_change_appends_a_record(self, admin_session, mongo_db):
        before = admin_session.get(f"{API}/admin/audit-log?page=1&page_size=1", timeout=15).json()["total"]
        c = admin_session.post(f"{API}/clients", json={
            "company_name": f"AUDIT_{uuid.uuid4().hex[:6]}", "contact_name": "Audit Test",
        }, timeout=15).json()
        after_total = admin_session.get(f"{API}/admin/audit-log?page=1&page_size=1", timeout=15).json()["total"]
        assert after_total >= before + 1
        # Find the specific record by resource_id (parallel tests may interleave).
        rec = mongo_db.audit_log.find_one({"resource_id": c["id"], "action": "client.create"})
        assert rec is not None
        assert rec["resource_type"] == "client"
        admin_session.delete(f"{API}/clients/{c['id']}", timeout=15)


class TestTamperDetection:
    """Modify a record in Mongo, ensure verify catches it, then restore."""

    def _create_then_locate_audit(self, admin_session, mongo_db) -> dict:
        # Create a known record we can find by resource_id
        c = admin_session.post(f"{API}/clients", json={
            "company_name": f"TAMPER_{uuid.uuid4().hex[:6]}", "contact_name": "Tamper Test",
        }, timeout=15).json()
        rec = mongo_db.audit_log.find_one({"resource_id": c["id"], "action": "client.create"})
        assert rec is not None
        return rec

    def _verify(self, admin_session) -> dict:
        return admin_session.get(f"{API}/admin/audit-log/verify", timeout=30).json()

    def test_modified_payload_hash_is_detected(self, admin_session, mongo_db):
        rec = self._create_then_locate_audit(admin_session, mongo_db)
        original = rec["payload_hash"]
        mongo_db.audit_log.update_one({"_id": rec["_id"]}, {"$set": {"payload_hash": "deadbeef" * 8}})
        try:
            d = self._verify(admin_session)
            assert d["ok"] is False
            # The tampered seq should appear in issues — both record_hash and signature checks fail
            issues_text = " | ".join(d["issues"])
            assert f"seq {rec['seq']}" in issues_text, d
            assert "record_hash mismatch" in issues_text
        finally:
            mongo_db.audit_log.update_one({"_id": rec["_id"]}, {"$set": {"payload_hash": original}})

    def test_modified_signature_is_detected(self, admin_session, mongo_db):
        rec = self._create_then_locate_audit(admin_session, mongo_db)
        original = rec["signature"]
        # Flip the first 4 chars of the signature — still valid base64, but wrong bytes
        bad = ("A" * 4) + original[4:]
        mongo_db.audit_log.update_one({"_id": rec["_id"]}, {"$set": {"signature": bad}})
        try:
            d = self._verify(admin_session)
            assert d["ok"] is False
            issues_text = " | ".join(d["issues"])
            assert "bad signature" in issues_text or "signature error" in issues_text, d
        finally:
            mongo_db.audit_log.update_one({"_id": rec["_id"]}, {"$set": {"signature": original}})

    def test_modified_prev_hash_breaks_chain_link(self, admin_session, mongo_db):
        rec = self._create_then_locate_audit(admin_session, mongo_db)
        original = rec["prev_hash"]
        mongo_db.audit_log.update_one({"_id": rec["_id"]}, {"$set": {"prev_hash": "0" * 64}})
        try:
            d = self._verify(admin_session)
            assert d["ok"] is False
            issues_text = " | ".join(d["issues"])
            assert "prev_hash mismatch" in issues_text, d
        finally:
            mongo_db.audit_log.update_one({"_id": rec["_id"]}, {"$set": {"prev_hash": original}})

    def test_chain_recovers_after_restore(self, admin_session):
        """Sanity: once tampering is reverted, verify is green again."""
        d = admin_session.get(f"{API}/admin/audit-log/verify", timeout=30).json()
        assert d["ok"] is True, d


class TestAdminAuthorization:
    def test_non_admin_cannot_verify(self):
        token, _ = _register("nonadm_verify")
        s = _session(token)
        r = s.get(f"{API}/admin/audit-log/verify", timeout=15)
        assert r.status_code == 403, r.text

    def test_non_admin_cannot_list(self):
        token, _ = _register("nonadm_list")
        s = _session(token)
        r = s.get(f"{API}/admin/audit-log", timeout=15)
        assert r.status_code == 403, r.text

    def test_non_admin_cannot_toggle_killswitch(self):
        token, _ = _register("nonadm_ks")
        s = _session(token)
        r = s.post(f"{API}/admin/killswitch", json={"enabled": True}, timeout=15)
        assert r.status_code == 403, r.text

    def test_unauthenticated_denied(self):
        for path in ("/admin/audit-log", "/admin/audit-log/verify", "/admin/killswitch"):
            r = requests.get(f"{API}{path}", timeout=15)
            assert r.status_code == 401, f"{path} -> {r.status_code}"


class TestKillSwitch:
    def test_default_off(self, admin_session):
        # Make sure it's off before the test (and at the end too — finally below)
        admin_session.post(f"{API}/admin/killswitch", json={"enabled": False}, timeout=15)
        r = admin_session.get(f"{API}/admin/killswitch", timeout=15)
        assert r.status_code == 200
        assert r.json() == {"ai_killswitch": False}

    def test_toggle_on_then_off_is_audited(self, admin_session, mongo_db):
        try:
            r = admin_session.post(f"{API}/admin/killswitch", json={"enabled": True}, timeout=15)
            assert r.status_code == 200 and r.json() == {"ai_killswitch": True}
            assert admin_session.get(f"{API}/admin/killswitch", timeout=15).json() == {"ai_killswitch": True}

            # Audit chain has admin.killswitch.set
            latest = mongo_db.audit_log.find_one({"action": "admin.killswitch.set"}, sort=[("seq", -1)])
            assert latest is not None
            assert latest["actor_email"].lower() == ADMIN_EMAIL.lower()
        finally:
            admin_session.post(f"{API}/admin/killswitch", json={"enabled": False}, timeout=15)

    def test_killswitch_blocks_generate_followup(self, admin_session):
        # Need a proposal owned by admin to attempt the call. Use an existing seed proposal.
        proposals = admin_session.get(f"{API}/proposals", timeout=15).json()
        assert proposals, "expected admin to have at least one seeded proposal"
        pid = proposals[0]["id"]
        try:
            admin_session.post(f"{API}/admin/killswitch", json={"enabled": True}, timeout=15)
            r = admin_session.post(f"{API}/proposals/{pid}/generate-followup", timeout=15)
            assert r.status_code == 503, r.text
            assert "disabled" in r.json()["detail"].lower()
        finally:
            admin_session.post(f"{API}/admin/killswitch", json={"enabled": False}, timeout=15)
