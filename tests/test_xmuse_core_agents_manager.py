from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from xmuse_core.agents.manager import ActiveSession, SessionManager, SessionState
from xmuse_core.agents.registry import AgentDescriptor, AgentRuntime, SessionConfig
from xmuse_core.agents.session import LocalSession

HELLO_ACK_AGENT = """\
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        d = json.loads(line)
    except json.JSONDecodeError:
        continue
    if d.get("type") == "hello":
        print(json.dumps({"type": "hello_ack", "protocol_version": "1.0", "runtime": "mock"}), flush=True)
    elif d.get("type") == "task":
        print(json.dumps({"type": "result", "status": "success", "artifacts": {"done": True}}), flush=True)
    elif d.get("type") == "ping":
        print(json.dumps({"type": "pong"}), flush=True)
    elif d.get("type") == "abort":
        break
"""

BAD_VERSION_AGENT = """\
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    d = json.loads(line)
    if d.get("type") == "hello":
        print(json.dumps({"type": "hello_ack", "protocol_version": "99.0", "runtime": "mock"}), flush=True)
    elif d.get("type") == "abort":
        break
"""


class MockLauncher:
    def build_command(self, feature_id, worktree):
        return [sys.executable, "-c", HELLO_ACK_AGENT]

    def format_prompt(self, task, context):
        return task

    def build_env(self, feature_id):
        return None

    def parse_output(self, msg):
        return None


class BadVersionLauncher:
    def build_command(self, feature_id, worktree):
        return [sys.executable, "-c", BAD_VERSION_AGENT]

    def format_prompt(self, task, context):
        return task

    def build_env(self, feature_id):
        return None

    def parse_output(self, msg):
        return None


def _make_agent(runtime=AgentRuntime.CODEX):
    return AgentDescriptor(
        runtime=runtime,
        name="test-agent",
        capabilities=["code"],
        session_config=SessionConfig(),
    )


@pytest.mark.asyncio
async def test_dispatch_success(tmp_path):
    mgr = SessionManager(
        launchers={AgentRuntime.CODEX: MockLauncher()},
        state_file=tmp_path / "active.json",
    )
    result = await mgr.dispatch(
        _make_agent(), "test-feature", "do something", tmp_path
    )
    assert result is not None
    assert result.status == "success"
    assert result.artifacts == {"done": True}


@pytest.mark.asyncio
async def test_dispatch_version_mismatch(tmp_path):
    mgr = SessionManager(
        launchers={AgentRuntime.CODEX: BadVersionLauncher()},
        state_file=tmp_path / "active.json",
    )
    result = await mgr.dispatch(
        _make_agent(), "test-feature", "do something", tmp_path
    )
    assert result is not None
    assert result.status == "error"
    assert "version" in (result.error_message or "")


@pytest.mark.asyncio
async def test_abort_removes_session(tmp_path):
    mgr = SessionManager(
        launchers={AgentRuntime.CODEX: MockLauncher()},
        state_file=tmp_path / "active.json",
    )
    # Start a long-running agent that we can abort
    agent = _make_agent()
    launcher = MockLauncher()
    cmd = launcher.build_command("f1", tmp_path)
    session = await LocalSession.spawn(cmd)
    active = ActiveSession(
        session=session, state=SessionState.RUNNING,
        feature_id="f1", agent=agent,
    )
    mgr._active["f1"] = active
    assert "f1" in mgr.active_sessions
    await mgr.abort("f1")
    assert "f1" not in mgr.active_sessions


@pytest.mark.asyncio
async def test_ping_all_increments_missed(tmp_path):
    mgr = SessionManager(
        launchers={AgentRuntime.CODEX: MockLauncher()},
        state_file=tmp_path / "active.json",
    )
    agent = _make_agent()
    # Create a session that won't respond to ping (already exited)
    session = await LocalSession.spawn([sys.executable, "-c", "pass"])
    await asyncio.sleep(0.1)
    active = ActiveSession(
        session=session, state=SessionState.RUNNING,
        feature_id="f1", agent=agent,
    )
    mgr._active["f1"] = active
    await mgr.ping_all()
    assert active.missed_pings == 1


def test_check_timeouts(tmp_path):
    mgr = SessionManager(
        launchers={AgentRuntime.CODEX: MockLauncher()},
        state_file=tmp_path / "active.json",
        max_missed_pings=3,
    )
    mock_session = MagicMock()
    active = ActiveSession(
        session=mock_session, state=SessionState.RUNNING,
        feature_id="f1", agent=_make_agent(), missed_pings=5,
    )
    mgr._active["f1"] = active
    timed_out = mgr.check_timeouts()
    assert "f1" in timed_out
    assert active.state == SessionState.TIMEOUT


@pytest.mark.asyncio
async def test_graceful_shutdown(tmp_path):
    mgr = SessionManager(
        launchers={AgentRuntime.CODEX: MockLauncher()},
        state_file=tmp_path / "active.json",
    )
    pending = [{"feature_id": "x", "prompt": "test"}]
    await mgr.graceful_shutdown(pending_tasks=pending)
    assert len(mgr.active_sessions) == 0
    pending_file = tmp_path / "pending_tasks.json"
    assert pending_file.exists()
    assert json.loads(pending_file.read_text()) == pending


def test_cleanup_orphans_kills_matching(tmp_path):
    state_file = tmp_path / "active.json"
    instance_id = "test-instance"
    state_file.write_text(json.dumps({
        "sessions": [
            {"feature_id": "f1", "pid": 999999, "instance_id": instance_id},
            {"feature_id": "f2", "pid": 999998, "instance_id": "other-instance"},
        ]
    }))
    mgr = SessionManager(
        launchers={AgentRuntime.CODEX: MockLauncher()},
        state_file=state_file,
        instance_id=instance_id,
    )
    # PIDs don't exist so kill will fail silently
    killed = mgr.cleanup_orphans()
    assert killed == 0  # PID doesn't exist
    assert not state_file.exists()


def test_persist_active(tmp_path):
    mgr = SessionManager(
        launchers={AgentRuntime.CODEX: MockLauncher()},
        state_file=tmp_path / "active.json",
    )
    mock_session = MagicMock()
    mock_session.pid = 12345
    active = ActiveSession(
        session=mock_session, state=SessionState.RUNNING,
        feature_id="f1", agent=_make_agent(),
    )
    mgr._active["f1"] = active
    mgr._persist_active()
    data = json.loads((tmp_path / "active.json").read_text())
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["pid"] == 12345
    assert data["sessions"][0]["feature_id"] == "f1"
