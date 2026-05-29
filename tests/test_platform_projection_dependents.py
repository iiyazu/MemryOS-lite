import json

import pytest

from xmuse_core.platform.projection.dependents import (
    aggregate_status,
    reproject_dependents_if_needed,
)
from xmuse_core.platform.state_machine import LaneStateMachine
from xmuse_core.structuring.graph_store import LaneGraphStore
from xmuse_core.structuring.models import LaneGraph, LaneNode


def _write_lanes(path, lanes):
    path.write_text(json.dumps({"lanes": lanes}), encoding="utf-8")


def _graph_store(tmp_path, graph: LaneGraph) -> LaneGraphStore:
    store = LaneGraphStore(tmp_path / "lane_graphs")
    store.save(graph)
    return store


def _graph(*, lanes: list[LaneNode]) -> LaneGraph:
    return LaneGraph(
        id="graph-1",
        conversation_id="conv-1",
        resolution_id="res-1",
        version=1,
        lanes=lanes,
    )


@pytest.mark.asyncio
async def test_reproject_dependents_handles_feature_group_none(tmp_path):
    lanes_path = tmp_path / "feature_lanes.json"
    _write_lanes(
        lanes_path,
        [
            {
                "feature_id": "lane-1",
                "status": "merged",
                "prompt": "build chat",
                "graph_id": "graph-1",
            }
        ],
    )
    graph_store = _graph_store(
        tmp_path,
        _graph(
            lanes=[
                LaneNode(feature_id="lane-1", prompt="build chat"),
                LaneNode(
                    feature_id="lane-2",
                    prompt="build dashboard",
                    depends_on=["lane-1"],
                    feature_group=None,
                ),
            ]
        ),
    )

    await reproject_dependents_if_needed(
        "lane-1",
        sm=LaneStateMachine(lanes_path),
        graph_store=graph_store,
    )

    lanes = json.loads(lanes_path.read_text(encoding="utf-8"))["lanes"]
    assert [lane["feature_id"] for lane in lanes] == ["lane-1", "lane-2"]
    assert lanes[1]["status"] == "pending"
    assert "feature_group" not in lanes[1]
    lane_1 = next(lane for lane in lanes if lane["feature_id"] == "lane-1")
    assert lane_1["dependency_projection_count"] == 1
    assert lane_1["dependency_projection_processed_at"] > 0


@pytest.mark.asyncio
async def test_reproject_dependents_waits_for_all_unmerged_dependencies(tmp_path):
    lanes_path = tmp_path / "feature_lanes.json"
    _write_lanes(
        lanes_path,
        [
            {"feature_id": "lane-a", "status": "merged", "prompt": "first", "graph_id": "graph-1"},
            {
                "feature_id": "lane-b",
                "status": "pending",
                "prompt": "second",
                "graph_id": "graph-1",
            },
            {
                "feature_id": "lane-d",
                "status": "executed",
                "prompt": "third",
                "graph_id": "graph-1",
            },
        ],
    )
    graph_store = _graph_store(
        tmp_path,
        _graph(
            lanes=[
                LaneNode(feature_id="lane-a", prompt="first"),
                LaneNode(feature_id="lane-b", prompt="second"),
                LaneNode(feature_id="lane-d", prompt="third"),
                LaneNode(
                    feature_id="lane-c",
                    prompt="combine results",
                    depends_on=["lane-a", "lane-b", "lane-d"],
                ),
            ]
        ),
    )

    await reproject_dependents_if_needed(
        "lane-a",
        sm=LaneStateMachine(lanes_path),
        graph_store=graph_store,
    )

    lanes = json.loads(lanes_path.read_text(encoding="utf-8"))["lanes"]
    assert [lane["feature_id"] for lane in lanes] == ["lane-a", "lane-b", "lane-d"]
    assert lanes[0]["dependency_projection_count"] == 0


@pytest.mark.asyncio
async def test_reproject_dependents_projects_after_all_dependencies_merged(tmp_path):
    lanes_path = tmp_path / "feature_lanes.json"
    _write_lanes(
        lanes_path,
        [
            {"feature_id": "lane-a", "status": "merged", "prompt": "first", "graph_id": "graph-1"},
            {"feature_id": "lane-b", "status": "merged", "prompt": "second", "graph_id": "graph-1"},
        ],
    )
    graph_store = _graph_store(
        tmp_path,
        _graph(
            lanes=[
                LaneNode(feature_id="lane-a", prompt="first"),
                LaneNode(feature_id="lane-b", prompt="second"),
                LaneNode(
                    feature_id="lane-c",
                    prompt="combine results",
                    depends_on=["lane-a", "lane-b"],
                    feature_group="chat/resolution",
                ),
            ]
        ),
    )

    await reproject_dependents_if_needed(
        "lane-a",
        sm=LaneStateMachine(lanes_path),
        graph_store=graph_store,
    )

    lanes = json.loads(lanes_path.read_text(encoding="utf-8"))["lanes"]
    assert [lane["feature_id"] for lane in lanes] == ["lane-a", "lane-b", "lane-c"]
    assert lanes[2]["status"] == "pending"
    assert lanes[2]["feature_group"] == "chat/resolution"
    assert lanes[0]["dependency_projection_count"] == 1


def test_aggregate_status_reports_graph_lanes(tmp_path):
    lanes = [
        {"feature_id": "other", "status": "pending", "graph_id": "other-graph"},
        {"feature_id": "lane-a", "status": "merged", "graph_id": "graph-1"},
        {"feature_id": "lane-b", "status": "pending", "graph_id": "graph-1"},
    ]

    status = aggregate_status(lanes, "graph-1")

    assert status.graph_id == "graph-1"
    assert status.status == "in_progress"
    assert status.terminal is False
    assert status.lane_counts["total"] == 2
