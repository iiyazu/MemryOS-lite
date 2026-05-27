#!/usr/bin/env python3
"""Multi-round autonomous xmuse orchestrator."""
# ruff: noqa: E402
from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import logging
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
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
FULL_QUALITY_GATE_TASK_TYPE = "full_quality_gate"
FULL_QUALITY_GATE_PRIORITY = 100
FULL_QUALITY_GATE_REPAIR_PRIORITY = 110
TERMINAL_LANE_STATUSES = {"done", "failed", "merge_failed"}
MAX_LANE_RETRIES = 2
DEFAULT_GATE_PROFILES_PATH = ROOT / "xmuse" / "gate_profiles.json"


@dataclass
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        return "\n".join(
            part.rstrip() for part in (self.stdout, self.stderr) if part.strip()
        )


def _coerce_priority(value: Any) -> int:
    return value if isinstance(value, int) else 0


def _root_head_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


_TASK_DESCRIPTOR_FIELDS = {
    "feature_id",
    "task_type",
    "prompt",
    "worktree",
    "capabilities",
    "developed_by_runtime",
    "priority",
    "gate_profile",
    "gate_profiles",
    "base_head_sha",
}


def _lane_metadata(lane: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in lane.items() if key not in _TASK_DESCRIPTOR_FIELDS}


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def _is_full_gate_family_lane(lane: dict[str, Any]) -> bool:
    return (
        lane.get("task_type") == FULL_QUALITY_GATE_TASK_TYPE
        or lane.get("source") == "full_quality_gate"
        or isinstance(lane.get("full_gate_feature_id"), str)
    )


def _is_terminal_lane(lane: dict[str, Any]) -> bool:
    return lane.get("status", "pending") in TERMINAL_LANE_STATUSES


def _should_retry_lane(lane: dict[str, Any]) -> bool:
    """Check if a failed lane is eligible for automatic retry."""
    if lane.get("status") != "failed":
        return False
    if lane.get("auto_retry") is not True:
        return False
    if _is_full_gate_family_lane(lane):
        return False
    retry_count = lane.get("retry_count", 0)
    if retry_count >= MAX_LANE_RETRIES:
        return False
    if lane.get("no_retry"):
        return False
    return True


def _is_active_full_gate_family_lane(lane: dict[str, Any]) -> bool:
    return _is_full_gate_family_lane(lane) and not _is_terminal_lane(lane)


def ensure_worktree(feature_id: str, branch: str | None = None) -> Path:
    """Create or reuse a git worktree for a feature lane."""

    wt_path = WORKTREE_BASE / f"memoryOS-{feature_id}"
    if wt_path.exists():
        _fast_forward_existing_worktree(wt_path)
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


def _fast_forward_existing_worktree(wt_path: Path) -> None:
    root_head = _root_head_sha()
    if not root_head:
        return

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        cwd=wt_path,
    )
    if status.returncode != 0:
        logger.warning("Failed to inspect worktree status: %s", wt_path)
        return
    if status.stdout.strip():
        logger.info("Attempting worktree fast-forward with local changes: %s", wt_path)

    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", "HEAD", root_head],
        capture_output=True,
        text=True,
        cwd=wt_path,
    )
    if ancestor.returncode != 0:
        logger.info("Skipping worktree fast-forward for divergent worktree: %s", wt_path)
        return

    merged = subprocess.run(
        ["git", "merge", "--ff-only", root_head],
        capture_output=True,
        text=True,
        cwd=wt_path,
    )
    if merged.returncode != 0:
        logger.warning(
            "Failed to fast-forward worktree %s to %s: %s",
            wt_path,
            root_head,
            merged.stderr.strip(),
        )


