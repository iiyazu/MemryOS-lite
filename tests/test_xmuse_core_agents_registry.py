from __future__ import annotations

import json
from pathlib import Path

import pytest

from xmuse_core.agents.registry import (
    AgentDescriptor,
    AgentRegistry,
    AgentRuntime,
    SessionConfig,
)


def _write_config(tmp: Path, agents: list[dict]) -> Path:
    p = tmp / "agents.json"
    p.write_text(json.dumps({"agents": agents}))
    return p


def test_load_from_json(tmp_path):
    cfg = _write_config(tmp_path, [
        {"runtime": "codex", "name": "w1", "capabilities": ["code"],
         "session_config": {"transport": "local"}},
    ])
    reg = AgentRegistry.from_file(cfg)
    assert len(reg.agents) == 1
    assert reg.agents[0].runtime == AgentRuntime.CODEX


def test_select_by_capability(tmp_path):
    cfg = _write_config(tmp_path, [
        {"runtime": "codex", "name": "w1", "capabilities": ["code", "test"],
         "session_config": {"transport": "local"}},
        {"runtime": "claude_code", "name": "r1", "capabilities": ["code", "review"],
         "session_config": {"transport": "local"}},
    ])
    reg = AgentRegistry.from_file(cfg)
    assert reg.select(["review"]).name == "r1"


def test_select_excludes_runtime(tmp_path):
    cfg = _write_config(tmp_path, [
        {"runtime": "codex", "name": "w1", "capabilities": ["code", "review"],
         "session_config": {"transport": "local"}},
        {"runtime": "claude_code", "name": "r1", "capabilities": ["code", "review"],
         "session_config": {"transport": "local"}},
    ])
    reg = AgentRegistry.from_file(cfg)
    agent = reg.select(["review"], exclude_runtime=AgentRuntime.CODEX)
    assert agent.runtime == AgentRuntime.CLAUDE_CODE


def test_select_no_match_raises(tmp_path):
    cfg = _write_config(tmp_path, [
        {"runtime": "codex", "name": "w1", "capabilities": ["code"],
         "session_config": {"transport": "local"}},
    ])
    reg = AgentRegistry.from_file(cfg)
    with pytest.raises(ValueError, match="no agent"):
        reg.select(["review"])


def test_select_round_robin(tmp_path):
    cfg = _write_config(tmp_path, [
        {"runtime": "codex", "name": "w1", "capabilities": ["code"],
         "session_config": {"transport": "local"}},
        {"runtime": "codex", "name": "w2", "capabilities": ["code"],
         "session_config": {"transport": "local"}},
    ])
    reg = AgentRegistry.from_file(cfg)
    first = reg.select(["code"])
    second = reg.select(["code"])
    assert first.name != second.name


def test_session_config_defaults(tmp_path):
    cfg = _write_config(tmp_path, [
        {"runtime": "codex", "name": "w1", "capabilities": ["code"],
         "session_config": {}},
    ])
    reg = AgentRegistry.from_file(cfg)
    sc = reg.agents[0].session_config
    assert sc.transport == "local"
    assert sc.heartbeat_interval_s == 30
    assert sc.heartbeat_timeout_s == 300
