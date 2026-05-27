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
        if live is not None and live.session.is_alive():
            return live.record

        launcher = self._launchers[agent.runtime]
        command = launcher.build_command(role, worktree)
        env = launcher.build_env(role)
        session = await LocalSession.spawn(command, env=env)
        record = self._registry.create(
            role=role,
            agent_name=agent.name,
            runtime=agent.runtime.value,
            session_address=f"@{role}",
            session_inbox_id=f"inbox-{role}",
        )
        self._live_sessions[record.god_session_id] = LiveGodSession(record=record, session=session)
        return record

    async def send_message(
        self,
        god_session_id: str,
        message_type: str,
        prompt: str,
        context: str,
    ) -> None:
        live = self._live_sessions[god_session_id]
        await live.session.send_typed(
            message_type,
            god_session_id=god_session_id,
            prompt=prompt,
            context=context,
        )

    def _find_live_session_by_role(self, role: str) -> LiveGodSession | None:
        for live in self._live_sessions.values():
            if live.record.role == role:
                return live
        return None
