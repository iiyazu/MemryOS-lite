"""
Focused tests for the graph_authority track of xmuse self-evolution.

Covers:
- RunTerminalAggregation exposes final_action_holds for awaiting_final_action lanes
- Aggregation reason is specific when final-action holds are present
- Merged final-action lane does not produce a hold
- final_action_holds is empty when no lanes are awaiting final action
- Multiple awaiting_final_action lanes all appear in final_action_holds
- final_action_holds includes verdict_id and action from lane metadata
- final_action_holds summary is compacted from review_summary
- Patch-forward descendant participates in lineage closure for aggregation
- Requeue (rejected/reworking) lane keeps run non-terminal
- LaneGraph resolution_id is propagated to aggregation
- verdict_lineage is populated from VerdictStore when wired in
- verdict_lineage falls back to lane metadata when no VerdictStore is wired
- verdict_lineage is empty when no verdicts exist for any lane
- verdict_lineage includes decision and summary from VerdictStore
- verdict_lineage is persisted in the aggregation store
- multiple verdicts for the same lane all appear in verdict_lineage
- verdict_lineage source field distinguishes store vs metadata origin
"""
from __future__ import annotations

import json
from pathlib import Path

from xmuse_core.self_evolution import SelfEvolutionController
from xmuse_core.self_evolution.models import RunTerminalStatus
from xmuse_core.structuring.models import ReviewDecision, ReviewVerdict
from xmuse_core.structuring.verdict_store import VerdictStore


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_blueprint(path: Path) -> None:
    path.write_text(
        "# xmuse Initial Self-Evolution Blueprint\n\n"
        "- `blueprint_set_id`: `xmuse-self-evolution-v0`\n\n"
        "## Tracks\n\n"
        "### graph_authority\n"
        "### review_plane\n"
        "### self_evolution_loop\n",
        encoding="utf-8",
    )


def _make_controller(tmp_path: Path) -> SelfEvolutionController:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    return SelfEvolutionController(xmuse_root=tmp_path, blueprint_path=blueprint)


def _make_controller_with_verdict_store(tmp_path: Path) -> SelfEvolutionController:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    verdict_store_path = tmp_path / "review_plane.json"
    return SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
        verdict_store_path=verdict_store_path,
    )


def _save_verdict(
    tmp_path: Path,
    *,
    verdict_id: str,
    lane_id: str,
    decision: ReviewDecision = ReviewDecision.MERGE,
    summary: str = "No findings.",
) -> ReviewVerdict:
    store = VerdictStore(tmp_path / "review_plane.json")
    verdict = ReviewVerdict(
        id=verdict_id,
        lane_id=lane_id,
        decision=decision,
        summary=summary,
        created_at="2026-05-28T10:00:00Z",
    )
    store.save_verdict(verdict)
    return verdict


# ---------------------------------------------------------------------------
# final_action_holds surface in aggregation
# ---------------------------------------------------------------------------


def test_awaiting_final_action_lane_produces_final_action_hold(tmp_path: Path) -> None:
    graph_id = "res-final-action-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-final-action",
            "resolution_id": "res-final-action",
            "version": 1,
            "lanes": [{"feature_id": "lane-hold", "prompt": "needs approval"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-hold",
                    "status": "awaiting_final_action",
                    "prompt": "needs approval",
                    "graph_id": graph_id,
                    "resolution_id": "res-final-action",
                    "review_verdict_id": "verdict-hold-1",
                    "final_action": "merge",
                    "review_summary": "No findings. Ready to merge.",
                }
            ]
        },
    )

    aggregation = _make_controller(tmp_path).aggregate_run_terminal(graph_id)

    assert aggregation.status == RunTerminalStatus.RUNNING
    assert aggregation.terminal is False
    assert len(aggregation.final_action_holds) == 1
    hold = aggregation.final_action_holds[0]
    assert hold["lane_id"] == "lane-hold"
    assert hold["action"] == "merge"
    assert hold["verdict_id"] == "verdict-hold-1"
    assert "No findings" in hold["summary"]


