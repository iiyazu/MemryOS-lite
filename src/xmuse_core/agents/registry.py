from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal


class AgentRuntime(StrEnum):
    CODEX = "codex"
    CLAUDE_CODE = "claude_code"


@dataclass
class SessionConfig:
    transport: Literal["local", "remote"] = "local"
    heartbeat_interval_s: int = 30
    heartbeat_timeout_s: int = 300
    max_context_tokens: int | None = None
    persistent_role: str | None = None


@dataclass
class AgentDescriptor:
    runtime: AgentRuntime
    name: str
    capabilities: list[str] = field(default_factory=list)
    session_config: SessionConfig = field(default_factory=SessionConfig)


class AgentRegistry:
    def __init__(self, agents: list[AgentDescriptor]) -> None:
        self.agents = agents
        self._round_robin_idx = 0

    @classmethod
    def from_file(cls, path: Path) -> AgentRegistry:
        data = json.loads(path.read_text())
        agents = []
        for entry in data["agents"]:
            sc = SessionConfig(**entry.get("session_config", {}))
            agents.append(AgentDescriptor(
                runtime=AgentRuntime(entry["runtime"]),
                name=entry["name"],
                capabilities=entry.get("capabilities", []),
                session_config=sc,
            ))
        return cls(agents)

    def select(
        self,
        required: list[str],
        exclude_runtime: AgentRuntime | None = None,
    ) -> AgentDescriptor:
        candidates = [
            a for a in self.agents
            if all(cap in a.capabilities for cap in required)
            and (exclude_runtime is None or a.runtime != exclude_runtime)
        ]
        if not candidates:
            raise ValueError(f"no agent matches capabilities={required}")
        idx = self._round_robin_idx % len(candidates)
        self._round_robin_idx += 1
        return candidates[idx]
