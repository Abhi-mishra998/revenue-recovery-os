"""
Pure unit tests for the locked status/overdue math.

These functions are the PRD's contract — they get loaded in every dashboard
read and every list response, so unit-testing the boundaries explicitly
guards against silent drift (see the cold/dead threshold regression
in the OPUS-0 audit).
"""

import os
from datetime import datetime, timedelta, timezone

# Test env needs the same vars as the live backend for `import server` to work,
# since server.py reads MONGO_URL / JWT_SECRET at import time.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "revora_test")
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use-in-prod")

import pytest

from server import (
    compute_invoice_status_and_overdue,
    compute_proposal_status,
    days_since,
)


def iso_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def iso_ahead(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


# ---------- compute_proposal_status (PRD: active ≤7, cold 8-21, dead >21) ----


class TestComputeProposalStatus:
    @pytest.mark.parametrize(
        "days,expected",
        [
            (0, "active"),
            (1, "active"),
            (7, "active"),
            (8, "cold"),
            (14, "cold"),
            (21, "cold"),
            (22, "dead"),
            (30, "dead"),
            (365, "dead"),
        ],
    )
    def test_boundaries(self, days, expected):
        assert compute_proposal_status(iso_ago(days)) == expected

    def test_naive_datetime_is_treated_as_utc(self):
        """A timestamp without tzinfo gets UTC attached — never raises."""
        naive = (datetime.utcnow() - timedelta(days=10)).isoformat()
        assert compute_proposal_status(naive) == "cold"

    def test_aware_datetime_with_offset(self):
        """ISO with a +05:30 (IST) offset still computes correctly."""
        ist_15d_ago = (
            datetime.now(timezone(timedelta(hours=5, minutes=30))) - timedelta(days=15)
        ).isoformat()
        assert compute_proposal_status(ist_15d_ago) == "cold"

    def test_future_date_is_active(self):
        """Defensive: a last_contact in the future shouldn't flip to dead."""
        assert compute_proposal_status(iso_ahead(5)) == "active"


# ---------- compute_invoice_status_and_overdue ----------


class TestComputeInvoiceStatus:
    def test_paid_invoice_is_paid_with_zero_overdue(self):
        inv = {"due_date": iso_ago(10), "paid_date": iso_ago(2), "amount_inr": 100}
        s, d = compute_invoice_status_and_overdue(inv)
        assert s == "paid" and d == 0

    def test_unpaid_future_due_is_unpaid(self):
        inv = {"due_date": iso_ahead(5), "amount_inr": 100}
        s, d = compute_invoice_status_and_overdue(inv)
        assert s == "unpaid" and d == 0

    def test_unpaid_past_due_is_overdue(self):
        inv = {"due_date": iso_ago(3), "amount_inr": 100}
        s, d = compute_invoice_status_and_overdue(inv)
        assert s == "overdue" and d == 3

    def test_paid_date_overrides_past_due(self):
        """An overdue invoice that later got paid should report 'paid'."""
        inv = {"due_date": iso_ago(30), "paid_date": iso_ago(1), "amount_inr": 100}
        s, d = compute_invoice_status_and_overdue(inv)
        assert s == "paid" and d == 0

    def test_due_today_is_unpaid(self):
        """Today's due date should not show 1 day overdue."""
        today = datetime.now(timezone.utc).isoformat()
        inv = {"due_date": today, "amount_inr": 100}
        s, d = compute_invoice_status_and_overdue(inv)
        assert s == "unpaid" and d == 0


# ---------- days_since ----------


class TestDaysSince:
    def test_zero_for_now(self):
        now = datetime.now(timezone.utc).isoformat()
        assert days_since(now) == 0

    def test_positive_for_past(self):
        assert days_since(iso_ago(10)) == 10

    def test_negative_for_future(self):
        """Future returns a negative day count (callers wrap with max(0,…) when they care)."""
        # 5 days ahead — days property of a negative timedelta is -6 or -5
        # depending on the sub-second remainder; either way, < 0
        assert days_since(iso_ahead(5)) < 0

    def test_naive_datetime_treated_as_utc(self):
        """No timezone in the input string still works."""
        naive = (datetime.utcnow() - timedelta(days=3)).isoformat()
        assert days_since(naive) == 3
