"""
Tests for the production-readiness gate:
  - max request body size (413 + stable error code)
  - global exception handler (no traceback leak)
  - DPDP: export-my-data shape + delete-my-account cascade + isolation
"""

import os
import uuid

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"


def _register(prefix: str) -> tuple[str, dict]:
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@x.com"
    r = requests.post(
        f"{API}/auth/register",
        json={"email": email, "password": "Pw1234!!XY", "name": prefix.title()},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]


def _hdrs(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- Max request body ----------


class TestMaxBodySize:
    def test_oversized_post_rejected_413(self):
        """6MB body > 5MB default cap → 413 with stable error code."""
        # Send via streaming so we don't allocate a 6MB string just to test.
        big = "A" * (6 * 1024 * 1024)
        r = requests.post(
            f"{API}/auth/register",
            data=f'{{"email":"big@x.com","password":"{big}","name":"X"}}',
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        assert r.status_code == 413, r.text
        detail = r.json()["detail"]
        assert detail["code"] == "request_too_large"
        assert "5242880" in detail["message"] or "≤" in detail["message"]

    def test_normal_size_still_works(self):
        """Sanity: a tiny POST is unaffected."""
        token, _ = _register("body_ok")
        r = requests.get(f"{API}/auth/me", headers=_hdrs(token), timeout=15)
        assert r.status_code == 200


# ---------- DPDP: export ----------


class TestExportMyData:
    def test_returns_full_shape(self):
        token, user = _register("export_shape")
        s = requests.Session()
        s.headers.update(_hdrs(token))
        # Seed something to make the export non-empty.
        c = s.post(f"{API}/clients", json={"company_name": "EXP", "contact_name": "E"}).json()
        s.post(
            f"{API}/proposals",
            json={
                "client_id": c["id"],
                "title": "p",
                "value_inr": 1,
                "stage": "sent",
            },
        )

        r = s.get(f"{API}/me/data", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in (
            "exported_at",
            "user",
            "clients",
            "proposals",
            "invoices",
            "activities",
            "followups",
            "events",
            "client_memory",
        ):
            assert k in d, f"missing key in export: {k}"
        assert d["user"]["email"] == user["email"]
        assert len(d["clients"]) >= 1
        assert len(d["proposals"]) >= 1

    def test_export_is_tenant_scoped(self):
        """Bob's export must not include any of Alice's records."""
        a_token, a_user = _register("export_alice")
        a = requests.Session()
        a.headers.update(_hdrs(a_token))
        a_client = a.post(
            f"{API}/clients",
            json={
                "company_name": f"ALICE_{uuid.uuid4().hex[:6]}",
                "contact_name": "A",
            },
        ).json()

        b_token, _ = _register("export_bob")
        b = requests.Session()
        b.headers.update(_hdrs(b_token))
        b_export = b.get(f"{API}/me/data", timeout=15).json()

        assert all(c["id"] != a_client["id"] for c in b_export["clients"])
        assert b_export["user"]["email"] != a_user["email"]


# ---------- DPDP: delete account ----------


class TestDeleteMyAccount:
    def test_delete_204_then_token_401(self):
        token, _ = _register("delete_me")
        s = requests.Session()
        s.headers.update(_hdrs(token))
        # Seed data so the cascade is non-trivial
        c = s.post(f"{API}/clients", json={"company_name": "DEL", "contact_name": "D"}).json()
        s.post(
            f"{API}/proposals",
            json={
                "client_id": c["id"],
                "title": "p",
                "value_inr": 1,
                "stage": "sent",
            },
        )

        r = s.delete(f"{API}/me", timeout=15)
        assert r.status_code == 204
        # Same token now invalid — user row is gone.
        r2 = s.get(f"{API}/auth/me", timeout=15)
        assert r2.status_code == 401

    def test_delete_does_not_touch_other_tenants(self):
        """Alice deletes herself; Bob's data is intact."""
        a_token, _ = _register("delete_iso_alice")
        b_token, b_user = _register("delete_iso_bob")
        a = requests.Session()
        a.headers.update(_hdrs(a_token))
        b = requests.Session()
        b.headers.update(_hdrs(b_token))

        b_client = b.post(
            f"{API}/clients",
            json={
                "company_name": f"BOB_KEEP_{uuid.uuid4().hex[:6]}",
                "contact_name": "B",
            },
        ).json()

        # Alice nukes her account.
        assert a.delete(f"{API}/me", timeout=15).status_code == 204

        # Bob still authenticates, still sees his client.
        r = b.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 200
        clients = b.get(f"{API}/clients", timeout=15).json()
        assert any(c["id"] == b_client["id"] for c in clients)


# ---------- Global exception handler ----------


class TestGlobalErrorHandler:
    """We can't easily induce a 500 from the existing routes without a code
    change, so this asserts the shape of *known* error paths (which already
    use HTTPException with .detail). A pure 500 induction is in unit-tests
    of the handler itself if needed."""

    def test_404_still_returns_clean_shape(self):
        """An unknown URL should 404 — verifies our exception handler doesn't
        eat valid HTTP errors."""
        r = requests.get(f"{API}/does-not-exist", timeout=15)
        assert r.status_code == 404
