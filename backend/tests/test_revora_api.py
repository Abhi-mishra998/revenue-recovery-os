"""Revora — Revenue Recovery OS backend API tests (schema v2)."""
import os
import uuid
import pytest
import requests
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "founder@bytehubble.com"
ADMIN_PASSWORD = "ByteHubble@2025"


def _iso_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _iso_ahead(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def auth_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    assert isinstance(data["token"], str) and len(data["token"]) > 10
    assert data["user"]["email"] == ADMIN_EMAIL
    assert data["user"]["auth_provider"] == "email"
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
        body = r.json()
        assert body["email"] == ADMIN_EMAIL
        assert "password_hash" not in body
        assert body["auth_provider"] == "email"

    def test_me_unauth(self):
        r = requests.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 401

    def test_register_then_login(self):
        email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Pw1234!!", "name": "TestUser"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["user"]["auth_provider"] == "email"
        # Duplicate
        r2 = requests.post(f"{API}/auth/register", json={"email": email, "password": "Pw1234!!", "name": "X"}, timeout=15)
        assert r2.status_code == 400
        # Login back
        r3 = requests.post(f"{API}/auth/login", json={"email": email, "password": "Pw1234!!"}, timeout=15)
        assert r3.status_code == 200

    def test_google_session_bad(self):
        r = requests.post(f"{API}/auth/google/session", json={"session_id": f"bogus-{uuid.uuid4().hex}"}, timeout=20)
        assert r.status_code in (401, 502), f"expected 401/502, got {r.status_code}: {r.text}"


# ---------- Data isolation ----------
class TestAuthorization:
    def test_other_user_sees_empty(self):
        email = f"iso_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Pw1234!!", "name": "IsoUser"}, timeout=15)
        token = r.json()["token"]
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {token}"})
        assert s.get(f"{API}/clients", timeout=15).json() == []
        assert s.get(f"{API}/proposals", timeout=15).json() == []
        assert s.get(f"{API}/invoices", timeout=15).json() == []


# ---------- Dashboard ----------
class TestDashboard:
    def test_summary_shape_and_values(self, client):
        r = client.get(f"{API}/dashboard/summary", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ["total_pipeline_inr", "cold_proposals_count", "overdue_invoices_count",
                  "overdue_invoices_inr", "revenue_at_risk_inr", "by_status", "by_stage"]:
            assert k in d
        # Expected from seed (11 proposals in sent/negotiating: 3 active + 6 cold + 2 dead)
        assert d["total_pipeline_inr"] == 3775000
        assert d["cold_proposals_count"] == 6
        assert d["overdue_invoices_count"] == 6
        assert d["overdue_invoices_inr"] == 1157500
        assert d["revenue_at_risk_inr"] == 2715000


# ---------- Clients ----------
class TestClients:
    def test_list_has_seed(self, client):
        rows = client.get(f"{API}/clients", timeout=15).json()
        assert len(rows) >= 12
        for k in ("company_name", "contact_name", "language", "id"):
            assert k in rows[0]

    def test_crud_client(self, client):
        payload = {
            "company_name": f"TEST_Co_{uuid.uuid4().hex[:6]}",
            "contact_name": "TEST_Person",
            "email": "test_client@example.com",
            "phone": "+91 99000 00000",
            "whatsapp": "+91 99000 00000",
            "industry": "Testing",
            "notes": "ephemeral"
        }
        r = client.post(f"{API}/clients", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        c = r.json()
        assert c["company_name"] == payload["company_name"]
        assert c["language"] == "English"
        cid = c["id"]
        g = client.get(f"{API}/clients/{cid}", timeout=15).json()
        assert g["client"]["id"] == cid
        assert "proposals" in g and "invoices" in g
        u = client.patch(f"{API}/clients/{cid}", json={"industry": "Updated"}, timeout=15)
        assert u.json()["industry"] == "Updated"
        client.delete(f"{API}/clients/{cid}", timeout=15)
        assert client.get(f"{API}/clients/{cid}", timeout=15).status_code == 404


# ---------- Proposals ----------
class TestProposals:
    def test_list_seed_14(self, client):
        rows = client.get(f"{API}/proposals", timeout=15).json()
        assert len(rows) >= 14
        p = rows[0]
        for k in ("value_inr", "stage", "status", "days_silent", "title", "client_id", "client_company_name"):
            assert k in p

    def test_status_compute(self, client):
        cid = client.get(f"{API}/clients", timeout=15).json()[0]["id"]
        cases = [(3, "active"), (14, "cold"), (30, "dead")]
        for days, expected in cases:
            r = client.post(f"{API}/proposals", json={
                "client_id": cid,
                "title": f"TEST_Prop_{expected}_{uuid.uuid4().hex[:5]}",
                "value_inr": 50000,
                "sent_date": _iso_ago(days),
                "last_contact_date": _iso_ago(days),
                "stage": "sent",
            }, timeout=15)
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["status"] == expected, f"days={days} expected={expected} got={d['status']}"
            client.delete(f"{API}/proposals/{d['id']}", timeout=15)

    def test_update_persistence(self, client):
        cid = client.get(f"{API}/clients", timeout=15).json()[0]["id"]
        r = client.post(f"{API}/proposals", json={
            "client_id": cid, "title": f"TEST_{uuid.uuid4().hex[:5]}",
            "value_inr": 111, "stage": "sent"
        }, timeout=15)
        pid = r.json()["id"]
        u = client.patch(f"{API}/proposals/{pid}", json={"stage": "negotiating", "value_inr": 222}, timeout=15)
        assert u.json()["stage"] == "negotiating" and u.json()["value_inr"] == 222
        g = client.get(f"{API}/proposals/{pid}", timeout=15).json()
        assert g["stage"] == "negotiating" and g["value_inr"] == 222
        client.delete(f"{API}/proposals/{pid}", timeout=15)


# ---------- Invoices ----------
class TestInvoices:
    def test_list_seed_10(self, client):
        rows = client.get(f"{API}/invoices", timeout=15).json()
        assert len(rows) >= 10
        inv = rows[0]
        for k in ("invoice_no", "amount_inr", "due_date", "status", "days_overdue", "client_company_name"):
            assert k in inv
        assert inv["status"] in ("paid", "unpaid", "overdue")

    def test_overdue_and_mark_paid(self, client):
        cid = client.get(f"{API}/clients", timeout=15).json()[0]["id"]
        r = client.post(f"{API}/invoices", json={
            "client_id": cid,
            "invoice_no": f"TEST-{uuid.uuid4().hex[:5]}",
            "amount_inr": 50000,
            "due_date": _iso_ago(10),
        }, timeout=15)
        inv = r.json()
        assert inv["status"] == "overdue"
        assert inv["days_overdue"] == 10
        u = client.patch(f"{API}/invoices/{inv['id']}", json={"paid_date": _iso_ago(1)}, timeout=15)
        assert u.json()["status"] == "paid"
        assert u.json()["days_overdue"] == 0
        client.delete(f"{API}/invoices/{inv['id']}", timeout=15)

    def test_unpaid_future(self, client):
        cid = client.get(f"{API}/clients", timeout=15).json()[0]["id"]
        r = client.post(f"{API}/invoices", json={
            "client_id": cid,
            "invoice_no": f"TEST-{uuid.uuid4().hex[:5]}",
            "amount_inr": 10000,
            "due_date": _iso_ahead(5),
        }, timeout=15)
        inv = r.json()
        assert inv["status"] == "unpaid"
        assert inv["days_overdue"] == 0
        client.delete(f"{API}/invoices/{inv['id']}", timeout=15)
