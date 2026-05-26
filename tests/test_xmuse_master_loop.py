from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "xmuse"))

from xmuse_core.agents.consumer import TaskDescriptor


@dataclass
class FakeGateResult:
    passed: bool
    errors: list[str]


@dataclass
class FakeLaneResult:
    status: str
    attempts: int = 0
    final_errors: list[str] | None = None


class FakeProcess:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self._stdout = stdout.encode()
        self._stderr = stderr.encode()
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


class FakeConsumer:
    def __init__(
        self,
        statuses: list[str] | None = None,
        *,
        shutdown_after_first: object | None = None,
    ) -> None:
        self.statuses = statuses or ["done"]
        self.dispatched: list[TaskDescriptor] = []
        self.shutdown_after_first = shutdown_after_first

    async def dispatch_task(self, task: TaskDescriptor) -> str:
        self.dispatched.append(task)
        if self.shutdown_after_first is not None and len(self.dispatched) == 1:
            self.shutdown_after_first.request_shutdown()
            await asyncio.sleep(0)
        if len(self.statuses) >= len(self.dispatched):
            return self.statuses[len(self.dispatched) - 1]
        return self.statuses[-1]

    def shutdown(self) -> None:
        pass


class FakeGate:
    def __init__(self, results: list[FakeGateResult] | None = None) -> None:
        self.results = results or [FakeGateResult(True, [])]
        self.checked: list[Path] = []

    async def check(self, worktree: Path) -> FakeGateResult:
        self.checked.append(worktree)
        if len(self.results) >= len(self.checked):
            return self.results[len(self.checked) - 1]
        return self.results[-1]


class FakeReworkLoop:
    def __init__(self, result: FakeLaneResult) -> None:
        self.result = result
        self.calls: list[tuple[TaskDescriptor, FakeGateResult]] = []

    async def run(
        self,
        lane: TaskDescriptor,
        initial_gate_result: FakeGateResult,
        dispatch_fn,
        gate: FakeGate,
        max_retries: int = 3,
    ) -> FakeLaneResult:
        self.calls.append((lane, initial_gate_result))
        return self.result


def _write_lanes(path: Path, lanes: list[dict]) -> None:
    path.write_text(json.dumps({"lanes": lanes}))


def _read_lanes(path: Path) -> list[dict]:
    return json.loads(path.read_text())["lanes"]


def test_load_lanes_orders_by_priority_without_breaking_dependencies(tmp_path):
    from master_loop import load_lanes

    lanes_path = tmp_path / "feature_lanes.json"
    _write_lanes(
        lanes_path,
        [
            {
                "feature_id": "low",
                "task_type": "execute",
                "prompt": "low",
                "worktree": str(tmp_path),
                "priority": 1,
            },
            {
                "feature_id": "blocked-high",
                "task_type": "execute",
                "prompt": "blocked",
                "worktree": str(tmp_path),
                "priority": 100,
                "depends_on": ["missing"],
            },
            {
                "feature_id": "high",
                "task_type": "execute",
                "prompt": "high",
                "worktree": str(tmp_path),
                "priority": 100,
            },
            {
                "feature_id": "same-priority",
                "task_type": "execute",
                "prompt": "same",
                "worktree": str(tmp_path),
                "priority": 100,
            },
            {
                "feature_id": "invalid-priority",
                "task_type": "execute",
                "prompt": "invalid",
                "worktree": str(tmp_path),
                "priority": "urgent",
            },
        ],
    )

    tasks = load_lanes(lanes_path)

    assert [task.feature_id for task in tasks] == [
        "high",
        "same-priority",
        "low",
        "invalid-priority",
    ]
    assert [task.priority for task in tasks] == [100, 100, 1, 0]