def test_awaiting_final_action_reason_is_specific(tmp_path: Path) -> None:
    graph_id = "res-final-action-reason-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-final-action-reason",
            "resolution_id": "res-final-action-reason",
            "version": 1,
            "lanes": [{"feature_id": "lane-hold-reason", "prompt": "needs approval"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-hold-reason",
                    "status": "awaiting_final_action",
                    "prompt": "needs approval",
                    "graph_id": graph_id,
                }
            ]
        },
    )

    aggregation = _make_controller(tmp_path).aggregate_run_terminal(graph_id)

    assert aggregation.reason == "one or more lanes are awaiting final-action approval"


def test_merged_lane_does_not_produce_final_action_hold(tmp_path: Path) -> None:
    graph_id = "res-merged-no-hold-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-merged-no-hold",
            "resolution_id": "res-merged-no-hold",
            "version": 1,
            "lanes": [{"feature_id": "lane-merged", "prompt": "done"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-merged",
                    "status": "merged",
                    "prompt": "done",
                    "graph_id": graph_id,
                    "review_verdict_id": "verdict-merged-1",
                }
            ]
        },
    )

    aggregation = _make_controller(tmp_path).aggregate_run_terminal(graph_id)

    assert aggregation.status == RunTerminalStatus.MERGED
    assert aggregation.final_action_holds == []


def test_no_awaiting_lanes_yields_empty_final_action_holds(tmp_path: Path) -> None:
    graph_id = "res-no-holds-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-no-holds",
            "resolution_id": "res-no-holds",
            "version": 1,
            "lanes": [
                {"feature_id": "lane-a", "prompt": "a"},
                {"feature_id": "lane-b", "prompt": "b"},
            ],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {"feature_id": "lane-a", "status": "merged", "graph_id": graph_id},
                {"feature_id": "lane-b", "status": "merged", "graph_id": graph_id},
            ]
        },
    )

    aggregation = _make_controller(tmp_path).aggregate_run_terminal(graph_id)

    assert aggregation.final_action_holds == []
    assert aggregation.status == RunTerminalStatus.MERGED


def test_multiple_awaiting_final_action_lanes_all_appear_in_holds(tmp_path: Path) -> None:
    graph_id = "res-multi-hold-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-multi-hold",
            "resolution_id": "res-multi-hold",
            "version": 1,
            "lanes": [
                {"feature_id": "lane-hold-a", "prompt": "a"},
                {"feature_id": "lane-hold-b", "prompt": "b"},
            ],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-hold-a",
                    "status": "awaiting_final_action",
                    "graph_id": graph_id,
                    "review_verdict_id": "verdict-a",
                    "final_action": "merge",
                },
                {
                    "feature_id": "lane-hold-b",
                    "status": "awaiting_final_action",
                    "graph_id": graph_id,
                    "review_verdict_id": "verdict-b",
                    "final_action": "terminate",
                },
            ]
        },
    )

    aggregation = _make_controller(tmp_path).aggregate_run_terminal(graph_id)

    assert len(aggregation.final_action_holds) == 2
    hold_ids = {h["lane_id"] for h in aggregation.final_action_holds}
    assert hold_ids == {"lane-hold-a", "lane-hold-b"}
    actions = {h["lane_id"]: h["action"] for h in aggregation.final_action_holds}
    assert actions["lane-hold-a"] == "merge"
    assert actions["lane-hold-b"] == "terminate"


def test_final_action_hold_defaults_action_to_merge_when_absent(tmp_path: Path) -> None:
    graph_id = "res-hold-default-action-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-hold-default-action",
            "resolution_id": "res-hold-default-action",
            "version": 1,
            "lanes": [{"feature_id": "lane-no-action", "prompt": "no action field"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-no-action",
                    "status": "awaiting_final_action",
                    "graph_id": graph_id,
                }
            ]
        },
    )

    aggregation = _make_controller(tmp_path).aggregate_run_terminal(graph_id)

    assert len(aggregation.final_action_holds) == 1
    assert aggregation.final_action_holds[0]["action"] == "merge"


