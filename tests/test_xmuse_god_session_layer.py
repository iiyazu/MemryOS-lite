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
async def test_ensure_session_rejects_role_reuse_when_shape_differs(tmp_path, monkeypatch):
    launcher = FakeLauncher()
    layer = GodSessionLayer(
        registry_path=tmp_path / "god_sessions.json",
        launchers={AgentRuntime.CODEX: launcher},
    )

    async def fake_spawn(command, env=None):
        return FakeSession()

    monkeypatch.setattr(
        "xmuse_core.agents.god_session_layer.LocalSession.spawn",
        fake_spawn,
    )

    await layer.ensure_session(role="execute", agent=_make_agent(), worktree=tmp_path)

    other_agent = AgentDescriptor(
        runtime=AgentRuntime.CLAUDE_CODE,
        name="reviewer",
        capabilities=["code"],
        session_config=SessionConfig(),
    )
    with pytest.raises(RuntimeError, match="role='execute'.*existing live session.*requested agent/worktree"):
        await layer.ensure_session(
            role="execute",
            agent=other_agent,
            worktree=tmp_path / "other-worktree",
        )


@pytest.mark.asyncio
async def test_ensure_session_respawns_dead_role_once_then_reuses_new_live_session(tmp_path, monkeypatch):
    launcher = FakeLauncher()
    layer = GodSessionLayer(
        registry_path=tmp_path / "god_sessions.json",
        launchers={AgentRuntime.CODEX: launcher},
    )
    spawned_sessions: list[FakeSession] = []

    async def fake_spawn(command, env=None):
        session = FakeSession()
        spawned_sessions.append(session)
        return session

    monkeypatch.setattr(
        "xmuse_core.agents.god_session_layer.LocalSession.spawn",
        fake_spawn,
    )

    first = await layer.ensure_session(role="execute", agent=_make_agent(), worktree=tmp_path)
    spawned_sessions[0]._alive = False

    second = await layer.ensure_session(role="execute", agent=_make_agent(), worktree=tmp_path)
    third = await layer.ensure_session(role="execute", agent=_make_agent(), worktree=tmp_path)

    assert first.god_session_id == second.god_session_id == third.god_session_id
    assert len(spawned_sessions) == 2
    assert launcher.build_command_calls == [("execute", tmp_path), ("execute", tmp_path)]
    assert launcher.build_env_calls == ["execute", "execute"]


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


@pytest.mark.asyncio
async def test_send_message_rejects_registered_but_unattached_session(tmp_path):
    layer = GodSessionLayer(
        registry_path=tmp_path / "god_sessions.json",
        launchers={},
    )
    record = layer._registry.create(
        role="execute",
        agent_name="executor",
        runtime="codex",
        session_address="@execute",
        session_inbox_id="inbox-execute",
    )

    with pytest.raises(RuntimeError, match="registered.*no live transport attached"):
        await layer.send_message(
            god_session_id=record.god_session_id,
            message_type="task",
            prompt="ship it",
            context="ctx",
        )


@pytest.mark.asyncio
async def test_send_message_rejects_unknown_god_session_id(tmp_path):
    layer = GodSessionLayer(
        registry_path=tmp_path / "god_sessions.json",
        launchers={},
    )

    with pytest.raises(LookupError, match="Unknown god_session_id: god-missing"):
        await layer.send_message(
            god_session_id="god-missing",
            message_type="task",
            prompt="ship it",
            context="ctx",
        )
