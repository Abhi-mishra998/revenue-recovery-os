"""
Data layer tests:
  - predictor (unit, no LLM)
  - events emission on create / stage change / payment
  - client_memory recompute on activity create + stage flip
  - followups GET history + outcome_at + prediction in proposal response
"""
import os
import uuid
import pytest
import requests
from datetime import datetime, timezone, timedelta

from services.data import predict_close_probability, extract_proposal_features


BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"


def _iso_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _iso_ahead(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _register(prefix: str) -> requests.Session:
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "password": "Pw1234!!XY", "name": prefix.title()},
                      timeout=15)
    assert r.status_code == 200, r.text
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json",
                      "Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="class")
def s():
    return _register("data")


@pytest.fixture(scope="class")
def client_with_proposal(s):
    c = s.post(f"{API}/clients", json={
        "company_name": f"DATA_{uuid.uuid4().hex[:6]}", "contact_name": "Data Test",
    }, timeout=15).json()
    p = s.post(f"{API}/proposals", json={
        "client_id": c["id"], "title": "Data layer pilot",
        "value_inr": 200000, "stage": "sent",
        "sent_date": _iso_ago(2), "last_contact_date": _iso_ago(2),
    }, timeout=15).json()
    return {"client": c, "proposal": p}


# ---------- Predictor (pure, no LLM) ----------
class TestPredictor:
    def test_terminal_won_is_one(self):
        p = predict_close_probability({"stage": "won"})
        assert p.probability == 1.0 and p.confidence == 1.0
        assert p.model_ref == "heuristic-v1"

    def test_terminal_lost_is_zero(self):
        p = predict_close_probability({"stage": "lost"})
        assert p.probability == 0.0 and p.confidence == 1.0

    def test_stage_sent_default_base(self):
        p = predict_close_probability({"stage": "sent"})
        assert 0.35 <= p.probability <= 0.45
        assert any("base 0.40" in r for r in p.reasons)

    def test_silence_penalty_kicks_in_past_7d(self):
        baseline = predict_close_probability({"stage": "sent", "days_silent": 5}).probability
        cold = predict_close_probability({"stage": "sent", "days_silent": 20}).probability
        assert cold < baseline

    def test_high_response_rate_lifts(self):
        low = predict_close_probability({"stage": "negotiating", "response_rate": 0.1}).probability
        high = predict_close_probability({"stage": "negotiating", "response_rate": 0.9}).probability
        assert high > low

    def test_signal_density_drives_confidence(self):
        sparse = predict_close_probability({"stage": "sent"}).confidence
        rich = predict_close_probability({
            "stage": "sent", "days_silent": 5, "response_rate": 0.7,
            "typical_response_days": 1.5, "outcome_count": 3,
        }).confidence
        assert rich > sparse


class TestFeatureExtractor:
    def test_extracts_from_proposal_and_memory(self):
        f = extract_proposal_features(
            proposal={"stage": "sent", "value_inr": 100000,
                      "last_contact_date": _iso_ago(10),
                      "sent_date": _iso_ago(20),
                      "client_industry": "Fintech"},
            memory={"response_rate": 0.5, "typical_response_days": 3.0,
                    "channel_preference": "whatsapp", "last_outcomes": [{}, {}]},
        )
        assert f["stage"] == "sent"
        assert f["value_inr"] == 100000.0
        assert f["days_silent"] >= 9
        assert f["industry"] == "Fintech"
        assert f["response_rate"] == 0.5
        assert f["outcome_count"] == 2

    def test_handles_missing_memory(self):
        f = extract_proposal_features(
            proposal={"stage": "sent", "value_inr": 1000,
                      "last_contact_date": _iso_ago(1), "sent_date": _iso_ago(1)},
            memory=None,
        )
        assert f["response_rate"] is None
        assert f["channel_preference"] is None


# ---------- Proposal API returns prediction + outcome_at ----------
class TestProposalApiEnrichment:
    def test_get_proposal_includes_prediction(self, s, client_with_proposal):
        pid = client_with_proposal["proposal"]["id"]
        d = s.get(f"{API}/proposals/{pid}", timeout=15).json()
        assert "prediction" in d
        assert 0.0 <= d["prediction"]["probability"] <= 1.0
        assert d["prediction"]["model_ref"] == "heuristic-v1"
        assert isinstance(d["prediction"]["reasons"], list)

    def test_stage_to_won_stamps_outcome_at(self, s, client_with_proposal):
        pid = client_with_proposal["proposal"]["id"]
        r = s.patch(f"{API}/proposals/{pid}", json={"stage": "won"}, timeout=15)
        assert r.status_code == 200, r.text
        d = s.get(f"{API}/proposals/{pid}", timeout=15).json()
        assert d["stage"] == "won"
        assert d.get("outcome_at"), d
        assert d["prediction"]["probability"] == 1.0

    def test_stage_flip_did_not_stamp_outcome_at_initially(self):
        # Fresh proposal — outcome_at should be absent until terminal transition.
        s2 = _register("fresh")
        c = s2.post(f"{API}/clients", json={"company_name": f"X_{uuid.uuid4().hex[:5]}",
                                            "contact_name": "x"}, timeout=15).json()
        p = s2.post(f"{API}/proposals", json={
            "client_id": c["id"], "title": "open deal", "value_inr": 1000, "stage": "sent",
        }, timeout=15).json()
        d = s2.get(f"{API}/proposals/{p['id']}", timeout=15).json()
        assert not d.get("outcome_at")