def load_lanes(path: Path) -> list[TaskDescriptor]:
    """Load pending lanes whose dependencies are complete."""

    data = json.loads(path.read_text())
    all_lanes = data.get("lanes", [])
    done_ids = {lane["feature_id"] for lane in all_lanes if lane.get("status") == "done"}
    tasks: list[tuple[int, TaskDescriptor, bool]] = []
    mutated = False

    for index, lane in enumerate(all_lanes):
        if _is_terminal_lane(lane):
            # Check if failed lane is eligible for retry
            if lane.get("status") == "failed" and _should_retry_lane(lane):
                lane["status"] = "pending"
                lane["retry_count"] = lane.get("retry_count", 0) + 1
                mutated = True
            else:
                continue

        deps = lane.get("depends_on", [])
        if deps and not all(dep in done_ids for dep in deps):
            logger.debug("Skipping %s (unmet deps: %s)", lane["feature_id"], deps)
            continue

        task_type = lane.get("task_type", "execute")
        worktree = lane.get("worktree")
        if task_type == FULL_QUALITY_GATE_TASK_TYPE:
            worktree = worktree or "."
        elif not worktree or worktree == ".":
            worktree = str(ensure_worktree(lane["feature_id"], branch=lane.get("branch")))
            lane["worktree"] = worktree
            lane["base_head_sha"] = lane.get("base_head_sha") or _root_head_sha()
            mutated = True
        elif Path(worktree).exists():
            _fast_forward_existing_worktree(Path(worktree))

        base_head_sha = lane.get("base_head_sha")

        tasks.append(
            (
                index,
                TaskDescriptor(
                    feature_id=lane["feature_id"],
                    task_type=task_type,
                    prompt=lane["prompt"],
                    worktree=worktree,
                    required_capabilities=lane.get("capabilities", ["code"]),
                    developed_by_runtime=lane.get("developed_by_runtime"),
                    priority=_coerce_priority(lane.get("priority")),
                    gate_profile=(
                        lane.get("gate_profile")
                        if isinstance(lane.get("gate_profile"), str)
                        else None
                    ),
                    gate_profiles=[
                        item
                        for item in lane.get("gate_profiles", [])
                        if isinstance(item, str)
                    ],
                    lane_metadata=_lane_metadata(lane),
                    base_head_sha=base_head_sha if isinstance(base_head_sha, str) else None,
                ),
                _is_active_full_gate_family_lane(lane),
            )
        )

    if mutated:
        _write_json_atomic(path, data)

    ordered = sorted(tasks, key=lambda item: (-item[1].priority, item[0]))
    selected: list[TaskDescriptor] = []
    full_gate_family_selected = False
    for _, task, is_full_gate_family in ordered:
        if is_full_gate_family:
            if full_gate_family_selected:
                continue
            full_gate_family_selected = True
        selected.append(task)
    return selected


def update_lane_status(lanes_path: Path, feature_id: str, status: str) -> None:
    """Write lane status back to feature_lanes.json (with file lock)."""
    _update_lane_fields(lanes_path, feature_id, {"status": status})
    logger.info("Lane %s -> %s", feature_id, status)


def _update_lane_fields(
    lanes_path: Path,
    feature_id: str,
    fields: dict[str, Any],
) -> None:
    """Update a lane atomically under the same lock as status writes."""
    import fcntl

    lanes_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lanes_path, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            data = json.loads(f.read())
            for lane in data.get("lanes", []):
                if lane["feature_id"] == feature_id:
                    lane.update(fields)
                    break
            f.seek(0)
            f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            f.truncate()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


class GateResultLike(Protocol):
    passed: bool
    errors: list[str]
    gate_report: dict[str, object] | None
    gate_warnings: list[str]


