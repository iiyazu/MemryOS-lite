"""Injectable structured-JSON LLM client for the curator.

The curator never depends on a live provider in tests or CI: callers pass a
:class:`CuratorLLM` fake.  The production client is built the same way the
repository builds other chat models (``chat_api_key``/``chat_model``/base URL
from settings, ``memoryos_llm_timeout_s``) and requests JSON output mode.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Protocol

from memoryos_lite.chat_models import build_chat_openai, message_text

if TYPE_CHECKING:
    from memoryos_lite.config import Settings


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
        self._model = build_chat_openai(settings, json_mode=True)

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        try:
            result = self._model.invoke(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ]
            )
        except Exception as exc:
            # Deliberately avoid provider error text: it can echo request
            # metadata, and nothing here needs more than the failure class.
            raise CuratorLLMError(f"provider call failed: {type(exc).__name__}") from exc
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
