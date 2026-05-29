import json
from pathlib import Path

from xmuse_core.structuring.models import LaneGraph, LaneNode
from xmuse_core.structuring.projection import project_ready_lanes


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_project_ready_lanes_materializes_only_dependency_ready_nodes(tmp_path: Path) -> None:
    lanes_path = tmp_path / "feature_lanes.json"
    graph = LaneGraph(
        id="graph-1",
        conversation_id="conv-1",
        resolution_id="res-1",
        version=1,
        status="planned",
        lanes=[
            LaneNode(feature_id="chat", prompt="Build chat", priority=80),
            LaneNode(
                feature_id="dashboard",
                prompt="Build dashboard",
                priority=60,
                depends_on=["chat"],
            ),
            LaneNode(feature_id="review", prompt="Build review flow", priority=40),
        ],
    )

    projected = project_ready_lanes(graph, lanes_path)

    assert [lane["feature_id"] for lane in projected] == ["chat", "review"]
    assert [lane["feature_id"] for lane in _read_json(lanes_path)["lanes"]] == [
        "chat",
        "review",
    ]
    assert projected[0]["conversation_id"] == "conv-1"
    assert projected[0]["resolution_id"] == "res-1"
    assert projected[0]["graph_id"] == "graph-1"
    assert projected[0]["graph_version"] == 1


def test_project_ready_lanes_adds_newly_ready_nodes_without_duplication(tmp_path: Path) -> None:
    lanes_path = tmp_path / "feature_lanes.json"
    lanes_path.write_text(
        json.dumps(
            {
                "lanes": [
                    {"feature_id": "chat", "status": "merged", "prompt": "Build chat"},
                    {"feature_id": "review", "status": "pending", "prompt": "Build review flow"},
                ]
            }
        ),
        encoding="utf-8",
    )
    graph = LaneGraph(
        id="graph-1",
        conversation_id="conv-1",
        resolution_id="res-1",
        version=1,
        status="running",
        lanes=[
            LaneNode(feature_id="chat", prompt="Build chat", priority=80),
            LaneNode(
                feature_id="dashboard",
                prompt="Build dashboard",
                priority=60,
                depends_on=["chat"],
            ),
            LaneNode(feature_id="review", prompt="Build review flow", priority=40),
        ],
    )

    projected = project_ready_lanes(graph, lanes_path)
    data = _read_json(lanes_path)

    assert [lane["feature_id"] for lane in projected] == ["dashboard"]
    assert [lane["feature_id"] for lane in data["lanes"]] == [
        "chat",
        "review",
        "dashboard",
    ]
    assert data["lanes"][-1]["depends_on"] == ["chat"]
