"""Shared construction of the remote chat model used by the curator and RoomMem.

Providers differ in wire API: DeepSeek and OpenAI-compatible endpoints speak
Chat Completions, while OpenCode Go serves some models (Muse Spark) only on
the Responses API.  Callers build the model here and read replies with
:func:`message_text`, so they never depend on the wire format.  The API key
stays inside the LangChain client; it is never logged or returned.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

    from memoryos_lite.config import Settings


def build_chat_openai(settings: Settings, *, json_mode: bool = False) -> ChatOpenAI:
    """Build the configured provider's chat model at temperature 0.

    ``json_mode`` requests a JSON object reply; LangChain maps it to
    ``response_format`` (Chat Completions) or ``text.format`` (Responses).
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
    if json_mode:
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
    return ChatOpenAI(
        model=settings.chat_model,
        api_key=SecretStr(api_key),
        temperature=0,
        timeout=settings.memoryos_llm_timeout_s,
        **kwargs,
    )


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
