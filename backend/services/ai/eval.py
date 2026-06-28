"""
Thin eval harness for prompt versions and providers.

Usage (from backend/):
    python -m services.ai.eval                                          # all fixtures, active prompt, router-picked model
    python -m services.ai.eval --prompts proposal_followup@v1 proposal_followup@v2
    python -m services.ai.eval --providers emergent_gemini emergent_anthropic
    python -m services.ai.eval --dry-run                                # render prompts, no LLM call

Prints a markdown table — paste into Slack/Notion, diff across runs.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import time
from dataclasses import dataclass
from typing import Optional

from . import generate_proposal_followup, redact as redact_mod
from .client import MalformedOutputError, NoApiKeyError
from .fixtures import FIXTURES, ProposalFixture
from .guardrail import GuardrailViolation, check_followup_draft
from .prompts import ACTIVE, ALL, PromptTemplate
from .router import RouteSignals, route
from .schemas import FollowUpDraft


@dataclass
class RunRecord:
    fixture_id: str
    prompt_ref: str
    route_ref: str
    ok: bool
    guardrail_ok: bool
    latency_ms: int
    wa_words: int
    email_words: int
    error: Optional[str] = None


def _words(s: str) -> int:
    return len(re.findall(r"\S+", s or ""))


async def _run_one(
    fix: ProposalFixture, template: PromptTemplate, provider: Optional[str],
    dry_run: bool,
) -> RunRecord:
    choice = route(RouteSignals(task="proposal_followup", value_inr=fix.value_inr))
    route_ref = choice.ref if not provider else f"manual:{provider}/{choice.model}"

    if dry_run:
        # Show what we'd send (after redaction) without calling the LLM.
        from . import _build_context
        ctx = _build_context(
            sender_name=fix.sender_name, recipient_contact=fix.recipient_contact,
            recipient_company=fix.recipient_company, industry=fix.industry,
            title=fix.title, value_inr=fix.value_inr, days_silent=fix.days_silent,
        )
        redacted, _ = redact_mod.redact(ctx)
        system, user = template.render(context=redacted)
        print(f"\n--- DRY RUN: {fix.id} / {template.ref} ---")
        print("[system]\n" + system)
        print("[user]\n" + user)
        return RunRecord(fix.id, template.ref, route_ref, ok=True, guardrail_ok=True,
                         latency_ms=0, wa_words=0, email_words=0)

    t0 = time.perf_counter()
    try:
        result = await generate_proposal_followup(
            sender_name=fix.sender_name, recipient_contact=fix.recipient_contact,
            recipient_company=fix.recipient_company, industry=fix.industry,
            title=fix.title, value_inr=fix.value_inr, days_silent=fix.days_silent,
            provider=provider, prompt_ref=template.ref,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return RunRecord(
            fixture_id=fix.id, prompt_ref=template.ref, route_ref=result.get("route_ref", route_ref),
            ok=True, guardrail_ok=True, latency_ms=latency_ms,
            wa_words=_words(result["whatsapp_text"]),
            email_words=_words(result["email_body"]),
        )
    except GuardrailViolation as e:
        return RunRecord(fix.id, template.ref, route_ref, ok=True, guardrail_ok=False,
                         latency_ms=int((time.perf_counter() - t0) * 1000),
                         wa_words=0, email_words=0, error=f"guardrail: {e}")
    except (MalformedOutputError, NoApiKeyError) as e:
        return RunRecord(fix.id, template.ref, route_ref, ok=False, guardrail_ok=False,
                         latency_ms=int((time.perf_counter() - t0) * 1000),
                         wa_words=0, email_words=0, error=f"{type(e).__name__}: {e}")
    except Exception as e:  # surface unexpected provider errors
        return RunRecord(fix.id, template.ref, route_ref, ok=False, guardrail_ok=False,
                         latency_ms=int((time.perf_counter() - t0) * 1000),
                         wa_words=0, email_words=0, error=f"{type(e).__name__}: {e}")


def _print_table(rows: list[RunRecord]) -> None:
    header = "| Fixture | Prompt | Route | OK | Guard | Lat(ms) | WA words | Email words | Error |"
    sep    = "| ------- | ------ | ----- | -- | ----- | ------- | -------- | ----------- | ----- |"
    print(header); print(sep)
    for r in rows:
        ok = "yes" if r.ok else "no"
        gd = "yes" if r.guardrail_ok else "no"
        err = (r.error or "")[:80].replace("|", "\\|")
        print(f"| {r.fixture_id} | {r.prompt_ref} | {r.route_ref} | {ok} | {gd} | "
              f"{r.latency_ms} | {r.wa_words} | {r.email_words} | {err} |")


async def main() -> int:
    p = argparse.ArgumentParser(description="Eval harness for AI follow-up drafts.")
    p.add_argument("--prompts", nargs="+", default=[ACTIVE["proposal_followup"].ref],
                   help="Prompt refs (e.g. proposal_followup@v1). Default: active.")
    p.add_argument("--providers", nargs="+", default=[None],
                   help="Provider names to test; 'None' means router decides. Default: router.")
    p.add_argument("--fixtures", nargs="+", default=[f.id for f in FIXTURES],
                   help="Fixture ids. Default: all.")
    p.add_argument("--dry-run", action="store_true", help="Render prompts, don't call the model.")
    args = p.parse_args()

    fixes = [f for f in FIXTURES if f.id in args.fixtures]
    if not fixes:
        print("No matching fixtures."); return 2
    for pref in args.prompts:
        if pref not in ALL:
            print(f"Unknown prompt ref: {pref}. Available: {list(ALL)}"); return 2

    rows: list[RunRecord] = []
    for pref in args.prompts:
        template = ALL[pref]
        for prov in args.providers:
            prov_arg = None if (prov in (None, "None", "router")) else prov
            for fx in fixes:
                rows.append(await _run_one(fx, template, prov_arg, args.dry_run))

    if not args.dry_run:
        _print_table(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
