"""
Unit tests for the structured-output validator + retry.

A stub provider is registered for the test, so no real LLM is called.
The provider returns a queue of pre-canned responses, letting us exercise:
  - valid JSON first try
  - valid JSON wrapped in ```json``` fences
  - valid JSON with prose around it (extracted by brace search)
  - malformed first, valid second (retry path)
  - malformed both → raises MalformedOutputError
  - schema-violation both → raises MalformedOutputError
"""

import asyncio

import pytest

from services.ai.client import PROVIDERS, MalformedOutputError, generate_json
from services.ai.schemas import FollowUpDraft

VALID_DRAFT = {
    "whatsapp_text": "Hi Priya, quick nudge on the Nexora catalog redesign proposal we sent last week. Happy to chat. - Rohan",
    "email_subject": "Quick nudge on Nexora catalog redesign",
    "email_body": "Hi Priya,\n\nFollowing up on the catalog redesign sprint proposal — happy to walk through scope or timeline whenever it suits.\n\nBest,\nRohan, Revora",
}


class StubProvider:
    name = "stub"
    default_model = "stub"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def generate_text(self, **_):
        if self.calls >= len(self.responses):
            raise AssertionError(
                f"Stub called {self.calls + 1} times but only {len(self.responses)} responses queued"
            )
        r = self.responses[self.calls]
        self.calls += 1
        return r


@pytest.fixture
def register_stub():
    """Yields a function to register a stub and clean it up after."""

    def _register(stub):
        PROVIDERS["__test_stub__"] = stub

    yield _register
    PROVIDERS.pop("__test_stub__", None)


def _run(coro):
    return asyncio.run(coro)


def _valid_json() -> str:
    import json

    return json.dumps(VALID_DRAFT)


class TestValidJsonFirstTry:
    def test_plain_json(self, register_stub):
        stub = StubProvider([_valid_json()])
        register_stub(stub)
        draft = _run(generate_json(system="x", user="y", schema=FollowUpDraft, provider="__test_stub__"))
        assert isinstance(draft, FollowUpDraft)
        assert draft.email_subject == VALID_DRAFT["email_subject"]
        assert stub.calls == 1, "no retry needed"

    def test_json_in_code_fence(self, register_stub):
        stub = StubProvider([f"```json\n{_valid_json()}\n```"])
        register_stub(stub)
        draft = _run(generate_json(system="x", user="y", schema=FollowUpDraft, provider="__test_stub__"))
        assert draft.email_subject == VALID_DRAFT["email_subject"]
        assert stub.calls == 1

    def test_json_with_prose_around(self, register_stub):
        stub = StubProvider([f"Sure, here you go:\n{_valid_json()}\nLet me know if you need changes."])
        register_stub(stub)
        draft = _run(generate_json(system="x", user="y", schema=FollowUpDraft, provider="__test_stub__"))
        assert draft.email_subject == VALID_DRAFT["email_subject"]
        assert stub.calls == 1


class TestRetryPath:
    def test_malformed_first_valid_second(self, register_stub):
        stub = StubProvider(["this is not json at all sorry", _valid_json()])
        register_stub(stub)
        draft = _run(generate_json(system="x", user="y", schema=FollowUpDraft, provider="__test_stub__"))
        assert draft.email_subject == VALID_DRAFT["email_subject"]
        assert stub.calls == 2, "retry happened"

    def test_schema_violation_first_valid_second(self, register_stub):
        import json

        bad = json.dumps({"whatsapp_text": "x", "email_subject": "ok", "email_body": "short"})  # too short
        stub = StubProvider([bad, _valid_json()])
        register_stub(stub)
        draft = _run(generate_json(system="x", user="y", schema=FollowUpDraft, provider="__test_stub__"))
        assert draft.email_subject == VALID_DRAFT["email_subject"]
        assert stub.calls == 2


class TestFailures:
    def test_malformed_twice_raises(self, register_stub):
        stub = StubProvider(["nope", "still nope"])
        register_stub(stub)
        with pytest.raises(MalformedOutputError):
            _run(generate_json(system="x", user="y", schema=FollowUpDraft, provider="__test_stub__"))
        assert stub.calls == 2, "exactly one retry, no infinite loop"

    def test_schema_violation_twice_raises(self, register_stub):
        import json

        bad = json.dumps({"whatsapp_text": "x", "email_subject": "z", "email_body": "no"})
        stub = StubProvider([bad, bad])
        register_stub(stub)
        with pytest.raises(MalformedOutputError):
            _run(generate_json(system="x", user="y", schema=FollowUpDraft, provider="__test_stub__"))
        assert stub.calls == 2
