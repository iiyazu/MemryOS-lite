from __future__ import annotations

from types import SimpleNamespace

import pytest

from xmuse_core.gates.review_gate import CodexReviewGate, DiffResult, LLMReviewGate


@pytest.mark.asyncio
async def test_review_gate_without_diff_auto_approves(tmp_path, monkeypatch):
    gate = LLMReviewGate()
    monkeypatch.setattr(
        gate,
        "_get_diff",
        lambda worktree, base_ref: DiffResult(text=""),
    )

    verdict = await gate.review(
        feature_id="lane",
        worktree=tmp_path,
        original_prompt="do work",
    )

    assert verdict.approved is True
    assert verdict.summary == "no changes"


@pytest.mark.asyncio
async def test_review_gate_rejects_when_diff_collection_fails(tmp_path, monkeypatch):
    gate = LLMReviewGate()
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


@pytest.mark.asyncio
async def test_review_gate_passes_gate_context_and_detects_self_modification(
    tmp_path,
    monkeypatch,
):
    calls = []

    def fake_run(cmd, *, input, capture_output, text, cwd, timeout):
        calls.append(input)
        stdout = (
            '{"approved": false, "concerns": ["unsafe"], '
            '"summary": "reject", "confidence": 0.8}'
        )
        return SimpleNamespace(
            returncode=0,
            stdout=stdout,
            stderr="",
        )

    gate = LLMReviewGate()
    monkeypatch.setattr(
        gate,
        "_get_diff",
        lambda worktree, base_ref: DiffResult(
            text="diff --git a/src/xmuse_core/agents/foo.py b/src/xmuse_core/agents/foo.py"
        ),
    )
    monkeypatch.setattr("subprocess.run", fake_run)

    verdict = await gate.review(
        feature_id="lane",
        worktree=tmp_path,
        original_prompt="do work",
        gate_context='{"passed": true, "profile_ids": ["xmuse"]}',
    )

    prompt = calls[0]
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


@pytest.mark.asyncio
async def test_codex_review_gate_invokes_codex_exec_with_prompt_on_stdin(
    tmp_path,
    monkeypatch,
):
    calls = []

    def fake_run(cmd, *, input, capture_output, text, cwd, timeout):
        calls.append(
            {
                "cmd": cmd,
                "input": input,
                "capture_output": capture_output,
                "text": text,
                "cwd": cwd,
                "timeout": timeout,
            }
        )
        return SimpleNamespace(
            returncode=0,
            stdout='{"approved": true, "concerns": [], "summary": "ok", "confidence": 0.91}',
            stderr="",
        )

    gate = CodexReviewGate(model="gpt-5.5", timeout_s=12.0)
    monkeypatch.setattr(
        gate,
        "_get_diff",
        lambda worktree, base_ref: DiffResult(text="diff --git a/app.py b/app.py"),
    )
    monkeypatch.setattr("subprocess.run", fake_run)

    verdict = await gate.review(
        feature_id="lane",
        worktree=tmp_path,
        original_prompt="do work",
        base_ref="abc123",
        gate_context='{"passed": true}',
    )

    assert verdict.approved is True
    assert verdict.confidence == 0.91
    assert calls == [
        {
            "cmd": [
                "codex",
                "exec",
                "-m",
                "gpt-5.5",
                "--dangerously-bypass-approvals-and-sandbox",
                "-C",
                str(tmp_path),
            ],
            "input": calls[0]["input"],
            "capture_output": True,
            "text": True,
            "cwd": tmp_path,
            "timeout": 12.0,
        }
    ]
    assert "## Lane: lane" in calls[0]["input"]
    assert "## Quality Gate Context" in calls[0]["input"]
    assert "diff --git a/app.py b/app.py" in calls[0]["input"]


@pytest.mark.asyncio
async def test_codex_review_gate_raises_when_codex_process_fails(
    tmp_path,
    monkeypatch,
):
    def fake_run(cmd, *, input, capture_output, text, cwd, timeout):
        return SimpleNamespace(returncode=2, stdout="", stderr="bad codex")

    gate = CodexReviewGate()
    monkeypatch.setattr(
        gate,
        "_get_diff",
        lambda worktree, base_ref: DiffResult(text="diff --git a/app.py b/app.py"),
    )
    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(RuntimeError, match="codex_review_failed: bad codex"):
        await gate.review(
            feature_id="lane",
            worktree=tmp_path,
            original_prompt="do work",
        )
