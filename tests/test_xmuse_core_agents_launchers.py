from __future__ import annotations

from pathlib import Path

from xmuse_core.agents.launchers.codex import CodexLauncher
from xmuse_core.agents.launchers.claude_code import ClaudeCodeLauncher
from xmuse_core.agents.protocol import StdoutMessage


def test_codex_build_command():
    launcher = CodexLauncher()
    cmd = launcher.build_command("my-feature", Path("/tmp/worktree"))
    assert cmd == ["codex", "--cwd", "/tmp/worktree", "--quiet"]


def test_claude_code_build_command():
    launcher = ClaudeCodeLauncher()
    cmd = launcher.build_command("my-feature", Path("/tmp/worktree"))
    assert cmd == ["claude", "--cwd", "/tmp/worktree", "--output-format", "json"]


def test_codex_format_prompt_with_context():
    launcher = CodexLauncher()
    result = launcher.format_prompt("do the thing", "some context")
    assert "some context" in result
    assert "do the thing" in result


def test_codex_format_prompt_without_context():
    launcher = CodexLauncher()
    result = launcher.format_prompt("do the thing", "")
    assert result == "do the thing"


def test_claude_code_format_prompt_with_context():
    launcher = ClaudeCodeLauncher()
    result = launcher.format_prompt("do the thing", "some context")
    assert "## Context" in result
    assert "## Task" in result


def test_codex_build_env():
    launcher = CodexLauncher()
    env = launcher.build_env("archive-rag")
    assert env["XMUSE_FEATURE_ID"] == "archive-rag"


def test_claude_code_build_env():
    launcher = ClaudeCodeLauncher()
    env = launcher.build_env("archive-rag")
    assert env["XMUSE_FEATURE_ID"] == "archive-rag"


def test_codex_parse_output_result():
    launcher = CodexLauncher()
    msg = StdoutMessage(type="result", status="success", artifacts={"key": "val"})
    output = launcher.parse_output(msg)
    assert output is not None
    assert output.status == "success"


def test_codex_parse_output_progress_returns_none():
    launcher = CodexLauncher()
    msg = StdoutMessage(type="progress", stage="running")
    assert launcher.parse_output(msg) is None
