"""
End-to-end test of the AI follow-up pipeline with a stub LLM provider.

Exercises the real generate_proposal_followup() through:
  router → prompt render → redact → generate_json (validator/retry) →
  rehydrate → guardrail → response

No external LLM call. The StubProvider is registered in PROVIDERS and the
test pins it via the `provider=` keyword. Covers:

  - happy path: clean output, all fields rehydrated, all badges populated
  - PII in the proposal title is redacted out and rehydrated back in
  - malformed JSON triggers ONE retry and recovers
  - guardrail blocks an output that echoes 'as an AI'
"""

import asyncio
import json
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "revora_test")
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use-in-prod")

from services.ai import GuardrailViolation, LLMProviderUnavailable, generate_proposal_followup
from services.ai.client import PROVIDERS


def _run(coro):
    return asyncio.run(coro)


class StubProvider:
    name = "stub-e2e"
    default_model = "stub"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.last_system: str | None = None
        self.last_user: str | None = None

    async def generate_text(self, *, system, user, model=None, max_tokens=1500, session_id=None):
        self.last_system, self.last_user = system, user
        if self.calls >= len(self.responses):
            raise AssertionError(f"stub exhausted after {self.calls} calls")
        r = self.responses[self.calls]
        self.calls += 1
        return r


@pytest.fixture
def register_stub():
    def _register(stub):
        PROVIDERS["__e2e_stub__"] = stub
        return stub

    yield _register
    PROVIDERS.pop("__e2e_stub__", None)


VALID_DRAFT = {
    "whatsapp_text": "Hi Priya, just a quick nudge on the FinKart KYC proposal we sent last week. Happy to discuss whenever. - Rohan",
    "email_subject": "Quick nudge on FinKart KYC proposal",
    "email_body": (
        "Hi Priya,\n\nFollowing up on the FinKart KYC + UPI flows proposal we shared. Happy to walk through "
        "scope or timeline whenever it suits.\n\nBest,\nRohan, Revora"
    ),
    "confidence": 0.85,
}


def _stub_payload(**overrides) -> str:
    return json.dumps({**VALID_DRAFT, **overrides})


# ---------- happy path ----------


class TestHappyPath:
    def test_returns_all_fields_including_meta(self, register_stub):
        stub = register_stub(StubProvider([_stub_payload()]))
        result = _run(
            generate_proposal_followup(
                sender_name="Rohan",
                recipient_contact="Priya",
                recipient_company="FinKart",
                industry="Fintech",
                title="KYC + UPI flows",
                value_inr=620000,
                days_silent=4,
                provider="__e2e_stub__",
            )
        )
        assert result["whatsapp_text"] == VALID_DRAFT["whatsapp_text"]
        assert result["email_subject"] == VALID_DRAFT["email_subject"]
        assert result["email_body"] == VALID_DRAFT["email_body"]
        assert result["confidence"] == 0.85
        assert result["prompt_ref"].startswith("proposal_followup@v")
        assert result["route_ref"].startswith("simple:")  # ₹6.2L is under threshold
        assert stub.calls == 1, "single LLM call, no retry"

    def test_high_value_proposal_routes_to_complex_tier(self, register_stub):
        stub = register_stub(StubProvider([_stub_payload()]))
        result = _run(
            generate_proposal_followup(
                sender_name="Rohan",
                recipient_contact="Priya",
                recipient_company="FinKart",
                industry="Fintech",
                title="enterprise rollout",
                value_inr=10_000_000,  # ≥ ₹50L threshold
                days_silent=4,
                provider="__e2e_stub__",
            )
        )
        assert result["route_ref"].startswith("complex:")


# ---------- PII redaction roundtrip ----------


class TestPiiRedaction:
    def test_email_in_title_redacted_before_llm(self, register_stub):
        stub = register_stub(StubProvider([_stub_payload()]))
        _run(
            generate_proposal_followup(
                sender_name="Rohan",
                recipient_contact="Priya",
                recipient_company="FinKart",
                industry="Fintech",
                title="Onboard ops@finkart.io to the new flow",  # email in title
                value_inr=100000,
                days_silent=4,
                provider="__e2e_stub__",
            )
        )
        # The model never saw the literal email
        assert "ops@finkart.io" not in stub.last_user
        assert "[REDACTED:EMAIL_1]" in stub.last_user

    def test_phone_in_title_redacted(self, register_stub):
        stub = register_stub(StubProvider([_stub_payload()]))
        _run(
            generate_proposal_followup(
                sender_name="Rohan",
                recipient_contact="Priya",
                recipient_company="FinKart",
                industry="Fintech",
                title="Call +91 98201 84421 to confirm",
                value_inr=100000,
                days_silent=4,
                provider="__e2e_stub__",
            )
        )
        assert "98201" not in stub.last_user
        assert "[REDACTED:PHONE_1]" in stub.last_user

    def test_token_echoed_by_model_gets_rehydrated(self, register_stub):
        """If the model parrots a PII token in its output, rehydrate restores
        the original value before the result reaches the user."""
        # Stub returns a draft that includes the EMAIL token in the body
        echo_draft = {
            **VALID_DRAFT,
            "email_body": "Hi,\n\nPlease confirm at [REDACTED:EMAIL_1].\n\nBest,\nRohan, Revora",
        }
        register_stub(StubProvider([json.dumps(echo_draft)]))
        result = _run(
            generate_proposal_followup(
                sender_name="Rohan",
                recipient_contact="Priya",
                recipient_company="FinKart",
                industry="Fintech",
                title="Confirm ops@finkart.io",  # introduces EMAIL_1 mapping
                value_inr=100000,
                days_silent=4,
                provider="__e2e_stub__",
            )
        )
        assert "ops@finkart.io" in result["email_body"]
        assert "[REDACTED:" not in result["email_body"]


