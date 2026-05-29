import json
from pathlib import Path

from xmuse_core.chat.store import ChatStore
from xmuse_core.self_evolution import SelfEvolutionController
from xmuse_core.self_evolution.adapters.chat_reader import ChatReader
from xmuse_core.self_evolution.adapters.lanes_reader import LanesReader


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_lanes_reader_lists_and_gets_lanes(tmp_path: Path) -> None:
    lanes_path = tmp_path / "feature_lanes.json"
    _write_json(
        lanes_path,
        {
            "lanes": [
                {"feature_id": "lane-a", "status": "merged"},
                {"feature_id": "lane-b", "status": "pending"},
                "ignored",
            ]
        },
    )
    reader = LanesReader(lanes_path)

    assert [lane["feature_id"] for lane in reader.list_lanes()] == ["lane-a", "lane-b"]
    assert reader.list_lanes(status="pending") == [{"feature_id": "lane-b", "status": "pending"}]
    assert reader.get_lane("lane-a") == {"feature_id": "lane-a", "status": "merged"}
    assert reader.get_lane("missing") is None


def test_lanes_reader_resolves_lineage_ids(tmp_path: Path) -> None:
    lanes_path = tmp_path / "feature_lanes.json"
    _write_json(
        lanes_path,
        {
            "lanes": [
                {"feature_id": "root", "graph_id": "graph-1"},
                {"feature_id": "child", "source_lane_id": "root"},
                {"feature_id": "grandchild", "source_lane_id": "child"},
                {"feature_id": "other", "graph_id": "graph-2"},
            ]
        },
    )

    assert LanesReader(lanes_path).lineage_lane_ids("graph-1") == [
        "root",
        "child",
        "grandchild",
    ]


def test_lanes_reader_reports_open_lineages(tmp_path: Path) -> None:
    reader = LanesReader(tmp_path / "feature_lanes.json")
    lane_by_id = {
        "merged-child": {
            "feature_id": "merged-child",
            "source_lane_id": "root",
            "status": "merged",
        },
        "open-child": {
            "feature_id": "open-child",
            "source_lane_id": "root",
            "status": "pending",
        },
        "failed-child": {
            "feature_id": "failed-child",
            "source_lane_id": "root",
            "status": "failed",
        },
    }

    assert reader.open_lineages(lane_by_id) == [
        {"source_lane_id": "root", "feature_id": "open-child", "status": "pending"}
    ]


def test_lanes_reader_open_lineages_uses_normalized_terminal_statuses(tmp_path: Path) -> None:
    reader = LanesReader(tmp_path / "feature_lanes.json")
    lane_by_id = {
        "done-child": {
            "feature_id": "done-child",
            "source_lane_id": "root",
            "status": "done",
        },
        "completed-child": {
            "feature_id": "completed-child",
            "source_lane_id": "root",
            "status": "completed",
        },
        "exec-failed-child": {
            "feature_id": "exec-failed-child",
            "source_lane_id": "root",
            "status": "exec_failed",
        },
        "gate-failed-child": {
            "feature_id": "gate-failed-child",
            "source_lane_id": "root",
            "status": "gate_failed",
        },
        "aborted-child": {
            "feature_id": "aborted-child",
            "source_lane_id": "root",
            "status": "aborted",
        },
        "review-infra-child": {
            "feature_id": "review-infra-child",
            "source_lane_id": "root",
            "status": "gate_failed",
            "failure_reason": "review_infra_unavailable",
        },
        "pending-child": {
            "feature_id": "pending-child",
            "source_lane_id": "root",
            "status": "pending",
        },
    }

    assert reader.open_lineages(lane_by_id) == [
        {
            "source_lane_id": "root",
            "feature_id": "review-infra-child",
            "status": "gate_failed",
        },
        {"source_lane_id": "root", "feature_id": "pending-child", "status": "pending"},
    ]


def test_lanes_reader_extracts_blocked_object(tmp_path: Path) -> None:
    reader = LanesReader(tmp_path / "feature_lanes.json")

    assert reader.blocked_object_for_lane(
        {
            "feature_id": "lane-1",
            "clarification_request": {
                "missing_input": "API key",
                "owner": "operator",
                "resume_path": "rerun gate",
            },
        }
    ) == {
        "lane_id": "lane-1",
        "missing_input": "API key",
        "owner": "operator",
        "resume_path": "rerun gate",
    }
    assert reader.blocked_object_for_lane(
        {
            "feature_id": "lane-2",
            "status": "blocked_for_input",
            "missing_input": "scope",
            "input_owner": "architect",
        }
    ) == {
        "lane_id": "lane-2",
        "missing_input": "scope",
        "owner": "architect",
        "resume_path": "provide information and resume lane",
    }


