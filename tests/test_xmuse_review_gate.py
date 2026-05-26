from __future__ import annotations

from types import SimpleNamespace

import pytest

from xmuse_core.gates.review_gate import DiffResult, LLMReviewGate


class FakeLLM:
    def __init__(self, content: str) -> None:
        self.content = content
        self.messages: list[object] = []

    def invoke(self, messages: list[object]) -> SimpleNamespace:
        self.messages = messages
        return SimpleNamespace(content=self.content)


@pytest.mark.asyncio
async def test_review_gate_without_llm_auto_approves(tmp_path):
    verdict = await LLMReviewGate().review(
        feature_id="lane",
        worktree=tmp_path,
        original_prompt="do work",
    )

    assert verdict.approved is True
    assert verdict.summary == "no LLM configured, auto-approve"


@pytest.mark.asyncio
async def test_review_gate_rejects_when_diff_collection_fails(tmp_path, monkeypatch):
    gate = LLMReviewGate(api_key="test")
    fake_llm = FakeLLM('{"approved": true, "concerns": [], "summary": "ok"}')
    gate._llm = fake_llm
    monkeypatch.setattr(
        gate,
        "_get_diff",
        lambda worktree, base_ref: DiffResult(text="", error="diff_failed: bad ref"),
    )

    verdict = await gate.review(
        feature_id="lane",
        worktree=tmp_path,
        original_prompt="do work",
    )

    assert verdict.approved is False
    assert verdict.concerns == ["diff_failed: bad ref"]
    assert fake_llm.messages == []


@pytest.mark.asyncio
async def test_review_gate_passes_gate_context_and_detects_self_modification(
    tmp_path,
    monkeypatch,
):
    gate = LLMReviewGate(api_key="test")
    fake_llm = FakeLLM(
        '{"approved": false, "concerns": ["unsafe"], "summary": "reject", "confidence": 0.8}'
    )
    gate._llm = fake_llm
    monkeypatch.setattr(
        gate,
        "_get_diff",
        lambda worktree, base_ref: DiffResult(
            text="diff --git a/src/xmuse_core/agents/foo.py b/src/xmuse_core/agents/foo.py"
        ),
    )

    verdict = await gate.review(
        feature_id="lane",
        worktree=tmp_path,
        original_prompt="do work",
        gate_context='{"passed": true, "profile_ids": ["xmuse"]}',
    )

    prompt = fake_llm.messages[0]["content"]
    assert verdict.approved is False
    assert verdict.self_modification is True
    assert "Quality Gate Context" in prompt
    assert '"profile_ids": ["xmuse"]' in prompt
    assert "自修改审查" in prompt


def test_review_gate_parses_fenced_json_rejection():
    gate = LLMReviewGate()

    verdict = gate._parse_verdict(
        '```json\n{"approved": false, "concerns": ["bug"], "summary": "bad"}\n```'
    )

    assert verdict.approved is False
    assert verdict.concerns == ["bug"]
    assert verdict.summary == "bad"


def test_review_gate_parse_failure_rejects():
    verdict = LLMReviewGate()._parse_verdict("not json")

    assert verdict.approved is False
    assert verdict.concerns == ["review_parse_failed"]
    assert verdict.confidence == 0.0


def test_review_gate_rejects_invalid_json_schema():
    verdict = LLMReviewGate()._parse_verdict(
        '{"approved": "false", "concerns": "bug", "summary": "bad"}'
    )

    assert verdict.approved is False
    assert verdict.concerns == ["review_schema_invalid"]
