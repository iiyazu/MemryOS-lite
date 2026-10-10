from __future__ import annotations

from typing import Any

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage

from memoryos_lite.chat_models import build_chat_openai, message_text
from memoryos_lite.config import Settings
from memoryos_lite.curator.curate import CurateRequest
from memoryos_lite.curator.graph import run_curate
from memoryos_lite.curator.llm import (
    ChatCuratorLLM,
    CuratorLLMError,
    CuratorSchemaError,
    record_attempts,
)


def _opencode_settings(**overrides: Any) -> Settings:
    return Settings(
        memoryos_llm_provider="opencode",
        opencode_api_key="oc-test-key",
        deepseek_api_key=None,
        openai_api_key=None,
        **overrides,
    )


class _RecordingChatOpenAI:
    instances: list[_RecordingChatOpenAI] = []
    reply: AIMessage = AIMessage(content="{}")
    #: Raised (in order) before the reply is returned.
    errors: list[Exception] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.calls: list[Any] = []
        _RecordingChatOpenAI.instances.append(self)

    def invoke(self, messages: Any) -> AIMessage:
        self.calls.append(messages)
        if _RecordingChatOpenAI.errors:
            raise _RecordingChatOpenAI.errors.pop(0)
        return _RecordingChatOpenAI.reply


@pytest.fixture
def fake_chat_openai(monkeypatch: pytest.MonkeyPatch) -> type[_RecordingChatOpenAI]:
    import langchain_openai

    _RecordingChatOpenAI.instances = []
    _RecordingChatOpenAI.errors = []
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _RecordingChatOpenAI)
    return _RecordingChatOpenAI


_REQUEST = httpx.Request("POST", "https://provider.test/v1/responses")


def _status_error(status: int) -> openai.APIStatusError:
    return openai.APIStatusError(
        "provider said no", response=httpx.Response(status, request=_REQUEST), body=None
    )


def test_opencode_provider_resolves_go_endpoint_and_responses_wire() -> None:
    settings = _opencode_settings()

    assert settings.chat_api_key == "oc-test-key"
    assert settings.chat_api_key_name == "OPENCODE_API_KEY"
    assert settings.chat_base_url == "https://opencode.ai/zen/go/v1"
    assert settings.chat_model == "muse-spark-1.3-contributor"
    assert settings.chat_wire_api == "responses"


def test_non_opencode_providers_keep_chat_completions() -> None:
    settings = Settings(memoryos_llm_provider="deepseek", deepseek_api_key="sk-test")

    assert settings.chat_wire_api == "chat"
    assert settings.chat_api_key_name == "DEEPSEEK_API_KEY"


def test_unknown_provider_and_wire_api_are_rejected() -> None:
    with pytest.raises(ValueError, match="opencode"):
        _ = Settings(memoryos_llm_provider="anthropic").chat_model
    with pytest.raises(ValueError, match="OPENCODE_WIRE_API"):
        _ = _opencode_settings(opencode_wire_api="grpc").chat_wire_api


def test_build_chat_openai_uses_responses_api_and_json_mode(
    fake_chat_openai: type[_RecordingChatOpenAI],
) -> None:
    build_chat_openai(_opencode_settings(), json_mode=True)

    kwargs = fake_chat_openai.instances[-1].kwargs
    assert kwargs["model"] == "muse-spark-1.3-contributor"
    assert kwargs["base_url"] == "https://opencode.ai/zen/go/v1"
    assert kwargs["use_responses_api"] is True
    assert kwargs["model_kwargs"] == {"response_format": {"type": "json_object"}}
    assert kwargs["api_key"].get_secret_value() == "oc-test-key"


def test_opencode_requests_carry_a_session_id_and_own_user_agent(
    fake_chat_openai: type[_RecordingChatOpenAI],
) -> None:
    build_chat_openai(_opencode_settings(opencode_session_id="room-42"))
    pinned = fake_chat_openai.instances[-1].kwargs["default_headers"]
    build_chat_openai(_opencode_settings())
    build_chat_openai(_opencode_settings())
    generated = [
        i.kwargs["default_headers"]["x-opencode-session"] for i in fake_chat_openai.instances[-2:]
    ]

    assert pinned["x-opencode-session"] == "room-42"
    assert pinned["User-Agent"].startswith("memoryos-lite/")
    assert generated[0] != generated[1]


def test_deepseek_requests_carry_no_opencode_headers(
    fake_chat_openai: type[_RecordingChatOpenAI],
) -> None:
    build_chat_openai(Settings(memoryos_llm_provider="deepseek", deepseek_api_key="sk-test"))

    assert "default_headers" not in fake_chat_openai.instances[-1].kwargs


def test_build_chat_openai_chat_wire_omits_responses_flag(
    fake_chat_openai: type[_RecordingChatOpenAI],
) -> None:
    build_chat_openai(_opencode_settings(opencode_wire_api="chat", opencode_model="kimi-k3"))

    kwargs = fake_chat_openai.instances[-1].kwargs
    assert "use_responses_api" not in kwargs
    assert "model_kwargs" not in kwargs
    assert kwargs["model"] == "kimi-k3"


