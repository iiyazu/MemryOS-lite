from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Any

from xmuse_core.platform.agent_spawner import AgentSpawner, GodConfig, SpawnResult
from xmuse_core.platform.event_bus import EventBus
from xmuse_core.platform.mcp_tools import McpToolHandler
from xmuse_core.platform.state_machine import LaneStateMachine

logger = logging.getLogger(__name__)

EXECUTION_GOD = GodConfig(
    name="execution-god",
    runtime="codex",
    timeout_s=3600,
    skill_prompt_path="xmuse/god_prompts/execution_god.md",
)

REVIEW_GOD = GodConfig(
    name="review-god",
    runtime="codex",
    timeout_s=120,
    skill_prompt_path="xmuse/god_prompts/review_god.md",
)


class PlatformOrchestrator:
    def __init__(
        self,
        *,
        lanes_path: Path,
        xmuse_root: Path,
        mcp_port: int = 9800,
    ) -> None:
        self._sm = LaneStateMachine(lanes_path)
        self._bus = EventBus()
        self._spawner = AgentSpawner(repo_root=xmuse_root, mcp_port=mcp_port)
        self._root = xmuse_root
        self._tools = McpToolHandler(
            state_machine=self._sm,
            xmuse_root=xmuse_root,
            on_status_change=self._on_mcp_status_change,
        )

    def _on_mcp_status_change(self, lane_id: str, new_status: str) -> None:
        event_map = {
            "executed": "lane_executed",
            "exec_failed": "lane_exec_failed",
            "reviewed": "lane_reviewed",
            "rejected": "lane_rejected",
            "gate_failed": "lane_gate_failed",
        }
        event = event_map.get(new_status)
        if event:
            asyncio.get_event_loop().create_task(
                self._bus.publish(event, {"lane_id": lane_id})
            )

    async def dispatch_lane(self, lane_id: str) -> None:
        self._sm.transition(lane_id, "dispatched")
        asyncio.create_task(self._run_execution_god(lane_id))

    async def _run_execution_god(self, lane_id: str) -> None:
        lane = self._sm.get_lane(lane_id)
        prompt = self._build_execution_prompt(lane)
        worktree = Path(lane.get("worktree", "."))

        result = await self._spawner.spawn(
            god_config=EXECUTION_GOD,
            lane_id=lane_id,
            prompt=prompt,
            worktree=worktree,
        )

        if result.timed_out:
            self._sm.transition(lane_id, "exec_failed",
                                metadata={"failure_reason": "timeout"})
            return

        current = self._sm.get_lane(lane_id)
        if current["status"] == "dispatched":
            if result.exit_code == 0:
                self._sm.transition(lane_id, "executed")
                await self._on_lane_executed(lane_id)
            else:
                self._sm.transition(lane_id, "exec_failed",
                                    metadata={"failure_reason": "non_zero_exit"})

    async def _on_lane_executed(self, lane_id: str) -> None:
        passed = await self._run_gate(lane_id)
        if passed:
            self._sm.transition(lane_id, "gated")
        else:
            self._sm.transition(lane_id, "gated",
                                metadata={"gate_passed": False})
        asyncio.create_task(self._run_review_god(lane_id))

    async def _run_review_god(self, lane_id: str) -> None:
        lane = self._sm.get_lane(lane_id)
        prompt = self._build_review_prompt(lane)
        worktree = Path(lane.get("worktree", "."))

        result = await self._spawner.spawn(
            god_config=REVIEW_GOD,
            lane_id=lane_id,
            prompt=prompt,
            worktree=worktree,
        )

        if result.timed_out:
            self._sm.transition(lane_id, "gate_failed",
                                metadata={"failure_reason": "review_timeout"})

    async def on_lane_reviewed(self, lane_id: str) -> None:
        self._sm.transition(lane_id, "merged")
        logger.info("Lane %s merged", lane_id)

    async def on_lane_rejected(self, lane_id: str) -> None:
        lane = self._sm.get_lane(lane_id)
        retries = lane.get("retry_count", 0)
        if retries >= 2:
            self._sm.transition(lane_id, "failed")
            logger.info("Lane %s failed after max retries", lane_id)
            return
        self._sm.transition(lane_id, "reworking")
        self._sm.transition(lane_id, "dispatched")
        asyncio.create_task(self._run_execution_god(lane_id))

    async def _run_gate(self, lane_id: str) -> bool:
        lane = self._sm.get_lane(lane_id)
        worktree = Path(lane.get("worktree", "."))
        gate_profile = lane.get("gate_profile")

        try:
            from xmuse_core.gates.loader import load_gate_config
            from xmuse_core.gates.resolver import GateProfileResolver
            from xmuse_core.gates.runner import GateRunner

            config_path = self._root / "gate_profiles.json"
            if not config_path.exists():
                logger.warning("No gate_profiles.json, skipping gate for %s", lane_id)
                return True

            config = load_gate_config(config_path, repo_root=self._root.parent)
            resolver = GateProfileResolver(config)

            explicit_profiles = [gate_profile] if gate_profile else []
            changed = self._get_changed_paths(worktree)

            plan = resolver.resolve(
                feature_id=lane_id,
                worktree=worktree,
                explicit_profiles=explicit_profiles,
                changed_paths=changed,
            )

            runner = GateRunner(
                repo_root=self._root.parent,
                logs_root=self._root / "logs" / "gates",
            )
            report = await runner.run(plan)
            return report.passed

        except Exception as exc:
            logger.exception("Gate failed for %s: %s", lane_id, exc)
            return False

    def _get_changed_paths(self, worktree: Path) -> list[str]:
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=worktree, capture_output=True, text=True, timeout=10,
            )
            return [p for p in result.stdout.strip().splitlines() if p]
        except Exception:
            return []

    def _build_execution_prompt(self, lane: dict[str, Any]) -> str:
        prompt_path = self._root / EXECUTION_GOD.skill_prompt_path
        skill = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
        task = lane.get("prompt", "")
        lid = lane.get("feature_id", "")
        return f"{skill}\n\n## Task\n\nLane ID: {lid}\n\n{task}"

    def _build_review_prompt(self, lane: dict[str, Any]) -> str:
        prompt_path = self._root / REVIEW_GOD.skill_prompt_path
        skill = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
        lid = lane.get("feature_id", "")
        return f"{skill}\n\n## Task\n\nReview lane: {lid}"