def test_final_action_hold_summary_is_compacted_from_review_summary(tmp_path: Path) -> None:
    graph_id = "res-hold-summary-graph-v1"
    long_summary = "No findings. " + ("x" * 200) + " Ready to merge."
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-hold-summary",
            "resolution_id": "res-hold-summary",
            "version": 1,
            "lanes": [{"feature_id": "lane-long-summary", "prompt": "long summary"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-long-summary",
                    "status": "awaiting_final_action",
                    "graph_id": graph_id,
                    "review_summary": long_summary,
                }
            ]
        },
    )

    aggregation = _make_controller(tmp_path).aggregate_run_terminal(graph_id)

    hold = aggregation.final_action_holds[0]
    assert "summary" in hold
    assert len(hold["summary"]) <= 163  # 160 + "..."


def test_final_action_hold_omits_summary_when_review_summary_absent(tmp_path: Path) -> None:
    graph_id = "res-hold-no-summary-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-hold-no-summary",
            "resolution_id": "res-hold-no-summary",
            "version": 1,
            "lanes": [{"feature_id": "lane-no-summary", "prompt": "no summary"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-no-summary",
                    "status": "awaiting_final_action",
                    "graph_id": graph_id,
                }
            ]
        },
    )

    aggregation = _make_controller(tmp_path).aggregate_run_terminal(graph_id)

    hold = aggregation.final_action_holds[0]
    assert "summary" not in hold


# ---------------------------------------------------------------------------
# graph_authority: LaneGraph is authoritative source for resolution_id
# ---------------------------------------------------------------------------


def test_aggregation_resolution_id_comes_from_lane_graph(tmp_path: Path) -> None:
    graph_id = "res-authority-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-authority",
            "resolution_id": "res-authority-canonical",
            "version": 1,
            "lanes": [{"feature_id": "lane-auth", "prompt": "auth"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-auth",
                    "status": "merged",
                    "graph_id": graph_id,
                    "resolution_id": "res-authority-canonical",
                }
            ]
        },
    )

    aggregation = _make_controller(tmp_path).aggregate_run_terminal(graph_id)

    assert aggregation.resolution_id == "res-authority-canonical"
    assert aggregation.graph_id == graph_id
    assert aggregation.run_id == graph_id


# ---------------------------------------------------------------------------
# graph_authority: patch-forward lineage closure
# ---------------------------------------------------------------------------


def test_patch_forward_descendant_in_lineage_closure_keeps_run_non_terminal(
    tmp_path: Path,
) -> None:
    graph_id = "res-pf-lineage-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-pf-lineage",
            "resolution_id": "res-pf-lineage",
            "version": 1,
            "lanes": [{"feature_id": "source-lane", "prompt": "source"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "source-lane",
                    "status": "failed",
                    "failure_reason": "patch_forward_requested",
                    "graph_id": graph_id,
                },
                {
                    "feature_id": "source-lane-patch-forward",
                    "status": "pending",
                    "source_lane_id": "source-lane",
                    "graph_id": graph_id,
                },
            ]
        },
    )

    aggregation = _make_controller(tmp_path).aggregate_run_terminal(graph_id)

    assert aggregation.status == RunTerminalStatus.RUNNING
    assert aggregation.terminal is False
    lane_ids = {s["feature_id"] for s in aggregation.lane_statuses}
    assert "source-lane-patch-forward" in lane_ids


def test_patch_forward_descendant_merged_completes_run(tmp_path: Path) -> None:
    graph_id = "res-pf-merged-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-pf-merged",
            "resolution_id": "res-pf-merged",
            "version": 1,
            "lanes": [{"feature_id": "source-lane", "prompt": "source"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "source-lane",
                    "status": "failed",
                    "failure_reason": "patch_forward_requested",
                    "graph_id": graph_id,
                },
                {
                    "feature_id": "source-lane-patch-forward",
                    "status": "merged",
                    "source_lane_id": "source-lane",
                    "graph_id": graph_id,
                },
            ]
        },
    )

    aggregation = _make_controller(tmp_path).aggregate_run_terminal(graph_id)

    # source-lane is terminal (failed), patch-forward is terminal (merged)
    # but not all are merged, so status is TERMINATED
    assert aggregation.terminal is True
    assert aggregation.status == RunTerminalStatus.TERMINATED