# ---------- malformed output retry ----------


class TestRetryRecovery:
    def test_first_call_garbage_second_call_valid(self, register_stub):
        stub = register_stub(StubProvider(["not json at all", _stub_payload()]))
        result = _run(
            generate_proposal_followup(
                sender_name="Rohan",
                recipient_contact="Priya",
                recipient_company="FinKart",
                industry="Fintech",
                title="KYC flows",
                value_inr=100000,
                days_silent=4,
                provider="__e2e_stub__",
            )
        )
        assert result["email_subject"] == VALID_DRAFT["email_subject"]
        assert stub.calls == 2, "retried once and recovered"

    def test_corrective_system_prompt_on_retry(self, register_stub):
        """The retry must include the corrective ask for valid JSON only."""
        stub = register_stub(StubProvider(["nope", _stub_payload()]))
        _run(
            generate_proposal_followup(
                sender_name="Rohan",
                recipient_contact="Priya",
                recipient_company="FinKart",
                industry="Fintech",
                title="KYC flows",
                value_inr=100000,
                days_silent=4,
                provider="__e2e_stub__",
            )
        )
        assert "Return ONLY a single JSON object" in stub.last_system


# ---------- guardrail integration ----------


class TestGuardrailIntegration:
    def test_ai_disclaimer_in_output_raises_guardrail(self, register_stub):
        bad = {
            **VALID_DRAFT,
            "whatsapp_text": "As an AI, I cannot generate marketing copy for you, sorry friend.",
        }
        register_stub(StubProvider([json.dumps(bad)]))
        with pytest.raises(GuardrailViolation) as exc:
            _run(
                generate_proposal_followup(
                    sender_name="Rohan",
                    recipient_contact="Priya",
                    recipient_company="FinKart",
                    industry="Fintech",
                    title="KYC flows",
                    value_inr=100000,
                    days_silent=4,
                    provider="__e2e_stub__",
                )
            )
        assert any("blacklisted" in i for i in exc.value.issues)

    def test_single_line_email_raises_guardrail(self, register_stub):
        bad = {
            **VALID_DRAFT,
            "email_body": "Hi, quick nudge on the proposal happy to discuss thanks Rohan Revora",
        }
        register_stub(StubProvider([json.dumps(bad)]))
        with pytest.raises(GuardrailViolation):
            _run(
                generate_proposal_followup(
                    sender_name="Rohan",
                    recipient_contact="Priya",
                    recipient_company="FinKart",
                    industry="Fintech",
                    title="KYC flows",
                    value_inr=100000,
                    days_silent=4,
                    provider="__e2e_stub__",
                )
            )


# ---------- graceful degradation: provider retry + exhaustion ----------


class _FlakyProvider:
    """Provider that raises N times before returning success — exercises the
    retry path in client.generate_text without hitting an actual LLM."""

    name = "stub-flaky"
    default_model = "stub"

    def __init__(self, fail_times: int, then_response: str):
        self.fail_times = fail_times
        self.then_response = then_response
        self.calls = 0

    async def generate_text(self, *, system, user, model=None, max_tokens=1500, session_id=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ConnectionError(f"simulated transport failure #{self.calls}")
        return self.then_response


class TestProviderRetry:
    """Verify exponential-backoff retry hides transient provider failures."""

    def test_recovers_after_two_transient_failures(self, monkeypatch, register_stub):
        monkeypatch.setenv("LLM_MAX_ATTEMPTS", "3")
        monkeypatch.setenv("LLM_RETRY_BASE_SECONDS", "0.01")
        monkeypatch.setenv("LLM_RETRY_CAP_SECONDS", "0.02")
        flaky = register_stub(_FlakyProvider(fail_times=2, then_response=_stub_payload()))
        result = _run(
            generate_proposal_followup(
                sender_name="Rohan", recipient_contact="Priya",
                recipient_company="FinKart", industry="Fintech",
                title="KYC flows", value_inr=100000, days_silent=4,
                provider="__e2e_stub__",
            )
        )
        assert result["email_subject"] == VALID_DRAFT["email_subject"]
        assert flaky.calls == 3, f"expected 3 calls (2 fails + 1 success), got {flaky.calls}"

    def test_raises_llm_unavailable_after_all_attempts_fail(self, monkeypatch, register_stub):
        monkeypatch.setenv("LLM_MAX_ATTEMPTS", "3")
        monkeypatch.setenv("LLM_RETRY_BASE_SECONDS", "0.01")
        monkeypatch.setenv("LLM_RETRY_CAP_SECONDS", "0.02")
        flaky = register_stub(_FlakyProvider(fail_times=10, then_response=_stub_payload()))
        with pytest.raises(LLMProviderUnavailable):
            _run(
                generate_proposal_followup(
                    sender_name="Rohan", recipient_contact="Priya",
                    recipient_company="FinKart", industry="Fintech",
                    title="KYC flows", value_inr=100000, days_silent=4,
                    provider="__e2e_stub__",
                )
            )
        assert flaky.calls == 3, f"expected exactly LLM_MAX_ATTEMPTS calls, got {flaky.calls}"
