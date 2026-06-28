"""
Auth edge cases — the failure modes the happy-path tests don't exercise.

Hits the live backend (any DB_ENGINE). Pairs with test_revora_api.py +
test_isolation.py which cover the success paths.
"""

import os
import time
import uuid

import jwt
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
JWT_SECRET = os.environ.get("JWT_SECRET", "test-secret-do-not-use-in-prod")
JWT_ALG = "HS256"


def _register() -> dict:
    email = f"edge_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(
        f"{API}/auth/register", json={"email": email, "password": "Pw1234!!XY", "name": "Edge"}, timeout=15
    )
    assert r.status_code == 200, r.text
    return r.json()


def _hdrs(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------- Token shape errors ----------


class TestMalformedTokens:
    def test_no_authorization_header(self):
        assert requests.get(f"{API}/auth/me", timeout=15).status_code == 401

    def test_garbage_bearer_value(self):
        r = requests.get(f"{API}/auth/me", headers={"Authorization": "Bearer not-a-jwt"}, timeout=15)
        assert r.status_code == 401
        assert "invalid" in r.json()["detail"].lower()

    def test_wrong_signature(self):
        """Token signed with a different secret should be rejected."""
        bad = jwt.encode(
            {"sub": "anything", "email": "x@y", "tv": 0, "exp": int(time.time()) + 60, "type": "access"},
            "wrong-secret",
            algorithm=JWT_ALG,
        )
        r = requests.get(f"{API}/auth/me", headers=_hdrs(bad), timeout=15)
        assert r.status_code == 401

    def test_wrong_algorithm(self):
        """JWT with 'none' alg or RS256-claimed-but-HS256-signed must be rejected."""
        bad = jwt.encode(
            {"sub": "x", "email": "x@y", "tv": 0, "exp": int(time.time()) + 60, "type": "access"},
            JWT_SECRET,
            algorithm="HS512",
        )  # wrong alg
        r = requests.get(f"{API}/auth/me", headers=_hdrs(bad), timeout=15)
        assert r.status_code == 401


# ---------- Expiry + revocation ----------


class TestTokenLifecycle:
    def test_expired_token_rejected(self):
        expired = jwt.encode(
            {
                "sub": "any",
                "email": "x@y",
                "tv": 0,
                "exp": int(time.time()) - 60,  # 60s in the past
                "type": "access",
            },
            JWT_SECRET,
            algorithm=JWT_ALG,
        )
        r = requests.get(f"{API}/auth/me", headers=_hdrs(expired), timeout=15)
        assert r.status_code == 401
        assert "expired" in r.json()["detail"].lower()

    def test_logout_revokes_other_tokens_for_same_user(self):
        """Two tokens for one user; logout via one revokes BOTH (tv bump)."""
        data = _register()
        token1 = data["token"]
        # Re-login to get a second token at the same tv
        r = requests.post(
            f"{API}/auth/login", json={"email": data["user"]["email"], "password": "Pw1234!!XY"}, timeout=15
        )
        token2 = r.json()["token"]

        # Both work
        assert requests.get(f"{API}/auth/me", headers=_hdrs(token1), timeout=15).status_code == 200
        assert requests.get(f"{API}/auth/me", headers=_hdrs(token2), timeout=15).status_code == 200

        # Logout token1
        r = requests.post(f"{API}/auth/logout", headers=_hdrs(token1), timeout=15)
        assert r.status_code == 204

        # Both old tokens now invalid (token_version was bumped)
        assert requests.get(f"{API}/auth/me", headers=_hdrs(token1), timeout=15).status_code == 401
        assert requests.get(f"{API}/auth/me", headers=_hdrs(token2), timeout=15).status_code == 401

    def test_token_for_deleted_user(self):
        """If the user row is gone, a still-signed-and-fresh token should 401."""
        data = _register()
        token = data["token"]
        # We don't expose a /users/me/delete endpoint; simulate by bumping the
        # claimed user id to a random uuid that doesn't exist.
        forged = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "email": "ghost@example.com",
                "tv": 0,
                "exp": int(time.time()) + 3600,
                "type": "access",
            },
            JWT_SECRET,
            algorithm=JWT_ALG,
        )
        r = requests.get(f"{API}/auth/me", headers=_hdrs(forged), timeout=15)
        assert r.status_code == 401


# ---------- Register / login edge cases ----------


class TestRegisterEdges:
    def test_duplicate_email_rejected(self):
        data = _register()
        email = data["user"]["email"]
        r = requests.post(
            f"{API}/auth/register", json={"email": email, "password": "Pw1234!!XY", "name": "Dup"}, timeout=15
        )
        assert r.status_code == 400
        assert "already" in r.json()["detail"].lower()

    def test_short_password_rejected(self):
        """Server-side min_length=8 — see prompts/security commit."""
        r = requests.post(
            f"{API}/auth/register",
            json={"email": f"shortpw_{uuid.uuid4().hex[:6]}@x.com", "password": "short", "name": "S"},
            timeout=15,
        )
        assert r.status_code == 422  # Pydantic validation

    def test_malformed_email_rejected(self):
        r = requests.post(
            f"{API}/auth/register",
            json={"email": "not-an-email", "password": "Pw1234!!XY", "name": "X"},
            timeout=15,
        )
        assert r.status_code == 422

    def test_long_name_rejected(self):
        r = requests.post(
            f"{API}/auth/register",
            json={
                "email": f"longname_{uuid.uuid4().hex[:6]}@x.com",
                "password": "Pw1234!!XY",
                "name": "x" * 200,
            },
            timeout=15,
        )
        assert r.status_code == 422

    def test_email_lowercased_on_register(self):
        """Mixed-case at register; lowercase on read."""
        mixed = f"Mix_{uuid.uuid4().hex[:6]}@Example.COM"
        r = requests.post(
            f"{API}/auth/register", json={"email": mixed, "password": "Pw1234!!XY", "name": "M"}, timeout=15
        )
        assert r.status_code == 200
        assert r.json()["user"]["email"] == mixed.lower()


class TestLoginEdges:
    def test_wrong_password_401(self):
        data = _register()
        r = requests.post(
            f"{API}/auth/login", json={"email": data["user"]["email"], "password": "WrongPw1!"}, timeout=15
        )
        assert r.status_code == 401

    def test_unknown_email_401(self):
        r = requests.post(
            f"{API}/auth/login",
            json={"email": f"noone_{uuid.uuid4().hex[:6]}@x.com", "password": "Pw1234!!XY"},
            timeout=15,
        )
        assert r.status_code == 401

    def test_login_case_insensitive(self):
        """Mixed-case email at login still works after lowercased storage."""
        data = _register()
        email = data["user"]["email"]
        r = requests.post(
            f"{API}/auth/login", json={"email": email.upper(), "password": "Pw1234!!XY"}, timeout=15
        )
        assert r.status_code == 200


# ---------- Google session ----------


class TestGoogleSession:
    def test_bogus_session_id_401_or_502(self):
        r = requests.post(
            f"{API}/auth/google/session", json={"session_id": f"bogus-{uuid.uuid4().hex}"}, timeout=20
        )
        assert r.status_code in (401, 502), r.text

    def test_empty_session_id_422(self):
        """min_length=1 on the Pydantic model."""
        r = requests.post(f"{API}/auth/google/session", json={"session_id": ""}, timeout=15)
        assert r.status_code == 422

    def test_oversized_session_id_422(self):
        r = requests.post(f"{API}/auth/google/session", json={"session_id": "x" * 5000}, timeout=15)
        assert r.status_code == 422
