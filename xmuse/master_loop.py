#!/usr/bin/env python3
"""Multi-round autonomous xmuse orchestrator."""
# ruff: noqa: E402
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import subprocess
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

from error_knowledge import ErrorKnowledge

from xmuse_core.agents.consumer import TaskDescriptor, WorklistConsumer
from xmuse_core.agents.launchers.codex import CodexLauncher
from xmuse_core.agents.manager import SessionManager
from xmuse_core.agents.memoryos_client import MemoryOSClient
from xmuse_core.agents.registry import AgentRegistry, AgentRuntime

logger = logging.getLogger("xmuse.master_loop")
WORKTREE_BASE = ROOT.parent


def ensure_worktree(feature_id: str, branch: str | None = None) -> Path:
    """Create or reuse a git worktree for a feature lane."""

    wt_path = WORKTREE_BASE / f"memoryOS-{feature_id}"
    if wt_path.exists():
        return wt_path

    branch_name = branch or f"feat/{feature_id}"
    result = subprocess.run(
        ["git", "worktree", "add", "-b", branch_name, str(wt_path), "HEAD"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if result.returncode != 0:
        subprocess.run(
            ["git", "worktree", "add", str(wt_path), branch_name],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )

    if wt_path.exists():
        logger.info("Worktree ready: %s", wt_path)
    else:
        logger.warning("Failed to create worktree for %s: %s", feature_id, result.stderr)
    return wt_path


def load_lanes(path: Path) -> list[TaskDescriptor]:
    """Load pending lanes whose dependencies are complete."""

    data = json.loads(path.read_text())
    all_lanes = data.get("lanes", [])
    done_ids = {lane["feature_id"] for lane in all_lanes if lane.get("status") == "done"}
    tasks: list[TaskDescriptor] = []

    for lane in all_lanes:
        if lane.get("status") in ("done", "failed"):
            continue

        deps = lane.get("depends_on", [])
        if deps and not all(dep in done_ids for dep in deps):
            logger.debug("Skipping %s (unmet deps: %s)", lane["feature_id"], deps)
            continue

        worktree = lane.get("worktree")
        if not worktree or worktree == ".":
            worktree = str(ensure_worktree(lane["feature_id"], branch=lane.get("branch")))

        tasks.append(
            TaskDescriptor(
                feature_id=lane["feature_id"],
                task_type=lane.get("task_type", "execute"),
                prompt=lane["prompt"],
                worktree=worktree,
                required_capabilities=lane.get("capabilities", ["code"]),
                developed_by_runtime=lane.get("developed_by_runtime"),
            )
        )

    return tasks


def update_lane_status(lanes_path: Path, feature_id: str, status: str) -> None:
    """Write lane status back to feature_lanes.json."""

    data = json.loads(lanes_path.read_text())
    for lane in data.get("lanes", []):
        if lane["feature_id"] == feature_id:
            lane["status"] = status
            break
    lanes_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    logger.info("Lane %s -> %s", feature_id, status)


class GateResultLike(Protocol):
    passed: bool
    errors: list[str]


class QualityGateLike(Protocol):
    async def check(self, worktree: Path) -> GateResultLike: ...


class LaneResultLike(Protocol):
    status: str
    final_errors: list[str] | None


class ReworkLoopLike(Protocol):
    async def run(
        self,
        lane: TaskDescriptor,
        initial_gate_result: GateResultLike,
        dispatch_fn: Any,
        gate: QualityGateLike,
        max_retries: int = 3,
    ) -> LaneResultLike: ...


class ConsumerLike(Protocol):
    async def dispatch_task(self, task: TaskDescriptor) -> str: ...
    def shutdown(self) -> None: ...


class ErrorKnowledgeLike(Protocol):
    def record_failure(
        self,
        lane_id: str,
        error_output: str,
        fix_output: str | None = None,
    ) -> dict[str, Any]: ...

    def inject_context(self, prompt: str) -> str: ...


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
        error_knowledge: ErrorKnowledgeLike | None = None,
        max_hours: float = 10.0,
        max_concurrent: int = 2,
        discovery_enabled: bool = True,
        python_executable: str = sys.executable,
        monotonic: Any = time.monotonic,
    ) -> None:
        self.lanes_path = lanes_path
        self.auto_discovery_path = auto_discovery_path
        self.consumer = consumer
        self.quality_gate = quality_gate
        self.rework_loop = rework_loop
        self.error_knowledge = error_knowledge
        self.max_hours = max_hours
        self.max_concurrent = max(1, max_concurrent)
        self.discovery_enabled = discovery_enabled
        self.python_executable = python_executable
        self._monotonic = monotonic
        self._shutdown_requested = asyncio.Event()
        self._merge_lock = asyncio.Lock()

    @classmethod
    def from_defaults(
        cls,
        *,
        lanes_path: Path = Path("xmuse/feature_lanes.json"),
        auto_discovery_path: Path = Path("xmuse/auto_discovery.py"),
        agents_path: Path = Path("xmuse/agents.json"),
        memoryos_url: str = "http://127.0.0.1:8000",
        max_hours: float = 10.0,
        max_concurrent: int = 2,
        discovery_enabled: bool = True,
    ) -> MasterLoop:
        from xmuse_core.agents.quality_gate import QualityGate
        from xmuse_core.agents.rework_loop import ReworkLoop

        registry = AgentRegistry.from_file(agents_path)
        memoryos = MemoryOSClient(base_url=memoryos_url)
        session_mgr = SessionManager(
            launchers={AgentRuntime.CODEX: CodexLauncher()},
            state_file=Path("xmuse/active_sessions.json"),
            memoryos_client=memoryos,
        )
        consumer = WorklistConsumer(
            registry=registry,
            session_mgr=session_mgr,
            max_concurrent=max_concurrent,
            on_complete=lambda fid, st: update_lane_status(lanes_path, fid, st),
        )
        error_knowledge = ErrorKnowledge()
        return cls(
            lanes_path=lanes_path,
            auto_discovery_path=auto_discovery_path,
            consumer=consumer,
            quality_gate=QualityGate(),
            rework_loop=ReworkLoop(error_knowledge=error_knowledge),
            error_knowledge=error_knowledge,
            max_hours=max_hours,
            max_concurrent=max_concurrent,
            discovery_enabled=discovery_enabled,
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
            new_discovered_count = 0
            if self.discovery_enabled:
                discovered = await self._run_auto_discovery()
                new_discovered_count = self._merge_discovered_lanes(discovered)
            pending = load_lanes(self.lanes_path)

            if not pending and new_discovered_count == 0:
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

    def _merge_discovered_lanes(self, discovered: list[dict[str, Any]]) -> int:
        data = self._read_lanes_json()
        lanes = data.setdefault("lanes", [])
        existing_ids = {lane.get("feature_id") for lane in lanes}
        new_count = 0
        changed = False
        for lane in discovered:
            if lane.get("feature_id") in existing_ids:
                continue
            lane.setdefault("status", "pending")
            lane.setdefault("depends_on", [])
            lanes.append(lane)
            existing_ids.add(lane.get("feature_id"))
            new_count += 1
            changed = True
        if changed:
            self._write_lanes_json(data)
        return new_count

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
        dispatch_task = self._inject_error_knowledge(task)
        dispatch_status = await self.consumer.dispatch_task(dispatch_task)
        if dispatch_status != "done":
            self._update_lane_status(task.feature_id, "failed")
            return "failed"

        gate_result = await self.quality_gate.check(Path(task.worktree))
        if gate_result.passed:
            merged = await self._auto_merge_worktree(task)
            self._update_lane_status(task.feature_id, "done" if merged else "merge_failed")
            return "done" if merged else "failed"

        async def dispatch_rework(rework_prompt: str, worktree: str | Path) -> str:
            enriched_prompt = self._inject_error_knowledge_text(rework_prompt)
            rework_task = TaskDescriptor(
                feature_id=task.feature_id,
                task_type="rework",
                prompt=enriched_prompt,
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
            max_retries=3,
        )
        status = "done" if lane_result.status == "done" else "failed"
        if status == "done":
            self._auto_merge_worktree(task)
        elif status == "failed":
            self._record_failed_rework(task, gate_result, lane_result)
        self._update_lane_status(task.feature_id, status)
        return status

    def _update_lane_status(self, feature_id: str, status: str) -> None:
        update_lane_status(self.lanes_path, feature_id, status)

    def _auto_merge_worktree(self, task: TaskDescriptor) -> None:
        """Merge worktree branch back to current branch after successful gate."""
        wt_path = Path(task.worktree)
        if not wt_path.exists() or str(wt_path) == ".":
            return
        branch = task.feature_id
        result = subprocess.run(
            ["git", "-C", str(wt_path), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
        # Check if there are commits to merge
        diff_check = subprocess.run(
            ["git", "log", f"HEAD..{branch}", "--oneline"],
            capture_output=True, text=True, cwd=ROOT,
        )
        if not diff_check.stdout.strip():
            logger.info("No new commits on %s to merge", branch)
            return
        merge_result = subprocess.run(
            ["git", "merge", "--no-ff", branch, "-m",
             f"auto-merge: {task.feature_id} (lane done)"],
            capture_output=True, text=True, cwd=ROOT,
        )
        if merge_result.returncode == 0:
            logger.info("Auto-merged %s into main branch", branch)
        else:
            logger.warning(
                "Auto-merge failed for %s: %s",
                branch, merge_result.stderr[:500],
            )

    def _record_failed_rework(
        self,
        task: TaskDescriptor,
        gate_result: GateResultLike,
        lane_result: LaneResultLike,
    ) -> None:
        if self.error_knowledge is None:
            return
        final_errors = lane_result.final_errors or gate_result.errors
        error_output = "\n\n".join(final_errors)
        try:
            self.error_knowledge.record_failure(task.feature_id, error_output)
        except Exception as exc:
            logger.warning("error knowledge record_failure failed: %s", exc)

    def _inject_error_knowledge(self, task: TaskDescriptor) -> TaskDescriptor:
        enriched_prompt = self._inject_error_knowledge_text(task.prompt)
        if enriched_prompt == task.prompt:
            return task
        return TaskDescriptor(
            feature_id=task.feature_id,
            task_type=task.task_type,
            prompt=enriched_prompt,
            worktree=task.worktree,
            required_capabilities=task.required_capabilities,
            developed_by_runtime=task.developed_by_runtime,
        )

    def _inject_error_knowledge_text(self, prompt: str) -> str:
        if self.error_knowledge is None:
            return prompt
        try:
            return self.error_knowledge.inject_context(prompt)
        except Exception as exc:
            logger.warning("error knowledge injection failed: %s", exc)
            return prompt

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
    parser.add_argument(
        "--concurrency",
        "--max-concurrent",
        dest="concurrency",
        type=int,
        default=2,
        help="Max concurrent lanes",
    )
    parser.add_argument("--lanes", default="xmuse/feature_lanes.json", help="Feature lanes file")
    parser.add_argument("--config", default="xmuse/agents.json", help="Agent registry config")
    parser.add_argument(
        "--memoryos-url",
        default="http://127.0.0.1:8000",
        help="MemoryOS API URL",
    )
    parser.add_argument(
        "--auto-discovery",
        default="xmuse/auto_discovery.py",
        help="auto_discovery.py path",
    )
    parser.add_argument("--agents", dest="config", help=argparse.SUPPRESS)
    parser.add_argument(
        "--no-discovery",
        action="store_true",
        help="Skip auto_discovery.py at round start",
    )
    return parser.parse_args(argv)


async def main(args: argparse.Namespace) -> MasterLoopSummary:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    loop = MasterLoop.from_defaults(
        lanes_path=Path(args.lanes),
        auto_discovery_path=Path(args.auto_discovery),
        agents_path=Path(args.config),
        memoryos_url=args.memoryos_url,
        max_hours=args.max_hours,
        max_concurrent=args.concurrency,
        discovery_enabled=not args.no_discovery,
    )
    loop.install_signal_handlers()
    summary = await loop.run()
    logger.info("master loop exited: %s", summary)
    return summary


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
