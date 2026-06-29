"""Day 1 import pipeline tests.

Covers: ADMIN_EMAILS CSV/backward-compat helper, heuristic + mapping unit
behaviour, and the /import/{parse,map,commit,seed-demo}+/onboarding/state
HTTP surface with fresh per-test tenants so RLS isolation is enforced.
"""

from __future__ import annotations

import importlib
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"


def _ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


def _register() -> tuple[requests.Session, str]:
    email = f"imptest_{uuid.uuid4().hex[:8]}@x.com"
    r = requests.post(
        f"{API}/auth/register",
        json={"email": email, "password": "Pw1234!!", "name": "Imp Tester"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s, email


def _crm_csv() -> bytes:
    return (
        "Customer,Deal Value,Status,Last Contact\n"
        f"Acme Corp,12000,Open,{_ago(2)}\n"
        f"BetaWorks,8500,Won,{_ago(40)}\n"
        f"Cinco Pvt,15000,Overdue,{_ago(20)}\n"
        f"Delta Ltd,4000,Open,{_ago(5)}\n"
        f"Echo Co,22500,Lost,{_ago(60)}\n"
        f"Foxtrot,6000,Overdue,{_ago(18)}\n"
        f"Gamma Pvt,9500,Open,{_ago(35)}\n"
    ).encode()


# ---------- Unit: ADMIN_EMAILS helper ----------
class TestAdminEmails:
    def test_csv_takes_precedence(self, monkeypatch):
        import server

        monkeypatch.setenv("ADMIN_EMAILS", "a@x.com,b@y.com")
        monkeypatch.delenv("ADMIN_EMAIL", raising=False)
        assert server._admin_emails() == {"a@x.com", "b@y.com"}

    def test_backward_compat_single(self, monkeypatch):
        import server

        monkeypatch.delenv("ADMIN_EMAILS", raising=False)
        monkeypatch.setenv("ADMIN_EMAIL", "Founder@Y.com")
        assert server._admin_emails() == {"founder@y.com"}

    def test_empty(self, monkeypatch):
        import server

        monkeypatch.delenv("ADMIN_EMAILS", raising=False)
        monkeypatch.delenv("ADMIN_EMAIL", raising=False)
        assert server._admin_emails() == set()

    def test_whitespace_and_case(self, monkeypatch):
        import server

        monkeypatch.setenv("ADMIN_EMAILS", "  ONE@X.com , two@y.com ,")
        monkeypatch.delenv("ADMIN_EMAIL", raising=False)
        assert server._admin_emails() == {"one@x.com", "two@y.com"}


# ---------- Unit: heuristics (no HTTP) ----------
class TestHeuristics:
    def test_classifies_money_date_status_identifier(self):
        from services.data.import_heuristics import analyze_csv

        r = analyze_csv(_crm_csv())
        ct = r["column_types"]
        assert "Deal Value" in ct.get("money", [])
        assert "Last Contact" in ct.get("date", [])
        assert "Status" in ct.get("status", [])
        assert "Customer" in ct.get("identifier", [])

    def test_quick_signals_match_dates_and_money(self):
        from services.data.import_heuristics import analyze_csv

        r = analyze_csv(_crm_csv())
        qs = r["quick_signals"]
        assert qs["silent_clients_count"] == 5  # rows older than 14 days
        assert qs["inactive_deals_count"] == 3  # rows older than 30 days
        assert qs["overdue_invoices_count"] == 2
        assert qs["pipeline_inr"] == 77500

    def test_empty_input_raises_value_error(self):
        from services.data.import_heuristics import analyze_csv

        with pytest.raises(ValueError):
            analyze_csv(b"")

    def test_no_money_no_date_csv(self):
        from services.data.import_heuristics import analyze_csv

        r = analyze_csv(b"Name,Type\nAcme,Vendor\nBetaWorks,Customer\nCharlie,Vendor\n")
        assert r["quick_signals"]["pipeline_inr"] == 0
        assert r["quick_signals"]["silent_clients_count"] == 0


# ---------- Unit: heuristic mapping ----------
class TestHeuristicMapping:
    def test_deal_value_maps_to_value_inr_not_title(self):
        from services.data.import_mapping import heuristic_mapping

        m = {
            x["target_field"]: x["source_header"]
            for x in heuristic_mapping(["Customer", "Deal Value", "Last Contact"], "proposals")
        }
        assert m["value_inr"] == "Deal Value"
        assert m["client_name"] == "Customer"

    def test_business_maps_to_client_name(self):
        from services.data.import_mapping import heuristic_mapping

        m = {
            x["target_field"]: x["source_header"]
            for x in heuristic_mapping(["Business", "Revenue", "Status"], "proposals")
        }
        assert m["client_name"] == "Business"
        assert m["value_inr"] == "Revenue"
        assert m["stage"] == "Status"

    def test_unknown_target_raises(self):
        from services.data.import_mapping import heuristic_mapping

        with pytest.raises(ValueError):
            heuristic_mapping(["A"], "unknown")


# ---------- HTTP: full pipeline ----------
class TestImportParseEndpoint:
    def test_parse_csv_returns_quick_signals(self):
        s, _ = _register()
        r = s.post(f"{API}/import/parse", files={"file": ("a.csv", _crm_csv(), "text/csv")}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "file_id" in body
        assert body["data_quality"]["rows"] == 7
        assert body["quick_signals"]["pipeline_inr"] == 77500

    def test_parse_empty_body_400(self):
        s, _ = _register()
        r = s.post(f"{API}/import/parse", files={"file": ("e.csv", b"", "text/csv")}, timeout=15)
        assert r.status_code == 400

    def test_parse_unauthenticated_401(self):
        r = requests.post(
            f"{API}/import/parse", files={"file": ("a.csv", _crm_csv(), "text/csv")}, timeout=15
        )
        assert r.status_code == 401


class TestImportMapEndpoint:
    def test_map_returns_both_heuristic_and_ai_or_falls_back(self):
        s, _ = _register()
        fid = s.post(
            f"{API}/import/parse", files={"file": ("a.csv", _crm_csv(), "text/csv")}, timeout=30
        ).json()["file_id"]
        r = s.post(f"{API}/import/map", json={"file_id": fid, "target": "proposals"}, timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        # Heuristic is always populated. AI may be None if the LLM key is absent.
        assert body["heuristic_mapping"]
        h = {x["target_field"]: x["source_header"] for x in body["heuristic_mapping"]}
        assert h["value_inr"] == "Deal Value"
        assert h["client_name"] == "Customer"
        if body["ai_mapping"]:
            assert body["ai_error"] is None
        else:
            assert isinstance(body["ai_error"], str)

    def test_map_bad_target_422(self):
        s, _ = _register()
        fid = s.post(
            f"{API}/import/parse", files={"file": ("a.csv", _crm_csv(), "text/csv")}, timeout=30
        ).json()["file_id"]
        r = s.post(f"{API}/import/map", json={"file_id": fid, "target": "garbage"}, timeout=15)
        assert r.status_code == 422

    def test_map_missing_file_id_404(self):
        s, _ = _register()
        r = s.post(
            f"{API}/import/map",
            json={"file_id": "00000000-0000-0000-0000-000000000000", "target": "clients"},
            timeout=15,
        )
        assert r.status_code == 404

    def test_map_cross_tenant_404(self):
        s1, _ = _register()
        s2, _ = _register()
        fid = s1.post(
            f"{API}/import/parse", files={"file": ("a.csv", _crm_csv(), "text/csv")}, timeout=30
        ).json()["file_id"]
        r = s2.post(f"{API}/import/map", json={"file_id": fid, "target": "clients"}, timeout=15)
        assert r.status_code == 404


class TestImportCommitEndpoint:
    def test_commit_clients_target_inserts_rows(self):
        s, _ = _register()
        csv = (
            "Customer,Email,Phone\n"
            "Acme Corp,acme@x.com,9999900001\n"
            "BetaWorks,beta@y.com,9999900002\n"
            "Cinco Pvt,,9999900003\n"
            ",empty@x.com,9999900004\n"  # empty name -> skipped
        ).encode()
        fid = s.post(f"{API}/import/parse", files={"file": ("c.csv", csv, "text/csv")}, timeout=30).json()[
            "file_id"
        ]
        s.post(f"{API}/import/map", json={"file_id": fid, "target": "clients"}, timeout=60)
        r = s.post(f"{API}/import/commit", json={"file_id": fid}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["clients_inserted"] == 3
        assert body["skipped"] == 1

    def test_commit_proposals_does_not_orphan_clients_on_skip(self):
        """Regression: a row with bad value_inr must NOT create the lazy
        client. The fix builds the doc before ensure_client."""
        s, _ = _register()
        csv = (
            f"Client,Deal Value,Stage,Last Talk\nGoodCo,50000,Open,{_ago(10)}\nBadCo,abc,Open,{_ago(2)}\n"
        ).encode()
        fid = s.post(f"{API}/import/parse", files={"file": ("p.csv", csv, "text/csv")}, timeout=30).json()[
            "file_id"
        ]
        s.post(f"{API}/import/map", json={"file_id": fid, "target": "proposals"}, timeout=60)
        r = s.post(f"{API}/import/commit", json={"file_id": fid}, timeout=30).json()
        assert r["proposals_inserted"] == 1
        assert r["clients_inserted"] == 1  # BadCo skipped without leaving an orphan
        assert r["skipped"] == 1

    def test_commit_double_commit_409(self):
        s, _ = _register()
        csv = b"Customer,Email\nAcme,a@x.com\n"
        fid = s.post(f"{API}/import/parse", files={"file": ("c.csv", csv, "text/csv")}, timeout=30).json()[
            "file_id"
        ]
        s.post(f"{API}/import/map", json={"file_id": fid, "target": "clients"}, timeout=60)
        s.post(f"{API}/import/commit", json={"file_id": fid}, timeout=30)
        r = s.post(f"{API}/import/commit", json={"file_id": fid}, timeout=30)
        assert r.status_code == 409

    def test_commit_without_map_400(self):
        s, _ = _register()
        csv = b"Customer,Email\nAcme,a@x.com\n"
        fid = s.post(f"{API}/import/parse", files={"file": ("c.csv", csv, "text/csv")}, timeout=30).json()[
            "file_id"
        ]
        r = s.post(f"{API}/import/commit", json={"file_id": fid}, timeout=30)
        assert r.status_code == 400

    def test_commit_cross_tenant_404(self):
        s1, _ = _register()
        s2, _ = _register()
        csv = b"Customer\nAcme\n"
        fid = s1.post(f"{API}/import/parse", files={"file": ("c.csv", csv, "text/csv")}, timeout=30).json()[
            "file_id"
        ]
        s1.post(f"{API}/import/map", json={"file_id": fid, "target": "clients"}, timeout=60)
        r = s2.post(f"{API}/import/commit", json={"file_id": fid}, timeout=30)
        assert r.status_code == 404


class TestOnboardingAndSeed:
    def test_state_fresh_tenant_has_no_data(self):
        s, _ = _register()
        r = s.get(f"{API}/onboarding/state", timeout=15).json()
        assert r["has_data"] is False
        assert r["clients_count"] == 0

    def test_seed_demo_populates_then_409s(self):
        s, _ = _register()
        r1 = s.post(f"{API}/import/seed-demo", timeout=60).json()
        assert r1["clients"] > 0 and r1["proposals"] > 0 and r1["invoices"] > 0
        r2 = s.post(f"{API}/import/seed-demo", timeout=15)
        assert r2.status_code == 409
        state = s.get(f"{API}/onboarding/state", timeout=15).json()
        assert state["has_data"] is True
        assert state["clients_count"] == r1["clients"]


# Touch importlib to keep ruff happy about the import side-effect tests above.
_ = importlib  # ponytail: ruff F401 dance for the monkeypatch tests