def test_load_lanes_only_returns_one_active_full_gate_family_lane(tmp_path):
    from master_loop import FULL_QUALITY_GATE_TASK_TYPE, load_lanes

    lanes_path = tmp_path / "feature_lanes.json"
    _write_lanes(
        lanes_path,
        [
            {
                "feature_id": "full-gate-1",
                "task_type": FULL_QUALITY_GATE_TASK_TYPE,
                "prompt": "full",
                "worktree": ".",
                "priority": 100,
            },
            {
                "feature_id": "full-gate-2",
                "task_type": FULL_QUALITY_GATE_TASK_TYPE,
                "prompt": "full",
                "worktree": ".",
                "priority": 100,
            },
            {
                "feature_id": "repair",
                "task_type": "execute",
                "prompt": "repair",
                "worktree": str(tmp_path),
                "priority": 110,
                "source": "full_quality_gate",
                "full_gate_feature_id": "full-gate-1",
            },
            {
                "feature_id": "normal",
                "task_type": "execute",
                "prompt": "normal",
                "worktree": str(tmp_path),
                "priority": 1,
            },
        ],
    )

    tasks = load_lanes(lanes_path)

    assert [task.feature_id for task in tasks] == ["repair", "normal"]
    assert [
        task.feature_id for task in tasks if task.task_type == FULL_QUALITY_GATE_TASK_TYPE
    ] == []


def test_full_quality_gate_command_excludes_isolated_legacy_surfaces():
    from master_loop import FULL_QUALITY_GATE_COMMAND, FULL_QUALITY_GATE_IGNORES

    command = " ".join(FULL_QUALITY_GATE_COMMAND)

    assert "tests/test_agent.py" in FULL_QUALITY_GATE_IGNORES
    assert "tests/test_agent_demo.py" in FULL_QUALITY_GATE_IGNORES
    assert "tests/test_cli_agent_demo.py" in FULL_QUALITY_GATE_IGNORES
    assert "tests/test_pagination_hotpath.py" in FULL_QUALITY_GATE_IGNORES
    assert "tests/test_item_retrieval.py" in FULL_QUALITY_GATE_IGNORES
    assert "tests/test_item_tools.py" in FULL_QUALITY_GATE_IGNORES
    assert "tests/test_retrieval.py" in FULL_QUALITY_GATE_IGNORES
    assert "tests/test_rag_pipeline.py" in FULL_QUALITY_GATE_IGNORES
    assert "test_memoryos_baseline_preserves_required_sources" in command
    assert "test_hard_cases_preserve_baseline_differentiation" in command
    assert "explicit_v1" in command
    assert "dropped_relevant_memoryos_page" in command
    assert "windowed_page_diagnostics" in command
    assert "temporal_anchor_exposes_page_candidate" in command


@pytest.mark.asyncio
async def test_discovers_merges_dispatches_and_marks_lane_done(tmp_path, monkeypatch):
    from master_loop import MasterLoop

    lanes_path = tmp_path / "feature_lanes.json"
    _write_lanes(lanes_path, [])
    discovery_outputs = [
        json.dumps([
            {
                "feature_id": "auto-fix",
                "task_type": "execute",
                "prompt": "fix it",
                "worktree": str(tmp_path),
                "capabilities": ["code"],
            }
        ]),
        "[]",
    ]

    async def fake_exec(*args, **kwargs):
        return FakeProcess(discovery_outputs.pop(0))

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    consumer = FakeConsumer(["done"])
    gate = FakeGate([FakeGateResult(True, [])])
    rework = FakeReworkLoop(FakeLaneResult("done"))

    loop = MasterLoop(
        lanes_path=lanes_path,
        consumer=consumer,
        quality_gate=gate,
        rework_loop=rework,
        max_hours=1,
        max_concurrent=2,
    )

    summary = await loop.run()

    assert summary.rounds == 2
    assert summary.successful_lanes == 1
    assert [task.feature_id for task in consumer.dispatched] == ["auto-fix"]
    lanes = _read_lanes(lanes_path)
    assert lanes[0]["feature_id"] == "auto-fix"
    assert lanes[0]["status"] == "done"
    assert gate.checked == [tmp_path]


