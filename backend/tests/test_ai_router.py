"""Unit tests for the AI model router — pure functions, no LLM."""

import os

import pytest

from services.ai.router import (
    HIGH_VALUE_THRESHOLD_INR,
    RouteSignals,
    Tier,
    pick_tier,
    route,
)


class TestPickTier:
    def test_default_no_signals(self):
        assert pick_tier(RouteSignals()) is Tier.SIMPLE

    def test_low_value(self):
        assert pick_tier(RouteSignals(value_inr=100_000)) is Tier.SIMPLE

    def test_value_below_threshold(self):
        assert pick_tier(RouteSignals(value_inr=HIGH_VALUE_THRESHOLD_INR - 1)) is Tier.SIMPLE

    def test_value_at_threshold_escalates(self):
        assert pick_tier(RouteSignals(value_inr=HIGH_VALUE_THRESHOLD_INR)) is Tier.COMPLEX

    def test_value_above_threshold_escalates(self):
        assert pick_tier(RouteSignals(value_inr=10_000_000)) is Tier.COMPLEX

    def test_previous_attempt_failed_escalates(self):
        assert pick_tier(RouteSignals(previous_attempt_failed=True)) is Tier.COMPLEX

    def test_override_simple_wins_over_high_value(self):
        assert pick_tier(RouteSignals(value_inr=10_000_000, override_tier=Tier.SIMPLE)) is Tier.SIMPLE

    def test_override_complex_wins_over_low_value(self):
        assert pick_tier(RouteSignals(value_inr=1000, override_tier=Tier.COMPLEX)) is Tier.COMPLEX


class TestRoute:
    def test_simple_default_claude_haiku(self):
        c = route(RouteSignals())
        assert c.tier is Tier.SIMPLE
        assert c.provider == "anthropic"
        assert "haiku" in c.model.lower()

    def test_complex_default_claude_haiku(self):
        c = route(RouteSignals(value_inr=10_000_000))
        assert c.tier is Tier.COMPLEX
        assert c.provider == "anthropic"
        assert "haiku" in c.model.lower()

    def test_ref_format(self):
        c = route(RouteSignals())
        assert c.ref == f"simple:{c.provider}/{c.model}"


class TestEnvOverride:
    def test_env_overrides_provider_and_model(self, monkeypatch):
        monkeypatch.setenv("AI_ROUTE_PROPOSAL_FOLLOWUP_SIMPLE_PROVIDER", "openai")
        monkeypatch.setenv("AI_ROUTE_PROPOSAL_FOLLOWUP_SIMPLE_MODEL", "gpt-4o-mini")
        c = route(RouteSignals())
        assert c.provider == "openai"
        assert c.model == "gpt-4o-mini"

    def test_env_override_partial_provider_only(self, monkeypatch):
        monkeypatch.setenv("AI_ROUTE_PROPOSAL_FOLLOWUP_SIMPLE_PROVIDER", "openai")
        # No model override — default model is kept (Day 4 default is Haiku 4.5)
        c = route(RouteSignals())
        assert c.provider == "openai"
        assert c.model == "claude-haiku-4-5-20251001"
