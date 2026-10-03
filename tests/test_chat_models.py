from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage

from memoryos_lite.chat_models import build_chat_openai, message_text
from memoryos_lite.config import Settings
from memoryos_lite.curator.llm import ChatCuratorLLM, CuratorSchemaError


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

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.calls: list[Any] = []
        _RecordingChatOpenAI.instances.append(self)

    def invoke(self, messages: Any) -> AIMessage:
        self.calls.append(messages)
        return _RecordingChatOpenAI.reply


@pytest.fixture
def fake_chat_openai(monkeypatch: pytest.MonkeyPatch) -> type[_RecordingChatOpenAI]:
    import langchain_openai

    _RecordingChatOpenAI.instances = []
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _RecordingChatOpenAI)
    return _RecordingChatOpenAI


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