@pytest.mark.asyncio
async def test_failed_quality_gate_runs_rework_and_marks_done(tmp_path, monkeypatch):
    from master_loop import MasterLoop

    lanes_path = tmp_path / "feature_lanes.json"
    _write_lanes(
        lanes_path,
        [
            {
                "feature_id": "needs-gate",
                "task_type": "execute",
                "prompt": "implement",
                "worktree": str(tmp_path),
                "capabilities": ["code"],
            }
        ],
    )

    async def fake_exec(*args, **kwargs):
        return FakeProcess("[]")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    gate_result = FakeGateResult(False, ["pytest failed"])
    consumer = FakeConsumer(["done"])
    gate = FakeGate([gate_result])
    rework = FakeReworkLoop(FakeLaneResult("done", attempts=1, final_errors=[]))
    loop = MasterLoop(
        lanes_path=lanes_path,
        consumer=consumer,
        quality_gate=gate,
        rework_loop=rework,
        max_hours=1,
        max_concurrent=1,
    )

    summary = await loop.run()

    assert summary.successful_lanes == 1
    assert len(rework.calls) == 1
    assert rework.calls[0][0].feature_id == "needs-gate"
    assert rework.calls[0][1] is gate_result
    assert _read_lanes(lanes_path)[0]["status"] == "done"


@pytest.mark.asyncio
async def test_exits_after_three_rounds_with_zero_successes(tmp_path, monkeypatch):
    from master_loop import MasterLoop

    lanes_path = tmp_path / "feature_lanes.json"
    _write_lanes(lanes_path, [])
    discovery_outputs = [
        json.dumps([
            {
                "feature_id": f"failing-{idx}",
                "task_type": "execute",
                "prompt": "will fail",
                "worktree": str(tmp_path),
                "capabilities": ["code"],
            }
        ])
        for idx in range(3)
    ]

    async def fake_exec(*args, **kwargs):
        return FakeProcess(discovery_outputs.pop(0))

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    consumer = FakeConsumer(["failed"])
    gate = FakeGate()
    rework = FakeReworkLoop(FakeLaneResult("failed"))
    loop = MasterLoop(
        lanes_path=lanes_path,
        consumer=consumer,
        quality_gate=gate,
        rework_loop=rework,
        max_hours=1,
        max_concurrent=2,
    )

    summary = await loop.run()

    assert summary.rounds == 3
    assert summary.zero_success_rounds == 3
    assert summary.exit_reason == "zero_success_rounds"
    assert [task.feature_id for task in consumer.dispatched] == [
        "failing-0",
        "failing-1",
        "failing-2",
    ]


@pytest.mark.asyncio
async def test_shutdown_finishes_current_lane_without_starting_more(tmp_path, monkeypatch):
    from master_loop import MasterLoop

    lanes_path = tmp_path / "feature_lanes.json"
    _write_lanes(
        lanes_path,
        [
            {
                "feature_id": "first",
                "task_type": "execute",
                "prompt": "one",
                "worktree": str(tmp_path),
                "capabilities": ["code"],
            },
            {
                "feature_id": "second",
                "task_type": "execute",
                "prompt": "two",
                "worktree": str(tmp_path),
                "capabilities": ["code"],
            },
        ],
    )

    async def fake_exec(*args, **kwargs):
        return FakeProcess("[]")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    gate = FakeGate([FakeGateResult(True, [])])
    rework = FakeReworkLoop(FakeLaneResult("done"))
    loop = MasterLoop(
        lanes_path=lanes_path,
        consumer=None,
        quality_gate=gate,
        rework_loop=rework,
        max_hours=1,
        max_concurrent=1,
    )
    consumer = FakeConsumer(["done"], shutdown_after_first=loop)
    loop.consumer = consumer

    summary = await loop.run()

    assert summary.exit_reason == "shutdown"
    assert [task.feature_id for task in consumer.dispatched] == ["first"]
    lanes = {lane["feature_id"]: lane.get("status") for lane in _read_lanes(lanes_path)}
    assert lanes["first"] == "done"
    assert lanes["second"] is None


