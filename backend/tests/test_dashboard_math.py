"""
Pure-function tests for the dashboard recovery math.

`compute_dashboard_summary(proposals, invoices, clients_map)` is the
extracted body of GET /dashboard/summary — same behaviour, but unit-testable
without a running backend. These tests pin every number the UI depends on.
"""
import os
from datetime import datetime, timezone, timedelta

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "revora_test")
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use-in-prod")

from server import compute_dashboard_summary


def iso_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def iso_ahead(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def P(*, id_, client_id, stage="sent", value=10000, last_days_ago=2):
    return {
        "id": id_, "client_id": client_id, "title": f"prop-{id_}",
        "stage": stage, "value_inr": value,
        "last_contact_date": iso_ago(last_days_ago),
        "sent_date": iso_ago(last_days_ago + 1),
    }


def I(*, id_, due_days, paid=False, amount=5000):
    inv = {"id": id_, "client_id": "c", "invoice_no": id_,
           "amount_inr": amount, "due_date": iso_ago(due_days) if due_days > 0
                                                else iso_ahead(-due_days)}
    if paid:
        inv["paid_date"] = iso_ago(1)
    return inv


class TestEmpty:
    def test_zero_data_zero_everything(self):
        d = compute_dashboard_summary([], [], {})
        assert d["total_pipeline_inr"] == 0
        assert d["revenue_at_risk_inr"] == 0
        assert d["estimated_recoverable_inr"] == 0
        assert d["overdue_invoices_count"] == 0
        assert d["overdue_invoices_inr"] == 0
        assert d["top_at_risk"] == []
        assert d["recoverable_assumption_pct"] == 25


class TestPipelineBuckets:
    def test_active_cold_dead_sums_match_status_thresholds(self):
        """active ≤7d, cold 8-21d, dead >21d — money totals split accordingly."""
        proposals = [
            P(id_="p1", client_id="c", value=100, last_days_ago=3),    # active
            P(id_="p2", client_id="c", value=200, last_days_ago=10),   # cold
            P(id_="p3", client_id="c", value=400, last_days_ago=30),   # dead
        ]
        d = compute_dashboard_summary(proposals, [], {})
        assert d["active_inr"] == 100
        assert d["cold_inr"] == 200
        assert d["dead_inr"] == 400
        assert d["total_pipeline_inr"] == 700
        assert d["by_status"] == {"active": 1, "cold": 1, "dead": 1}

    def test_terminal_stages_excluded_from_pipeline(self):
        """Won/lost don't count toward open pipeline."""
        proposals = [
            P(id_="o", client_id="c", value=100, stage="sent", last_days_ago=2),
            P(id_="w", client_id="c", value=999999, stage="won", last_days_ago=2),
            P(id_="l", client_id="c", value=999999, stage="lost", last_days_ago=2),
        ]
        d = compute_dashboard_summary(proposals, [], {})
        assert d["total_pipeline_inr"] == 100
        assert d["by_stage"] == {"sent": 1, "negotiating": 0, "won": 1, "lost": 1}


class TestRecoveryFormula:
    def test_revenue_at_risk_is_cold_plus_dead(self):
        proposals = [
            P(id_="cold1", client_id="c", value=300, last_days_ago=10),
            P(id_="cold2", client_id="c", value=200, last_days_ago=15),
            P(id_="dead1", client_id="c", value=500, last_days_ago=40),
        ]
        d = compute_dashboard_summary(proposals, [], {})
        assert d["revenue_at_risk_inr"] == 1000
        # active doesn't contribute
        assert d["active_inr"] == 0

    def test_estimated_recoverable_is_25pct_rounded(self):
        proposals = [P(id_="x", client_id="c", value=1000, last_days_ago=10)]
        d = compute_dashboard_summary(proposals, [], {})
        # 25% of 1000 = 250
        assert d["estimated_recoverable_inr"] == 250
        assert d["recoverable_assumption_pct"] == 25

    def test_estimated_recoverable_rounds_to_int(self):
        """₹133 × 0.25 = 33.25 → 33 (round to nearest)."""
        proposals = [P(id_="x", client_id="c", value=133, last_days_ago=10)]
        d = compute_dashboard_summary(proposals, [], {})
        assert d["estimated_recoverable_inr"] == 33


class TestOverdue:
    def test_only_past_due_unpaid_counts(self):
        invoices = [
            I(id_="paid", due_days=10, paid=True),           # paid, ignored
            I(id_="future", due_days=-5),                    # unpaid future, ignored
            I(id_="overdue1", due_days=3, amount=500),
            I(id_="overdue2", due_days=10, amount=1500),
        ]
        d = compute_dashboard_summary([], invoices, {})
        assert d["overdue_invoices_count"] == 2
        assert d["overdue_invoices_inr"] == 2000


class TestTopAtRiskRanking:
    def test_ranked_by_value_times_days_silent(self):
        """A low-value-very-cold proposal can outrank a high-value-slightly-cold one
        if value × days is bigger."""
        proposals = [
            P(id_="cheap_old",  client_id="c1", value=100, last_days_ago=30),  # 100 * 30 = 3000
            P(id_="rich_recent", client_id="c2", value=200, last_days_ago=10), # 200 * 10 = 2000
        ]
        d = compute_dashboard_summary(proposals, [], {})
        assert [p["id"] for p in d["top_at_risk"]] == ["cheap_old", "rich_recent"]

    def test_capped_at_five(self):
        proposals = [P(id_=f"p{i}", client_id="c", value=1000, last_days_ago=10) for i in range(8)]
        d = compute_dashboard_summary(proposals, [], {})
        assert len(d["top_at_risk"]) == 5

    def test_active_proposals_not_in_top_at_risk(self):
        proposals = [
            P(id_="active1", client_id="c", value=999999, last_days_ago=3),  # high $$ but active
            P(id_="cold1",   client_id="c", value=100,    last_days_ago=10),
        ]
        d = compute_dashboard_summary(proposals, [], {})
        assert [p["id"] for p in d["top_at_risk"]] == ["cold1"]

    def test_client_name_attached_when_known(self):
        clients = {"c": {"id": "c", "company_name": "Test Co", "contact_name": "Tester"}}
        proposals = [P(id_="cold", client_id="c", value=100, last_days_ago=10)]
        d = compute_dashboard_summary(proposals, [], clients)
        row = d["top_at_risk"][0]
        assert row["client_company_name"] == "Test Co"
        assert row["client_contact_name"] == "Tester"

    def test_client_name_falls_back_when_missing(self):
        proposals = [P(id_="cold", client_id="missing-cid", value=100, last_days_ago=10)]
        d = compute_dashboard_summary(proposals, [], {})
        assert d["top_at_risk"][0]["client_company_name"] == "Unknown"
        assert d["top_at_risk"][0]["client_contact_name"] == ""