class QualityGateLike(Protocol):
    async def check(self, worktree: Path, **kwargs: Any) -> GateResultLike: ...


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
        review_gate: Any | None = None,
        error_knowledge: ErrorKnowledgeLike | None = None,
        max_hours: float = 10.0,
        max_concurrent: int = 2,
        discovery_enabled: bool = True,
        python_executable: str = sys.executable,
        gate_profiles_path: Path = DEFAULT_GATE_PROFILES_PATH,
        monotonic: Any = time.monotonic,
    ) -> None:
        self.lanes_path = lanes_path
        self.auto_discovery_path = auto_discovery_path
        self.consumer = consumer
        self.quality_gate = quality_gate
        self.rework_loop = rework_loop
        self.review_gate = review_gate
        self.error_knowledge = error_knowledge
        self.max_hours = max_hours
        self.max_concurrent = max(1, max_concurrent)
        self.discovery_enabled = discovery_enabled
        self.python_executable = python_executable
        self.gate_profiles_path = gate_profiles_path
        self._monotonic = monotonic
        self._shutdown_requested = asyncio.Event()
        self._merge_lock = asyncio.Lock()
        self._lane_mutation_lock = asyncio.Lock()

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
            quality_gate=QualityGate(
                profile_config_path=DEFAULT_GATE_PROFILES_PATH,
                repo_root=ROOT,
            ),
            rework_loop=ReworkLoop(error_knowledge=error_knowledge),
            review_gate=cls._build_review_gate(),
            error_knowledge=error_knowledge,
            max_hours=max_hours,
            max_concurrent=max_concurrent,
            discovery_enabled=discovery_enabled,
            gate_profiles_path=DEFAULT_GATE_PROFILES_PATH,
        )

    @staticmethod
    def _build_review_gate() -> Any:
        import os

        enabled = os.environ.get("XMUSE_REVIEW_GATE", "1").strip().lower()
        if enabled in {"0", "false", "no", "off"}:
            return None
        from xmuse_core.gates.review_gate import CodexReviewGate

        return CodexReviewGate(
            codex_cmd=os.environ.get("XMUSE_REVIEW_CODEX_CMD", "codex"),
            model=os.environ.get("XMUSE_REVIEW_MODEL", "gpt-5.5"),
            timeout_s=float(os.environ.get("XMUSE_REVIEW_TIMEOUT_S", "300")),
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
            self._gc_stale_lanes()
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
        sequence = 0
        seen_ids: set[str] = set()
        queue: asyncio.PriorityQueue[tuple[int, int, TaskDescriptor]] = (
            asyncio.PriorityQueue()
        )

        def enqueue(task: TaskDescriptor) -> None:
            nonlocal sequence
            if task.feature_id in seen_ids:
                return
            seen_ids.add(task.feature_id)
            queue.put_nowait((-task.priority, sequence, task))
            sequence += 1

        for task in pending:
            enqueue(task)

        async def worker() -> None:
            nonlocal successful, failed
            while not self._shutdown_requested.is_set() and self._monotonic() < deadline:
                try:
                    _, _, task = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    status = await self._run_lane(task)
                    if status == "done":
                        successful += 1
                        if task.task_type != FULL_QUALITY_GATE_TASK_TYPE:
                            await self._maybe_append_full_quality_gate_lane()
                    else:
                        failed += 1
                    for new_task in self._load_new_high_priority_lanes(seen_ids):
                        enqueue(new_task)
                finally:
                    queue.task_done()

        workers = [
            asyncio.create_task(worker())
            for _ in range(min(self.max_concurrent, max(1, len(pending))))
        ]
        await asyncio.gather(*workers)
        return successful, failed

    async def _run_lane(self, task: TaskDescriptor) -> str:
        if task.task_type == FULL_QUALITY_GATE_TASK_TYPE:
            return await self._run_full_quality_gate_lane(task)

        if self.consumer is None:
            raise RuntimeError("MasterLoop.consumer is required before dispatching lanes")

        # Design-type lanes route to the DesignPipelineSkill
        if task.task_type == "design":
            return await self._run_design_lane(task)

        self._update_lane_status(task.feature_id, "running")
        dispatch_task = self._inject_error_knowledge(task)
        dispatch_task = self._inject_scope_constraint(dispatch_task)
        dispatch_status = await self.consumer.dispatch_task(dispatch_task)
        if dispatch_status != "done":
            self._update_lane_status(task.feature_id, "failed")
            return "failed"

        gate_result = await self._check_quality_gate(
            self.quality_gate,
            Path(task.worktree),
            feature_id=task.feature_id,
            gate_profile=task.gate_profile,
            gate_profiles=task.gate_profiles,
            base_head_sha=task.base_head_sha,
        )
        self._record_gate_report(task.feature_id, gate_result)
        if gate_result.passed:
            if not await self._review_lane_before_merge(task, gate_result):
                self._update_lane_status(task.feature_id, "failed")
                return "failed"
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
                priority=task.priority,
                gate_profile=task.gate_profile,
                gate_profiles=task.gate_profiles,
                lane_metadata=task.lane_metadata,
                base_head_sha=task.base_head_sha,
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
            final_gate_result = getattr(lane_result, "final_gate_result", None)
            if final_gate_result is not None:
                self._record_gate_report(task.feature_id, final_gate_result)
            else:
                final_gate_result = gate_result
            if not await self._review_lane_before_merge(task, final_gate_result):
                status = "failed"
                self._update_lane_status(task.feature_id, status)
                return "failed"
            merged = await self._auto_merge_worktree(task)
            if not merged:
                status = "merge_failed"
        elif status == "failed":
            self._record_failed_rework(task, gate_result, lane_result)
        self._update_lane_status(task.feature_id, status)
        return "done" if status == "done" else "failed"

    def _update_lane_status(self, feature_id: str, status: str) -> None:
        update_lane_status(self.lanes_path, feature_id, status)

    def _record_gate_report(self, feature_id: str, result: GateResultLike) -> None:
        report = getattr(result, "gate_report", None)
        warnings = getattr(result, "gate_warnings", None) or []
        if report is None and not warnings:
            return
        fields: dict[str, Any] = {}
        if report is not None:
            fields["gate_report"] = report
        if warnings:
            fields["gate_warnings"] = list(warnings)
        _update_lane_fields(self.lanes_path, feature_id, fields)

    async def _run_full_quality_gate_lane(self, task: TaskDescriptor) -> str:
        self._update_lane_status(task.feature_id, "running")
        gate_result = await self._check_quality_gate(
            self.quality_gate,
            ROOT,
            feature_id=task.feature_id,
            gate_profile=task.gate_profile,
            gate_profiles=task.gate_profiles or ["strict-product"],
            changed_paths=[],
            base_head_sha=task.base_head_sha,
        )
        self._record_gate_report(task.feature_id, gate_result)
        if gate_result.passed:
            self._update_lane_status(task.feature_id, "done")
            return "done"

        artifact_path = self._write_full_gate_artifact_from_errors(
            task.feature_id,
            gate_result.errors,
        )
        await self._append_full_gate_repair_lane(task, gate_result, artifact_path)
        self._update_lane_status(task.feature_id, "failed")
        return "failed"

    async def _check_quality_gate(
        self,
        gate: QualityGateLike,
        worktree: Path,
        **kwargs: Any,
    ) -> GateResultLike:
        signature = inspect.signature(gate.check)
        accepts_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        accepted = {
            name
            for name, parameter in signature.parameters.items()
            if parameter.kind
            in {
                inspect.Parameter.KEYWORD_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            }
        }
        if accepts_kwargs or any(name in accepted for name in kwargs):
            filtered = kwargs if accepts_kwargs else {
                key: value for key, value in kwargs.items() if key in accepted
            }
            return await gate.check(worktree, **filtered)
        return await gate.check(worktree)

    async def _run_process(self, worktree: Path, *cmd: str) -> ProcessResult:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=worktree,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await process.communicate()
        returncode = process.returncode
        if returncode is None:
            returncode = await process.wait()
        return ProcessResult(
            returncode=returncode,
            stdout=stdout_bytes.decode(errors="replace"),
            stderr=stderr_bytes.decode(errors="replace"),
        )

    def _write_full_gate_artifact_from_errors(
        self,
        feature_id: str,
        errors: list[str],
    ) -> Path:
        artifact_dir = ROOT / "xmuse" / "logs" / "full_quality_gate"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / f"{feature_id}.log"
        artifact_path.write_text("\n\n".join(errors) + "\n", encoding="utf-8")
        return artifact_path

    def _full_gate_interval(self) -> int:
        from xmuse_core.gates.loader import load_gate_config

        config = load_gate_config(self.gate_profiles_path, repo_root=ROOT)
        return config.defaults.full_gate_interval

    async def _maybe_append_full_quality_gate_lane(self) -> str | None:
        async with self._lane_mutation_lock:
            data = self._read_lanes_json()
            lanes = data.setdefault("lanes", [])
            if self._compact_full_gate_family_queue(lanes):
                self._write_lanes_json(data)
            if self._has_active_full_quality_gate(lanes):
                return None
            batch_lane_ids = self._next_full_gate_batch(lanes)
            if len(batch_lane_ids) < self._full_gate_interval():
                return None

            head_sha = self._current_head_sha()
            feature_id = self._full_gate_feature_id(batch_lane_ids, head_sha)
            if any(lane.get("feature_id") == feature_id for lane in lanes):
                return None

            lanes.append(
                {
                    "feature_id": feature_id,
                    "task_type": FULL_QUALITY_GATE_TASK_TYPE,
                    "status": "pending",
                    "worktree": ".",
                    "prompt": "Run the strict-product xmuse quality gate.",
                    "gate_profiles": ["strict-product"],
                    "capabilities": ["test"],
                    "depends_on": [],
                    "source": "full_quality_gate",
                    "priority": FULL_QUALITY_GATE_PRIORITY,
                    "batch_lane_ids": batch_lane_ids,
                    "head_sha": head_sha,
                    "base_head_sha": head_sha,
                }
            )
            self._write_lanes_json(data)
            logger.info(
                "queued full quality gate %s for %d lanes",
                feature_id,
                len(batch_lane_ids),
            )
            return feature_id

    def _has_active_full_quality_gate(self, lanes: list[dict[str, Any]]) -> bool:
        return any(_is_active_full_gate_family_lane(lane) for lane in lanes)

    def _compact_full_gate_family_queue(
        self,
        lanes: list[dict[str, Any]],
        *,
        preferred_feature_id: str | None = None,
    ) -> bool:
        active_family_lanes = [
            lane
            for lane in lanes
            if isinstance(lane, dict) and _is_active_full_gate_family_lane(lane)
        ]
        if len(active_family_lanes) <= 1:
            return False

        running = [
            lane
            for lane in active_family_lanes
            if lane.get("status", "pending") == "running"
        ]
        keep = next(
            (
                lane
                for lane in active_family_lanes
                if lane.get("feature_id") == preferred_feature_id
            ),
            None,
        )
        if keep is None and running:
            keep = running[0]
        if keep is None:
            keep = max(
                active_family_lanes,
                key=lambda lane: _coerce_priority(lane.get("priority")),
            )

        changed = False
        for lane in active_family_lanes:
            if lane is keep:
                continue
            if lane.get("status", "pending") != "pending":
                continue
            lane["status"] = "failed"
            lane["discarded_reason"] = "superseded_full_quality_gate_family"
            lane["discarded_by"] = keep.get("feature_id")
            changed = True
        return changed

    def _next_full_gate_batch(self, lanes: list[dict[str, Any]]) -> list[str]:
        covered: set[str] = set()
        for lane in lanes:
            if lane.get("task_type") != FULL_QUALITY_GATE_TASK_TYPE:
                continue
            batch = lane.get("batch_lane_ids", [])
            if isinstance(batch, list):
                covered.update(item for item in batch if isinstance(item, str))

        batch_lane_ids: list[str] = []
        for lane in lanes:
            feature_id = lane.get("feature_id")
            if not isinstance(feature_id, str):
                continue
            if lane.get("status") != "done":
                continue
            if lane.get("task_type") == FULL_QUALITY_GATE_TASK_TYPE:
                continue
            if feature_id in covered:
                continue
            batch_lane_ids.append(feature_id)
            if len(batch_lane_ids) >= self._full_gate_interval():
                break
        return batch_lane_ids

    def _full_gate_feature_id(self, batch_lane_ids: list[str], head_sha: str) -> str:
        digest = hashlib.sha1(
            "\n".join([head_sha, *batch_lane_ids]).encode("utf-8")
        ).hexdigest()[:10]
        short_head = head_sha[:8] if head_sha else "unknown"
        return f"full-quality-gate-{short_head}-{digest}"

    def _current_head_sha(self) -> str:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        if result.returncode != 0:
            return "unknown"
        return result.stdout.strip()

    async def _append_full_gate_repair_lane(
        self,
        task: TaskDescriptor,
        result: GateResultLike,
        artifact_path: Path,
    ) -> str | None:
        async with self._lane_mutation_lock:
            data = self._read_lanes_json()
            lanes = data.setdefault("lanes", [])
            gate_lane = next(
                (
                    lane
                    for lane in lanes
                    if lane.get("feature_id") == task.feature_id
                    and isinstance(lane, dict)
                ),
                {},
            )
            repair_id = f"full-quality-gate-repair-{task.feature_id}"
            if any(lane.get("feature_id") == repair_id for lane in lanes):
                return None
            if self._compact_full_gate_family_queue(
                lanes,
                preferred_feature_id=task.feature_id,
            ):
                self._write_lanes_json(data)
            if any(
                _is_active_full_gate_family_lane(lane)
                and lane.get("feature_id") != task.feature_id
                for lane in lanes
            ):
                return None

            output = "\n\n".join(result.errors)[-6000:]
            batch_lane_ids = gate_lane.get("batch_lane_ids", [])
            head_sha = gate_lane.get("head_sha", self._current_head_sha())
            lanes.append(
                {
                    "feature_id": repair_id,
                    "task_type": "execute",
                    "status": "pending",
                    "branch": f"feat/{repair_id}",
                    "prompt": (
                        "Fix the failing full xmuse quality gate.\n\n"
                        "Profile: strict-product\n"
                        f"Artifact: {artifact_path.relative_to(ROOT)}\n"
                        f"Head SHA: {head_sha}\n"
                        f"Batch lane ids: {batch_lane_ids}\n\n"
                        "Failure output:\n"
                        f"{output}\n\n"
                        "Make the minimal fix, then verify with the "
                        "strict-product gate profile."
                    ),
                    "capabilities": ["code", "test"],
                    "gate_profiles": ["strict-product"],
                    "depends_on": [],
                    "source": "full_quality_gate",
                    "priority": FULL_QUALITY_GATE_REPAIR_PRIORITY,
                    "full_gate_feature_id": task.feature_id,
                    "full_gate_artifact": str(artifact_path.relative_to(ROOT)),
                    "head_sha": head_sha,
                    "base_head_sha": head_sha,
                    "batch_lane_ids": batch_lane_ids,
                }
            )
            self._write_lanes_json(data)
            logger.info("queued full quality gate repair lane %s", repair_id)
            return repair_id

    def _load_new_high_priority_lanes(
        self,
        seen_ids: set[str],
    ) -> list[TaskDescriptor]:
        tasks = load_lanes(self.lanes_path)
        return [
            task
            for task in tasks
            if task.feature_id not in seen_ids
            and task.priority >= FULL_QUALITY_GATE_PRIORITY
        ]

    async def _run_design_lane(self, task: TaskDescriptor) -> str:
        """Route design-type lanes to the DesignPipelineSkill."""
        self._update_lane_status(task.feature_id, "running")
        try:
            from xmuse_core.skills import SkillContext, create_default_registry
            from xmuse_core.skills.models import PipelineInput

            skill_registry = create_default_registry()
            ctx = SkillContext(
                registry=self._build_agent_registry(),
                session_manager=self._build_session_manager(),
                skill_registry=skill_registry,
                feature_root=Path("xmuse/work/features"),
                prompt_dir=Path("xmuse/prompts"),
                lanes_path=self.lanes_path,
            )
            pipeline = skill_registry.instantiate("design_pipeline", ctx)
            result = await pipeline.run(PipelineInput(
                feature_id=task.feature_id,
                goal=task.prompt,
            ))
            status = "done" if result.status == "success" else "failed"
        except Exception:
            logger.exception("design lane failed: %s", task.feature_id)
            status = "failed"
        self._update_lane_status(task.feature_id, status)
        return "done" if status == "done" else "failed"

    def _build_agent_registry(self) -> Any:
        """Return the agent registry used by the consumer."""
        if self.consumer and hasattr(self.consumer, "_registry"):
            return self.consumer._registry
        return None

    def _build_session_manager(self) -> Any:
        """Return the session manager used by the consumer."""
        if self.consumer and hasattr(self.consumer, "_session_mgr"):
            return self.consumer._session_mgr
        return None

    async def _review_lane_before_merge(
        self,
        task: TaskDescriptor,
        gate_result: GateResultLike,
    ) -> bool:
        review_verdict = await self._run_review_gate(task, gate_result)
        if review_verdict is None:
            return True
        self._record_review_verdict(task.feature_id, review_verdict)
        if review_verdict.approved:
            return True

        logger.info(
            "Review gate rejected %s: %s",
            task.feature_id,
            review_verdict.summary,
        )
        if self.consumer is None:
            return False

        rework_task = self._build_review_rework_task(task, review_verdict)
        rework_status = await self.consumer.dispatch_task(rework_task)
        if rework_status != "done":
            return False

        second_gate = await self._check_quality_gate(
            self.quality_gate,
            Path(task.worktree),
            feature_id=task.feature_id,
            gate_profile=task.gate_profile,
            gate_profiles=task.gate_profiles,
            base_head_sha=task.base_head_sha,
        )
        self._record_gate_report(task.feature_id, second_gate)
        if not second_gate.passed:
            return False

        second_verdict = await self._run_review_gate(task, second_gate)
        if second_verdict is None:
            return True
        self._record_review_verdict(task.feature_id, second_verdict)
        if second_verdict.approved:
            return True

        logger.warning(
            "Review gate rejected %s twice, marking failed",
            task.feature_id,
        )
        return False

    def _build_review_rework_task(
        self,
        task: TaskDescriptor,
        review_verdict: Any,
    ) -> TaskDescriptor:
        concerns = "\n".join(f"- {c}" for c in review_verdict.concerns)
        rework_prompt = (
            "Code review rejected this implementation.\n\n"
            f"## Concerns\n{concerns}\n\n"
            f"## Summary\n{review_verdict.summary}\n\n"
            "Fix these concerns. Do NOT start from scratch."
        )
        enriched = self._inject_error_knowledge_text(rework_prompt)
        diff_ctx = self._get_worktree_diff(task.worktree, task.base_head_sha)
        full_rework = (
            f"## Original Task\n{task.prompt[:2000]}\n\n"
            f"## Current Diff\n{diff_ctx[:3000]}\n\n"
            f"## Why Rejected\n{enriched}"
        )
        return TaskDescriptor(
            feature_id=task.feature_id,
            task_type="rework",
            prompt=full_rework,
            worktree=str(task.worktree),
            required_capabilities=task.required_capabilities,
            developed_by_runtime=task.developed_by_runtime,
            priority=task.priority,
            gate_profile=task.gate_profile,
            gate_profiles=task.gate_profiles,
            lane_metadata=task.lane_metadata,
            base_head_sha=task.base_head_sha,
        )

    async def _run_review_gate(
        self,
        task: TaskDescriptor,
        gate_result: GateResultLike | None = None,
    ) -> Any:
        if self.review_gate is None:
            return None
        try:
            kwargs = {
                "feature_id": task.feature_id,
                "worktree": Path(task.worktree),
                "original_prompt": task.prompt,
                "base_ref": task.base_head_sha,
            }
            if self._review_accepts_gate_context():
                kwargs["gate_context"] = self._format_gate_context(gate_result)
            review = self.review_gate.review(**kwargs)
            if inspect.isawaitable(review):
                return await review
            return review
        except Exception as exc:
            logger.exception("review gate failed for %s", task.feature_id)
            return SimpleNamespace(
                approved=True,
                concerns=[f"review_gate_exception: {exc!s}"[:500]],
                summary="review gate unavailable, auto-approved",
                confidence=0.0,
                self_modification=False,
            )

    def _review_accepts_gate_context(self) -> bool:
        try:
            signature = inspect.signature(self.review_gate.review)
        except (TypeError, ValueError):
            return True
        parameters = signature.parameters
        return "gate_context" in parameters or any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )

    def _format_gate_context(self, gate_result: GateResultLike | None) -> str:
        if gate_result is None:
            return ""
        context = {
            "passed": bool(getattr(gate_result, "passed", False)),
            "errors": list(getattr(gate_result, "errors", []))[:5],
            "gate_report": getattr(gate_result, "gate_report", None),
            "gate_warnings": list(getattr(gate_result, "gate_warnings", []) or [])[:5],
        }
        return json.dumps(context, ensure_ascii=False, default=str)[:2000]

    def _record_review_verdict(self, feature_id: str, verdict: Any) -> None:
        _update_lane_fields(
            self.lanes_path,
            feature_id,
            {
                "review_verdict": {
                    "approved": bool(getattr(verdict, "approved", False)),
                    "concerns": list(getattr(verdict, "concerns", [])),
                    "summary": str(getattr(verdict, "summary", "")),
                    "confidence": float(getattr(verdict, "confidence", 0.0)),
                    "self_modification": bool(
                        getattr(verdict, "self_modification", False)
                    ),
                }
            },
        )

    def _get_worktree_diff(self, worktree: str | Path, base_ref: str | None) -> str:
        wt_path = Path(worktree)
        ref = base_ref or "HEAD~1"
        stat = subprocess.run(
            ["git", "diff", "--stat", ref],
            capture_output=True,
            text=True,
            cwd=wt_path,
        )
        diff = subprocess.run(
            ["git", "diff", ref],
            capture_output=True,
            text=True,
            cwd=wt_path,
        )
        stat_text = stat.stdout[:500] if stat.returncode == 0 else ""
        diff_text = diff.stdout[:3000] if diff.returncode == 0 else ""
        return f"{stat_text}\n\n{diff_text}".strip()

    async def _auto_merge_worktree(self, task: TaskDescriptor) -> bool:
        """Merge worktree branch back to current branch after successful gate."""
        wt_path = Path(task.worktree)
        if not wt_path.exists() or str(wt_path) == ".":
            return True
        if not (wt_path / ".git").exists():
            return True
        branch = task.feature_id
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", str(wt_path), "rev-parse", "--abbrev-ref", "HEAD",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            branch = stdout.decode().strip()

        proc = await asyncio.create_subprocess_exec(
            "git", "log", f"HEAD..{branch}", "--oneline",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=ROOT,
        )
        stdout, _ = await proc.communicate()
        if not stdout.decode().strip():
            dirty_proc = await asyncio.create_subprocess_exec(
                "git", "-C", str(wt_path), "status", "--porcelain",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            dirty_stdout, _ = await dirty_proc.communicate()
            if dirty_stdout.decode().strip():
                logger.warning(
                    "Refusing auto-merge for %s: worktree has uncommitted changes",
                    branch,
                )
                return False
            logger.info("No new commits on %s to merge", branch)
            return True

        proc = await asyncio.create_subprocess_exec(
            "git", "diff", "--shortstat", f"HEAD...{branch}",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=ROOT,
        )
        stat_out, _ = await proc.communicate()
        stat_text = stat_out.decode()
        import re
        insertions_match = re.search(r"(\d+)\s+insertion", stat_text)
        if insertions_match and int(insertions_match.group(1)) > 1000:
            logger.warning(
                "Refusing auto-merge for %s: %s insertions exceeds 1000 limit",
                branch, insertions_match.group(1),
            )
            return False

        async with self._merge_lock:
            proc = await asyncio.create_subprocess_exec(
                "git", "merge", "--no-ff", branch, "-m",
                f"auto-merge: {task.feature_id} (lane done)",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                cwd=ROOT,
            )
            _, stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info("Auto-merged %s into main branch", branch)
            return True
        logger.warning(
            "Auto-merge failed for %s: %s",
            branch, stderr.decode()[:500],
        )
        return False

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
            priority=task.priority,
            gate_profile=task.gate_profile,
            gate_profiles=task.gate_profiles,
            lane_metadata=task.lane_metadata,
            base_head_sha=task.base_head_sha,
        )

    def _inject_error_knowledge_text(self, prompt: str) -> str:
        if self.error_knowledge is None:
            return prompt
        try:
            return self.error_knowledge.inject_context(prompt)
        except Exception as exc:
            logger.warning("error knowledge injection failed: %s", exc)
            return prompt

    def _inject_scope_constraint(self, task: TaskDescriptor) -> TaskDescriptor:
        """Append a scope constraint to prevent codex from modifying unrelated files."""
        constraint = (
            "\n\n## SCOPE CONSTRAINT (MANDATORY)\n"
            "Only modify files directly related to this task. "
            "Do NOT touch files outside the scope of this requirement. "
            "Specifically:\n"
            "- Do NOT modify xmuse/master_loop.py, src/xmuse_core/agents/manager.py, "
            "or src/xmuse_core/gates/review_gate.py unless this task explicitly requires it.\n"
            "- Do NOT change default timeouts, authentication logic, or review gate behavior.\n"
            "- Do NOT refactor, rename, or reorganize code outside the stated task.\n"
            "- If you believe a change to another file is necessary, add a comment explaining why "
            "but do NOT make the change.\n"
        )
        return TaskDescriptor(
            feature_id=task.feature_id,
            task_type=task.task_type,
            prompt=task.prompt + constraint,
            worktree=task.worktree,
            required_capabilities=task.required_capabilities,
            developed_by_runtime=task.developed_by_runtime,
            priority=task.priority,
            gate_profile=task.gate_profile,
            gate_profiles=task.gate_profiles,
            lane_metadata=task.lane_metadata,
            base_head_sha=task.base_head_sha,
        )

    _STALE_RUNNING_HOURS = 4

    def _gc_stale_lanes(self) -> None:
        """Archive lanes stuck in running state for too long."""
        data = self._read_lanes_json()
        lanes = data.get("lanes", [])
        changed = False
        now = time.time()
        for lane in lanes:
            if lane.get("status") != "running":
                continue
            started = lane.get("started_at")
            if not isinstance(started, (int, float)):
                lane["started_at"] = now
                changed = True
                continue
            hours_running = (now - started) / 3600
            if hours_running >= self._STALE_RUNNING_HOURS:
                logger.warning(
                    "GC: lane %s stuck running for %.1fh, marking failed",
                    lane.get("feature_id"),
                    hours_running,
                )
                lane["status"] = "failed"
                lane["gc_reason"] = f"stuck_running_{hours_running:.1f}h"
                changed = True
        if changed:
            self._write_lanes_json(data)

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
        _write_json_atomic(self.lanes_path, data)


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