def test_failed_lineage_without_merge_verdict_keeps_authority_run_non_terminal(
    tmp_path: Path,
) -> None:
    graph_id = "res-unmerged-terminal-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-unmerged-terminal",
            "resolution_id": "res-unmerged-terminal",
            "version": 1,
            "lanes": [{"feature_id": "lane-unmerged", "prompt": "needs merge"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-unmerged",
                    "status": "failed",
                    "graph_id": graph_id,
                    "review_decision": "rework",
                }
            ]
        },
    )

    aggregation = _make_controller_with_verdict_store(tmp_path).aggregate_run_terminal(graph_id)

    assert aggregation.status == RunTerminalStatus.RUNNING
    assert aggregation.terminal is False
    assert aggregation.reason == "graph lineage merge coordination pending"


def test_rework_terminal_lineage_without_verdict_store_stays_non_terminal(
    tmp_path: Path,
) -> None:
    """Regression for evbundle_97a436...: rework lanes require merge coordination."""
    graph_id = "res-aab31382-graph-v1"
    lane_id = "phase-a-demo-health-endpoint"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-aab31382",
            "resolution_id": "res-aab31382",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "add dashboard health endpoint"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "failed",
                    "graph_id": graph_id,
                    "resolution_id": "res-aab31382",
                    "gate_passed": True,
                    "review_decision": "rework",
                    "retry_count": 2,
                }
            ]
        },
    )

    aggregation = _make_controller(tmp_path).aggregate_run_terminal(graph_id)

    assert aggregation.status == RunTerminalStatus.RUNNING
    assert aggregation.terminal is False
    assert aggregation.reason == "graph lineage merge coordination pending"
    assert aggregation.lane_statuses[0]["review_decision"] == "rework"


def test_failed_lineage_with_merge_verdict_can_terminalize(
    tmp_path: Path,
) -> None:
    graph_id = "res-merged-terminal-graph-v1"
    lane_id = "lane-merged-terminal"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-merged-terminal",
            "resolution_id": "res-merged-terminal",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "needs merge verdict"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "failed",
                    "graph_id": graph_id,
                    "review_decision": "rework",
                }
            ]
        },
    )
    _save_verdict(
        tmp_path,
        verdict_id="verdict-terminal-merge",
        lane_id=lane_id,
        decision=ReviewDecision.MERGE,
        summary="Lineage consolidated.",
    )

    aggregation = _make_controller_with_verdict_store(tmp_path).aggregate_run_terminal(graph_id)

    assert aggregation.status == RunTerminalStatus.TERMINATED
    assert aggregation.terminal is True


# ---------------------------------------------------------------------------
# graph_authority: requeue (rejected/reworking) keeps run non-terminal
# ---------------------------------------------------------------------------


def test_rejected_lane_keeps_run_non_terminal(tmp_path: Path) -> None:
    graph_id = "res-rejected-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-rejected",
            "resolution_id": "res-rejected",
            "version": 1,
            "lanes": [{"feature_id": "lane-rejected", "prompt": "needs rework"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-rejected",
                    "status": "rejected",
                    "graph_id": graph_id,
                }
            ]
        },
    )

    aggregation = _make_controller(tmp_path).aggregate_run_terminal(graph_id)

    assert aggregation.status == RunTerminalStatus.RUNNING
    assert aggregation.terminal is False
    lane_status = next(
        s for s in aggregation.lane_statuses if s["feature_id"] == "lane-rejected"
    )
    assert lane_status["normalized_status"] == "requeued"
    assert lane_status["terminal"] is False


def test_reworking_lane_keeps_run_non_terminal(tmp_path: Path) -> None:
    graph_id = "res-reworking-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-reworking",
            "resolution_id": "res-reworking",
            "version": 1,
            "lanes": [{"feature_id": "lane-reworking", "prompt": "reworking"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-reworking",
                    "status": "reworking",
                    "graph_id": graph_id,
                }
            ]
        },
    )

    aggregation = _make_controller(tmp_path).aggregate_run_terminal(graph_id)

    assert aggregation.status == RunTerminalStatus.RUNNING
    assert aggregation.terminal is False
    lane_status = next(
        s for s in aggregation.lane_statuses if s["feature_id"] == "lane-reworking"
    )
    assert lane_status["normalized_status"] == "requeued"


