"""Shared construction of the remote chat model used by the curator and RoomMem.

Providers differ in wire API: DeepSeek and OpenAI-compatible endpoints speak
Chat Completions, while OpenCode Go serves some models (Muse Spark) only on
the Responses API.  Callers build the model here and read replies with
:func:`message_text`, so they never depend on the wire format.  The API key
stays inside the LangChain client; it is never logged or returned.
"""

from __future__ import annotations

import importlib.metadata
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

    from memoryos_lite.config import Settings

MAX_RETRIES = 5


def build_chat_openai(
    settings: Settings,
    *,
    json_mode: bool = False,
    max_retries: int = MAX_RETRIES,
    timeout_s: float | None = None,
) -> ChatOpenAI:
    """Build the configured provider's chat model at temperature 0.

    ``json_mode`` requests a JSON object reply; LangChain maps it to
    ``response_format`` (Chat Completions) or ``text.format`` (Responses).
    The SDK retries silently (timeouts included), so a caller that accounts
    for every attempt passes ``max_retries=0`` and retries itself.
    """

    from langchain_openai import ChatOpenAI
    from pydantic import SecretStr

    api_key = settings.chat_api_key
    if not api_key:
        raise ValueError(f"{settings.chat_api_key_name} is required")
    kwargs: dict[str, Any] = {}
    if settings.chat_base_url:
        kwargs["base_url"] = settings.chat_base_url
    if settings.chat_wire_api == "responses":
        kwargs["use_responses_api"] = True
    if settings.resolved_llm_provider == "opencode":
        kwargs["default_headers"] = opencode_headers(settings)
    if json_mode:
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
    return ChatOpenAI(
        model=settings.chat_model,
        api_key=SecretStr(api_key),
        temperature=0,
        timeout=settings.memoryos_llm_timeout_s if timeout_s is None else timeout_s,
        # Transient TLS/connection drops were seen on long eval runs.
        max_retries=max_retries,
        **kwargs,
    )


def opencode_headers(settings: Settings) -> dict[str, str]:
    """Client identification OpenCode Go requires from third-party clients.

    Go rejects requests without ``x-opencode-session`` (``MissingSessionID``)
    and asks clients to send their own user agent instead of an SDK default
    (https://opencode.ai/docs/go/#where-can-i-use-it).  The session id is
    ``OPENCODE_SESSION_ID`` when set, otherwise one id per built client.
    """

    try:
        version = importlib.metadata.version("memoryos-lite")
    except importlib.metadata.PackageNotFoundError:
        version = "dev"
    session = settings.opencode_session_id or f"memoryos-{uuid.uuid4()}"
    return {"User-Agent": f"memoryos-lite/{version}", "x-opencode-session": session}


def message_text(message: object) -> str:
    """Return the reply text of a chat or Responses API message.

    Responses API replies carry a list of content blocks (reasoning, text);
    only the text blocks are joined.
    """

    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") in {"text", "output_text"}:
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    raise TypeError("chat response content was not text")
