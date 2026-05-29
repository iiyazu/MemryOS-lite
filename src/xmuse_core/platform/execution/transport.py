from __future__ import annotations

from pathlib import Path
from typing import Protocol

from xmuse_core.platform.agent_spawner import AgentSpawner, GodConfig, SpawnResult
from xmuse_core.platform.execution.review import review_infra_failure_reason
from xmuse_core.self_evolution.recovery import TransientRecoveryError


class Transport(Protocol):
    async def spawn_god(
        self, *, god: GodConfig, lane_id: str, prompt: str, worktree: Path
    ) -> SpawnResult: ...


class SpawnerTransport:
    """Default Transport: spawn a god via AgentSpawner and translate infra
    failures (usage/rate limits, transient outages) into a
    TransientRecoveryError so the recovery layer can retry or trip the circuit.

    Holds the spawner instance and calls ``.spawn`` at call time so tests that
    patch ``orchestrator._spawner.spawn`` continue to take effect.
    """

    def __init__(self, spawner: AgentSpawner) -> None:
        self._spawner = spawner

    async def spawn_god(
        self, *, god: GodConfig, lane_id: str, prompt: str, worktree: Path
    ) -> SpawnResult:
        result = await self._spawner.spawn(
            god_config=god,
            lane_id=lane_id,
            prompt=prompt,
            worktree=worktree,
        )
        infra_reason = review_infra_failure_reason(result)
        if infra_reason is not None:
            output = getattr(result, "stderr", "") or getattr(result, "stdout", "")
            raise TransientRecoveryError(
                f"{infra_reason}: {output or 'spawn infrastructure failure'}"
            )
        return result