# ---------------------------------------------------------------------------
# graph_authority: mixed final-action hold + clarification block
# ---------------------------------------------------------------------------


def test_clarification_block_takes_precedence_over_final_action_hold(
    tmp_path: Path,
) -> None:
    graph_id = "res-mixed-block-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-mixed-block",
            "resolution_id": "res-mixed-block",
            "version": 1,
            "lanes": [
                {"feature_id": "lane-clarification", "prompt": "needs info"},
                {"feature_id": "lane-hold", "prompt": "needs approval"},
            ],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-clarification",
                    "status": "blocked_for_input",
                    "graph_id": graph_id,
                    "missing_input": "deployment target",
                    "input_owner": "human",
                    "resume_path": "provide target and resume",
                },
                {
                    "feature_id": "lane-hold",
                    "status": "awaiting_final_action",
                    "graph_id": graph_id,
                    "final_action": "merge",
                },
            ]
        },
    )

    aggregation = _make_controller(tmp_path).aggregate_run_terminal(graph_id)

    # clarification block takes precedence
    assert aggregation.status == RunTerminalStatus.BLOCKED_FOR_INPUT
    assert len(aggregation.blocked_objects) == 1
    assert aggregation.blocked_objects[0]["lane_id"] == "lane-clarification"
    # final_action_holds still populated for observability
    assert len(aggregation.final_action_holds) == 1
    assert aggregation.final_action_holds[0]["lane_id"] == "lane-hold"


# ---------------------------------------------------------------------------
# graph_authority: aggregation is persisted and retrievable
# ---------------------------------------------------------------------------


def test_aggregation_is_persisted_to_store(tmp_path: Path) -> None:
    graph_id = "res-persist-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-persist",
            "resolution_id": "res-persist",
            "version": 1,
            "lanes": [{"feature_id": "lane-persist", "prompt": "persist"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-persist",
                    "status": "merged",
                    "graph_id": graph_id,
                }
            ]
        },
    )
    controller = _make_controller(tmp_path)

    aggregation = controller.aggregate_run_terminal(graph_id)

    stored = controller.store.list_aggregations()
    assert any(a.aggregation_id == aggregation.aggregation_id for a in stored)


def test_final_action_holds_are_persisted_in_aggregation(tmp_path: Path) -> None:
    graph_id = "res-hold-persist-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-hold-persist",
            "resolution_id": "res-hold-persist",
            "version": 1,
            "lanes": [{"feature_id": "lane-hold-persist", "prompt": "hold persist"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-hold-persist",
                    "status": "awaiting_final_action",
                    "graph_id": graph_id,
                    "review_verdict_id": "verdict-persist-1",
                    "final_action": "merge",
                }
            ]
        },
    )
    controller = _make_controller(tmp_path)

    aggregation = controller.aggregate_run_terminal(graph_id)

    stored = controller.store.list_aggregations()
    matching = next(
        a for a in stored if a.aggregation_id == aggregation.aggregation_id
    )
    assert len(matching.final_action_holds) == 1
    assert matching.final_action_holds[0]["verdict_id"] == "verdict-persist-1"


# ---------------------------------------------------------------------------
# graph_authority: verdict_lineage from VerdictStore
# ---------------------------------------------------------------------------