@pytest.mark.asyncio
async def test_twelve_successful_lanes_enqueue_full_quality_gate(tmp_path, monkeypatch):
    from master_loop import FULL_QUALITY_GATE_TASK_TYPE, MasterLoop

    lanes_path = tmp_path / "feature_lanes.json"
    _write_lanes(
        lanes_path,
        [
            {
                "feature_id": f"lane-{idx}",
                "task_type": "execute",
                "prompt": "fix",
                "worktree": str(tmp_path),
                "capabilities": ["code"],
            }
            for idx in range(12)
        ],
    )

    async def fake_exec(*args, **kwargs):
        return FakeProcess("pytest ok")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    consumer = FakeConsumer(["done"] * 12)
    gate = FakeGate([FakeGateResult(True, [])])
    rework = FakeReworkLoop(FakeLaneResult("done"))
    loop = MasterLoop(
        lanes_path=lanes_path,
        consumer=consumer,
        quality_gate=gate,
        rework_loop=rework,
        max_hours=1,
        max_concurrent=4,
        discovery_enabled=False,
    )

    summary = await loop.run()

    lanes = _read_lanes(lanes_path)
    full_gate_lanes = [
        lane for lane in lanes if lane.get("task_type") == FULL_QUALITY_GATE_TASK_TYPE
    ]
    assert summary.successful_lanes == 13
    assert len(full_gate_lanes) == 1
    assert full_gate_lanes[0]["status"] == "done"
    assert full_gate_lanes[0]["priority"] == 100
    assert full_gate_lanes[0]["worktree"] == "."
    assert full_gate_lanes[0]["batch_lane_ids"] == [f"lane-{idx}" for idx in range(12)]
    assert [task.feature_id for task in consumer.dispatched] == [
        f"lane-{idx}" for idx in range(12)
    ]


@pytest.mark.asyncio
async def test_does_not_enqueue_full_gate_when_one_is_already_active(tmp_path):
    from master_loop import FULL_QUALITY_GATE_TASK_TYPE, MasterLoop

    lanes_path = tmp_path / "feature_lanes.json"
    _write_lanes(
        lanes_path,
        [
            *[
                {
                    "feature_id": f"lane-{idx}",
                    "task_type": "execute",
                    "prompt": "done",
                    "worktree": str(tmp_path),
                    "status": "done",
                }
                for idx in range(12)
            ],
            {
                "feature_id": "full-gate-active",
                "task_type": FULL_QUALITY_GATE_TASK_TYPE,
                "prompt": "full",
                "worktree": ".",
                "status": "running",
                "priority": 100,
            },
        ],
    )
    loop = MasterLoop(
        lanes_path=lanes_path,
        consumer=None,
        quality_gate=FakeGate(),
        rework_loop=FakeReworkLoop(FakeLaneResult("done")),
        discovery_enabled=False,
    )

    queued = await loop._maybe_append_full_quality_gate_lane()

    full_gates = [
        lane
        for lane in _read_lanes(lanes_path)
        if lane.get("task_type") == FULL_QUALITY_GATE_TASK_TYPE
    ]
    assert queued is None
    assert [lane["feature_id"] for lane in full_gates] == ["full-gate-active"]


@pytest.mark.asyncio
async def test_does_not_enqueue_full_gate_when_repair_is_already_active(tmp_path):
    from master_loop import FULL_QUALITY_GATE_TASK_TYPE, MasterLoop

    lanes_path = tmp_path / "feature_lanes.json"
    _write_lanes(
        lanes_path,
        [
            *[
                {
                    "feature_id": f"lane-{idx}",
                    "task_type": "execute",
                    "prompt": "done",
                    "worktree": str(tmp_path),
                    "status": "done",
                }
                for idx in range(12)
            ],
            {
                "feature_id": "full-gate-repair",
                "task_type": "execute",
                "prompt": "repair",
                "worktree": str(tmp_path),
                "status": "running",
                "source": "full_quality_gate",
                "full_gate_feature_id": "full-gate-failed",
                "priority": 110,
            },
        ],
    )
    loop = MasterLoop(
        lanes_path=lanes_path,
        consumer=None,
        quality_gate=FakeGate(),
        rework_loop=FakeReworkLoop(FakeLaneResult("done")),
        discovery_enabled=False,
    )

    queued = await loop._maybe_append_full_quality_gate_lane()

    full_gates = [
        lane
        for lane in _read_lanes(lanes_path)
        if lane.get("task_type") == FULL_QUALITY_GATE_TASK_TYPE
    ]
    assert queued is None
    assert full_gates == []