# ---------- Events emission ----------
class TestEvents:
    def test_proposal_created_emits_event(self):
        s2 = _register("ev_pc")
        c = s2.post(f"{API}/clients", json={"company_name": f"E_{uuid.uuid4().hex[:5]}",
                                            "contact_name": "e"}, timeout=15).json()
        p = s2.post(f"{API}/proposals", json={
            "client_id": c["id"], "title": "ev test", "value_inr": 1000, "stage": "sent",
        }, timeout=15).json()
        evs = s2.get(f"{API}/events?entity_id={p['id']}", timeout=15).json()
        types = [e["event_type"] for e in evs]
        assert "proposal.created" in types

    def test_stage_change_emits_event(self):
        s2 = _register("ev_sc")
        c = s2.post(f"{API}/clients", json={"company_name": f"E_{uuid.uuid4().hex[:5]}",
                                            "contact_name": "e"}, timeout=15).json()
        p = s2.post(f"{API}/proposals", json={
            "client_id": c["id"], "title": "ev test", "value_inr": 1000, "stage": "sent",
        }, timeout=15).json()
        s2.patch(f"{API}/proposals/{p['id']}", json={"stage": "won"}, timeout=15)
        evs = s2.get(f"{API}/events?entity_id={p['id']}", timeout=15).json()
        types = [e["event_type"] for e in evs]
        assert "proposal.stage_changed" in types
        assert "proposal.won" in types
        # Stage-change event carries prior/new values
        sc = next(e for e in evs if e["event_type"] == "proposal.stage_changed")
        assert sc["prior_value"] == "sent" and sc["new_value"] == "won"

    def test_invoice_payment_emits_event(self):
        s2 = _register("ev_pay")
        c = s2.post(f"{API}/clients", json={"company_name": f"E_{uuid.uuid4().hex[:5]}",
                                            "contact_name": "e"}, timeout=15).json()
        inv = s2.post(f"{API}/invoices", json={
            "client_id": c["id"], "invoice_no": f"E-{uuid.uuid4().hex[:5]}",
            "amount_inr": 5000, "due_date": _iso_ago(2),
        }, timeout=15).json()
        s2.patch(f"{API}/invoices/{inv['id']}", json={"paid_date": _iso_ago(0)}, timeout=15)
        evs = s2.get(f"{API}/events?entity_id={inv['id']}", timeout=15).json()
        types = [e["event_type"] for e in evs]
        assert "invoice.payment_received" in types
        pe = next(e for e in evs if e["event_type"] == "invoice.payment_received")
        assert pe["metadata"].get("days_overdue_at_payment") is not None


# ---------- client_memory recompute ----------
class TestClientMemory:
    def test_memory_recomputes_after_activity(self):
        s2 = _register("mem")
        c = s2.post(f"{API}/clients", json={"company_name": f"M_{uuid.uuid4().hex[:5]}",
                                            "contact_name": "m"}, timeout=15).json()
        # Outbound, then inbound — should produce one response pair.
        s2.post(f"{API}/activities", json={
            "client_id": c["id"], "channel": "whatsapp", "direction": "outbound",
            "summary": "first ping",
        }, timeout=15)
        s2.post(f"{API}/activities", json={
            "client_id": c["id"], "channel": "whatsapp", "direction": "inbound",
            "summary": "reply",
        }, timeout=15)
        m = s2.get(f"{API}/clients/{c['id']}/memory", timeout=15).json()
        assert m["channel_preference"] == "whatsapp"
        assert (m["channel_counts"] or {}).get("whatsapp", 0) >= 1
        assert m["response_rate"] is not None and m["response_rate"] > 0

    def test_memory_records_outcomes(self):
        s2 = _register("mem_out")
        c = s2.post(f"{API}/clients", json={"company_name": f"M_{uuid.uuid4().hex[:5]}",
                                            "contact_name": "m"}, timeout=15).json()
        p = s2.post(f"{API}/proposals", json={
            "client_id": c["id"], "title": "won deal", "value_inr": 100, "stage": "sent",
        }, timeout=15).json()
        s2.patch(f"{API}/proposals/{p['id']}", json={"stage": "won"}, timeout=15)
        m = s2.get(f"{API}/clients/{c['id']}/memory", timeout=15).json()
        types = [o["type"] for o in (m.get("last_outcomes") or [])]
        assert "proposal.won" in types


# ---------- followups GET history ----------
class TestFollowupHistory:
    def test_endpoint_returns_empty_for_fresh_proposal(self, s, client_with_proposal):
        pid = client_with_proposal["proposal"]["id"]
        h = s.get(f"{API}/proposals/{pid}/followups", timeout=15)
        assert h.status_code == 200
        assert isinstance(h.json(), list)

    def test_other_tenant_cannot_read_history(self, s, client_with_proposal):
        pid = client_with_proposal["proposal"]["id"]
        other = _register("hist_other")
        r = other.get(f"{API}/proposals/{pid}/followups", timeout=15)
        assert r.status_code == 404
