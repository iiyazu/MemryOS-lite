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
