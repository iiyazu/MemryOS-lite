from xmuse_core.chat.models import StructuredResolution
from xmuse_core.structuring.planner import build_lane_graph


def test_build_lane_graph_preserves_lane_order_and_dependencies() -> None:
    resolution = StructuredResolution(
        id="res-1",
        conversation_id="conv-1",
        version=1,
        derived_from_proposal_ids=["prop-1"],
        approved_by=["human"],
        approval_mode="human",
        goal_summary="Build xmuse MVP",
        status="approved",
        created_at="2026-05-27T00:00:00Z",
        content={
            "lanes": [
                {
                    "feature_id": "chat-plane",
                    "title": "Chat plane",
                    "prompt": "Build the chat plane.",
                    "priority": 90,
                    "capabilities": ["code"],
                    "depends_on": [],
                },
                {
                    "feature_id": "dashboard-read-model",
                    "title": "Dashboard",
                    "prompt": "Build the dashboard read model.",
                    "priority": 60,
                    "capabilities": ["code", "test"],
                    "depends_on": ["chat-plane"],
                },
            ]
        },
    )

    graph = build_lane_graph(resolution)

    assert graph.resolution_id == "res-1"
    assert graph.version == 1
    assert graph.status == "planned"
    assert [lane.feature_id for lane in graph.lanes] == [
        "chat-plane",
        "dashboard-read-model",
    ]
    assert graph.lanes[0].priority == 90
    assert graph.lanes[1].depends_on == ["chat-plane"]


def test_build_lane_graph_falls_back_to_single_lane_from_goal_summary() -> None:
    resolution = StructuredResolution(
        id="res-2",
        conversation_id="conv-1",
        version=2,
        derived_from_proposal_ids=["prop-2"],
        approved_by=["human"],
        approval_mode="human",
        goal_summary="Add a chat-first xmuse surface",
        status="approved",
        created_at="2026-05-27T00:00:00Z",
        content={},
    )

    graph = build_lane_graph(resolution)

    assert len(graph.lanes) == 1
    assert graph.lanes[0].feature_id == "res-2-lane-1"
    assert graph.lanes[0].prompt == "Add a chat-first xmuse surface"
    assert graph.lanes[0].depends_on == []
