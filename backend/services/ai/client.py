"""
LLM provider abstraction.

A Provider exposes one method — generate_text — and the business logic only
talks to the registry, never to a specific vendor SDK. To add a provider:
implement the protocol, register it in PROVIDERS at the bottom of this file.

Active provider is chosen by:
  1. explicit `provider=` argument
  2. AI_PROVIDER env var
  3. DEFAULT_PROVIDER constant
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import uuid
from typing import Optional, Protocol, Type, TypeVar, runtime_checkable

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class MalformedOutputError(RuntimeError):
    """Raised when the model returns output that doesn't match the schema even after retry."""


class NoApiKeyError(RuntimeError):
    """Raised when the active provider has no API key configured."""


class LLMProviderUnavailable(RuntimeError):
    """Raised when the provider call fails after retries exhausted. Maps to
    HTTP 503 at the API layer + a calm 'AI busy, try again' message on the UI."""


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    default_model: str

    async def generate_text(
        self,
        *,
        system: str,
        user: str,
        model: Optional[str] = None,
        max_tokens: int = 1500,
        session_id: Optional[str] = None,
    ) -> str: ...


# ---------- Emergent gateway (default) ----------
class _EmergentProvider:
    """Routes Gemini and Anthropic calls through the Emergent Universal LLM key."""

    def __init__(self, vendor: str, default_model: str):
        self.name = f"emergent_{vendor}"
        self._vendor = vendor
        self.default_model = default_model

    def _api_key(self) -> str:
        key = os.environ.get("EMERGENT_LLM_KEY")
        if not key:
            raise NoApiKeyError("EMERGENT_LLM_KEY not set. Add an API key in settings.")
        return key

    async def generate_text(self, *, system, user, model=None, max_tokens=1500, session_id=None) -> str:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # lazy: keep import out of cold path

        chat = LlmChat(
            api_key=self._api_key(),
            session_id=session_id or f"revora-{uuid.uuid4()}",
            system_message=system,
        ).with_model(self._vendor, model or self.default_model)
        text = await chat.send_message(UserMessage(text=user))
        return (text or "").strip()


# ---------- Direct vendor providers (activate if SDK + key are present) ----------
class _GeminiDirectProvider:
    name = "gemini"
    default_model = "gemini-2.5-flash"

    async def generate_text(self, *, system, user, model=None, max_tokens=1500, session_id=None) -> str:
        try:
            import google.generativeai as genai  # type: ignore
        except ImportError as e:
            raise NoApiKeyError("google-generativeai not installed (pip install google-generativeai)") from e
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise NoApiKeyError("GEMINI_API_KEY not set.")
        genai.configure(api_key=key)
        m = genai.GenerativeModel(model or self.default_model, system_instruction=system)
        resp = await m.generate_content_async(
            user,
            generation_config={"max_output_tokens": max_tokens},
        )
        return (resp.text or "").strip()


