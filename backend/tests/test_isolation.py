"""
Cross-tenant isolation tests.

Two fresh users — Alice and Bob — are registered for each test class. Alice
seeds a client, proposal, invoice, and activity; Bob then tries every way to
read, modify, delete, or cross-reference them. Every attempt must fail (404
or empty list); Alice's data must remain intact after each.
"""
import os
import uuid
import pytest
import requests
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"


def _iso_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _iso_ahead(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _register(prefix: str) -> dict:
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(
        f"{API}/auth/register",
        json={"email": email, "password": "Pw1234!!XY", "name": prefix.title()},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="class")
def alice():
    data = _register("alice")
    s = _session(data["token"])
    # Seed one of each owned by Alice
    c = s.post(f"{API}/clients", json={
        "company_name": f"Alice_Co_{uuid.uuid4().hex[:6]}",
        "contact_name": "Alice Contact",
        "email": "alice_client@example.com",
        "phone": "+91 99000 00001",
    }, timeout=15).json()
    p = s.post(f"{API}/proposals", json={
        "client_id": c["id"], "title": "Alice secret proposal",
        "value_inr": 50000, "stage": "sent",
        "sent_date": _iso_ago(3), "last_contact_date": _iso_ago(3),
    }, timeout=15).json()
    inv = s.post(f"{API}/invoices", json={
        "client_id": c["id"], "invoice_no": f"ALICE-{uuid.uuid4().hex[:5]}",
        "amount_inr": 25000, "due_date": _iso_ahead(7),
    }, timeout=15).json()
    a = s.post(f"{API}/activities", json={
        "client_id": c["id"], "related_type": "proposal", "related_id": p["id"],
        "channel": "note", "direction": "internal", "summary": "Alice internal note",
    }, timeout=15).json()
    return {"user": data["user"], "token": data["token"], "session": s,
            "client": c, "proposal": p, "invoice": inv, "activity": a}


@pytest.fixture(scope="class")
def bob():
    data = _register("bob")
    return {"user": data["user"], "token": data["token"], "session": _session(data["token"])}


class TestReadIsolation:
    """Bob can't read any of Alice's records by direct ID."""

    def test_get_client_by_alice_id_404s(self, alice, bob):
        r = bob["session"].get(f"{API}/clients/{alice['client']['id']}", timeout=15)
        assert r.status_code == 404, r.text

    def test_get_proposal_by_alice_id_404s(self, alice, bob):
        r = bob["session"].get(f"{API}/proposals/{alice['proposal']['id']}", timeout=15)
        assert r.status_code == 404, r.text

    def test_get_invoice_by_alice_id_404s(self, alice, bob):
        r = bob["session"].get(f"{API}/invoices/{alice['invoice']['id']}", timeout=15)
        assert r.status_code == 404, r.text

    def test_list_clients_does_not_leak(self, alice, bob):
        ids = [c["id"] for c in bob["session"].get(f"{API}/clients", timeout=15).json()]
        assert alice["client"]["id"] not in ids

    def test_list_proposals_does_not_leak(self, alice, bob):
        ids = [p["id"] for p in bob["session"].get(f"{API}/proposals", timeout=15).json()]
        assert alice["proposal"]["id"] not in ids

    def test_list_invoices_does_not_leak(self, alice, bob):
        ids = [i["id"] for i in bob["session"].get(f"{API}/invoices", timeout=15).json()]
        assert alice["invoice"]["id"] not in ids

    def test_list_activities_does_not_leak(self, alice, bob):
        ids = [a["id"] for a in bob["session"].get(f"{API}/activities", timeout=15).json()]
        assert alice["activity"]["id"] not in ids

    def test_dashboard_summary_is_bob_only(self, alice, bob):
        d = bob["session"].get(f"{API}/dashboard/summary", timeout=15).json()
        # Bob has no clients/proposals/invoices of his own
        assert d["total_pipeline_inr"] == 0
        assert d["overdue_invoices_count"] == 0
        assert d["overdue_invoices_inr"] == 0


class TestUpdateIsolation:
    """Bob's PATCH attempts must 404 and leave Alice's data untouched."""

    def test_patch_alice_client(self, alice, bob):
        r = bob["session"].patch(
            f"{API}/clients/{alice['client']['id']}",
            json={"company_name": "Pwned by Bob"}, timeout=15,
        )
        assert r.status_code == 404, r.text
        fresh = alice["session"].get(f"{API}/clients/{alice['client']['id']}", timeout=15).json()
        assert fresh["client"]["company_name"] == alice["client"]["company_name"]

    def test_patch_alice_proposal(self, alice, bob):
        r = bob["session"].patch(
            f"{API}/proposals/{alice['proposal']['id']}",
            json={"value_inr": 1}, timeout=15,
        )
        assert r.status_code == 404, r.text
        fresh = alice["session"].get(f"{API}/proposals/{alice['proposal']['id']}", timeout=15).json()
        assert fresh["value_inr"] == alice["proposal"]["value_inr"]

    def test_patch_alice_invoice(self, alice, bob):
        r = bob["session"].patch(
            f"{API}/invoices/{alice['invoice']['id']}",
            json={"amount_inr": 1}, timeout=15,
        )
        assert r.status_code == 404, r.text
        fresh = alice["session"].get(f"{API}/invoices/{alice['invoice']['id']}", timeout=15).json()
        assert fresh["amount_inr"] == alice["invoice"]["amount_inr"]


class TestDeleteIsolation:
    """Bob's DELETE attempts must not remove Alice's data."""

    def test_delete_alice_client(self, alice, bob):
        bob["session"].delete(f"{API}/clients/{alice['client']['id']}", timeout=15)
        # Alice still sees her client
        r = alice["session"].get(f"{API}/clients/{alice['client']['id']}", timeout=15)
        assert r.status_code == 200, r.text

    def test_delete_alice_proposal(self, alice, bob):
        bob["session"].delete(f"{API}/proposals/{alice['proposal']['id']}", timeout=15)
        r = alice["session"].get(f"{API}/proposals/{alice['proposal']['id']}", timeout=15)
        assert r.status_code == 200, r.text

    def test_delete_alice_invoice(self, alice, bob):
        bob["session"].delete(f"{API}/invoices/{alice['invoice']['id']}", timeout=15)
        r = alice["session"].get(f"{API}/invoices/{alice['invoice']['id']}", timeout=15)
        assert r.status_code == 200, r.text


class TestCrossReferenceIsolation:
    """Bob can't create rows that point at Alice's UUIDs."""

    def test_create_proposal_with_alice_client_id(self, alice, bob):
        r = bob["session"].post(f"{API}/proposals", json={
            "client_id": alice["client"]["id"],
            "title": "Bob hijack attempt", "value_inr": 100, "stage": "sent",
        }, timeout=15)
        assert r.status_code == 404, r.text

    def test_create_invoice_with_alice_client_id(self, alice, bob):
        r = bob["session"].post(f"{API}/invoices", json={
            "client_id": alice["client"]["id"],
            "invoice_no": f"BOB-{uuid.uuid4().hex[:5]}",
            "amount_inr": 100, "due_date": _iso_ahead(7),
        }, timeout=15)
        assert r.status_code == 404, r.text

    def test_create_activity_with_alice_client_id(self, alice, bob):
        r = bob["session"].post(f"{API}/activities", json={
            "client_id": alice["client"]["id"],
            "channel": "note", "summary": "leak",
        }, timeout=15)
        assert r.status_code == 404, r.text

    def test_create_activity_with_alice_proposal_id(self, alice, bob):
        # Bob would need his own client first
        own_client = bob["session"].post(f"{API}/clients", json={
            "company_name": f"Bob_Co_{uuid.uuid4().hex[:6]}", "contact_name": "Bob Contact",
        }, timeout=15).json()
        r = bob["session"].post(f"{API}/activities", json={
            "client_id": own_client["id"],
            "related_type": "proposal", "related_id": alice["proposal"]["id"],
            "channel": "note", "summary": "leak",
        }, timeout=15)
        assert r.status_code == 404, r.text


class TestSessionIsolation:
    """Bob revoking his own session must not affect Alice."""

    def test_bob_logout_does_not_revoke_alice(self, alice, bob):
        # Bob logs out — token_version bumps for Bob only
        r = bob["session"].post(f"{API}/auth/logout", timeout=15)
        assert r.status_code == 204, r.text
        # Bob's old token is now invalid
        r = bob["session"].get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 401, r.text
        # Alice's token still works
        r = alice["session"].get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 200, r.text


class TestUnauthenticated:
    """No bearer → 401 on every protected endpoint."""

    def test_clients_requires_auth(self):
        assert requests.get(f"{API}/clients", timeout=15).status_code == 401

    def test_proposals_requires_auth(self):
        assert requests.get(f"{API}/proposals", timeout=15).status_code == 401

    def test_invoices_requires_auth(self):
        assert requests.get(f"{API}/invoices", timeout=15).status_code == 401

    def test_activities_requires_auth(self):
        assert requests.get(f"{API}/activities", timeout=15).status_code == 401

    def test_dashboard_requires_auth(self):
        assert requests.get(f"{API}/dashboard/summary", timeout=15).status_code == 401
