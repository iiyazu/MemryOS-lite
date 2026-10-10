"""Injectable structured-JSON LLM client for the curator.

The curator never depends on a live provider in tests or CI: callers pass a
:class:`CuratorLLM` fake.  The production client is built the same way the
repository builds other chat models (``chat_api_key``/``chat_model``/base URL
from settings, ``memoryos_curate_timeout_s``) and requests JSON output mode.

The production client retries itself instead of leaving it to the SDK, so
that every provider attempt is visible: each one is logged and appended to
the list opened by :func:`record_attempts`. A timed-out attempt is not
retried (the model would most likely run out of time again, and the
abandoned generation may still be billed); a connection error, 429 or 5xx is
retried up to :data:`RETRIES` times.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol

from memoryos_lite.chat_models import build_chat_openai, message_text
from memoryos_lite.observability import log_event

if TYPE_CHECKING:
    from memoryos_lite.config import Settings

logger = logging.getLogger(__name__)

#: Retries after a connection error, 429 or 5xx; never after a timeout.
RETRIES = 2
RETRY_BACKOFF_S = (1.0, 2.0)


@dataclass(frozen=True)
class LLMAttempt:
    """One provider attempt: ``usage`` is ``None`` when the provider reported none."""

    outcome: Literal["ok", "timeout", "error"]
    secs: float
    usage: dict[str, int | None] | None = None


_ATTEMPTS: ContextVar[list[LLMAttempt] | None] = ContextVar("curator_attempts", default=None)


@contextmanager
def record_attempts() -> Iterator[list[LLMAttempt]]:
    """Collect the provider attempts made inside the block (per request, thread-safe)."""

    attempts: list[LLMAttempt] = []
    token = _ATTEMPTS.set(attempts)
    try:
        yield attempts
    finally:
        _ATTEMPTS.reset(token)


class CuratorLLMError(RuntimeError):
    """The provider call itself failed (transport, auth, provider error)."""


class CuratorSchemaError(RuntimeError):
    """The provider response was not a usable JSON object."""


class CuratorLLM(Protocol):
    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        """Return one JSON object for the given system/user prompt pair."""
        ...


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse the first JSON object in ``text``, tolerating fences and prose."""

    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            value, _end = decoder.raw_decode(text[start:])
        except ValueError:
            start = text.find("{", start + 1)
            continue
        if isinstance(value, dict):
            return value
        start = text.find("{", start + 1)
    raise CuratorSchemaError("curator response did not contain a JSON object")


def _usage_from_result(result: object) -> dict[str, int | None] | None:
    """Normalize provider token usage from a LangChain response, if present."""

    payload: dict[str, object] | None = None
    usage_metadata = getattr(result, "usage_metadata", None)
    if isinstance(usage_metadata, dict):
        payload = usage_metadata
    else:
        response_metadata = getattr(result, "response_metadata", None)
        if isinstance(response_metadata, dict):
            token_usage = response_metadata.get("token_usage")
            if isinstance(token_usage, dict):
                payload = token_usage
    if payload is None:
        return None

    def as_int(*keys: str) -> int | None:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
        return None

    usage = {
        "prompt_tokens": as_int("input_tokens", "prompt_tokens"),
        "completion_tokens": as_int("output_tokens", "completion_tokens"),
        "total_tokens": as_int("total_tokens"),
    }
    if all(value is None for value in usage.values()):
        return None
    return usage


def _classify(exc: Exception) -> tuple[Literal["timeout", "error"], bool]:
    """``(outcome, retryable)``: retry dropped connections, 429 and 5xx, never a timeout."""

    import openai

    if isinstance(exc, openai.APITimeoutError):
        return "timeout", False
    if isinstance(exc, openai.APIConnectionError):
        return "error", True
    if isinstance(exc, openai.APIStatusError):
        return "error", exc.status_code == 429 or exc.status_code >= 500
    return "error", False


def _attempt(
    index: int,
    outcome: Literal["ok", "timeout", "error"],
    started: float,
    usage: dict[str, int | None] | None,
    error: str | None = None,
) -> None:
    attempt = LLMAttempt(outcome, round(time.perf_counter() - started, 3), usage)
    sink = _ATTEMPTS.get()
    if sink is not None:
        sink.append(attempt)
    log_event(
        logger,
        logging.INFO if outcome == "ok" else logging.WARNING,
        "curator_llm_attempt",
        extra=usage,
        attempt=index + 1,
        outcome=outcome,
        secs=attempt.secs,
        error=error,
    )


class ChatCuratorLLM:
    """ChatOpenAI-backed curator client with JSON output mode.

    Works over Chat Completions or the Responses API, whichever the configured
    provider serves.  The API key is held by the LangChain client only; it is
    never logged, traced, or returned by ``complete_json`` errors.  After each
    provider call, ``last_usage`` holds the normalized token usage
    (``prompt_tokens``/``completion_tokens``/``total_tokens``, any of which
    may be ``None``) or ``None`` when the provider reported none.
    """

    def __init__(self, settings: Settings) -> None:
        self.last_usage: dict[str, int | None] | None = None
        if not settings.chat_api_key:
            raise ValueError(f"{settings.chat_api_key_name} is required for the curator")
        self._model = build_chat_openai(
            settings, json_mode=True, max_retries=0, timeout_s=settings.memoryos_curate_timeout_s
        )
        self._sleep = time.sleep

    def _invoke(self, system: str, user: str) -> object:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for attempt in range(RETRIES + 1):
            started = time.perf_counter()
            try:
                result = self._model.invoke(messages)
            except Exception as exc:
                outcome, retryable = _classify(exc)
                _attempt(attempt, outcome, started, None, error=type(exc).__name__)
                if retryable and attempt < RETRIES:
                    self._sleep(RETRY_BACKOFF_S[attempt])
                    continue
                # Deliberately avoid provider error text: it can echo request
                # metadata, and nothing here needs more than the failure class.
                raise CuratorLLMError(f"provider call failed: {type(exc).__name__}") from exc
            _attempt(attempt, "ok", started, _usage_from_result(result))
            return result
        raise AssertionError("unreachable")  # pragma: no cover

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        result = self._invoke(system, user)
        self.last_usage = _usage_from_result(result)
        try:
            content = message_text(result)
        except TypeError as exc:
            raise CuratorSchemaError("curator response content was not text") from exc
        return extract_json_object(content)


def build_curator_llm(settings: Settings) -> CuratorLLM | None:
    """Build the production client, or ``None`` when no API key is configured."""

    if not settings.chat_api_key:
        return None
    return ChatCuratorLLM(settings)