def test_verdict_lineage_populated_from_verdict_store(tmp_path: Path) -> None:
    graph_id = "res-vl-store-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-vl-store",
            "resolution_id": "res-vl-store",
            "version": 1,
            "lanes": [{"feature_id": "lane-vl-store", "prompt": "store verdict"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-vl-store",
                    "status": "merged",
                    "graph_id": graph_id,
                }
            ]
        },
    )
    _save_verdict(
        tmp_path,
        verdict_id="verdict-store-1",
        lane_id="lane-vl-store",
        decision=ReviewDecision.MERGE,
        summary="No findings. Ready to merge.",
    )

    aggregation = _make_controller_with_verdict_store(tmp_path).aggregate_run_terminal(graph_id)

    assert len(aggregation.verdict_lineage) == 1
    entry = aggregation.verdict_lineage[0]
    assert entry["lane_id"] == "lane-vl-store"
    assert entry["verdict_id"] == "verdict-store-1"
    assert entry["decision"] == "merge"
    assert "No findings" in entry["summary"]
    assert entry["source"] == "verdict_store"


def test_verdict_lineage_empty_when_no_verdicts_exist(tmp_path: Path) -> None:
    graph_id = "res-vl-empty-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-vl-empty",
            "resolution_id": "res-vl-empty",
            "version": 1,
            "lanes": [{"feature_id": "lane-vl-empty", "prompt": "no verdict"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-vl-empty",
                    "status": "merged",
                    "graph_id": graph_id,
                }
            ]
        },
    )

    aggregation = _make_controller_with_verdict_store(tmp_path).aggregate_run_terminal(graph_id)

    assert aggregation.verdict_lineage == []


def test_verdict_lineage_fallback_to_lane_metadata_when_no_store(tmp_path: Path) -> None:
    graph_id = "res-vl-fallback-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-vl-fallback",
            "resolution_id": "res-vl-fallback",
            "version": 1,
            "lanes": [{"feature_id": "lane-vl-fallback", "prompt": "fallback verdict"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-vl-fallback",
                    "status": "merged",
                    "graph_id": graph_id,
                    "review_verdict_id": "verdict-fallback-1",
                    "review_decision": "merge",
                    "review_summary": "No findings. Merged.",
                }
            ]
        },
    )

    # No verdict_store_path — uses lane metadata fallback
    aggregation = _make_controller(tmp_path).aggregate_run_terminal(graph_id)

    assert len(aggregation.verdict_lineage) == 1
    entry = aggregation.verdict_lineage[0]
    assert entry["lane_id"] == "lane-vl-fallback"
    assert entry["verdict_id"] == "verdict-fallback-1"
    assert entry["decision"] == "merge"
    assert entry["source"] == "lane_metadata"


def test_verdict_lineage_fallback_omits_lane_without_verdict_id(tmp_path: Path) -> None:
    graph_id = "res-vl-no-vid-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-vl-no-vid",
            "resolution_id": "res-vl-no-vid",
            "version": 1,
            "lanes": [{"feature_id": "lane-no-vid", "prompt": "no verdict id"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-no-vid",
                    "status": "merged",
                    "graph_id": graph_id,
                    # no review_verdict_id field
                }
            ]
        },
    )

    aggregation = _make_controller(tmp_path).aggregate_run_terminal(graph_id)

    assert aggregation.verdict_lineage == []


def test_verdict_lineage_multiple_verdicts_for_same_lane(tmp_path: Path) -> None:
    graph_id = "res-vl-multi-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-vl-multi",
            "resolution_id": "res-vl-multi",
            "version": 1,
            "lanes": [{"feature_id": "lane-vl-multi", "prompt": "multi verdict"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-vl-multi",
                    "status": "merged",
                    "graph_id": graph_id,
                }
            ]
        },
    )
    # First verdict: rework
    _save_verdict(
        tmp_path,
        verdict_id="verdict-multi-1",
        lane_id="lane-vl-multi",
        decision=ReviewDecision.REWORK,
        summary="Medium: missing test coverage.",
    )
    # Second verdict: merge after rework
    _save_verdict(
        tmp_path,
        verdict_id="verdict-multi-2",
        lane_id="lane-vl-multi",
        decision=ReviewDecision.MERGE,
        summary="No findings. Coverage added.",
    )

    aggregation = _make_controller_with_verdict_store(tmp_path).aggregate_run_terminal(graph_id)

    assert len(aggregation.verdict_lineage) == 2
    verdict_ids = {e["verdict_id"] for e in aggregation.verdict_lineage}
    assert verdict_ids == {"verdict-multi-1", "verdict-multi-2"}
    decisions = {e["verdict_id"]: e["decision"] for e in aggregation.verdict_lineage}
    assert decisions["verdict-multi-1"] == "rework"
    assert decisions["verdict-multi-2"] == "merge"


