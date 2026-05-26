from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from xmuse_core.agents.launchers.base import LauncherAdapter
from xmuse_core.agents.memoryos_client import MemoryOSClient
from xmuse_core.agents.protocol import (
    PROTOCOL_VERSION,
    AgentOutput,
)
from xmuse_core.agents.registry import AgentDescriptor, AgentRuntime
from xmuse_core.agents.session import LocalSession

logger = logging.getLogger(__name__)


class SessionState(StrEnum):
    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    COMPLETING = "completing"
    DONE = "done"
    ABORTING = "aborting"
    TIMEOUT = "timeout"
    FAILED = "failed"


@dataclass
class ActiveSession:
    session: LocalSession
    state: SessionState
    feature_id: str
    agent: AgentDescriptor
    started_at: float = field(default_factory=time.time)
    last_pong: float = field(default_factory=time.time)
    missed_pings: int = 0
    memoryos_session_id: str | None = None


class SessionManager:
    def __init__(
        self,
        launchers: dict[AgentRuntime, LauncherAdapter],
        state_file: Path | None = None,
        instance_id: str | None = None,
        max_missed_pings: int = 10,
        memoryos_client: MemoryOSClient | None = None,
    ) -> None:
        self._launchers = launchers
        self._active: dict[str, ActiveSession] = {}
        self._state_file = state_file or Path("xmuse/active_sessions.json")
        self._instance_id = instance_id or f"master-{os.getpid()}"
        self._max_missed_pings = max_missed_pings
        self._memoryos_client = memoryos_client
        self._shutdown = False

    @property
    def active_sessions(self) -> dict[str, ActiveSession]:
        return self._active

    async def dispatch(
        self,
        agent: AgentDescriptor,
        feature_id: str,
        prompt: str,
        worktree: Path,
        context: str = "",
    ) -> AgentOutput | None:
        launcher = self._launchers[agent.runtime]
        cmd = launcher.build_command(feature_id, worktree)
        env = launcher.build_env(feature_id)

        session = await LocalSession.spawn(cmd, env=env)
        active = ActiveSession(
            session=session,
            state=SessionState.STARTING,
            feature_id=feature_id,
            agent=agent,
        )
        self._active[feature_id] = active
        self._persist_active()

        # Hello handshake
        await session.send_typed(
            "hello", protocol_version=PROTOCOL_VERSION, feature_id=feature_id
        )
        hello_resp = await session.receive()
        if hello_resp is None or hello_resp.type != "hello_ack":
            active.state = SessionState.FAILED
            await session.abort(grace_period=5.0)
            self._active.pop(feature_id, None)
            self._persist_active()
            return AgentOutput(status="error", error_message="hello handshake failed")

        if hello_resp.protocol_version != PROTOCOL_VERSION:
            active.state = SessionState.FAILED
            await session.abort(grace_period=5.0)
            self._active.pop(feature_id, None)
            self._persist_active()
            return AgentOutput(status="error", error_message="protocol version mismatch")

        # Send task
        active.state = SessionState.RUNNING
        formatted = launcher.format_prompt(prompt, context)
        await session.send_typed("task", feature_id=feature_id, prompt=formatted, context=context)

        # Read output until result or error
        while session.is_alive():
            msg = await session.receive()
            if msg is None:
                if not session.is_alive():
                    break
                continue
            if msg.type == "result":
                active.state = SessionState.DONE
                output = AgentOutput.from_result(msg)
                self._active.pop(feature_id, None)
                self._persist_active()
                return output
            if msg.type == "error":
                active.state = SessionState.FAILED
                output = AgentOutput.from_error(msg)
                self._active.pop(feature_id, None)
                self._persist_active()
                return output
            if msg.type == "pong":
                active.last_pong = time.time()
                active.missed_pings = 0

        active.state = SessionState.FAILED
        self._active.pop(feature_id, None)
        self._persist_active()
        return AgentOutput(status="error", error_message="agent process exited unexpectedly")

    async def abort(self, feature_id: str) -> None:
        active = self._active.get(feature_id)
        if active:
            active.state = SessionState.ABORTING
            await active.session.abort(grace_period=10.0)
            self._active.pop(feature_id, None)
            self._persist_active()

    async def ping_all(self) -> None:
        for active in list(self._active.values()):
            if active.state == SessionState.RUNNING:
                try:
                    await active.session.send_typed("ping")
                    active.missed_pings += 1
                except (BrokenPipeError, ConnectionResetError):
                    active.missed_pings += 1

    def check_timeouts(self) -> list[str]:
        timed_out = []
        for fid, active in list(self._active.items()):
            if active.missed_pings >= self._max_missed_pings:
                active.state = SessionState.TIMEOUT
                timed_out.append(fid)
        return timed_out

    async def graceful_shutdown(self, pending_tasks: list[dict[str, Any]] | None = None) -> None:
        self._shutdown = True
        for active in list(self._active.values()):
            await active.session.abort(grace_period=10.0)
        self._active.clear()
        self._persist_active()
        if pending_tasks:
            pending_file = self._state_file.parent / "pending_tasks.json"
            pending_file.parent.mkdir(parents=True, exist_ok=True)
            pending_file.write_text(json.dumps(pending_tasks))

    def cleanup_orphans(self) -> int:
        if not self._state_file.exists():
            return 0
        try:
            data = json.loads(self._state_file.read_text())
        except (json.JSONDecodeError, OSError):
            return 0
        killed = 0
        for entry in data.get("sessions", []):
            if entry.get("instance_id") != self._instance_id:
                continue
            pid = entry.get("pid")
            if pid:
                try:
                    os.kill(pid, signal.SIGKILL)
                    killed += 1
                except (ProcessLookupError, PermissionError):
                    pass
        self._state_file.unlink(missing_ok=True)
        return killed

    def _persist_active(self) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        sessions = []
        for fid, active in self._active.items():
            sessions.append({
                "feature_id": fid,
                "pid": active.session.pid,
                "instance_id": self._instance_id,
                "state": active.state.value,
                "started_at": active.started_at,
            })
        self._state_file.write_text(json.dumps({"sessions": sessions}))

    _DEFAULT_TIMEOUT: float = 3600.0

    async def dispatch_one_shot(
        self,
        agent: AgentDescriptor,
        feature_id: str,
        prompt: str,
        worktree: Path,
        context: str = "",
        timeout: float | None = _DEFAULT_TIMEOUT,
    ) -> AgentOutput:
        launcher = self._launchers[agent.runtime]
        cmd = launcher.build_command(feature_id, worktree)
        env = launcher.build_env(feature_id)
        formatted = launcher.format_prompt(prompt, context)
        memoryos_session_id = await self._memoryos_create_session(feature_id)
        if memoryos_session_id:
            memory_context = await self._memoryos_build_context(memoryos_session_id, prompt)
            if memory_context:
                formatted = f"{memory_context}\n\n{formatted}"

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        active = ActiveSession(
            session=LocalSession(process),
            state=SessionState.RUNNING,
            feature_id=feature_id,
            agent=agent,
        )
        self._active[feature_id] = active
        self._persist_active()

        try:
            communicate = process.communicate(input=formatted.encode())
            if timeout is None:
                stdout_bytes, stderr_bytes = await communicate
            else:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    communicate,
                    timeout=timeout,
                )
        except TimeoutError:
            process.kill()
            await process.wait()
            self._active.pop(feature_id, None)
            self._persist_active()
            return AgentOutput(status="timeout", error_message="process timed out")

        self._active.pop(feature_id, None)
        self._persist_active()

        stdout_str = stdout_bytes.decode(errors="replace")
        stderr_str = stderr_bytes.decode(errors="replace")
        if memoryos_session_id:
            await self._memoryos_ingest_dispatch(memoryos_session_id, prompt, stdout_str)

        if process.returncode == 0:
            return AgentOutput(
                status="success",
                artifacts={"stdout": stdout_str, "stderr": stderr_str},
            )
        return AgentOutput(
            status="error",
            error_code=f"exit_{process.returncode}",
            error_message=stderr_str[:500] or stdout_str[:500],
            artifacts={"stdout": stdout_str, "stderr": stderr_str},
        )

    async def _memoryos_create_session(self, feature_id: str) -> str | None:
        if not self._memoryos_client:
            return None
        try:
            return await self._memoryos_client.create_session(f"xmuse:{feature_id}")
        except Exception as exc:
            logger.warning("memoryos create_session failed: %s", exc)
            return None

    async def _memoryos_build_context(self, session_id: str, prompt: str) -> str:
        if not self._memoryos_client:
            return ""
        try:
            return await self._memoryos_client.build_context(session_id, prompt)
        except Exception as exc:
            logger.warning("memoryos build_context failed: %s", exc)
            return ""

    async def _memoryos_ingest_dispatch(
        self, session_id: str, prompt: str, stdout: str
    ) -> None:
        await self._memoryos_ingest(session_id, "user", prompt)
        await self._memoryos_ingest(session_id, "assistant", stdout[:4000])

    async def _memoryos_ingest(self, session_id: str, role: str, content: str) -> None:
        if not self._memoryos_client:
            return
        try:
            await self._memoryos_client.ingest(session_id, role, content)
        except Exception as exc:
            logger.warning("memoryos ingest failed: %s", exc)