def test_build_chat_openai_requires_the_provider_key() -> None:
    settings = Settings(memoryos_llm_provider="opencode", opencode_api_key=None)

    with pytest.raises(ValueError, match="OPENCODE_API_KEY"):
        build_chat_openai(settings)


def test_message_text_joins_only_text_blocks_of_a_responses_reply() -> None:
    message = AIMessage(
        content=[
            {"type": "reasoning", "summary": [{"type": "summary_text", "text": "thinking"}]},
            {"type": "text", "text": '{"operations": ', "annotations": []},
            {"type": "text", "text": "[]}", "annotations": []},
        ]
    )

    assert message_text(message) == '{"operations": []}'
    assert message_text(AIMessage(content="plain")) == "plain"


def test_curator_llm_parses_a_responses_api_reply(
    fake_chat_openai: type[_RecordingChatOpenAI],
) -> None:
    fake_chat_openai.reply = AIMessage(
        content=[
            {"type": "reasoning", "summary": []},
            {"type": "text", "text": '{"operations": [{"op": "noop"}]}'},
        ],
        usage_metadata={"input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
    )
    llm = ChatCuratorLLM(_opencode_settings())

    assert llm.complete_json("system", "user") == {"operations": [{"op": "noop"}]}
    assert llm.last_usage == {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}


def test_curator_llm_rejects_a_reply_without_json(
    fake_chat_openai: type[_RecordingChatOpenAI],
) -> None:
    fake_chat_openai.reply = AIMessage(content=[{"type": "text", "text": "no json here"}])
    llm = ChatCuratorLLM(_opencode_settings())

    with pytest.raises(CuratorSchemaError):
        llm.complete_json("system", "user")


def _curator(**overrides: Any) -> ChatCuratorLLM:
    llm = ChatCuratorLLM(_opencode_settings(**overrides))
    llm._sleep = lambda _secs: None
    return llm


def test_curator_llm_owns_retries_and_its_own_timeout(
    fake_chat_openai: type[_RecordingChatOpenAI],
) -> None:
    _curator(memoryos_curate_timeout_s=90)

    kwargs = fake_chat_openai.instances[-1].kwargs
    assert (kwargs["max_retries"], kwargs["timeout"]) == (0, 90)


def test_curator_llm_does_not_retry_a_timeout(
    fake_chat_openai: type[_RecordingChatOpenAI],
) -> None:
    fake_chat_openai.errors = [openai.APITimeoutError(request=_REQUEST)]
    llm = _curator()

    with record_attempts() as attempts, pytest.raises(CuratorLLMError, match="APITimeoutError"):
        llm.complete_json("system", "user")
    assert [a.outcome for a in attempts] == ["timeout"]
    assert attempts[0].usage is None


def test_curator_llm_retries_dropped_connections_and_5xx_and_records_every_attempt(
    fake_chat_openai: type[_RecordingChatOpenAI],
) -> None:
    fake_chat_openai.errors = [openai.APIConnectionError(request=_REQUEST), _status_error(503)]
    fake_chat_openai.reply = AIMessage(
        content='{"ok": true}',
        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    )
    llm = _curator()

    with record_attempts() as attempts:
        assert llm.complete_json("system", "user") == {"ok": True}
    assert [a.outcome for a in attempts] == ["error", "error", "ok"]
    assert attempts[-1].usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}

    fake_chat_openai.errors = [_status_error(500)] * 3
    with record_attempts() as attempts, pytest.raises(CuratorLLMError):
        llm.complete_json("system", "user")
    assert len(attempts) == 3


def test_curator_llm_does_not_retry_a_client_error(
    fake_chat_openai: type[_RecordingChatOpenAI],
) -> None:
    fake_chat_openai.errors = [_status_error(401)]

    with record_attempts() as attempts, pytest.raises(CuratorLLMError):
        _curator().complete_json("system", "user")
    assert [a.outcome for a in attempts] == ["error"]


def test_collab_response_counts_usage_over_every_attempt(
    fake_chat_openai: type[_RecordingChatOpenAI],
) -> None:
    fake_chat_openai.errors = [openai.APIConnectionError(request=_REQUEST)]
    fake_chat_openai.reply = AIMessage(
        content='{"memories": []}',
        usage_metadata={"input_tokens": 800, "output_tokens": 6000, "total_tokens": 6800},
    )
    window = [{"id": "m1", "seq": 1, "type": "message", "kind": "message", "text": "ok"}]
    request = CurateRequest(scope_id="t1", profile="collab", window=window)

    diagnostics = run_curate(request, _curator()).model_dump()["diagnostics"]

    assert [a["outcome"] for a in diagnostics["attempts"]] == ["error", "ok"]
    assert diagnostics["attempts"][1]["completion_tokens"] == 6000
    assert diagnostics["usage"] == {
        "attempts": 2,
        "unmetered_attempts": 1,
        "prompt_tokens": 800,
        "completion_tokens": 6000,
        "total_tokens": 6800,
    }
    module = request.model_copy(update={"profile": "module"})
    assert "usage" not in run_curate(module, _curator()).model_dump()["diagnostics"]