def test_verdict_lineage_includes_patch_forward_descendant(tmp_path: Path) -> None:
    graph_id = "res-vl-pf-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-vl-pf",
            "resolution_id": "res-vl-pf",
            "version": 1,
            "lanes": [{"feature_id": "source-lane-vl", "prompt": "source"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "source-lane-vl",
                    "status": "failed",
                    "failure_reason": "patch_forward_requested",
                    "graph_id": graph_id,
                },
                {
                    "feature_id": "source-lane-vl-patch-forward",
                    "status": "merged",
                    "source_lane_id": "source-lane-vl",
                    "graph_id": graph_id,
                },
            ]
        },
    )
    _save_verdict(
        tmp_path,
        verdict_id="verdict-pf-1",
        lane_id="source-lane-vl-patch-forward",
        decision=ReviewDecision.MERGE,
        summary="Patch-forward accepted.",
    )

    aggregation = _make_controller_with_verdict_store(tmp_path).aggregate_run_terminal(graph_id)

    # Patch-forward descendant verdict must appear in lineage
    pf_entries = [
        e for e in aggregation.verdict_lineage
        if e["lane_id"] == "source-lane-vl-patch-forward"
    ]
    assert len(pf_entries) == 1
    assert pf_entries[0]["verdict_id"] == "verdict-pf-1"
    assert pf_entries[0]["decision"] == "merge"


def test_verdict_lineage_is_persisted_in_aggregation_store(tmp_path: Path) -> None:
    graph_id = "res-vl-persist-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-vl-persist",
            "resolution_id": "res-vl-persist",
            "version": 1,
            "lanes": [{"feature_id": "lane-vl-persist", "prompt": "persist verdict"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-vl-persist",
                    "status": "merged",
                    "graph_id": graph_id,
                }
            ]
        },
    )
    _save_verdict(
        tmp_path,
        verdict_id="verdict-persist-vl-1",
        lane_id="lane-vl-persist",
        decision=ReviewDecision.MERGE,
        summary="Persisted verdict.",
    )
    controller = _make_controller_with_verdict_store(tmp_path)

    aggregation = controller.aggregate_run_terminal(graph_id)

    stored = controller.store.list_aggregations()
    matching = next(
        a for a in stored if a.aggregation_id == aggregation.aggregation_id
    )
    assert len(matching.verdict_lineage) == 1
    assert matching.verdict_lineage[0]["verdict_id"] == "verdict-persist-vl-1"
    assert matching.verdict_lineage[0]["source"] == "verdict_store"


def test_verdict_lineage_source_distinguishes_store_vs_metadata(tmp_path: Path) -> None:
    """Two lanes: one with a VerdictStore entry, one with only lane metadata."""
    graph_id = "res-vl-source-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-vl-source",
            "resolution_id": "res-vl-source",
            "version": 1,
            "lanes": [
                {"feature_id": "lane-store-source", "prompt": "store"},
                {"feature_id": "lane-meta-source", "prompt": "meta"},
            ],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-store-source",
                    "status": "merged",
                    "graph_id": graph_id,
                },
                {
                    "feature_id": "lane-meta-source",
                    "status": "merged",
                    "graph_id": graph_id,
                    # no review_verdict_id — won't appear in fallback
                },
            ]
        },
    )
    _save_verdict(
        tmp_path,
        verdict_id="verdict-source-1",
        lane_id="lane-store-source",
        decision=ReviewDecision.MERGE,
        summary="Store verdict.",
    )

    aggregation = _make_controller_with_verdict_store(tmp_path).aggregate_run_terminal(graph_id)

    sources = {e["lane_id"]: e["source"] for e in aggregation.verdict_lineage}
    assert sources.get("lane-store-source") == "verdict_store"
    # lane-meta-source has no verdict in the store, so it should not appear
    assert "lane-meta-source" not in sources
