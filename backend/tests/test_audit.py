"""
Audit log + kill-switch tests.

Requires MONGO_URL and DB_NAME in env so the tamper tests can poke records
directly. Admin email = ADMIN_EMAIL (defaults to founder@bytehubble.com).
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


@pytest.fixture(scope="module")
def mongo_db():
    c = MongoClient(MONGO_URL)
    try:
        yield c[DB_NAME]
    finally:
        c.close()


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