class _OpenAIDirectProvider:
    name = "openai"
    default_model = "gpt-4o-mini"

    async def generate_text(self, *, system, user, model=None, max_tokens=1500, session_id=None) -> str:
        try:
            from openai import AsyncOpenAI  # type: ignore
        except ImportError as e:
            raise NoApiKeyError("openai not installed (pip install openai)") from e
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise NoApiKeyError("OPENAI_API_KEY not set.")
        client = AsyncOpenAI(api_key=key)
        resp = await client.chat.completions.create(
            model=model or self.default_model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()


class _AnthropicDirectProvider:
    name = "anthropic"
    default_model = "claude-haiku-4-5-20251001"

    async def generate_text(self, *, system, user, model=None, max_tokens=1500, session_id=None) -> str:
        try:
            from anthropic import AsyncAnthropic  # type: ignore
        except ImportError as e:
            raise NoApiKeyError("anthropic not installed (pip install anthropic)") from e
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise NoApiKeyError("ANTHROPIC_API_KEY not set.")
        client = AsyncAnthropic(api_key=key)
        resp = await client.messages.create(
            model=model or self.default_model,
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=max_tokens,
        )
        return (resp.content[0].text or "").strip()


# ---------- Registry ----------
PROVIDERS: dict[str, LLMProvider] = {
    "emergent_gemini": _EmergentProvider("gemini", "gemini-2.5-flash"),
    "emergent_anthropic": _EmergentProvider("anthropic", "claude-haiku-4-5-20251001"),
    "gemini": _GeminiDirectProvider(),
    "openai": _OpenAIDirectProvider(),
    "anthropic": _AnthropicDirectProvider(),
}

DEFAULT_PROVIDER = "emergent_gemini"


def get_provider(name: Optional[str] = None) -> LLMProvider:
    name = name or os.environ.get("AI_PROVIDER") or DEFAULT_PROVIDER
    if name not in PROVIDERS:
        raise ValueError(f"Unknown provider {name!r}. Registered: {list(PROVIDERS)}")
    return PROVIDERS[name]


# Retry config — read at call time so monkeypatched env in tests takes effect.
def _max_attempts() -> int:
    return int(os.environ.get("LLM_MAX_ATTEMPTS", "3"))


def _retry_base_seconds() -> float:
    return float(os.environ.get("LLM_RETRY_BASE_SECONDS", "0.5"))


def _retry_cap_seconds() -> float:
    return float(os.environ.get("LLM_RETRY_CAP_SECONDS", "8.0"))


def _retry_delay(attempt: int) -> float:
    """Exponential backoff with full jitter, capped. attempt is 1-indexed."""
    expo = min(_retry_cap_seconds(), _retry_base_seconds() * (2 ** (attempt - 1)))
    return random.uniform(0, expo)


async def _call_with_retry(p: LLMProvider, **kw) -> str:
    """Shared retry wrapper used by generate_text and generate_json.

    Retries any provider error EXCEPT NoApiKeyError (permanent). After
    _max_attempts() the underlying exception is converted to
    LLMProviderUnavailable so the server can return a 503 with a calm
    'AI busy' message instead of leaking the transport error.
    """
    max_attempts = _max_attempts()
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await p.generate_text(**kw)
        except NoApiKeyError:
            raise
        except Exception as e:
            last_exc = e
            if attempt == max_attempts:
                break
            delay = _retry_delay(attempt)
            logger.warning(
                "LLM call failed (attempt %d/%d), retrying in %.2fs: %s",
                attempt, max_attempts, delay, type(e).__name__,
            )
            await asyncio.sleep(delay)
    raise LLMProviderUnavailable(
        f"Provider {p.name} failed {max_attempts} attempts. "
        f"Last error: {type(last_exc).__name__}: {last_exc}"
    )


async def generate_text(
    *,
    system: str,
    user: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 1500,
    session_id: Optional[str] = None,
) -> str:
    """Top-level text generation with exponential-backoff retry."""
    return await _call_with_retry(
        get_provider(provider),
        system=system, user=user, model=model,
        max_tokens=max_tokens, session_id=session_id,
    )


# ---------- Structured JSON output with validation + 1 retry ----------
_FENCE_RE = re.compile(r"^```(?:json)?\s*([\s\S]+?)\s*```$", re.MULTILINE)
_BRACE_RE = re.compile(r"\{[\s\S]*\}")


def _extract_json(text: str) -> str:
    """Strip ```json``` fences and prose; return the first JSON object found."""
    s = (text or "").strip()
    m = _FENCE_RE.search(s)
    if m:
        s = m.group(1).strip()
    if s.startswith("{") and s.endswith("}"):
        return s
    m = _BRACE_RE.search(s)
    if m:
        return m.group(0)
    return s  # let json.loads fail with a clear error


async def generate_json(
    *,
    system: str,
    user: str,
    schema: Type[T],
    provider: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 1500,
    session_id: Optional[str] = None,
) -> T:
    """
    Ask the model for a JSON object that validates against `schema`. One
    corrective retry on malformed output, then raise MalformedOutputError.
    Provider-agnostic — works without JSON-mode SDK support.
    """
    p = get_provider(provider)
    last_err: Optional[Exception] = None
    last_raw: str = ""

    for attempt in (1, 2):
        sys_msg = system
        if attempt == 2:
            sys_msg = system + (
                "\n\nIMPORTANT: your previous response was not valid JSON for the schema. "
                "Return ONLY a single JSON object with the required fields, "
                "no prose, no code fences, no commentary."
            )
        # Use the retry wrapper so transport failures don't kill a JSON
        # call after a single network blip. NoApiKeyError still propagates;
        # LLMProviderUnavailable also propagates (no point trying again).
        raw = await _call_with_retry(
            p,
            system=sys_msg,
            user=user,
            model=model,
            max_tokens=max_tokens,
            session_id=session_id,
        )
        last_raw = raw
        try:
            obj = json.loads(_extract_json(raw))
            return schema.model_validate(obj)
        except (json.JSONDecodeError, ValidationError) as e:
            last_err = e
            logger.warning(
                "structured-output attempt %d failed (%s): %s", attempt, type(e).__name__, str(e)[:200]
            )

    raise MalformedOutputError(
        f"Model returned invalid output after retry. Last error: {last_err!r}. "
        f"Raw (truncated): {last_raw[:400]!r}"
    )
