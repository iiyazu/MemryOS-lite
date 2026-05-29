from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT / "xmuse" / "platform_runner.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("xmuse_platform_runner", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


platform_runner = _load_module()


class _FakeStateMachine:
    def __init__(self, lanes=None):
        self._lanes = lanes or []

    def get_lanes(self, status: str | None = None):
        if status is None:
            return list(self._lanes)
        return [lane for lane in self._lanes if lane.get("status") == status]


@pytest.mark.asyncio
async def test_runner_does_not_require_final_action_approval_by_default(
    monkeypatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    class FakeOrchestrator:
        def __init__(
            self,
            *,
            lanes_path: Path,
            xmuse_root: Path,
            mcp_port: int,
            require_final_action_approval: bool,
            god_runtime: str | None = None,
        ) -> None:
            captured["lanes_path"] = lanes_path
            captured["xmuse_root"] = xmuse_root
            captured["mcp_port"] = mcp_port
            captured["require_final_action_approval"] = require_final_action_approval
            captured["god_runtime"] = god_runtime
            self._sm = _FakeStateMachine()

        async def reconcile_status_changes(self) -> None:
            return None

        async def dispatch_lane(self, lane_id: str) -> None:
            return None

    monkeypatch.setattr(platform_runner, "PlatformOrchestrator", FakeOrchestrator)

    await platform_runner.run(
        lanes_path=tmp_path / "feature_lanes.json",
        xmuse_root=tmp_path / "xmuse",
        mcp_port=8100,
        max_hours=0,
        max_concurrent=1,
    )

    assert captured["require_final_action_approval"] is False
    assert captured["god_runtime"] is None


@pytest.mark.asyncio
async def test_runner_can_require_final_action_approval(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakeOrchestrator:
        def __init__(
            self,
            *,
            lanes_path: Path,
            xmuse_root: Path,
            mcp_port: int,
            require_final_action_approval: bool,
            god_runtime: str | None = None,
        ) -> None:
            captured["require_final_action_approval"] = require_final_action_approval
            captured["god_runtime"] = god_runtime
            self._sm = _FakeStateMachine()

        async def reconcile_status_changes(self) -> None:
            return None

        async def dispatch_lane(self, lane_id: str) -> None:
            return None

    monkeypatch.setattr(platform_runner, "PlatformOrchestrator", FakeOrchestrator)

    await platform_runner.run(
        lanes_path=tmp_path / "feature_lanes.json",
        xmuse_root=tmp_path / "xmuse",
        mcp_port=8100,
        max_hours=0,
        max_concurrent=1,
        require_final_action_approval=True,
        god_runtime="claude",
    )

    assert captured["require_final_action_approval"] is True
    assert captured["god_runtime"] == "claude"


def test_candidate_lanes_filters_to_target_graph_and_includes_reworking() -> None:
    class FakeOrchestrator:
        def __init__(self) -> None:
            self._sm = _FakeStateMachine(
                [
                    {"feature_id": "lane-1", "status": "pending", "graph_id": "graph-a"},
                    {"feature_id": "lane-2", "status": "reworking", "graph_id": "graph-a"},
                    {"feature_id": "lane-3", "status": "pending", "graph_id": "graph-b"},
                    {"feature_id": "lane-4", "status": "exec_failed", "graph_id": "graph-a"},
                ]
            )

    lanes = platform_runner._candidate_lanes(
        FakeOrchestrator(),
        graph_id="graph-a",
        resolution_id=None,
    )

    assert [lane["feature_id"] for lane in lanes] == ["lane-1", "lane-2"]
