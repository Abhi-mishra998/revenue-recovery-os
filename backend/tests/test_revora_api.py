"""Revora — Revenue Recovery OS backend API tests."""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://revora-hub.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "founder@bytehubble.com"
ADMIN_PASSWORD = "ByteHubble@2025"


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def auth_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data and isinstance(data["token"], str) and len(data["token"]) > 10
    assert data["user"]["email"] == ADMIN_EMAIL
    return data["token"]


@pytest.fixture(scope="session")
def client(auth_token):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {auth_token}"})
    return s


# ---------- Auth ----------
class TestAuth:
    def test_login_invalid(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"}, timeout=15)
        assert r.status_code == 401

    def test_me(self, client):
        r = client.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL
        assert "password_hash" not in r.json()

    def test_me_unauth(self):
        r = requests.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 401


# ---------- Dashboard ----------
class TestDashboard:
    def test_summary(self, client):
        r = client.get(f"{API}/dashboard/summary", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for key in ["revenue_at_risk", "recoverable", "pipeline_value", "outstanding_invoices",
                    "collected", "proposal_buckets", "proposal_counts", "invoice_buckets", "invoice_counts"]:
            assert key in d
        assert isinstance(d["revenue_at_risk"], (int, float))
        # seed has cold/dead proposals so at_risk > 0
        assert d["revenue_at_risk"] >= 0
        assert d["outstanding_invoices"] >= 0

    def test_today_actions(self, client):
        r = client.get(f"{API}/dashboard/today", timeout=15)
        assert r.status_code == 200
        actions = r.json()
        assert isinstance(actions, list)
        # seed should produce cold/dead proposals + overdue invoices
        assert len(actions) > 0
        for a in actions:
            assert "kind" in a and a["kind"] in ("proposal", "invoice")
            assert "id" in a and "value" in a and "urgency" in a and "status" in a


# ---------- Clients ----------
class TestClients:
    def test_list(self, client):
        r = client.get(f"{API}/clients", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list) and len(rows) >= 6  # seed has 6

    def test_create_and_get(self, client):
        payload = {"name": f"TEST_Client_{uuid.uuid4().hex[:6]}", "company": "TEST Co",
                   "email": "test@example.com", "phone": "+91 99xxxxxx00"}
        r = client.post(f"{API}/clients", json=payload, timeout=15)
        assert r.status_code == 200
        c = r.json()
        assert c["name"] == payload["name"]
        cid = c["id"]
        r2 = client.get(f"{API}/clients/{cid}", timeout=15)
        assert r2.status_code == 200
        body = r2.json()
        assert body["client"]["id"] == cid
        assert "proposals" in body and "invoices" in body and "activities" in body


# ---------- Proposals ----------
class TestProposals:
    def test_list(self, client):
        r = client.get(f"{API}/proposals", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list) and len(rows) >= 6
        for p in rows:
            assert "status" in p and p["status"] in ("active", "cold", "dead", "won", "lost")
            assert "days_silent" in p and "client_name" in p

    def test_create_and_touch(self, client):
        clients_resp = client.get(f"{API}/clients", timeout=15).json()
        cid = clients_resp[0]["id"]
        payload = {"client_id": cid, "title": f"TEST_Proposal_{uuid.uuid4().hex[:6]}",
                   "value": 99000}
        r = client.post(f"{API}/proposals", json=payload, timeout=15)
        assert r.status_code == 200
        prop = r.json()
        pid = prop["id"]
        assert prop["title"] == payload["title"]
        assert prop["value"] == 99000

        # touch -> mark as just contacted; status should be active
        r2 = client.post(f"{API}/proposals/{pid}/touch", timeout=15)
        assert r2.status_code == 200

        # verify in list -> status active
        all_p = client.get(f"{API}/proposals", timeout=15).json()
        match = [p for p in all_p if p["id"] == pid]
        assert match
        assert match[0]["status"] == "active"

        # cleanup
        rd = client.delete(f"{API}/proposals/{pid}", timeout=15)
        assert rd.status_code == 200


# ---------- Invoices ----------
class TestInvoices:
    def test_list(self, client):
        r = client.get(f"{API}/invoices", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list) and len(rows) >= 5
        for inv in rows:
            assert inv["status"] in ("paid", "due", "overdue", "critical")

    def test_create_and_mark_paid(self, client):
        clients_resp = client.get(f"{API}/clients", timeout=15).json()
        cid = clients_resp[0]["id"]
        # past-due so it shows in overdue bucket
        from datetime import datetime, timedelta, timezone
        due = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        payload = {"client_id": cid, "invoice_number": f"TEST-{uuid.uuid4().hex[:5]}",
                   "amount": 50000, "due_date": due}
        r = client.post(f"{API}/invoices", json=payload, timeout=15)
        assert r.status_code == 200
        inv = r.json()
        iid = inv["id"]

        # verify in list status overdue
        all_i = client.get(f"{API}/invoices", timeout=15).json()
        match = [i for i in all_i if i["id"] == iid]
        assert match and match[0]["status"] in ("overdue", "critical")

        # mark paid
        r2 = client.post(f"{API}/invoices/{iid}/mark-paid", timeout=15)
        assert r2.status_code == 200

        all_i2 = client.get(f"{API}/invoices", timeout=15).json()
        match2 = [i for i in all_i2 if i["id"] == iid]
        assert match2 and match2[0]["status"] == "paid"

        # cleanup
        rd = client.delete(f"{API}/invoices/{iid}", timeout=15)
        assert rd.status_code == 200


# ---------- AI Draft ----------
class TestAIDraft:
    def test_draft_whatsapp(self, client):
        proposals = client.get(f"{API}/proposals", timeout=15).json()
        # pick a cold/dead proposal so reference is meaningful
        target = next((p for p in proposals if p["status"] in ("cold", "dead")), proposals[0])
        payload = {"kind": "whatsapp", "tone": "gentle", "proposal_id": target["id"]}
        r = client.post(f"{API}/ai/draft", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["kind"] == "whatsapp"
        assert isinstance(d["text"], str) and len(d["text"]) > 20

    def test_draft_email(self, client):
        proposals = client.get(f"{API}/proposals", timeout=15).json()
        target = next((p for p in proposals if p["status"] in ("cold", "dead")), proposals[0])
        payload = {"kind": "email", "tone": "firm", "proposal_id": target["id"]}
        r = client.post(f"{API}/ai/draft", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "Subject:" in d["text"] or "subject:" in d["text"].lower()

    def test_invoice_reminder(self, client):
        invoices = client.get(f"{API}/invoices", timeout=15).json()
        target = next((i for i in invoices if i["status"] in ("overdue", "critical")), invoices[0])
        payload = {"kind": "invoice_reminder", "tone": "gentle", "invoice_id": target["id"]}
        r = client.post(f"{API}/ai/draft", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["text"]) > 30
