from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from xmuse_core.agents.god_session_registry import GodSessionRecord, GodSessionRegistry
from xmuse_core.agents.registry import AgentDescriptor, AgentRuntime
from xmuse_core.agents.session import LocalSession


@dataclass
class LiveGodSession:
    record: GodSessionRecord
    session: LocalSession
    worktree: Path


class GodSessionLayer:
    def __init__(self, registry_path: Path, launchers: dict[AgentRuntime, object]) -> None:
        self._registry = GodSessionRegistry(registry_path)
        self._launchers = launchers
        self._live_sessions: dict[str, LiveGodSession] = {}

    async def ensure_session(
        self,
        role: str,
        agent: AgentDescriptor,
        worktree: Path,
    ) -> GodSessionRecord:
        live = self._find_live_session_by_role(role)
        if live is not None:
            self._assert_session_shape_matches(live, agent, worktree)
            if live.session.is_alive():
                return live.record

        launcher = self._launchers[agent.runtime]
        command = launcher.build_command(role, worktree)
        env = launcher.build_env(role)
        session = await LocalSession.spawn(command, env=env)
        if live is not None:
            self._live_sessions[live.record.god_session_id] = LiveGodSession(
                record=live.record,
                session=session,
                worktree=worktree,
            )
            return live.record
        record = self._registry.create(
            role=role,
            agent_name=agent.name,
            runtime=agent.runtime.value,
            session_address=f"@{role}",
            session_inbox_id=f"inbox-{role}",
        )
        self._live_sessions[record.god_session_id] = LiveGodSession(
            record=record,
            session=session,
            worktree=worktree,
        )
        return record

    async def send_message(
        self,
        god_session_id: str,
        message_type: str,
        prompt: str,
        context: str,
    ) -> None:
        live = self._live_sessions.get(god_session_id)
        if live is None:
            try:
                self._registry.get(god_session_id)
            except KeyError as exc:
                raise LookupError(f"Unknown god_session_id: {god_session_id}") from exc
            raise RuntimeError(
                f"god_session_id '{god_session_id}' is registered but has no live transport attached in this process"
            )
        await live.session.send_typed(
            message_type,
            god_session_id=god_session_id,
            prompt=prompt,
            context=context,
        )

    def _find_live_session_by_role(self, role: str) -> LiveGodSession | None:
        for live in reversed(list(self._live_sessions.values())):
            if live.record.role == role:
                return live
        return None

    def _assert_session_shape_matches(
        self,
        live: LiveGodSession,
        agent: AgentDescriptor,
        worktree: Path,
    ) -> None:
        if (
            live.record.agent_name != agent.name
            or live.record.runtime != agent.runtime.value
            or live.worktree != worktree
        ):
            raise RuntimeError(
                f"Cannot reuse role='{live.record.role}': existing live session does not match requested agent/worktree"
            )