@pytest.mark.asyncio
async def test_failed_full_quality_gate_generates_priority_repair_lane(
    tmp_path, monkeypatch
):
    from master_loop import FULL_QUALITY_GATE_COMMAND, MasterLoop, load_lanes

    lanes_path = tmp_path / "feature_lanes.json"
    _write_lanes(
        lanes_path,
        [
            {
                "feature_id": "full-quality-gate-abc",
                "task_type": "full_quality_gate",
                "prompt": "full gate",
                "worktree": ".",
                "status": "pending",
                "priority": 100,
                "batch_lane_ids": ["lane-a", "lane-b"],
                "head_sha": "abc123",
            }
        ],
    )
    calls: list[tuple[tuple[str, ...], Path]] = []

    async def fake_exec(*args, **kwargs):
        calls.append((args, kwargs["cwd"]))
        return FakeProcess("failed test output", returncode=1)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    loop = MasterLoop(
        lanes_path=lanes_path,
        consumer=None,
        quality_gate=FakeGate(),
        rework_loop=FakeReworkLoop(FakeLaneResult("done")),
        max_hours=1,
        discovery_enabled=False,
    )

    status = await loop._run_full_quality_gate_lane(load_lanes(lanes_path)[0])

    lanes = _read_lanes(lanes_path)
    repair = lanes[1]
    assert status == "failed"
    assert calls == [(FULL_QUALITY_GATE_COMMAND, Path(__file__).resolve().parent.parent)]
    assert lanes[0]["status"] == "failed"
    assert repair["feature_id"] == "full-quality-gate-repair-full-quality-gate-abc"
    assert repair["priority"] == 110
    assert repair["source"] == "full_quality_gate"
    assert "failed test output" in repair["prompt"]
    assert "test_memoryos_baseline_preserves_required_sources" in repair["prompt"]
    assert repair["batch_lane_ids"] == ["lane-a", "lane-b"]


@pytest.mark.asyncio
async def test_failed_full_quality_gate_discards_queued_full_gate_before_repair(
    tmp_path, monkeypatch
):
    from master_loop import MasterLoop, load_lanes

    lanes_path = tmp_path / "feature_lanes.json"
    _write_lanes(
        lanes_path,
        [
            {
                "feature_id": "full-quality-gate-current",
                "task_type": "full_quality_gate",
                "prompt": "full gate",
                "worktree": ".",
                "status": "pending",
                "priority": 100,
                "batch_lane_ids": ["lane-a"],
                "head_sha": "abc123",
            },
            {
                "feature_id": "full-quality-gate-queued",
                "task_type": "full_quality_gate",
                "prompt": "queued",
                "worktree": ".",
                "status": "pending",
                "priority": 100,
                "batch_lane_ids": ["lane-b"],
                "head_sha": "abc123",
            },
        ],
    )

    async def fake_exec(*args, **kwargs):
        return FakeProcess("failed test output", returncode=1)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    loop = MasterLoop(
        lanes_path=lanes_path,
        consumer=None,
        quality_gate=FakeGate(),
        rework_loop=FakeReworkLoop(FakeLaneResult("done")),
        max_hours=1,
        discovery_enabled=False,
    )

    await loop._run_full_quality_gate_lane(load_lanes(lanes_path)[0])

    lanes = {lane["feature_id"]: lane for lane in _read_lanes(lanes_path)}
    assert lanes["full-quality-gate-current"]["status"] == "failed"
    assert lanes["full-quality-gate-queued"]["status"] == "failed"
    assert (
        lanes["full-quality-gate-queued"]["discarded_reason"]
        == "superseded_full_quality_gate_family"
    )
    assert (
        lanes["full-quality-gate-queued"]["discarded_by"]
        == "full-quality-gate-current"
    )
    assert (
        lanes["full-quality-gate-repair-full-quality-gate-current"]["status"]
        == "pending"
    )
