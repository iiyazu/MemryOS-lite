from __future__ import annotations

import asyncio
import signal
from typing import Protocol

from xmuse_core.agents.protocol import StdoutMessage, format_stdin_message, parse_stdout_line


class AgentSession(Protocol):
    async def send(self, message: str) -> None: ...
    async def receive(self) -> StdoutMessage | None: ...
    async def abort(self) -> None: ...
    def is_alive(self) -> bool: ...


class LocalSession:
    """stdin/stdout transport for same-machine agents."""

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self._process = process
        self._health_warning = False
        self._consecutive_bad_lines = 0
        self._max_bad_lines = 50

    @classmethod
    async def spawn(cls, command: list[str], env: dict[str, str] | None = None) -> LocalSession:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        return cls(process)

    async def send(self, message: str) -> None:
        if self._process.stdin is None:
            return
        data = message.encode() if not message.endswith("\n") else message.encode()
        self._process.stdin.write(data)
        await self._process.stdin.drain()

    async def send_typed(self, msg_type: str, **kwargs) -> None:
        await self.send(format_stdin_message(msg_type, **kwargs))

    async def receive(self) -> StdoutMessage | None:
        if self._process.stdout is None:
            return None
        while True:
            line = await self._process.stdout.readline()
            if not line:
                return None
            decoded = line.decode().strip()
            if not decoded:
                continue
            msg = parse_stdout_line(decoded)
            if msg is not None:
                self._consecutive_bad_lines = 0
                return msg
            self._consecutive_bad_lines += 1
            if self._consecutive_bad_lines >= self._max_bad_lines:
                self._health_warning = True
            return None

    async def abort(self, grace_period: float = 10.0) -> None:
        if self._process.returncode is not None:
            return
        try:
            await self.send_typed("abort")
        except (BrokenPipeError, ConnectionResetError):
            pass
        try:
            self._process.send_signal(signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(self._process.wait(), timeout=grace_period)
        except asyncio.TimeoutError:
            try:
                self._process.kill()
            except ProcessLookupError:
                pass
            await self._process.wait()

    def is_alive(self) -> bool:
        return self._process.returncode is None

    @property
    def health_warning(self) -> bool:
        return self._health_warning

    @property
    def pid(self) -> int | None:
        return self._process.pid
