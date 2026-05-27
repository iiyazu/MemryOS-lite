from __future__ import annotations

from pathlib import Path

import pytest

from xmuse_core.agents.god_session_layer import GodSessionLayer
from xmuse_core.agents.registry import AgentDescriptor, AgentRuntime, SessionConfig


class FakeSession:
    def __init__(self, alive: bool = True) -> None:
        self._alive = alive
        self.sent_messages: list[tuple[str, dict[str, object]]] = []

    def is_alive(self) -> bool:
        return self._alive

    async def send_typed(self, msg_type: str, **kwargs) -> None:
        self.sent_messages.append((msg_type, kwargs))


class FakeLauncher:
    def __init__(self, command: list[str] | None = None) -> None:
        self.command = command or ["fake-agent"]
        self.build_command_calls: list[tuple[str, Path]] = []
        self.build_env_calls: list[str] = []

    def build_command(self, feature_id: str, worktree: Path) -> list[str]:
        self.build_command_calls.append((feature_id, worktree))
        return self.command

    def build_env(self, feature_id: str) -> dict[str, str] | None:
        self.build_env_calls.append(feature_id)
        return None


def _make_agent() -> AgentDescriptor:
    return AgentDescriptor(
        runtime=AgentRuntime.CODEX,
        name="executor",
        capabilities=["code"],
        session_config=SessionConfig(),
    )


@pytest.mark.asyncio
async def test_ensure_session_reuses_live_session_for_role(tmp_path, monkeypatch):
    launcher = FakeLauncher()
    layer = GodSessionLayer(
        registry_path=tmp_path / "god_sessions.json",
        launchers={AgentRuntime.CODEX: launcher},
    )
    spawned_sessions: list[FakeSession] = []

    async def fake_spawn(command, env=None):
        assert command == ["fake-agent"]
        assert env is None
        session = FakeSession()
        spawned_sessions.append(session)
        return session

    monkeypatch.setattr(
        "xmuse_core.agents.god_session_layer.LocalSession.spawn",
        fake_spawn,
    )

    first = await layer.ensure_session(role="execute", agent=_make_agent(), worktree=tmp_path)
    second = await layer.ensure_session(role="execute", agent=_make_agent(), worktree=tmp_path)

    assert first.god_session_id == second.god_session_id
    assert len(spawned_sessions) == 1
    assert launcher.build_command_calls == [("execute", tmp_path)]
    assert launcher.build_env_calls == ["execute"]


@pytest.mark.asyncio
async def test_send_message_routes_by_god_session_id_not_feature_id(tmp_path, monkeypatch):
    launcher = FakeLauncher()
    layer = GodSessionLayer(
        registry_path=tmp_path / "god_sessions.json",
        launchers={AgentRuntime.CODEX: launcher},
    )
    session = FakeSession()

    async def fake_spawn(command, env=None):
        return session

    monkeypatch.setattr(
        "xmuse_core.agents.god_session_layer.LocalSession.spawn",
        fake_spawn,
    )

    record = await layer.ensure_session(role="execute", agent=_make_agent(), worktree=tmp_path)

    await layer.send_message(
        god_session_id=record.god_session_id,
        message_type="task",
        prompt="ship it",
        context="ctx",
    )

    assert session.sent_messages == [
        (
            "task",
            {
                "god_session_id": record.god_session_id,
                "prompt": "ship it",
                "context": "ctx",
            },
        )
    ]
