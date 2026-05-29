"""
Focused tests for the review_plane track — run-level lineage and auto-wiring.

Covers:
- verdict_lineage_for_run returns entries for all lanes in a graph
- verdict_lineage_for_run returns empty list when no tasks exist for the graph
- verdict_lineage_for_run includes patch-forward descendants via source_lane_id
- verdict_lineage_for_run excludes lanes from other graphs
- verdict_lineage_for_run returns multiple tasks per lane when lane was reworked
- SelfEvolutionController auto-discovers review_plane.json when it exists
- SelfEvolutionController verdict_store is None when review_plane.json is absent
- SelfEvolutionController explicit verdict_store_path overrides auto-discovery
- aggregation verdict_lineage reads from review_plane.json when auto-wired
- aggregation verdict_lineage falls back to lane metadata when no store file
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from xmuse_core.platform.review_plane import ReviewPlaneController
from xmuse_core.self_evolution import SelfEvolutionController
from xmuse_core.structuring.models import ReviewDecision, ReviewVerdict
from xmuse_core.structuring.verdict_store import VerdictStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _make_lanes(tmp_path: Path, lanes: list[dict]) -> Path:
    lanes_path = tmp_path / "feature_lanes.json"
    _write_json(lanes_path, {"lanes": lanes})
    return lanes_path


def _make_controller(
    tmp_path: Path,
    lanes: list[dict],
    *,
    require_final_action_approval: bool = False,
) -> ReviewPlaneController:
    lanes_path = _make_lanes(tmp_path, lanes)
    store_path = tmp_path / "review_plane.json"
    final_actions_path = tmp_path / "final_actions.json"
    return ReviewPlaneController(
        lanes_path=lanes_path,
        store_path=store_path,
        final_actions_path=final_actions_path,
        require_final_action_approval=require_final_action_approval,
    )


def _gated_lane(lane_id: str, graph_id: str = "graph-1", **extra) -> dict:
    return {
        "feature_id": lane_id,
        "status": "gated",
        "prompt": f"Implement {lane_id}",
        "graph_id": graph_id,
        "gate_passed": True,
        **extra,
    }


def _merge_verdict(lane_id: str, verdict_id: str = "verdict-1") -> ReviewVerdict:
    return ReviewVerdict(
        id=verdict_id,
        lane_id=lane_id,
        decision=ReviewDecision.MERGE,
        summary="No findings. Ready to merge.",
    )


def _write_blueprint(path: Path) -> None:
    path.write_text(
        "# xmuse Initial Self-Evolution Blueprint\n\n"
        "- `blueprint_set_id`: `xmuse-self-evolution-v0`\n\n"
        "## Priority Policy\n\n"
        "1. `graph_authority`\n"
        "2. `review_plane`\n"
        "3. `self_evolution_loop`\n\n"
        "## Tracks\n\n"
        "### graph_authority\n"
        "### review_plane\n"
        "### self_evolution_loop\n",
        encoding="utf-8",
    )


def _write_graph(tmp_path: Path, graph_id: str, lane_ids: list[str]) -> None:
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": f"conv-{graph_id}",
            "resolution_id": f"res-{graph_id}",
            "version": 1,
            "lanes": [
                {"feature_id": lid, "prompt": f"Implement {lid}"}
                for lid in lane_ids
            ],
        },
    )


# ---------------------------------------------------------------------------
# verdict_lineage_for_run
# ---------------------------------------------------------------------------


def test_verdict_lineage_for_run_returns_entries_for_all_graph_lanes(
    tmp_path: Path,
) -> None:
    controller = _make_controller(
        tmp_path,
        [
            _gated_lane("lane-a", graph_id="graph-run"),
            _gated_lane("lane-b", graph_id="graph-run"),
        ],
    )
    task_a = controller.open_review_task("lane-a")
    task_b = controller.open_review_task("lane-b")
    controller.ingest_verdict(task_a.task_id, _merge_verdict("lane-a", "verdict-a"))
    controller.ingest_verdict(task_b.task_id, _merge_verdict("lane-b", "verdict-b"))

    lineage = controller.verdict_lineage_for_run("graph-run")

    lane_ids = {entry["task"]["lane_id"] for entry in lineage}
    assert lane_ids == {"lane-a", "lane-b"}
    verdict_ids = {entry["verdict"]["id"] for entry in lineage if entry["verdict"]}
    assert verdict_ids == {"verdict-a", "verdict-b"}


def test_verdict_lineage_for_run_empty_when_no_tasks_exist(tmp_path: Path) -> None:
    controller = _make_controller(
        tmp_path,
        [_gated_lane("lane-no-task", graph_id="graph-empty")],
    )

    lineage = controller.verdict_lineage_for_run("graph-empty")

    assert lineage == []


def test_verdict_lineage_for_run_excludes_lanes_from_other_graphs(
    tmp_path: Path,
) -> None:
    controller = _make_controller(
        tmp_path,
        [
            _gated_lane("lane-target", graph_id="graph-target"),
            _gated_lane("lane-other", graph_id="graph-other"),
        ],
    )
    task_target = controller.open_review_task("lane-target")
    task_other = controller.open_review_task("lane-other")
    controller.ingest_verdict(
        task_target.task_id, _merge_verdict("lane-target", "verdict-target")
    )
    controller.ingest_verdict(
        task_other.task_id, _merge_verdict("lane-other", "verdict-other")
    )

    lineage = controller.verdict_lineage_for_run("graph-target")

    lane_ids = {entry["task"]["lane_id"] for entry in lineage}
    assert lane_ids == {"lane-target"}
    assert "lane-other" not in lane_ids


def test_verdict_lineage_for_run_includes_patch_forward_descendants(
    tmp_path: Path,
) -> None:
    """Patch-forward lanes linked via source_lane_id appear in run lineage."""
    controller = _make_controller(
        tmp_path,
        [
            _gated_lane("lane-orig", graph_id="graph-pf"),
            # Patch-forward descendant: same graph, source_lane_id set.
            {
                "feature_id": "lane-orig-patch-forward",
                "status": "gated",
                "prompt": "Fix edge case.",
                "graph_id": "graph-pf",
                "source_lane_id": "lane-orig",
                "gate_passed": True,
            },
        ],
    )
    task_orig = controller.open_review_task("lane-orig")
    task_pf = controller.open_review_task("lane-orig-patch-forward")
    controller.ingest_verdict(
        task_orig.task_id, _merge_verdict("lane-orig", "verdict-orig")
    )
    controller.ingest_verdict(
        task_pf.task_id, _merge_verdict("lane-orig-patch-forward", "verdict-pf")
    )

    lineage = controller.verdict_lineage_for_run("graph-pf")

    lane_ids = {entry["task"]["lane_id"] for entry in lineage}
    assert "lane-orig" in lane_ids
    assert "lane-orig-patch-forward" in lane_ids


def test_verdict_lineage_for_run_multiple_tasks_per_lane(tmp_path: Path) -> None:
    """A reworked lane produces two tasks; both appear in run lineage."""
    from xmuse_core.structuring.models import ReviewTaskStatus

    controller = _make_controller(
        tmp_path,
        [_gated_lane("lane-rework", graph_id="graph-rw")],
    )
    # First review: rework
    task1 = controller.open_review_task("lane-rework")
    rework_verdict = ReviewVerdict(
        id="verdict-rw-1",
        lane_id="lane-rework",
        decision=ReviewDecision.REWORK,
        summary="Needs rework.",
    )
    controller.ingest_verdict(task1.task_id, rework_verdict)

    # Second review: merge
    task2 = controller.open_review_task("lane-rework")
    controller.ingest_verdict(
        task2.task_id, _merge_verdict("lane-rework", "verdict-rw-2")
    )

    lineage = controller.verdict_lineage_for_run("graph-rw")

    assert len(lineage) == 2
    decisions = {entry["verdict"]["decision"] for entry in lineage if entry["verdict"]}
    assert decisions == {"rework", "merge"}


def test_verdict_lineage_for_run_returns_empty_for_unknown_graph(
    tmp_path: Path,
) -> None:
    controller = _make_controller(tmp_path, [_gated_lane("lane-x", graph_id="graph-x")])
    task = controller.open_review_task("lane-x")
    controller.ingest_verdict(task.task_id, _merge_verdict("lane-x", "verdict-x"))

    lineage = controller.verdict_lineage_for_run("graph-nonexistent")

    assert lineage == []


# ---------------------------------------------------------------------------
# SelfEvolutionController auto-discovery of review_plane.json
# ---------------------------------------------------------------------------


def test_self_evolution_controller_auto_discovers_review_plane_json(
    tmp_path: Path,
) -> None:
    """When review_plane.json exists in xmuse_root, verdict_store is auto-wired."""
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    # Create the review_plane.json file (empty but present).
    review_plane_path = tmp_path / "review_plane.json"
    _write_json(review_plane_path, {"review_tasks": [], "review_verdicts": []})

    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    assert controller._verdict_store is not None


def test_self_evolution_controller_verdict_store_none_when_no_review_plane_json(
    tmp_path: Path,
) -> None:
    """When review_plane.json is absent, verdict_store is None (no auto-wiring)."""
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    # Ensure review_plane.json does NOT exist.
    assert not (tmp_path / "review_plane.json").exists()

    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    assert controller._verdict_store is None


def test_self_evolution_controller_explicit_verdict_store_path_overrides_auto(
    tmp_path: Path,
) -> None:
    """An explicit verdict_store_path is used even when review_plane.json exists."""
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    # Create both the default and an explicit path.
    _write_json(
        tmp_path / "review_plane.json",
        {"review_tasks": [], "review_verdicts": []},
    )
    explicit_path = tmp_path / "custom_verdicts.json"
    _write_json(explicit_path, {"review_tasks": [], "review_verdicts": []})

    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
        verdict_store_path=explicit_path,
    )

    assert controller._verdict_store is not None
    assert controller._verdict_store._path == explicit_path


# ---------------------------------------------------------------------------
# aggregation reads verdict_lineage from auto-wired review_plane.json
# ---------------------------------------------------------------------------


def test_aggregation_reads_verdict_lineage_from_auto_wired_store(
    tmp_path: Path,
) -> None:
    """When review_plane.json exists, aggregation verdict_lineage uses the store."""
    graph_id = "res-auto-wire-graph-v1"
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    _write_graph(tmp_path, graph_id, ["lane-auto"])
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-auto",
                    "status": "merged",
                    "graph_id": graph_id,
                }
            ]
        },
    )
    # Write a verdict into review_plane.json directly.
    store = VerdictStore(tmp_path / "review_plane.json")
    store.save_verdict(
        ReviewVerdict(
            id="verdict-auto-1",
            lane_id="lane-auto",
            decision=ReviewDecision.MERGE,
            summary="Auto-wired verdict.",
            created_at="2026-05-28T00:00:00Z",
        )
    )

    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
        # No explicit verdict_store_path — should auto-discover.
    )
    aggregation = controller.aggregate_run_terminal(graph_id)

    assert len(aggregation.verdict_lineage) == 1
    entry = aggregation.verdict_lineage[0]
    assert entry["lane_id"] == "lane-auto"
    assert entry["verdict_id"] == "verdict-auto-1"
    assert entry["source"] == "verdict_store"


def test_aggregation_falls_back_to_lane_metadata_when_no_review_plane_json(
    tmp_path: Path,
) -> None:
    """When review_plane.json is absent, aggregation falls back to lane metadata."""
    graph_id = "res-fallback-graph-v1"
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    _write_graph(tmp_path, graph_id, ["lane-fallback"])
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-fallback",
                    "status": "merged",
                    "graph_id": graph_id,
                    "review_verdict_id": "verdict-meta-1",
                    "review_decision": "merge",
                    "review_summary": "Metadata fallback verdict.",
                }
            ]
        },
    )
    # Ensure review_plane.json does NOT exist.
    assert not (tmp_path / "review_plane.json").exists()

    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )
    aggregation = controller.aggregate_run_terminal(graph_id)

    assert len(aggregation.verdict_lineage) == 1
    entry = aggregation.verdict_lineage[0]
    assert entry["verdict_id"] == "verdict-meta-1"
    assert entry["source"] == "lane_metadata"


def test_aggregation_verdict_lineage_empty_when_no_verdicts_and_no_store(
    tmp_path: Path,
) -> None:
    """No verdict lineage when neither store nor lane metadata has verdicts."""
    graph_id = "res-no-verdict-graph-v1"
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    _write_graph(tmp_path, graph_id, ["lane-no-verdict"])
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-no-verdict",
                    "status": "merged",
                    "graph_id": graph_id,
                }
            ]
        },
    )
    assert not (tmp_path / "review_plane.json").exists()

    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )
    aggregation = controller.aggregate_run_terminal(graph_id)

    assert aggregation.verdict_lineage == []
