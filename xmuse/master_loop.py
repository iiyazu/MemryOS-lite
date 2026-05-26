#!/usr/bin/env python3
"""Multi-round autonomous xmuse orchestrator."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

ROOT = Path(__file__).resolve().parent.parent
XMUSE_DIR = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(XMUSE_DIR) not in sys.path:
    sys.path.insert(0, str(XMUSE_DIR))

from xmuse_main import load_lanes, update_lane_status
from xmuse_core.agents.consumer import TaskDescriptor, WorklistConsumer
from xmuse_core.agents.launchers.codex import CodexLauncher
from xmuse_core.agents.manager import SessionManager
from xmuse_core.agents.registry import AgentRegistry, AgentRuntime

logger = logging.getLogger("xmuse.master_loop")


class GateResultLike(Protocol):
    passed: bool
    errors: list[str]


class QualityGateLike(Protocol):
    async def check(self, worktree: Path) -> GateResultLike: ...


class LaneResultLike(Protocol):
    status: str


class ReworkLoopLike(Protocol):
    async def run(
        self,
        lane: TaskDescriptor,
        initial_gate_result: GateResultLike,
        dispatch_fn: Any,
        gate: QualityGateLike,
    ) -> LaneResultLike: ...


class ConsumerLike(Protocol):
    async def dispatch_task(self, task: TaskDescriptor) -> str: ...
    def shutdown(self) -> None: ...


@dataclass
class MasterLoopSummary:
    rounds: int = 0
    successful_lanes: int = 0
    failed_lanes: int = 0
    zero_success_rounds: int = 0
    exit_reason: str = ""


class MasterLoop:
    """Run discovery, dispatch, quality gate, and rework rounds until quiescent."""

    def __init__(
        self,
        *,
        lanes_path: Path = Path("xmuse/feature_lanes.json"),
        auto_discovery_path: Path = Path("xmuse/auto_discovery.py"),
        consumer: ConsumerLike | None,
        quality_gate: QualityGateLike,
        rework_loop: ReworkLoopLike,
        max_hours: float = 10.0,
        max_concurrent: int = 2,
        python_executable: str = sys.executable,
        monotonic: Any = time.monotonic,
    ) -> None:
        self.lanes_path = lanes_path
        self.auto_discovery_path = auto_discovery_path
        self.consumer = consumer
        self.quality_gate = quality_gate
        self.rework_loop = rework_loop
        self.max_hours = max_hours
        self.max_concurrent = max(1, max_concurrent)
        self.python_executable = python_executable
        self._monotonic = monotonic
        self._shutdown_requested = asyncio.Event()

    @classmethod
    def from_defaults(
        cls,
        *,
        lanes_path: Path = Path("xmuse/feature_lanes.json"),
        auto_discovery_path: Path = Path("xmuse/auto_discovery.py"),
        agents_path: Path = Path("xmuse/agents.json"),
        max_hours: float = 10.0,
        max_concurrent: int = 2,
    ) -> MasterLoop:
        from xmuse_core.agents.quality_gate import QualityGate
        from xmuse_core.agents.rework_loop import ReworkLoop

        registry = AgentRegistry.from_file(agents_path)
        session_mgr = SessionManager(
            launchers={AgentRuntime.CODEX: CodexLauncher()},
            state_file=Path("xmuse/active_sessions.json"),
        )
        consumer = WorklistConsumer(
            registry=registry,
            session_mgr=session_mgr,
            max_concurrent=max_concurrent,
        )
        return cls(
            lanes_path=lanes_path,
            auto_discovery_path=auto_discovery_path,
            consumer=consumer,
            quality_gate=QualityGate(),
            rework_loop=ReworkLoop(),
            max_hours=max_hours,
            max_concurrent=max_concurrent,
        )

    async def run(self) -> MasterLoopSummary:
        summary = MasterLoopSummary()
        deadline = self._monotonic() + self.max_hours * 3600

        while True:
            if self._shutdown_requested.is_set():
                summary.exit_reason = "shutdown"
                break
            if self._monotonic() >= deadline:
                summary.exit_reason = "timeout"
                break

            summary.rounds += 1
            discovered = await self._run_auto_discovery()
            self._merge_discovered_lanes(discovered)
            pending = load_lanes(self.lanes_path)

            if not pending and not discovered:
                summary.exit_reason = "idle"
                break

            round_successes, round_failures = await self._dispatch_round(pending, deadline)
            summary.successful_lanes += round_successes
            summary.failed_lanes += round_failures

            if round_successes == 0:
                summary.zero_success_rounds += 1
            else:
                summary.zero_success_rounds = 0

            if self._shutdown_requested.is_set():
                summary.exit_reason = "shutdown"
                break
            if self._monotonic() >= deadline:
                summary.exit_reason = "timeout"
                break
            if summary.zero_success_rounds >= 3:
                summary.exit_reason = "zero_success_rounds"
                break

        if self.consumer is not None:
            self.consumer.shutdown()
        return summary

    def request_shutdown(self) -> None:
        self._shutdown_requested.set()

    def install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self.request_shutdown)
            except NotImplementedError:
                signal.signal(sig, lambda _signum, _frame: self.request_shutdown())

    async def _run_auto_discovery(self) -> list[dict[str, Any]]:
        process = await asyncio.create_subprocess_exec(
            self.python_executable,
            str(self.auto_discovery_path),
            "--all",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=ROOT,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            logger.warning(
                "auto discovery failed with exit %s: %s",
                process.returncode,
                stderr.decode(errors="replace")[:1000],
            )
            return []
        output = stdout.decode(errors="replace").strip()
        if not output:
            return []
        try:
            lanes = json.loads(output)
        except json.JSONDecodeError:
            logger.warning("auto discovery returned invalid JSON: %s", output[:1000])
            return []
        if not isinstance(lanes, list):
            logger.warning("auto discovery returned %s, expected list", type(lanes).__name__)
            return []
        return [lane for lane in lanes if isinstance(lane, dict) and lane.get("feature_id")]

    def _merge_discovered_lanes(self, discovered: list[dict[str, Any]]) -> None:
        data = self._read_lanes_json()
        lanes = data.setdefault("lanes", [])
        existing_ids = {lane.get("feature_id") for lane in lanes}
        changed = False
        for lane in discovered:
            if lane.get("feature_id") in existing_ids:
                continue
            lanes.append(lane)
            existing_ids.add(lane.get("feature_id"))
            changed = True
        if changed:
            self._write_lanes_json(data)

    async def _dispatch_round(
        self,
        pending: list[TaskDescriptor],
        deadline: float,
    ) -> tuple[int, int]:
        successful = 0
        failed = 0
        queue = asyncio.Queue[TaskDescriptor]()
        for task in pending:
            queue.put_nowait(task)

        async def worker() -> None:
            nonlocal successful, failed
            while not self._shutdown_requested.is_set() and self._monotonic() < deadline:
                try:
                    task = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    status = await self._run_lane(task)
                    if status == "done":
                        successful += 1
                    else:
                        failed += 1
                finally:
                    queue.task_done()

        workers = [
            asyncio.create_task(worker())
            for _ in range(min(self.max_concurrent, max(1, len(pending))))
        ]
        await asyncio.gather(*workers)
        return successful, failed

    async def _run_lane(self, task: TaskDescriptor) -> str:
        if self.consumer is None:
            raise RuntimeError("MasterLoop.consumer is required before dispatching lanes")

        self._update_lane_status(task.feature_id, "running")
        dispatch_status = await self.consumer.dispatch_task(task)
        if dispatch_status != "done":
            self._update_lane_status(task.feature_id, "failed")
            return "failed"

        gate_result = await self.quality_gate.check(Path(task.worktree))
        if gate_result.passed:
            self._update_lane_status(task.feature_id, "done")
            return "done"

        async def dispatch_rework(rework_prompt: str, worktree: Path) -> str:
            rework_task = TaskDescriptor(
                feature_id=task.feature_id,
                task_type="rework",
                prompt=rework_prompt,
                worktree=str(worktree),
                required_capabilities=task.required_capabilities,
                developed_by_runtime=task.developed_by_runtime,
            )
            return await self.consumer.dispatch_task(rework_task)

        lane_result = await self.rework_loop.run(
            task,
            gate_result,
            dispatch_rework,
            self.quality_gate,
        )
        status = "done" if lane_result.status == "done" else "failed"
        self._update_lane_status(task.feature_id, status)
        return status

    def _update_lane_status(self, feature_id: str, status: str) -> None:
        update_lane_status(self.lanes_path, feature_id, status)

    def _read_lanes_json(self) -> dict[str, Any]:
        if not self.lanes_path.exists():
            return {"lanes": []}
        try:
            data = json.loads(self.lanes_path.read_text())
        except json.JSONDecodeError:
            logger.warning("invalid lanes JSON in %s; resetting", self.lanes_path)
            return {"lanes": []}
        if not isinstance(data, dict):
            return {"lanes": []}
        lanes = data.get("lanes")
        if not isinstance(lanes, list):
            data["lanes"] = []
        return data

    def _write_lanes_json(self, data: dict[str, Any]) -> None:
        self.lanes_path.parent.mkdir(parents=True, exist_ok=True)
        self.lanes_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="xmuse autonomous master loop")
    parser.add_argument("--max-hours", type=float, default=10.0, help="Global timeout in hours")
    parser.add_argument("--max-concurrent", type=int, default=2, help="Max concurrent lanes")
    parser.add_argument("--lanes", default="xmuse/feature_lanes.json", help="Feature lanes file")
    parser.add_argument(
        "--auto-discovery",
        default="xmuse/auto_discovery.py",
        help="auto_discovery.py path",
    )
    parser.add_argument("--agents", default="xmuse/agents.json", help="Agent registry config")
    return parser.parse_args(argv)


async def main(args: argparse.Namespace) -> MasterLoopSummary:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    loop = MasterLoop.from_defaults(
        lanes_path=Path(args.lanes),
        auto_discovery_path=Path(args.auto_discovery),
        agents_path=Path(args.agents),
        max_hours=args.max_hours,
        max_concurrent=args.max_concurrent,
    )
    loop.install_signal_handlers()
    summary = await loop.run()
    logger.info("master loop exited: %s", summary)
    return summary


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