def test_lanes_reader_extracts_final_action_hold(tmp_path: Path) -> None:
    reader = LanesReader(tmp_path / "feature_lanes.json")
    summary = " ".join(["summary"] * 40)

    hold = reader.final_action_hold_for_lane(
        {
            "feature_id": "lane-1",
            "status": "awaiting_final_action",
            "final_action": "terminate",
            "review_verdict_id": "verdict-1",
            "review_summary": summary,
        }
    )

    assert hold is not None
    assert hold["lane_id"] == "lane-1"
    assert hold["action"] == "terminate"
    assert hold["verdict_id"] == "verdict-1"
    assert hold["summary"].endswith("...")
    assert len(hold["summary"]) <= 160
    assert reader.final_action_hold_for_lane({"status": "merged"}) is None


def test_chat_reader_reads_conversations_proposals_and_resolutions(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.db"
    store = ChatStore(db_path)
    conversation = store.create_conversation("self evolution")
    proposal = store.create_proposal(
        conversation_id=conversation.id,
        author="agent",
        proposal_type="lane-plan",
        content="land lanes",
        references=["feature_lanes.json"],
    )
    resolution = store.approve_proposal(
        proposal_id=proposal.id,
        approved_by=["reviewer"],
        approval_mode="god-review",
        goal_summary="approved graph",
        content={"lanes": [{"feature_id": "lane-1"}]},
    )

    reader = ChatReader(db_path)

    assert reader.list_conversations() == [conversation]
    assert reader.get_proposal(proposal.id).accepted_resolution_id == resolution.id
    assert reader.get_resolution(resolution.id).content == {
        "lanes": [{"feature_id": "lane-1"}]
    }


class _FixtureLanesReader:
    def __init__(self, lanes: list[dict]) -> None:
        self._lanes = lanes

    def list_lanes(self, *, status: str | None = None) -> list[dict]:
        if status is None:
            return list(self._lanes)
        return [lane for lane in self._lanes if lane.get("status") == status]

    def lineage_lane_ids(self, graph_id: str) -> list[str]:
        return [
            str(lane["feature_id"])
            for lane in self._lanes
            if lane.get("graph_id") == graph_id and lane.get("feature_id")
        ]

    def blocked_object_for_lane(self, lane: dict) -> dict | None:
        return LanesReader("unused").blocked_object_for_lane(lane)

    def final_action_hold_for_lane(self, lane: dict) -> dict | None:
        return LanesReader("unused").final_action_hold_for_lane(lane)

    def open_lineages(self, lane_by_id: dict[str, dict]) -> list[dict]:
        return LanesReader("unused").open_lineages(lane_by_id)


class _ContractOnlyLanesReader:
    def __init__(self, lanes: list[dict]) -> None:
        self._lanes = lanes

    def list_lanes(self, *, status: str | None = None) -> list[dict]:
        if status is None:
            return list(self._lanes)
        return [lane for lane in self._lanes if lane.get("status") == status]

    def lineage_lane_ids(self, graph_id: str) -> list[str]:
        return [
            str(lane["feature_id"])
            for lane in self._lanes
            if lane.get("graph_id") == graph_id and lane.get("feature_id")
        ]

    def blocked_object_for_lane(self, lane: dict) -> dict | None:
        return LanesReader("unused").blocked_object_for_lane(lane)

    def final_action_hold_for_lane(self, lane: dict) -> dict | None:
        return LanesReader("unused").final_action_hold_for_lane(lane)

    def open_lineages(self, lane_by_id: dict[str, dict]) -> list[dict]:
        return LanesReader("unused").open_lineages(lane_by_id)


def test_controller_aggregates_via_injected_lanes_reader(tmp_path: Path) -> None:
    graph_id = "res-adapter-graph-v1"
    blueprint = tmp_path / "blueprint.md"
    blueprint.write_text("# blueprint\n", encoding="utf-8")
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-adapter",
            "resolution_id": "res-adapter",
            "version": 1,
            "lanes": [{"feature_id": "lane-root", "prompt": "root"}],
        },
    )
    reader = _FixtureLanesReader(
        [
            {
                "feature_id": "lane-root",
                "graph_id": graph_id,
                "status": "merged",
            }
        ]
    )

    aggregation = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
        lanes_reader=reader,
    ).aggregate_run_terminal(graph_id)

    assert aggregation.status == "merged"
    assert aggregation.lane_statuses[0]["feature_id"] == "lane-root"


def test_controller_uses_documented_lanes_reader_contract(tmp_path: Path) -> None:
    graph_id = "res-contract-graph-v1"
    blueprint = tmp_path / "blueprint.md"
    blueprint.write_text("# blueprint\n", encoding="utf-8")
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-contract",
            "resolution_id": "res-contract",
            "version": 1,
            "lanes": [{"feature_id": "lane-root", "prompt": "root"}],
        },
    )
    reader = _ContractOnlyLanesReader(
        [
            {
                "feature_id": "lane-root",
                "graph_id": graph_id,
                "status": "merged",
            }
        ]
    )

    aggregation = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
        lanes_reader=reader,
    ).aggregate_run_terminal(graph_id)

    assert aggregation.status == "merged"
    assert aggregation.lane_statuses == [
        {
            "feature_id": "lane-root",
            "raw_status": "merged",
            "normalized_status": "merged",
            "terminal": True,
        }
    ]
