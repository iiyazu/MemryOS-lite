import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xmuse_core.self_evolution import (
    EvolutionBudgetWindow,
    SelfEvolutionController,
    StructuredEvidenceBundle,
)
from xmuse_core.self_evolution.models import RunTerminalStatus

PROJECT = Path(__file__).resolve().parents[1]
DASHBOARD_MODULE_PATH = PROJECT / "xmuse" / "dashboard_api.py"


def _load_dashboard_module():
    spec = importlib.util.spec_from_file_location(
        "xmuse_dashboard_api_self_evolution",
        DASHBOARD_MODULE_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_blueprint(path: Path) -> None:
    path.write_text(
        """
# xmuse Initial Self-Evolution Blueprint

- `blueprint_set_id`: `xmuse-self-evolution-v0`

## Tracks

### graph_authority
### review_plane
### self_evolution_loop
### clarification_recovery
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_single_track_blueprint(path: Path) -> None:
    path.write_text(
        """
# xmuse Initial Self-Evolution Blueprint

- `blueprint_set_id`: `xmuse-self-evolution-v0`

## Tracks

### self_evolution_loop
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _seed_merged_run(tmp_path: Path) -> str:
    graph_id = "res-source-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-source",
            "resolution_id": "res-source",
            "version": 1,
            "status": "planned",
            "lanes": [
                {"feature_id": "source-lane-1", "prompt": "first", "depends_on": []},
                {
                    "feature_id": "source-lane-2",
                    "prompt": "second",
                    "depends_on": ["source-lane-1"],
                },
            ],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "source-lane-1",
                    "status": "merged",
                    "prompt": "first",
                    "graph_id": graph_id,
                    "resolution_id": "res-source",
                    "review_verdict_id": "verdict-1",
                },
                {
                    "feature_id": "source-lane-2",
                    "status": "merged",
                    "prompt": "second",
                    "graph_id": graph_id,
                    "resolution_id": "res-source",
                    "review_verdict_id": "verdict-2",
                },
            ]
        },
    )
    return graph_id


def _seed_merged_review_signal_run(tmp_path: Path) -> tuple[str, str]:
    graph_id = "res-merged-review-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-res-review-success-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-merged-review",
            "resolution_id": "res-merged-review",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-merged-review",
                    "gate_passed": True,
                    "review_decision": "merge",
                    "retry_count": 1,
                    "review_summary": (
                        "No blocking findings in the current lane state.\n\n"
                        "Verification:\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution.py -q` "
                        "-> `18 passed`\n"
                        "- `uv run ruff check src/xmuse_core/self_evolution/controller.py` "
                        "-> `All checks passed`"
                    ),
                }
            ]
        },
    )
    return graph_id, lane_id


def test_aggregate_run_terminal_reports_graph_level_merged(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = _seed_merged_run(tmp_path)

    aggregation = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    ).aggregate_run_terminal(graph_id)

    assert aggregation.status == "merged"
    assert aggregation.terminal is True
    assert aggregation.reason == "all graph lineage lanes merged"
    assert aggregation.lane_counts["merged"] == 2


def test_aggregate_run_terminal_treats_review_infra_failure_as_running(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-review-infra-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-review-infra",
            "resolution_id": "res-review-infra",
            "version": 1,
            "status": "planned",
            "lanes": [
                {"feature_id": "lane-infra", "prompt": "review blocked", "depends_on": []},
            ],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-infra",
                    "status": "gate_failed",
                    "prompt": "review blocked",
                    "graph_id": graph_id,
                    "resolution_id": "res-review-infra",
                    "gate_passed": True,
                    "failure_reason": "review_infra_unavailable",
                },
            ]
        },
    )

    aggregation = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    ).aggregate_run_terminal(graph_id)

    assert aggregation.status == RunTerminalStatus.RUNNING
    assert aggregation.terminal is False
    assert aggregation.lane_counts["terminal"] == 0
    assert aggregation.lane_counts["review_infra_unavailable"] == 1


def test_aggregate_run_terminal_treats_legacy_done_as_merged(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-legacy-done-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-legacy",
            "resolution_id": "res-legacy",
            "version": 1,
            "status": "planned",
            "lanes": [
                {"feature_id": "legacy-done", "prompt": "done", "depends_on": []},
                {
                    "feature_id": "legacy-completed",
                    "prompt": "completed",
                    "depends_on": [],
                },
            ],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "legacy-done",
                    "status": "done",
                    "prompt": "done",
                    "graph_id": graph_id,
                },
                {
                    "feature_id": "legacy-completed",
                    "status": "completed",
                    "prompt": "completed",
                    "graph_id": graph_id,
                },
            ]
        },
    )

    aggregation = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    ).aggregate_run_terminal(graph_id)

    assert aggregation.status == "merged"
    assert aggregation.terminal is True
    assert aggregation.lane_counts["merged"] == 2


def test_aggregate_run_terminal_reports_high_quality_blocked_for_input(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-blocked-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-blocked",
            "resolution_id": "res-blocked",
            "version": 1,
            "lanes": [{"feature_id": "blocked-lane", "prompt": "needs info"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "blocked-lane",
                    "status": "blocked_for_input",
                    "prompt": "needs info",
                    "graph_id": graph_id,
                    "missing_input": "target deployment environment",
                    "input_owner": "human",
                    "resume_path": "add deployment target and resume graph",
                }
            ]
        },
    )

    aggregation = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    ).aggregate_run_terminal(graph_id)

    assert aggregation.status == "blocked_for_input"
    assert aggregation.terminal is True
    assert aggregation.blocked_objects == [
        {
            "lane_id": "blocked-lane",
            "missing_input": "target deployment environment",
            "owner": "human",
            "resume_path": "add deployment target and resume graph",
        }
    ]


def test_merged_lane_stale_clarification_does_not_block_run(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-stale-clarification-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-stale",
            "resolution_id": "res-stale",
            "version": 1,
            "lanes": [{"feature_id": "lane-with-old-clarification", "prompt": "done"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-with-old-clarification",
                    "status": "merged",
                    "prompt": "done",
                    "graph_id": graph_id,
                    "clarification_request": {
                        "missing_input": "old question",
                        "owner": "human",
                        "resume_path": "obsolete",
                    },
                }
            ]
        },
    )

    aggregation = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    ).aggregate_run_terminal(graph_id)

    assert aggregation.status == "merged"
    assert aggregation.blocked_objects == []


def test_patch_forward_descendant_keeps_run_non_terminal(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-patch-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-patch",
            "resolution_id": "res-patch",
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
                    "prompt": "source",
                    "graph_id": graph_id,
                },
                {
                    "feature_id": "source-lane-patch-forward",
                    "status": "pending",
                    "prompt": "patch",
                    "source_lane_id": "source-lane",
                    "graph_id": graph_id,
                },
            ]
        },
    )

    aggregation = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    ).aggregate_run_terminal(graph_id)

    assert aggregation.status == "running"
    assert aggregation.terminal is False
    assert aggregation.reason == "at least one graph lineage lane is not terminal"


def test_evidence_bundle_captures_patch_forward_descendant_without_graph_id(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-patch-signal-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-patch-signal",
            "resolution_id": "res-patch-signal",
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
                    "prompt": "source",
                    "graph_id": graph_id,
                },
                {
                    "feature_id": "source-lane-patch-forward",
                    "status": "failed",
                    "prompt": "patch",
                    "source_lane_id": "source-lane",
                    "gate_passed": True,
                    "review_decision": "rework",
                    "retry_count": 1,
                },
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert aggregation.lane_counts["total"] == 2
    assert evidence.lineage_refs == ["lane:source-lane->source-lane-patch-forward"]
    assert any(
        signal["feature_id"] == "source-lane-patch-forward"
        and signal["review_decision"] == "rework"
        and signal["gate_passed"] is True
        for signal in lane_signals
    )


def test_evidence_bundle_captures_terminal_review_signal_for_next_prompt(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-review-rework-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-source-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-review-rework",
            "resolution_id": "res-review-rework",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "failed",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-review-rework",
                    "gate_passed": True,
                    "review_decision": "rework",
                    "retry_count": 2,
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals == [
        {
            "feature_id": lane_id,
            "gate_passed": True,
            "normalized_status": "terminated",
            "raw_status": "failed",
            "retry_count": 2,
            "review_decision": "rework",
            "terminal": True,
        }
    ]
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert f"Use evidence bundle {evidence.bundle_id}" in prompt
    assert f"lane {lane_id} status=terminated review=rework" in prompt


def test_rework_review_findings_are_preserved_as_compact_evidence_signals(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-review-findings-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-source-review-findings-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-review-findings",
            "resolution_id": "res-review-findings",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "failed",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-review-findings",
                    "gate_passed": True,
                    "review_decision": "rework",
                    "retry_count": 2,
                    "review_summary": (
                        "**Findings**\n"
                        "1. High: externally reported executed lanes can stall before gates.\n"
                        "2. Medium: patch-forward lineage evidence drops descendant review signals."
                    ),
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals[0]["review_findings"] == [
        "High: externally reported executed lanes can stall before gates.",
        "Medium: patch-forward lineage evidence drops descendant review signals.",
    ]
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert "review=rework gate=passed retries=2" in prompt
    assert "finding=High: externally reported executed lanes can stall before gates." in prompt


def test_merge_review_confirmations_are_preserved_as_compact_evidence_signals(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id, lane_id = _seed_merged_review_signal_run(tmp_path)
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert evidence.selection_policy_version == "21"
    assert lane_signals == [
        {
            "feature_id": lane_id,
            "gate_passed": True,
            "normalized_status": "merged",
            "raw_status": "merged",
            "retry_count": 1,
            "review_confirmations": [
                "uv run pytest tests/test_xmuse_self_evolution.py -q -> 18 passed",
                (
                    "uv run ruff check src/xmuse_core/self_evolution/controller.py "
                    "-> All checks passed"
                ),
            ],
            "review_decision": "merge",
            "terminal": True,
        }
    ]
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert f"lane {lane_id} status=merged review=merge gate=passed retries=1" in prompt
    assert "confirmation=uv run pytest tests/test_xmuse_self_evolution.py -q -> 18 passed" in prompt
    assert "confirmation=uv run ruff check src/xmuse_core/self_evolution/controller.py" in prompt


def test_lane_recovery_provenance_is_preserved_as_compact_evidence_signal(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id, lane_id = _seed_merged_review_signal_run(tmp_path)
    lanes_path = tmp_path / "feature_lanes.json"
    lanes_data = json.loads(lanes_path.read_text(encoding="utf-8"))
    for lane in lanes_data["lanes"]:
        if lane.get("feature_id") == lane_id:
            lane["manual_recovery"] = (
                "applied parser risk fix after codex patch-conflict non_zero_exit"
            )
            lane["review_fallback"] = "stdout"
    lanes_path.write_text(json.dumps(lanes_data, indent=2) + "\n", encoding="utf-8")
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals[0]["manual_recovery"] == (
        "applied parser risk fix after codex patch-conflict non_zero_exit"
    )
    assert lane_signals[0]["review_fallback"] == "stdout"
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert "review_source=stdout" in prompt
    assert "review_fallback=stdout" in prompt
    assert (
        "recovery=applied parser risk fix after codex patch-conflict non_zero_exit"
        in prompt
    )


def test_review_fallback_reason_is_preserved_as_compact_evidence_signal(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id, lane_id = _seed_merged_review_signal_run(tmp_path)
    lanes_path = tmp_path / "feature_lanes.json"
    lanes_data = json.loads(lanes_path.read_text(encoding="utf-8"))
    for lane in lanes_data["lanes"]:
        if lane.get("feature_id") == lane_id:
            lane["review_fallback"] = "stdout"
            lane["review_fallback_reason"] = "reproduced_finding"
    lanes_path.write_text(json.dumps(lanes_data, indent=2) + "\n", encoding="utf-8")
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals[0]["review_fallback"] == "stdout"
    assert lane_signals[0]["review_fallback_reason"] == "reproduced_finding"
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert "review_source=stdout" in prompt
    assert "review_fallback=stdout" in prompt
    assert "fallback_reason=reproduced_finding" in prompt


def test_review_recovery_reason_is_derived_for_false_positive_fallback_merge(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id, lane_id = _seed_merged_review_signal_run(tmp_path)
    lanes_path = tmp_path / "feature_lanes.json"
    lanes_data = json.loads(lanes_path.read_text(encoding="utf-8"))
    for lane in lanes_data["lanes"]:
        if lane.get("feature_id") == lane_id:
            lane["review_fallback"] = "stdout"
            lane["manual_recovery"] = (
                "fixed reproduced-finding fallback after false-positive merge"
            )
            lane["review_summary"] = (
                "Manual recovery after false-positive merge: tightened stdout fallback "
                "so still-reproduces review text is treated as rework.\n\n"
                "Residual risk: recovery was applied directly by monitor after review "
                "fallback misclassified a reproduced finding as merge."
            )
    lanes_path.write_text(json.dumps(lanes_data, indent=2) + "\n", encoding="utf-8")
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals[0]["review_recovery_reason"] == (
        "reproduced_finding_false_positive_merge"
    )
    assert "review_fallback_reason" not in lane_signals[0]
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert "review_source=stdout" in prompt
    assert "review_fallback=stdout" in prompt
    assert "recovery_reason=reproduced_finding_false_positive_merge" in prompt
    assert (
        "risk=recovery was applied directly by monitor after review fallback "
        "misclassified a reproduced finding as merge."
        in prompt
    )


def test_review_scope_refs_are_preserved_as_compact_evidence_signals(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-review-scope-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-source-review-scope-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-review-scope",
            "resolution_id": "res-review-scope",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-review-scope",
                    "gate_passed": True,
                    "review_decision": "merge",
                    "review_fallback": "stdout",
                    "review_summary": (
                        "No findings for the lane.\n\n"
                        "Reviewed the touched evidence path around "
                        "[controller.py](/home/iiyatu/projects/python/memoryOS/"
                        "src/xmuse_core/self_evolution/controller.py:37) and "
                        "the regression at [test_xmuse_self_evolution.py]"
                        "(/home/iiyatu/projects/python/memoryOS/"
                        "tests/test_xmuse_self_evolution.py:1131).\n\n"
                        "Verification:\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution.py -q` "
                        "-> `59 passed`\n\n"
                        "Residual risk: review was scoped to live lane artifacts."
                    ),
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals[0]["review_scope_refs"] == [
        "src/xmuse_core/self_evolution/controller.py",
        "tests/test_xmuse_self_evolution.py",
    ]
    expected = (
        "reviewed=src/xmuse_core/self_evolution/controller.py,"
        "tests/test_xmuse_self_evolution.py"
    )
    assert expected in evidence.summary
    assert expected in proposal.candidate_graph["lanes"][0]["prompt"]


def test_bold_verification_heading_stops_review_scope_ref_collection(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-review-scope-bold-verification-graph-v1"
    lane_id = (
        "self-evolution-self_evolution_loop-source-review-scope-bold-"
        "verification-graph-v1"
    )
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-review-scope-bold-verification",
            "resolution_id": "res-review-scope-bold-verification",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-review-scope-bold-verification",
                    "gate_passed": True,
                    "review_decision": "merge",
                    "review_fallback": "stdout",
                    "review_summary": (
                        "No findings for the lane.\n\n"
                        "**Verification**\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution.py -q` "
                        "-> `59 passed`\n\n"
                        "Residual risk: review was scoped to live lane artifacts."
                    ),
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert "review_scope_refs" not in lane_signals[0]
    assert "reviewed=tests/test_xmuse_self_evolution.py" not in evidence.summary
    assert "reviewed=tests/test_xmuse_self_evolution.py" not in (
        proposal.candidate_graph["lanes"][0]["prompt"]
    )


def test_failed_verification_lines_are_not_stored_as_merge_confirmations(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-mixed-verification-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-source-mixed-verification-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-mixed-verification",
            "resolution_id": "res-mixed-verification",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-mixed-verification",
                    "gate_passed": True,
                    "review_decision": "merge",
                    "review_summary": (
                        "Verification:\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution.py -q` "
                        "-> `1 failed, 17 passed`\n"
                        "- `uv run ruff check src/xmuse_core/self_evolution/controller.py` "
                        "-> `All checks passed`"
                    ),
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals[0]["review_confirmations"] == [
        "uv run ruff check src/xmuse_core/self_evolution/controller.py -> All checks passed"
    ]
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert "1 failed, 17 passed" not in evidence.summary
    assert "1 failed, 17 passed" not in prompt
    assert "confirmation=uv run ruff check" in prompt


def test_merge_review_verification_run_header_is_evidence_first(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-review-verification-run-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-source-verification-run-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-review-verification-run",
            "resolution_id": "res-review-verification-run",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-review-verification-run",
                    "gate_passed": True,
                    "review_decision": "merge",
                    "review_summary": (
                        "No findings in the reviewed scope.\n\n"
                        "Verification run:\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution.py -q` "
                        "-> `20 passed`\n"
                        "- `uv run ruff check src/xmuse_core/self_evolution/controller.py "
                        "tests/test_xmuse_self_evolution.py` -> passed"
                    ),
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals[0]["review_confirmations"] == [
        "uv run pytest tests/test_xmuse_self_evolution.py -q -> 20 passed",
        (
            "uv run ruff check src/xmuse_core/self_evolution/controller.py "
            "tests/test_xmuse_self_evolution.py -> passed"
        ),
    ]
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert "status=merged review=merge gate=passed" in prompt
    assert "confirmation=uv run pytest tests/test_xmuse_self_evolution.py -q -> 20 passed" in prompt
    assert "confirmation=uv run ruff check src/xmuse_core/self_evolution/controller.py" in prompt


def test_multiple_merge_verifications_displace_generic_no_findings_in_signal_slots(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-many-verifications-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-source-many-verifications-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-many-verifications",
            "resolution_id": "res-many-verifications",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-many-verifications",
                    "gate_passed": True,
                    "review_decision": "merge",
                    "review_summary": (
                        "No findings in the reviewed scope.\n\n"
                        "Verification run:\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution.py -q` "
                        "-> `21 passed`\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution_checkpoint.py -q` "
                        "-> `1 passed`\n"
                        "- `uv run ruff check src/xmuse_core/self_evolution/controller.py "
                        "tests/test_xmuse_self_evolution.py` -> passed"
                    ),
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals[0]["review_confirmations"] == [
        "uv run pytest tests/test_xmuse_self_evolution.py -q -> 21 passed",
        "uv run pytest tests/test_xmuse_self_evolution_checkpoint.py -q -> 1 passed",
    ]
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert "confirmation=uv run pytest tests/test_xmuse_self_evolution.py -q -> 21 passed" in prompt
    assert (
        "confirmation=uv run pytest tests/test_xmuse_self_evolution_checkpoint.py -q -> 1 passed"
        in prompt
    )
    assert "No findings in the reviewed scope" not in evidence.summary
    assert "No findings in the reviewed scope" not in prompt


def test_narrow_targeted_confirmation_does_not_displace_broader_merge_evidence(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-broader-confirmations-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-source-broader-confirmations-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-broader-confirmations",
            "resolution_id": "res-broader-confirmations",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-broader-confirmations",
                    "gate_passed": True,
                    "review_decision": "merge",
                    "review_summary": (
                        "Verification:\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution.py::test_small -q` "
                        "-> `2 passed`\n"
                        "- `uv run ruff check src/xmuse_core/self_evolution/controller.py "
                        "tests/test_xmuse_self_evolution.py` -> passed\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution.py "
                        "tests/test_xmuse_self_evolution_checkpoint.py -q` -> `38 passed`"
                    ),
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals[0]["review_confirmations"] == [
        (
            "uv run ruff check src/xmuse_core/self_evolution/controller.py "
            "tests/test_xmuse_self_evolution.py -> passed"
        ),
        (
            "uv run pytest tests/test_xmuse_self_evolution.py "
            "tests/test_xmuse_self_evolution_checkpoint.py -q -> 38 passed"
        ),
    ]
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert "test_small" not in prompt
    assert "confirmation=uv run ruff check src/xmuse_core/self_evolution/controller.py" in prompt
    assert (
        "confirmation=uv run pytest tests/test_xmuse_self_evolution.py "
        "tests/test_xmuse_self_evolution_checkpoint.py -q -> 38 passed"
        in prompt
    )


def test_bare_passed_verification_lines_are_evidence_confirmations(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-bare-passed-confirmations-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-source-bare-passed-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-bare-passed-confirmations",
            "resolution_id": "res-bare-passed-confirmations",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-bare-passed-confirmations",
                    "gate_passed": True,
                    "review_decision": "merge",
                    "review_summary": (
                        f"No findings for `{lane_id}`.\n\n"
                        "Verification:\n"
                        "- `uv run ruff check src/xmuse_core/self_evolution/controller.py "
                        "tests/test_xmuse_self_evolution.py` passed\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution.py::"
                        "test_long_gate_diagnostic_preserves_dirty_worktree_warning_tail -q` "
                        "passed\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution.py "
                        "tests/test_xmuse_self_evolution_checkpoint.py -q` passed: 42 tests\n"
                        "- Existing lane gate report shows `214 passed, 1 warning`; "
                        "warning is the known asyncio resource warning."
                    ),
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals[0]["review_confirmations"] == [
        (
            "uv run ruff check src/xmuse_core/self_evolution/controller.py "
            "tests/test_xmuse_self_evolution.py passed"
        ),
        (
            "uv run pytest tests/test_xmuse_self_evolution.py "
            "tests/test_xmuse_self_evolution_checkpoint.py -q passed: 42 tests"
        ),
    ]
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert "confirmation=uv run ruff check src/xmuse_core/self_evolution/controller.py" in prompt
    assert (
        "confirmation=uv run pytest tests/test_xmuse_self_evolution.py "
        "tests/test_xmuse_self_evolution_checkpoint.py -q passed: 42 tests"
        in prompt
    )
    assert "No findings for" not in prompt
    assert "Existing lane gate report shows" not in prompt


def test_result_line_confirmation_preserves_preceding_verification_command(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-command-result-confirmation-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-command-result-confirmation-graph-v1"
    command = (
        "uv run pytest tests/test_xmuse_self_evolution.py::"
        "test_review_residual_risk_is_preserved_as_evidence_signal "
        "tests/test_xmuse_self_evolution.py::"
        "test_review_residual_risk_stops_at_later_review_section_heading "
        "tests/test_xmuse_self_evolution.py::"
        "test_guardrail_dedup_ignores_review_risk_signal -q"
    )
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-command-result-confirmation",
            "resolution_id": "res-command-result-confirmation",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-command-result-confirmation",
                    "gate_passed": True,
                    "review_decision": "merge",
                    "retry_count": 1,
                    "review_summary": (
                        "Decision: merge.\n\n"
                        "**Findings**\n\n"
                        f"No findings for `{lane_id}`.\n\n"
                        "**Verification**\n\n"
                        "I ran the focused regression set:\n\n"
                        f"`{command}`\n\n"
                        "Result: `3 passed`.\n\n"
                        "The lane gate report also shows `218 passed, 1 warning`; "
                        "the warning is the known asyncio unraisable subprocess cleanup warning."
                    ),
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert lane_signals[0]["review_confirmations"][0].startswith(
        "uv run pytest tests/test_xmuse_self_evolution.py::"
        "test_review_residual_risk_is_preserved_as_evidence_signal"
    )
    assert lane_signals[0]["review_confirmations"][0].endswith(" -> 3 passed.")
    assert lane_signals[0]["review_confirmations"][1] == (
        "The lane gate report also shows 218 passed, 1 warning; the warning is "
        "the known asyncio unraisable subprocess cleanup warning."
    )
    assert "confirmation=Result: 3 passed" not in prompt
    assert "confirmation=uv run pytest tests/test_xmuse_self_evolution.py::" in prompt
    assert "... -> 3 passed." in prompt
    assert (
        "confirmation=The lane gate report also shows 218 passed, 1 warning; "
        "the warning is the known asyncio unraisable subprocess cleanup..."
    ) in prompt


def test_review_residual_risk_is_preserved_as_evidence_signal(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-review-risk-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-source-review-risk-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-review-risk",
            "resolution_id": "res-review-risk",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-review-risk",
                    "gate_passed": True,
                    "review_decision": "merge",
                    "review_summary": (
                        "No findings in the reviewed scope.\n\n"
                        "Verification run:\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution.py -q` "
                        "-> `42 passed`\n\n"
                        "Residual risk: I did not run the full repository suite.\n"
                        "The workspace is dirty, so review used live lane artifacts."
                    ),
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert evidence.selection_policy_version == "21"
    assert lane_signals[0]["review_risks"] == [
        "I did not run the full repository suite.",
        "The workspace is dirty, so review used live lane artifacts.",
    ]
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert "risk=I did not run the full repository suite." in evidence.summary
    assert "risk=I did not run the full repository suite." in prompt
    assert "confirmation=uv run pytest tests/test_xmuse_self_evolution.py -q -> 42 passed" in prompt


def test_long_review_residual_risk_preserves_scope_tail_in_prompt(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-long-review-risk-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-source-long-review-risk-graph-v1"
    risk = (
        "I did not run the full repository suite, and the worktree is heavily "
        "dirty, so review isolation is scoped to this lane's self-evolution "
        "changes."
    )
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-long-review-risk",
            "resolution_id": "res-long-review-risk",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-long-review-risk",
                    "gate_passed": True,
                    "review_decision": "merge",
                    "retry_count": 1,
                    "review_summary": (
                        "No findings in the reviewed scope.\n\n"
                        "Verification run:\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution.py -q` "
                        "-> `58 passed`\n\n"
                        f"Residual risk: {risk}"
                    ),
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals[0]["review_risks"] == [risk]
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert "risk=I did not run the full repository suite" in evidence.summary
    assert "self-evolution changes." in evidence.summary
    assert "risk=I did not run the full repository suite" in prompt
    assert "self-evolution changes." in prompt
    assert "scoped to this lan..." not in prompt


def test_long_untracked_review_risk_preserves_path_and_clean_diff_tail(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-untracked-review-risk-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-source-untracked-review-risk-graph-v1"
    risk = (
        "the broader worktree is heavily dirty and "
        "src/xmuse_core/self_evolution/ is untracked, so this review is scoped "
        "to the lane artifact and current file contents rather than a clean tracked diff."
    )
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-untracked-review-risk",
            "resolution_id": "res-untracked-review-risk",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-untracked-review-risk",
                    "gate_passed": True,
                    "review_decision": "merge",
                    "review_fallback": "stdout",
                    "review_summary": (
                        "No findings in the reviewed scope.\n\n"
                        "Verification run:\n"
                        "- Existing lane gate: 230 passed, 1 warning\n\n"
                        f"Residual risk: {risk}"
                    ),
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    expected_risk = (
        "risk=the broader worktree is heavily dirty; "
        "src/xmuse_core/self_evolution/ is untracked; "
        "rather than a clean tracked diff."
    )
    assert expected_risk in evidence.summary
    assert expected_risk in prompt
    assert "src/xmuse_core/s...and current file contents" not in prompt


def test_review_residual_risk_stops_at_later_review_section_heading(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-review-risk-heading-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-source-review-risk-heading-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-review-risk-heading",
            "resolution_id": "res-review-risk-heading",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-review-risk-heading",
                    "gate_passed": True,
                    "review_decision": "merge",
                    "review_summary": (
                        "No findings in the reviewed scope.\n\n"
                        "Verification:\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution.py -q` "
                        "-> `42 passed`\n\n"
                        "Residual risk: I did not run the full suite.\n\n"
                        "Change summary:\n"
                        "- Added residual-risk evidence handling."
                    ),
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals[0]["review_risks"] == ["I did not run the full suite."]
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert "risk=I did not run the full suite." in prompt
    assert "Change summary" not in evidence.summary
    assert "Change summary" not in prompt
    assert "Added residual-risk evidence handling" not in prompt


def test_review_finding_residual_risk_examples_do_not_become_review_risks(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-review-finding-risk-example-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-source-finding-risk-example-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-finding-risk-example",
            "resolution_id": "res-finding-risk-example",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-finding-risk-example",
                    "gate_passed": True,
                    "review_decision": "merge",
                    "review_summary": (
                        "Decision: merge.\n\n"
                        "**Findings**\n"
                        "1. Medium-high: parser examples like Residual risk: I did "
                        "not run the full suite. should stay finding evidence.\n"
                        "2. Medium - another finding mentions residual risk: "
                        "workspace is dirty.\n\n"
                        "**Verification**\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution.py -q` "
                        "-> `42 passed`"
                    ),
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert "review_risks" not in lane_signals[0]
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert "risk=I did not run the full suite" not in prompt
    assert "risk=workspace is dirty" not in prompt
    assert "finding=Medium-high:" in prompt


def test_review_residual_risk_after_findings_block_is_preserved(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-review-risk-after-findings-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-source-risk-after-findings-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-risk-after-findings",
            "resolution_id": "res-risk-after-findings",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-risk-after-findings",
                    "gate_passed": True,
                    "review_decision": "merge",
                    "review_summary": (
                        "**Findings**\n"
                        "1. Low: non-blocking issue remains.\n\n"
                        "Residual risk:\n"
                        "I did not run the full repository suite.\n\n"
                        "**Verification**\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution.py -q` "
                        "-> `42 passed`"
                    ),
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals[0]["review_risks"] == [
        "I did not run the full repository suite."
    ]
    assert "risk=I did not run the full repository suite." in evidence.summary
    assert "risk=I did not run the full repository suite." in (
        proposal.candidate_graph["lanes"][0]["prompt"]
    )


def test_inline_main_residual_risk_is_preserved_as_evidence_signal(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-inline-review-risk-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-source-inline-review-risk-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-inline-review-risk",
            "resolution_id": "res-inline-review-risk",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-inline-review-risk",
                    "gate_passed": True,
                    "review_decision": "merge",
                    "review_summary": (
                        "No blocking findings for the lane.\n\n"
                        "Verification:\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution.py::"
                        "test_gate_report_signal_remains_visible_with_many_lane_signals "
                        "-q` -> `2 passed in 0.27s`\n\n"
                        "Lane gate artifact also reports `220 passed, 1 warning` "
                        "for the `xmuse-core` profile. The main residual risk is "
                        "scope: the broader worktree is very dirty, so this review "
                        "is limited to the named lane delta and its saved artifacts.\n\n"
                        "Change summary:\n"
                        "- Promoted inline residual risk wording."
                    ),
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals[0]["review_risks"] == [
        (
            "scope: the broader worktree is very dirty, so this review is "
            "limited to the named lane delta and its saved artifacts."
        )
    ]
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert "risk=scope: the broader worktree is very dirty" in evidence.summary
    assert "risk=scope: the broader worktree is very dirty" in prompt
    assert "Promoted inline residual risk wording" not in prompt


def test_gate_artifact_confirmation_strips_inline_residual_risk_clause(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-inline-gate-risk-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-source-inline-gate-risk-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-inline-gate-risk",
            "resolution_id": "res-inline-gate-risk",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-inline-gate-risk",
                    "gate_passed": True,
                    "review_decision": "merge",
                    "review_summary": (
                        "No blocking findings for the lane.\n\n"
                        "Verification:\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution.py::"
                        "test_inline_main_residual_risk_is_preserved_as_evidence_signal "
                        "tests/test_xmuse_self_evolution.py::"
                        "test_review_residual_risk_is_preserved_as_evidence_signal -q` "
                        "-> `4 passed in 0.31s`.\n\n"
                        "Gate artifact also reports `221 passed, 1 warning` for the "
                        "`xmuse-core` profile. Residual risk: review was scoped to "
                        "this lane patch and saved artifacts because the broader "
                        "worktree is very dirty and these files are currently untracked."
                    ),
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals[0]["review_confirmations"] == [
        (
            "uv run pytest tests/test_xmuse_self_evolution.py::"
            "test_inline_main_residual_risk_is_preserved_as_evidence_signal "
            "tests/test_xmuse_self_evolution.py::"
            "test_review_residual_risk_is_preserved_as_evid... -> 4 passed in 0.31s."
        ),
        "Gate artifact also reports 221 passed, 1 warning for the xmuse-core profile.",
    ]
    assert lane_signals[0]["review_risks"] == [
        (
            "review was scoped to this lane patch and saved artifacts because the "
            "broader worktree is very dirty and these files are currently untracked."
        )
    ]
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert (
        "confirmation=Gate artifact also reports 221 passed, 1 warning for the "
        "xmuse-core profile."
    ) in prompt
    assert (
        "confirmation=Gate artifact also reports 221 passed, 1 warning "
        "for the xmuse-core profile...:"
    ) not in prompt
    assert "risk=review was scoped to this lane patch and saved artifacts" in prompt


def test_general_confirmation_strips_inline_residual_risk_clause(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-general-confirmation-risk-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-source-general-risk-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-general-confirmation-risk",
            "resolution_id": "res-general-confirmation-risk",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-general-confirmation-risk",
                    "gate_passed": True,
                    "review_decision": "merge",
                    "review_summary": (
                        "No findings. Residual risk: I did not run the full suite."
                    ),
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals[0]["review_confirmations"] == ["No findings."]
    assert lane_signals[0]["review_risks"] == ["I did not run the full suite."]
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert "confirmation=No findings." in prompt
    assert "confirmation=No findings. Residual risk" not in prompt
    assert "risk=I did not run the full suite." in prompt


def test_findings_residual_risk_examples_do_not_become_review_risks(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-finding-risk-example-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-source-finding-risk-example-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-finding-risk-example",
            "resolution_id": "res-finding-risk-example",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-finding-risk-example",
                    "gate_passed": True,
                    "review_decision": "merge",
                    "review_summary": (
                        "Findings\n"
                        "1. Medium: inline residual-risk text still leaks into "
                        "`review_confirmations`. `No findings. Residual risk: I "
                        "did not run the full suite.` is still stored.\n"
                        "   `['No findings. Residual risk: I did not run the full "
                        "suite.']`\n\n"
                        "Verification:\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution.py "
                        "tests/test_xmuse_self_evolution_checkpoint.py -q` "
                        "-> `50 passed`"
                    ),
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert "review_risks" not in lane_signals[0]
    assert lane_signals[0]["review_confirmations"] == [
        (
            "uv run pytest tests/test_xmuse_self_evolution.py "
            "tests/test_xmuse_self_evolution_checkpoint.py -q -> 50 passed"
        )
    ]
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert "risk=I did not run the full suite" not in prompt
    assert "confirmation=uv run pytest tests/test_xmuse_self_evolution.py" in prompt


def test_multiple_merge_confirmations_are_delimited_in_evidence_summary(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-delimited-confirmations-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-source-delimited-confirmations-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-delimited-confirmations",
            "resolution_id": "res-delimited-confirmations",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-delimited-confirmations",
                    "gate_passed": True,
                    "review_decision": "merge",
                    "review_summary": (
                        "Verification:\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution.py -q` "
                        "-> `22 passed`\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution_checkpoint.py -q` "
                        "-> `1 passed`"
                    ),
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert (
        "confirmation=uv run pytest tests/test_xmuse_self_evolution.py -q -> 22 passed; "
        "confirmation=uv run pytest tests/test_xmuse_self_evolution_checkpoint.py -q -> 1 passed"
        in evidence.summary
    )
    assert (
        "confirmation=uv run pytest tests/test_xmuse_self_evolution.py -q -> 22 passed; "
        "confirmation=uv run pytest tests/test_xmuse_self_evolution_checkpoint.py -q -> 1 passed"
        in prompt
    )
    assert "22 passed confirmation=uv run pytest" not in prompt


def test_candidate_prompt_formats_lane_counts_as_readable_evidence_signal(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id, _lane_id = _seed_merged_review_signal_run(tmp_path)
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert 'lane_counts:{"merged": 1, "terminal": 1, "total": 1}' in evidence.signal_refs
    assert "lane_counts total=1 terminal=1 merged=1" in prompt
    assert 'lane_counts:{"merged": 1, "terminal": 1, "total": 1}' not in prompt


def test_evidence_summary_formats_lane_counts_as_readable_evidence_signal(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id, _lane_id = _seed_merged_review_signal_run(tmp_path)
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    assert "Evidence signals:" in evidence.summary
    assert "lane_counts total=1 terminal=1 merged=1" in evidence.summary
    assert 'lane_counts:{"merged": 1, "terminal": 1, "total": 1}' not in evidence.summary
    assert proposal.why_now == evidence.summary


def test_evidence_summary_formats_primary_lane_counts_without_python_dict(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id, _lane_id = _seed_merged_review_signal_run(tmp_path)
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    assert "Lane counts: total=1 terminal=1 merged=1." in evidence.summary
    assert "Lane counts: {'total': 1, 'terminal': 1, 'merged': 1}" not in evidence.summary
    assert proposal.why_now == evidence.summary


def test_gate_report_ref_is_promoted_to_compact_evidence_signal(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id, lane_id = _seed_merged_review_signal_run(tmp_path)
    report_ref = f"logs/gates/{lane_id}/report.json"
    _write_json(
        tmp_path / report_ref,
        {
            "status": "passed",
            "commands": [
                {"command": "uv run pytest tests/test_xmuse_self_evolution.py -q"}
            ],
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    assert evidence.gate_report_refs == [report_ref]
    assert f"gate_report:{report_ref}" in evidence.signal_refs
    assert f"gate_report={report_ref}" in evidence.summary
    assert f"gate_report={report_ref}" in proposal.candidate_graph["lanes"][0]["prompt"]


def test_legacy_gate_report_status_and_commands_become_evidence_signals(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id, lane_id = _seed_merged_review_signal_run(tmp_path)
    report_ref = f"logs/gates/{lane_id}/report.json"
    _write_json(
        tmp_path / report_ref,
        {
            "status": "passed",
            "commands": [
                {"command": "uv run pytest tests/test_xmuse_self_evolution.py -q"}
            ],
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    gate_results = [
        json.loads(signal.removeprefix("gate_report_result:"))
        for signal in evidence.signal_refs
        if signal.startswith("gate_report_result:")
    ]
    assert gate_results == [
        {
            "command": "uv run pytest tests/test_xmuse_self_evolution.py -q",
            "command_id": "command_1",
            "outcome": "passed",
            "profile_id": "unknown",
            "report_ref": report_ref,
        }
    ]
    expected_report = f"gate_report={report_ref} status=passed"
    expected_command = (
        "gate_command=uv run pytest tests/test_xmuse_self_evolution.py -q -> passed"
    )
    assert expected_report in evidence.summary
    assert expected_command in evidence.summary
    assert expected_report in proposal.candidate_graph["lanes"][0]["prompt"]
    assert expected_command in proposal.candidate_graph["lanes"][0]["prompt"]


def test_gate_report_summary_includes_outcome_and_profiles(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id, lane_id = _seed_merged_review_signal_run(tmp_path)
    report_ref = f"logs/gates/{lane_id}/report.json"
    _write_json(
        tmp_path / report_ref,
        {
            "passed": True,
            "blocking_passed": True,
            "profile_ids": ["xmuse-core"],
            "command_results": [],
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    expected = f"gate_report={report_ref} status=passed blocking=passed profiles=xmuse-core"
    assert f"gate_report:{report_ref}" in evidence.signal_refs
    assert expected in evidence.summary
    assert expected in proposal.candidate_graph["lanes"][0]["prompt"]


def test_gate_report_resolution_reasons_reach_evidence_prompt(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id, lane_id = _seed_merged_review_signal_run(tmp_path)
    report_ref = f"logs/gates/{lane_id}/report.json"
    _write_json(
        tmp_path / report_ref,
        {
            "passed": True,
            "blocking_passed": True,
            "profile_ids": ["xmuse-core"],
            "resolution_reasons": {
                "xmuse-core": [
                    "explicit_lane_profile",
                    "diff_selector",
                ]
            },
            "command_results": [],
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    scope_signals = [
        json.loads(signal.removeprefix("gate_report_resolution:"))
        for signal in evidence.signal_refs
        if signal.startswith("gate_report_resolution:")
    ]
    assert scope_signals == [
        {
            "profile_reasons": [
                {
                    "profile_id": "xmuse-core",
                    "reasons": ["explicit_lane_profile", "diff_selector"],
                }
            ],
            "report_ref": report_ref,
        }
    ]
    expected = (
        f"gate_scope={report_ref} profile=xmuse-core "
        "reason=explicit_lane_profile +1 reasons"
    )
    assert expected in evidence.summary
    assert expected in proposal.candidate_graph["lanes"][0]["prompt"]


def test_gate_report_command_result_is_promoted_to_evidence_signal(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id, lane_id = _seed_merged_review_signal_run(tmp_path)
    report_ref = f"logs/gates/{lane_id}/report.json"
    stdout_path = tmp_path / "logs" / "gates" / lane_id / "xmuse-core__pytest.stdout"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text(
        "................................\n"
        "======================= 33 passed in 1.23s =======================\n",
        encoding="utf-8",
    )
    _write_json(
        tmp_path / report_ref,
        {
            "passed": True,
            "command_results": [
                {
                    "command_id": "pytest",
                    "profile_id": "xmuse-core",
                    "argv": [
                        "uv",
                        "run",
                        "pytest",
                        "-q",
                        "tests/test_xmuse_self_evolution.py",
                    ],
                    "returncode": 0,
                    "stdout_path": str(stdout_path),
                }
            ],
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    gate_results = [
        json.loads(signal.removeprefix("gate_report_result:"))
        for signal in evidence.signal_refs
        if signal.startswith("gate_report_result:")
    ]
    assert gate_results == [
        {
            "argv": [
                "uv",
                "run",
                "pytest",
                "-q",
                "tests/test_xmuse_self_evolution.py",
            ],
            "command_id": "pytest",
            "outcome": "passed",
            "profile_id": "xmuse-core",
            "report_ref": report_ref,
            "returncode": 0,
            "stdout_summary": "33 passed in 1.23s",
        }
    ]
    expected = (
        "gate_command=uv run pytest -q tests/test_xmuse_self_evolution.py "
        "-> passed (33 passed in 1.23s)"
    )
    assert expected in evidence.summary
    assert expected in proposal.candidate_graph["lanes"][0]["prompt"]


def test_long_pytest_gate_command_summarizes_target_count_without_truncation(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id, lane_id = _seed_merged_review_signal_run(tmp_path)
    report_ref = f"logs/gates/{lane_id}/report.json"
    stdout_path = tmp_path / "logs" / "gates" / lane_id / "xmuse-core__pytest.stdout"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text("210 passed, 1 warning in 12.49s\n", encoding="utf-8")
    test_targets = [
        "tests/test_xmuse_quality_gate.py",
        "tests/test_xmuse_gate_profiles.py",
        "tests/test_xmuse_master_loop.py",
        "tests/test_xmuse_master_loop_integration.py",
        "tests/test_xmuse_auto_discovery.py",
        "tests/test_xmuse_rework_loop.py",
        "tests/test_xmuse_core_agents_consumer.py",
        "tests/test_xmuse_core_agents_launchers.py",
        "tests/test_xmuse_core_agents_manager.py",
        "tests/test_xmuse_core_agents_protocol.py",
        "tests/test_xmuse_core_agents_registry.py",
        "tests/test_xmuse_core_agents_session.py",
        "tests/test_xmuse_core_schema.py",
        "tests/test_xmuse_core_state.py",
        "tests/test_xmuse_core_status.py",
        "tests/test_xmuse_core_routing.py",
        "tests/test_xmuse_core_callback_server.py",
        "tests/test_xmuse_mcp_server.py",
        "tests/test_xmuse_overnight_runner.py",
        "tests/test_xmuse_self_evolution.py",
        "tests/test_xmuse_self_evolution_checkpoint.py",
    ]
    _write_json(
        tmp_path / report_ref,
        {
            "passed": True,
            "blocking_passed": True,
            "profile_ids": ["xmuse-core"],
            "warnings": ["explicit profile warning"],
            "command_results": [
                {
                    "command_id": "pytest",
                    "profile_id": "xmuse-core",
                    "argv": ["uv", "run", "pytest", "-q", *test_targets],
                    "returncode": 0,
                    "stdout_path": str(stdout_path),
                }
            ],
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    gate_results = [
        json.loads(signal.removeprefix("gate_report_result:"))
        for signal in evidence.signal_refs
        if signal.startswith("gate_report_result:")
    ]
    assert gate_results[0]["argv"] == ["uv", "run", "pytest", "-q", *test_targets]
    expected = (
        "gate_command=uv run pytest -q tests/test_xmuse_quality_gate.py "
        "tests/test_xmuse_gate_profiles.py +19 test files -> passed "
        "(210 passed, 1 warning in 12.49s)"
    )
    assert expected in evidence.summary
    assert expected in proposal.candidate_graph["lanes"][0]["prompt"]
    assert "tests/test_xmuse..." not in evidence.summary
    assert "tests/test_xmuse..." not in proposal.candidate_graph["lanes"][0]["prompt"]


def test_gate_report_diagnostics_reach_evidence_prompt(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-gate-diagnostics-graph-v1"
    lane_id = "lane-gate-diagnostics"
    report_ref = f"logs/gates/{lane_id}/report.json"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-gate-diagnostics",
            "resolution_id": "res-gate-diagnostics",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-gate-diagnostics",
                    "gate_passed": True,
                    "review_decision": "merge",
                }
            ]
        },
    )
    _write_json(
        tmp_path / report_ref,
        {
            "passed": True,
            "blocking_passed": True,
            "profile_ids": ["xmuse-core"],
            "warnings": [
                "explicit gate_profiles selected; dirty coverage recorded but not blocking"
            ],
            "nonblocking_failures": [
                {"message": "coverage advisory skipped by profile"}
            ],
            "command_results": [
                {
                    "command_id": "pytest",
                    "profile_id": "xmuse-core",
                    "argv": [
                        "uv",
                        "run",
                        "pytest",
                        "-q",
                        "tests/test_xmuse_gate_profiles.py",
                    ],
                    "returncode": 0,
                }
            ],
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    diagnostics = [
        json.loads(signal.removeprefix("gate_report_diagnostic:"))
        for signal in evidence.signal_refs
        if signal.startswith("gate_report_diagnostic:")
    ]
    assert diagnostics == [
        {
            "nonblocking_failures": ["coverage advisory skipped by profile"],
            "report_ref": report_ref,
            "warnings": [
                "explicit gate_profiles selected; dirty coverage recorded but not blocking"
            ],
        }
    ]
    expected = (
        f"gate_diagnostic={report_ref} "
        "warning=explicit gate_profiles selected; dirty coverage recorded but not blocking "
        "nonblocking=coverage advisory skipped by profile"
    )
    assert expected in evidence.summary
    assert expected in proposal.candidate_graph["lanes"][0]["prompt"]
    assert (
        "gate_command=uv run pytest -q tests/test_xmuse_gate_profiles.py -> passed"
        in evidence.summary
    )


def test_long_gate_diagnostic_preserves_dirty_worktree_warning_tail(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-long-gate-diagnostic-graph-v1"
    lane_id = (
        "self-evolution-self_evolution_loop-"
        "res_6cfd36dfd4254c0ebb1770318a0aea96-graph-v1"
    )
    report_ref = f"logs/gates/{lane_id}/report.json"
    warning = (
        "explicit gate_profiles selected; full dirty-worktree coverage is recorded "
        "but not used to reject this lane"
    )
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-long-gate-diagnostic",
            "resolution_id": "res-long-gate-diagnostic",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-long-gate-diagnostic",
                    "gate_passed": True,
                    "review_decision": "merge",
                }
            ]
        },
    )
    _write_json(
        tmp_path / report_ref,
        {
            "passed": True,
            "blocking_passed": True,
            "profile_ids": ["xmuse-core"],
            "warnings": [warning],
            "command_results": [],
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    diagnostics = [
        json.loads(signal.removeprefix("gate_report_diagnostic:"))
        for signal in evidence.signal_refs
        if signal.startswith("gate_report_diagnostic:")
    ]
    expected_warning = f"warning={warning}"
    assert diagnostics == [{"report_ref": report_ref, "warnings": [warning]}]
    assert f"gate_report={report_ref} status=passed blocking=passed profiles=xmuse-core" in (
        evidence.summary
    )
    assert expected_warning in evidence.summary
    assert expected_warning in proposal.candidate_graph["lanes"][0]["prompt"]
    assert "used to..." not in evidence.summary
    assert "used to..." not in proposal.candidate_graph["lanes"][0]["prompt"]


def test_gate_report_signal_remains_visible_with_many_lane_signals(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-many-lane-gate-report-graph-v1"
    lane_ids = [
        "self-evolution-self_evolution_loop-many-gate-signal-a",
        "self-evolution-self_evolution_loop-many-gate-signal-b",
        "self-evolution-self_evolution_loop-many-gate-signal-c",
    ]
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-many-lane-gate-report",
            "resolution_id": "res-many-lane-gate-report",
            "version": 1,
            "lanes": [
                {"feature_id": lane_id, "prompt": f"improve loop {index}"}
                for index, lane_id in enumerate(lane_ids, start=1)
            ],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": f"improve loop {index}",
                    "graph_id": graph_id,
                    "resolution_id": "res-many-lane-gate-report",
                    "gate_passed": True,
                    "review_decision": "merge",
                }
                for index, lane_id in enumerate(lane_ids, start=1)
            ]
        },
    )
    report_ref = f"logs/gates/{lane_ids[0]}/report.json"
    stdout_path = tmp_path / "logs" / "gates" / lane_ids[0] / "xmuse-core__pytest.stdout"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text("35 passed in 2.61s\n", encoding="utf-8")
    _write_json(
        tmp_path / report_ref,
        {
            "passed": True,
            "blocking_passed": True,
            "profile_ids": ["xmuse-core"],
            "resolution_reasons": {"xmuse-core": ["explicit_lane_profile"]},
            "warnings": ["explicit profile warning"],
            "command_results": [
                {
                    "command_id": "pytest",
                    "profile_id": "xmuse-core",
                    "argv": [
                        "uv",
                        "run",
                        "pytest",
                        "tests/test_xmuse_self_evolution.py",
                        "-q",
                    ],
                    "returncode": 0,
                    "stdout_path": str(stdout_path),
                }
            ],
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    assert f"gate_report:{report_ref}" in evidence.signal_refs
    assert "lane_counts total=3 terminal=3 merged=3" in evidence.summary
    assert f"gate_report={report_ref}" in evidence.summary
    assert (
        f"gate_diagnostic={report_ref} warning=explicit profile warning"
        in evidence.summary
    )
    assert (
        "gate_command=uv run pytest tests/test_xmuse_self_evolution.py -q "
        "-> passed (35 passed in 2.61s)"
    ) in evidence.summary
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert "lane_counts total=3 terminal=3 merged=3" in prompt
    assert f"gate_report={report_ref}" in prompt
    assert f"gate_diagnostic={report_ref} warning=explicit profile warning" in prompt
    assert (
        "gate_command=uv run pytest tests/test_xmuse_self_evolution.py -q "
        "-> passed (35 passed in 2.61s)"
    ) in prompt


def test_recovery_provenance_remains_visible_with_many_lane_signals_and_gate_report(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-many-lane-recovery-gate-report-graph-v1"
    lane_ids = [
        "self-evolution-self_evolution_loop-recovery-signal-a",
        "self-evolution-self_evolution_loop-recovery-signal-b",
        "self-evolution-self_evolution_loop-recovery-signal-c",
    ]
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-many-lane-recovery-gate-report",
            "resolution_id": "res-many-lane-recovery-gate-report",
            "version": 1,
            "lanes": [
                {"feature_id": lane_id, "prompt": f"improve loop {index}"}
                for index, lane_id in enumerate(lane_ids, start=1)
            ],
        },
    )
    lanes = [
        {
            "feature_id": lane_id,
            "status": "merged",
            "prompt": f"improve loop {index}",
            "graph_id": graph_id,
            "resolution_id": "res-many-lane-recovery-gate-report",
            "gate_passed": True,
            "review_decision": "merge",
        }
        for index, lane_id in enumerate(lane_ids, start=1)
    ]
    lanes[2]["manual_recovery"] = "applied parser risk fix after codex patch conflict"
    lanes[2]["review_fallback"] = "stdout"
    _write_json(tmp_path / "feature_lanes.json", {"lanes": lanes})
    report_ref = f"logs/gates/{lane_ids[0]}/report.json"
    stdout_path = tmp_path / "logs" / "gates" / lane_ids[0] / "xmuse-core__pytest.stdout"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text("36 passed in 2.71s\n", encoding="utf-8")
    _write_json(
        tmp_path / report_ref,
        {
            "passed": True,
            "blocking_passed": True,
            "profile_ids": ["xmuse-core"],
            "command_results": [
                {
                    "command_id": "pytest",
                    "profile_id": "xmuse-core",
                    "argv": [
                        "uv",
                        "run",
                        "pytest",
                        "tests/test_xmuse_self_evolution.py",
                        "-q",
                    ],
                    "returncode": 0,
                    "stdout_path": str(stdout_path),
                }
            ],
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals[2]["manual_recovery"] == (
        "applied parser risk fix after codex patch conflict"
    )
    assert lane_signals[2]["review_fallback"] == "stdout"
    expected_recovery = (
        f"lane {lane_ids[2]} status=merged review=merge review_source=stdout "
        "review_fallback=stdout gate=passed recovery=applied parser risk fix "
        "after codex patch conflict"
    )
    expected_command = (
        "gate_command=uv run pytest tests/test_xmuse_self_evolution.py -q "
        "-> passed (36 passed in 2.71s)"
    )
    assert expected_recovery in evidence.summary
    assert f"gate_report={report_ref}" in evidence.summary
    assert expected_command in evidence.summary
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert expected_recovery in prompt
    assert f"gate_report={report_ref}" in prompt
    assert expected_command in prompt


def test_stale_many_lane_signals_keep_gate_command_without_lane_counts(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    report_ref = "logs/gates/self-evolution-stale-many-lanes/report.json"
    _write_json(tmp_path / report_ref, {"passed": True, "blocking_passed": True})
    signal_refs = [
        "lane_signal:"
        + json.dumps(
            {
                "feature_id": f"self-evolution-stale-lane-{index}",
                "normalized_status": "merged",
                "raw_status": "merged",
                "review_decision": "merge",
                "terminal": True,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        for index in range(1, 5)
    ]
    signal_refs.extend(
        [
            f"gate_report:{report_ref}",
            "gate_report_result:"
            + json.dumps(
                {
                    "argv": [
                        "uv",
                        "run",
                        "pytest",
                        "-q",
                        "tests/test_xmuse_quality_gate.py",
                    ],
                    "command_id": "pytest",
                    "outcome": "passed",
                    "profile_id": "xmuse-core",
                    "report_ref": report_ref,
                    "returncode": 0,
                    "stdout_summary": "209 passed, 1 warning in 12.91s",
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        ]
    )
    evidence = StructuredEvidenceBundle(
        bundle_id="evbundle-stale-many-lanes",
        source_run_id="res-stale-many-lanes-graph-v1",
        source_resolution_id="res-stale-many-lanes",
        selection_policy_id="xmuse-self-evolution-bootstrap",
        selection_policy_version="3",
        summary="stale evidence",
        run_terminal_status=RunTerminalStatus.MERGED,
        signal_refs=signal_refs,
        gate_report_refs=[report_ref],
        created_at="2026-05-27T00:00:00Z",
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    proposal = controller.draft_evolution_proposal(evidence)

    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert "lane self-evolution-stale-lane-1 status=merged review=merge" in prompt
    assert "lane self-evolution-stale-lane-4" not in prompt
    assert f"gate_report={report_ref} status=passed blocking=passed" in prompt
    assert (
        "gate_command=uv run pytest -q tests/test_xmuse_quality_gate.py "
        "-> passed (209 passed, 1 warning in 12.91s)"
    ) in prompt


def test_stale_lane_signal_prompt_marks_stdout_review_fallback(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    lane_id = "self-evolution-self_evolution_loop-review-fallback-source"
    signal_refs = [
        "lane_signal:"
        + json.dumps(
            {
                "feature_id": lane_id,
                "gate_passed": True,
                "normalized_status": "merged",
                "raw_status": "merged",
                "review_decision": "merge",
                "review_fallback": "stdout",
                "terminal": True,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        'lane_counts:{"merged": 1, "terminal": 1, "total": 1}',
    ]
    evidence = StructuredEvidenceBundle(
        bundle_id="evbundle-stale-review-fallback",
        source_run_id="res-stale-review-fallback-graph-v1",
        source_resolution_id="res-stale-review-fallback",
        selection_policy_id="xmuse-self-evolution-bootstrap",
        selection_policy_version="18",
        summary="stale evidence",
        run_terminal_status=RunTerminalStatus.MERGED,
        signal_refs=signal_refs,
        created_at="2026-05-28T00:00:00Z",
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    proposal = controller.draft_evolution_proposal(evidence)

    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert f"lane {lane_id} status=merged review=merge" in prompt
    assert "review_source=stdout" in prompt
    assert "review_fallback=stdout" in prompt


def test_candidate_prompt_preserves_long_confirmation_outcome(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-long-confirmation-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-source-long-confirmation-graph-v1"
    long_confirmation = (
        "uv run pytest "
        "tests/test_xmuse_self_evolution.py::"
        "test_candidate_prompt_preserves_lane_counts_when_many_lane_signals -q -> passed"
    )
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-long-confirmation",
            "resolution_id": "res-long-confirmation",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-long-confirmation",
                    "gate_passed": True,
                    "review_decision": "merge",
                    "retry_count": 1,
                    "review_summary": (
                        "Verification run:\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution.py::"
                        "test_candidate_prompt_preserves_lane_counts_when_many_lane_signals "
                        "-q` -> passed\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution.py -q` "
                        "-> `25 passed`"
                    ),
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals[0]["review_confirmations"][0] == long_confirmation
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert "confirmation=uv run pytest tests/test_xmuse_self_evolution.py::" in prompt
    assert "... -> passed" in prompt
    assert "confirmation=uv run pytest tests/test_xmuse_self_evolution.py -q -> 25 passed" in prompt


def test_candidate_prompt_preserves_long_colon_confirmation_outcome(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-long-colon-confirmation-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-source-long-colon-confirmation-graph-v1"
    long_confirmation = (
        "uv run pytest "
        "tests/test_xmuse_self_evolution.py::"
        "test_candidate_prompt_preserves_lane_counts_when_many_lane_signals -q: passed"
    )
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-long-colon-confirmation",
            "resolution_id": "res-long-colon-confirmation",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-long-colon-confirmation",
                    "gate_passed": True,
                    "review_decision": "merge",
                    "retry_count": 1,
                    "review_summary": (
                        "Verification run:\n"
                        "- `uv run pytest tests/test_xmuse_self_evolution.py::"
                        "test_candidate_prompt_preserves_lane_counts_when_many_lane_signals "
                        "-q`: passed"
                    ),
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals[0]["review_confirmations"] == [long_confirmation]
    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    assert "confirmation=uv run pytest tests/test_xmuse_self_evolution.py::" in prompt
    assert "...: passed" in prompt
    assert "many_lane_signals..." not in prompt


def test_candidate_prompt_preserves_lane_counts_when_many_lane_signals(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-many-lane-signals-graph-v1"
    lane_ids = [
        "self-evolution-self_evolution_loop-many-signal-a",
        "self-evolution-self_evolution_loop-many-signal-b",
        "self-evolution-self_evolution_loop-many-signal-c",
    ]
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-many-lane-signals",
            "resolution_id": "res-many-lane-signals",
            "version": 1,
            "lanes": [
                {"feature_id": lane_id, "prompt": f"improve loop {index}"}
                for index, lane_id in enumerate(lane_ids, start=1)
            ],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "merged",
                    "prompt": f"improve loop {index}",
                    "graph_id": graph_id,
                    "resolution_id": "res-many-lane-signals",
                    "gate_passed": True,
                    "review_decision": "merge",
                }
                for index, lane_id in enumerate(lane_ids, start=1)
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)

    prompt = proposal.candidate_graph["lanes"][0]["prompt"]
    lane_signal_refs = [
        signal for signal in evidence.signal_refs if signal.startswith("lane_signal:")
    ]
    assert len(lane_signal_refs) == 3
    assert "lane_counts total=3 terminal=3 merged=3" in prompt
    assert 'lane_counts:{"merged": 3, "terminal": 3, "total": 3}' not in prompt


def test_dry_run_lands_visible_conversation_resolution_graph_and_lineage(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = _seed_merged_run(tmp_path)

    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )
    lineage = controller.dry_run_from_graph(graph_id)

    assert lineage.source_run_id == graph_id
    assert lineage.source_resolution_id == "res-source"
    assert lineage.blueprint_set_id == "xmuse-self-evolution-v0"
    assert lineage.target_track_ids == ["graph_authority"]
    assert (tmp_path / "chat.db").exists()
    assert (tmp_path / "self_evolution" / "evidence_bundles.json").exists()
    assert (tmp_path / "self_evolution" / "proposals.json").exists()
    assert (tmp_path / "self_evolution" / "review_decisions.json").exists()
    assert (tmp_path / "self_evolution" / "guardrail_decisions.json").exists()
    assert (tmp_path / "self_evolution" / "lineage.json").exists()
    assert (tmp_path / "self_evolution" / "budget_windows.json").exists()
    assert (tmp_path / "self_evolution" / "dedup_records.json").exists()
    assert (tmp_path / "lane_graphs" / f"{lineage.spawned_graph_id}.json").exists()

    lanes = json.loads((tmp_path / "feature_lanes.json").read_text(encoding="utf-8"))["lanes"]
    spawned = [lane for lane in lanes if lane.get("resolution_id") == lineage.spawned_resolution_id]
    assert len(spawned) == 1
    assert spawned[0]["status"] == "pending"
    assert spawned[0]["priority"] == 100

    proposals = controller.store.list_proposals()
    reviews = controller.store.list_review_decisions()
    guardrails = controller.store.list_guardrail_decisions()
    evidence = controller.store.list_evidence_bundles()
    assert proposals[-1].status == "landed"
    assert reviews[-1].decision == "approve"
    assert guardrails[-1].action == "continue"
    assert guardrails[-1].budget_window_id
    assert guardrails[-1].dedup_key
    assert guardrails[-1].reason_codes == []
    assert lineage.terminal_aggregation_ref == guardrails[-1].terminal_aggregation_ref
    assert evidence[-1].selection_policy_id == "xmuse-self-evolution-bootstrap"
    assert "feature_lanes.json" in evidence[-1].primary_refs
    budget_window = controller.store.list_budget_windows()[-1]
    assert lineage.source_run_id in budget_window.consumed_run_ids
    assert lineage.spawned_graph_id in budget_window.consumed_run_ids


def test_spawned_run_reuses_existing_chain_budget_window(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = _seed_merged_run(tmp_path)
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )
    first_lineage = controller.dry_run_from_graph(graph_id)
    first_budget = controller.store.list_budget_windows()[-1]
    lanes_path = tmp_path / "feature_lanes.json"
    lanes_data = json.loads(lanes_path.read_text(encoding="utf-8"))
    for lane in lanes_data["lanes"]:
        if lane.get("graph_id") == first_lineage.spawned_graph_id:
            lane["status"] = "merged"
    lanes_path.write_text(json.dumps(lanes_data, indent=2) + "\n", encoding="utf-8")

    aggregation = controller.aggregate_run_terminal(first_lineage.spawned_graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)
    review = controller.review_proposal(proposal)
    guardrail = controller.guardrail_check(proposal, review, aggregation)

    assert guardrail.action == "continue"
    assert guardrail.budget_window_id == first_budget.window_id


def test_run_from_existing_evidence_bundle_preserves_bundle_identity(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = _seed_merged_run(tmp_path)
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )
    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)

    lineage = controller.run_from_evidence_bundle(evidence.bundle_id)

    assert lineage.source_run_id == graph_id
    assert lineage.evidence_bundle_id == evidence.bundle_id
    assert len(controller.store.list_evidence_bundles()) == 1
    lanes = json.loads((tmp_path / "feature_lanes.json").read_text(encoding="utf-8"))["lanes"]
    spawned = [lane for lane in lanes if lane.get("resolution_id") == lineage.spawned_resolution_id]
    assert spawned[0]["prompt"].count(evidence.bundle_id) == 1


def test_run_from_existing_evidence_bundle_recomputes_source_lineage_before_landing(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = _seed_merged_run(tmp_path)
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )
    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)

    lanes_path = tmp_path / "feature_lanes.json"
    lanes_data = json.loads(lanes_path.read_text(encoding="utf-8"))
    lanes_data["lanes"].append(
        {
            "feature_id": "source-lane-1-patch-forward",
            "status": "pending",
            "prompt": "patch current source lane before self-evolving",
            "source_lane_id": "source-lane-1",
            "graph_id": graph_id,
            "resolution_id": "res-source",
        }
    )
    lanes_path.write_text(json.dumps(lanes_data, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="source run is not terminal: running"):
        controller.run_from_evidence_bundle(evidence.bundle_id)

    assert controller.store.list_aggregations()[-1].status == "running"
    assert controller.store.list_lineage() == []
    assert controller.store.list_proposals() == []


def test_run_from_stale_evidence_bundle_blocks_unmerged_rework_lineage(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "res-review-rework-graph-v1"
    lane_id = "self-evolution-self_evolution_loop-source-graph-v1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv-review-rework",
            "resolution_id": "res-review-rework",
            "version": 1,
            "lanes": [{"feature_id": lane_id, "prompt": "improve loop"}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": lane_id,
                    "status": "failed",
                    "prompt": "improve loop",
                    "graph_id": graph_id,
                    "resolution_id": "res-review-rework",
                    "gate_passed": True,
                    "review_decision": "rework",
                    "retry_count": 2,
                }
            ]
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )
    controller.aggregate_run_terminal(graph_id)
    controller.store.save_evidence_bundle(
        StructuredEvidenceBundle(
            bundle_id="evbundle_a204cd8066df4961ac35eaf8a5d2c0da",
            source_run_id=graph_id,
            source_resolution_id="res-review-rework",
            selection_policy_id="xmuse-self-evolution-bootstrap",
            selection_policy_version="1",
            summary=(
                f"Run {graph_id} terminal status is terminated. "
                "Reason: at least one graph lineage terminalized without merge. "
                "Lane counts: {'total': 1, 'terminal': 1, 'terminated': 1}."
            ),
            run_terminal_status="terminated",
            artifact_refs=[
                "feature_lanes.json",
                f"lane_graphs/{graph_id}.json",
                "blueprint.md",
            ],
            signal_refs=[
                'lane_counts:{"terminal": 1, "terminated": 1, "total": 1}'
            ],
            primary_refs=[
                "feature_lanes.json",
                f"lane_graphs/{graph_id}.json",
                "blueprint.md",
            ],
            created_at="2026-05-27T19:46:30Z",
        )
    )

    with pytest.raises(RuntimeError, match="source run is not terminal: running"):
        controller.run_from_evidence_bundle("evbundle_a204cd8066df4961ac35eaf8a5d2c0da")


def test_run_from_stale_merged_evidence_bundle_hydrates_review_confirmations(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id, lane_id = _seed_merged_review_signal_run(tmp_path)
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )
    controller.aggregate_run_terminal(graph_id)
    controller.store.save_evidence_bundle(
        StructuredEvidenceBundle(
            bundle_id="evbundle_579ea21891ab4135885265c47222624b",
            source_run_id=graph_id,
            source_resolution_id="res-merged-review",
            selection_policy_id="xmuse-self-evolution-bootstrap",
            selection_policy_version="1",
            summary=(
                f"Run {graph_id} terminal status is merged. "
                "Reason: all graph lineage lanes merged. "
                "Lane counts: {'total': 1, 'terminal': 1, 'merged': 1}."
            ),
            run_terminal_status="merged",
            artifact_refs=[
                "feature_lanes.json",
                f"lane_graphs/{graph_id}.json",
                "blueprint.md",
            ],
            signal_refs=['lane_counts:{"merged": 1, "terminal": 1, "total": 1}'],
            primary_refs=[
                "feature_lanes.json",
                f"lane_graphs/{graph_id}.json",
                "blueprint.md",
            ],
            created_at="2026-05-27T21:02:33Z",
        )
    )

    lineage = controller.run_from_evidence_bundle(
        "evbundle_579ea21891ab4135885265c47222624b"
    )

    assert lineage.evidence_bundle_id == "evbundle_579ea21891ab4135885265c47222624b"
    hydrated = controller.store.list_evidence_bundles()[-1]
    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in hydrated.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert hydrated.selection_policy_version == "21"
    assert lane_signals[0]["feature_id"] == lane_id
    assert lane_signals[0]["review_confirmations"] == [
        "uv run pytest tests/test_xmuse_self_evolution.py -q -> 18 passed",
        (
            "uv run ruff check src/xmuse_core/self_evolution/controller.py "
            "-> All checks passed"
        ),
    ]
    assert (
        "confirmation=uv run pytest tests/test_xmuse_self_evolution.py -q -> 18 passed"
        in hydrated.summary
    )
    assert "lane_counts total=1 terminal=1 merged=1" in hydrated.summary
    assert 'lane_counts:{"merged": 1, "terminal": 1, "total": 1}' not in hydrated.summary

    lanes = json.loads((tmp_path / "feature_lanes.json").read_text(encoding="utf-8"))["lanes"]
    spawned = [lane for lane in lanes if lane.get("resolution_id") == lineage.spawned_resolution_id]
    assert len(spawned) == 1
    assert "status=merged review=merge gate=passed retries=1" in spawned[0]["prompt"]
    assert (
        "confirmation=uv run pytest tests/test_xmuse_self_evolution.py -q -> 18 passed"
        in spawned[0]["prompt"]
    )


def test_run_from_stale_evidence_bundle_hydrates_gate_report_signal(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id, lane_id = _seed_merged_review_signal_run(tmp_path)
    report_ref = f"logs/gates/{lane_id}/report.json"
    stdout_path = tmp_path / "logs" / "gates" / lane_id / "xmuse-core__pytest.stdout"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text(
        "======================= 34 passed in 1.45s =======================\n",
        encoding="utf-8",
    )
    _write_json(
        tmp_path / report_ref,
        {
            "status": "passed",
            "resolution_reasons": {"xmuse-core": ["explicit_lane_profile"]},
            "command_results": [
                {
                    "command_id": "pytest",
                    "profile_id": "xmuse-core",
                    "argv": [
                        "uv",
                        "run",
                        "pytest",
                        "-q",
                        "tests/test_xmuse_self_evolution.py",
                    ],
                    "returncode": 0,
                    "stdout_path": str(stdout_path),
                }
            ],
        },
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )
    controller.aggregate_run_terminal(graph_id)
    controller.store.save_evidence_bundle(
        StructuredEvidenceBundle(
            bundle_id="evbundle_47b13d1e63bd49ce97d3da2f82e04843",
            source_run_id=graph_id,
            source_resolution_id="res-merged-review",
            selection_policy_id="xmuse-self-evolution-bootstrap",
            selection_policy_version="2",
            summary=(
                f"Run {graph_id} terminal status is merged. "
                "Reason: all graph lineage lanes merged. "
                "Lane counts: total=1 terminal=1 merged=1."
            ),
            run_terminal_status="merged",
            artifact_refs=[
                "feature_lanes.json",
                f"lane_graphs/{graph_id}.json",
                "blueprint.md",
            ],
            signal_refs=['lane_counts:{"merged": 1, "terminal": 1, "total": 1}'],
            primary_refs=[
                "feature_lanes.json",
                f"lane_graphs/{graph_id}.json",
                "blueprint.md",
            ],
            created_at="2026-05-27T22:33:15Z",
        )
    )

    lineage = controller.run_from_evidence_bundle(
        "evbundle_47b13d1e63bd49ce97d3da2f82e04843"
    )

    hydrated = controller.store.list_evidence_bundles()[-1]
    assert hydrated.selection_policy_version == "21"
    assert hydrated.gate_report_refs == [report_ref]
    assert f"gate_report:{report_ref}" in hydrated.signal_refs
    assert any(
        signal.startswith("gate_report_resolution:") for signal in hydrated.signal_refs
    )
    assert any(
        signal.startswith("gate_report_result:") for signal in hydrated.signal_refs
    )
    assert f"gate_report={report_ref}" in hydrated.summary
    assert (
        f"gate_scope={report_ref} profile=xmuse-core reason=explicit_lane_profile"
        in hydrated.summary
    )
    assert (
        "gate_command=uv run pytest -q tests/test_xmuse_self_evolution.py "
        "-> passed (34 passed in 1.45s)"
        in hydrated.summary
    )
    lanes = json.loads((tmp_path / "feature_lanes.json").read_text(encoding="utf-8"))["lanes"]
    spawned = [lane for lane in lanes if lane.get("resolution_id") == lineage.spawned_resolution_id]
    assert f"gate_report={report_ref}" in spawned[0]["prompt"]
    assert (
        f"gate_scope={report_ref} profile=xmuse-core reason=explicit_lane_profile"
        in spawned[0]["prompt"]
    )
    assert (
        "gate_command=uv run pytest -q tests/test_xmuse_self_evolution.py "
        "-> passed (34 passed in 1.45s)"
        in spawned[0]["prompt"]
    )


def test_guardrail_blocks_duplicate_self_evolution_lineage(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_single_track_blueprint(blueprint)
    graph_id = _seed_merged_run(tmp_path)
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )
    controller.dry_run_from_graph(graph_id)

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)
    review = controller.review_proposal(proposal)
    guardrail = controller.guardrail_check(proposal, review, aggregation)

    assert guardrail.action == "hold"
    assert guardrail.reason_codes == ["dedupe_clear"]
    assert guardrail.checks["dedupe_clear"] is False
    assert controller.store.list_proposals()[-1].status == "guardrail_blocked"
    assert len(controller.store.list_lineage()) == 1


def test_guardrail_dedup_ignores_late_gate_report_signal(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_single_track_blueprint(blueprint)
    graph_id = _seed_merged_run(tmp_path)
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )
    controller.dry_run_from_graph(graph_id)
    report_ref = "logs/gates/source-lane-1/report.json"
    stdout_path = tmp_path / "logs" / "gates" / "source-lane-1" / "xmuse-core__pytest.stdout"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text("2 passed in 0.10s\n", encoding="utf-8")
    _write_json(
        tmp_path / report_ref,
        {
            "status": "passed",
            "resolution_reasons": {"xmuse-core": ["explicit_lane_profile"]},
            "command_results": [
                {
                    "command_id": "pytest",
                    "profile_id": "xmuse-core",
                    "argv": ["uv", "run", "pytest", "-q", "tests/test_xmuse_self_evolution.py"],
                    "returncode": 0,
                    "stdout_path": str(stdout_path),
                }
            ],
        },
    )

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)
    review = controller.review_proposal(proposal)
    guardrail = controller.guardrail_check(proposal, review, aggregation)

    assert f"gate_report:{report_ref}" in evidence.signal_refs
    assert any(
        signal.startswith("gate_report_resolution:") for signal in evidence.signal_refs
    )
    assert any(
        signal.startswith("gate_report_result:") for signal in evidence.signal_refs
    )
    assert guardrail.action == "hold"
    assert guardrail.reason_codes == ["dedupe_clear"]
    assert guardrail.checks["dedupe_clear"] is False


def test_guardrail_dedup_ignores_review_risk_signal(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_single_track_blueprint(blueprint)
    graph_id, lane_id = _seed_merged_review_signal_run(tmp_path)
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )
    controller.dry_run_from_graph(graph_id)

    lanes_path = tmp_path / "feature_lanes.json"
    lanes_data = json.loads(lanes_path.read_text(encoding="utf-8"))
    for lane in lanes_data["lanes"]:
        if lane.get("feature_id") == lane_id:
            lane["review_summary"] = (
                f"{lane['review_summary']}\n\n"
                "Residual risk: I did not run the full repository suite."
            )
    lanes_path.write_text(json.dumps(lanes_data, indent=2) + "\n", encoding="utf-8")

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)
    review = controller.review_proposal(proposal)
    guardrail = controller.guardrail_check(proposal, review, aggregation)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals[0]["review_risks"] == [
        "I did not run the full repository suite."
    ]
    assert "risk=I did not run the full repository suite." in evidence.summary
    assert guardrail.action == "hold"
    assert guardrail.reason_codes == ["dedupe_clear"]
    assert guardrail.checks["dedupe_clear"] is False


def test_guardrail_dedup_ignores_lane_recovery_provenance_signal(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_single_track_blueprint(blueprint)
    graph_id, lane_id = _seed_merged_review_signal_run(tmp_path)
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )
    controller.dry_run_from_graph(graph_id)

    lanes_path = tmp_path / "feature_lanes.json"
    lanes_data = json.loads(lanes_path.read_text(encoding="utf-8"))
    for lane in lanes_data["lanes"]:
        if lane.get("feature_id") == lane_id:
            lane["manual_recovery"] = (
                "fixed reproduced-finding fallback after false-positive merge"
            )
            lane["review_fallback"] = "stdout"
    lanes_path.write_text(json.dumps(lanes_data, indent=2) + "\n", encoding="utf-8")

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)
    review = controller.review_proposal(proposal)
    guardrail = controller.guardrail_check(proposal, review, aggregation)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals[0]["manual_recovery"] == (
        "fixed reproduced-finding fallback after false-positive merge"
    )
    assert lane_signals[0]["review_fallback"] == "stdout"
    assert lane_signals[0]["review_recovery_reason"] == (
        "reproduced_finding_false_positive_merge"
    )
    assert guardrail.action == "hold"
    assert guardrail.reason_codes == ["dedupe_clear"]
    assert guardrail.checks["dedupe_clear"] is False


def test_guardrail_dedup_ignores_review_scope_refs_signal(
    tmp_path: Path,
) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_single_track_blueprint(blueprint)
    graph_id, lane_id = _seed_merged_review_signal_run(tmp_path)
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )
    controller.dry_run_from_graph(graph_id)

    lanes_path = tmp_path / "feature_lanes.json"
    lanes_data = json.loads(lanes_path.read_text(encoding="utf-8"))
    for lane in lanes_data["lanes"]:
        if lane.get("feature_id") == lane_id:
            lane["review_summary"] = (
                "No findings.\n\n"
                "Reviewed [controller.py](/repo/src/xmuse_core/"
                "self_evolution/controller.py:37) and "
                "[test_xmuse_self_evolution.py]"
                "(/repo/tests/test_xmuse_self_evolution.py:620).\n\n"
                f"{lane['review_summary']}"
            )
    lanes_path.write_text(json.dumps(lanes_data, indent=2) + "\n", encoding="utf-8")

    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)
    review = controller.review_proposal(proposal)
    guardrail = controller.guardrail_check(proposal, review, aggregation)

    lane_signals = [
        json.loads(signal.removeprefix("lane_signal:"))
        for signal in evidence.signal_refs
        if signal.startswith("lane_signal:")
    ]
    assert lane_signals[0]["review_scope_refs"] == [
        "src/xmuse_core/self_evolution/controller.py",
        "tests/test_xmuse_self_evolution.py",
    ]
    assert guardrail.action == "hold"
    assert guardrail.reason_codes == ["dedupe_clear"]
    assert guardrail.checks["dedupe_clear"] is False


def test_expired_budget_window_does_not_block_new_chain(tmp_path: Path) -> None:
    """An expired window for a source must not gate a fresh chain.

    The operator-friendly semantic is: an expired chain is closed; a
    new merged source mints its own fresh window when the next chain spawns.
    """
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = _seed_merged_run(tmp_path)
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )
    controller.store.save_budget_window(
        EvolutionBudgetWindow(
            window_id="budget-expired",
            origin_run_id=graph_id,
            started_at="2000-01-01T00:00:00Z",
            expires_at="2000-01-01T10:00:00Z",
            status="active",
            consumed_run_ids=[graph_id],
        )
    )
    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)
    review = controller.review_proposal(proposal)

    guardrail = controller.guardrail_check(proposal, review, aggregation)

    assert guardrail.action == "continue"
    # A fresh window is minted; the expired one stays for audit.
    assert guardrail.budget_window_id != "budget-expired"
    windows = {w.window_id: w for w in controller.store.list_budget_windows()}
    assert windows["budget-expired"].status == "expired"
    assert windows[guardrail.budget_window_id].status == "active"


def test_review_narrow_records_structured_narrowing_decision(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = _seed_merged_run(tmp_path)
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )
    aggregation = controller.aggregate_run_terminal(graph_id)
    evidence = controller.build_evidence_bundle(aggregation)
    proposal = controller.draft_evolution_proposal(evidence)
    proposal.candidate_graph["lanes"][0].pop("feature_id")

    review = controller.review_proposal(proposal)

    assert review.decision == "narrow"
    assert review.narrowing_decision is not None
    assert review.narrowing_decision.target_draft_version == proposal.draft_version + 1


def test_dashboard_exposes_self_evolution_monitoring_read_model(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = _seed_merged_run(tmp_path)

    SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    ).dry_run_from_graph(graph_id)

    dashboard_api = _load_dashboard_module()
    client = TestClient(dashboard_api.create_app(base_dir=tmp_path))
    response = client.get("/api/self-evolution")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_aggregations"][0]["status"] == "merged"
    assert payload["evidence_bundles"][0]["selection_policy_id"]
    assert payload["proposals"][0]["status"] == "landed"
    assert payload["review_decisions"][0]["decision"] == "approve"
    assert payload["guardrail_decisions"][0]["action"] == "continue"
    assert payload["budget_windows"][0]["status"] == "active"
    assert payload["dedup_records"][0]["status"] == "continued"
    assert payload["lineage"][0]["spawned_graph_id"]


def _write_full_blueprint(path: Path) -> None:
    path.write_text(
        """
# xmuse Initial Self-Evolution Blueprint

- `blueprint_set_id`: `xmuse-self-evolution-v0`

## Priority Policy

Track priority order:

1. `graph_authority`
2. `review_plane`
3. `self_evolution_loop`
4. `clarification_recovery`
5. `dashboard_auditability`
6. `reliability_hardening`

## Tracks

### graph_authority
### review_plane
### self_evolution_loop
### clarification_recovery
### dashboard_auditability
### reliability_hardening
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_target_track_rotates_through_blueprint_priority(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_full_blueprint(blueprint)

    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )

    seen: list[str] = []
    for round_idx in range(6):
        graph_id = _seed_distinct_merged_run(tmp_path, round_idx)
        aggregation = controller.aggregate_run_terminal(graph_id)
        evidence = controller.build_evidence_bundle(aggregation)
        proposal = controller.draft_evolution_proposal(evidence)
        review = controller.review_proposal(proposal)
        guardrail = controller.guardrail_check(proposal, review, aggregation)
        controller.land_evolution_run(proposal, review, guardrail, evidence)
        seen.append(proposal.target_track_ids[0])

    assert seen == [
        "graph_authority",
        "review_plane",
        "self_evolution_loop",
        "clarification_recovery",
        "dashboard_auditability",
        "reliability_hardening",
    ]


def _seed_distinct_merged_run(tmp_path: Path, round_idx: int) -> str:
    graph_id = f"res-rotate-{round_idx}-graph-v1"
    resolution_id = f"res-rotate-{round_idx}"
    lane_id = f"lane-rotate-{round_idx}"
    graphs_dir = tmp_path / "lane_graphs"
    graphs_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        graphs_dir / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": f"conv-rotate-{round_idx}",
            "resolution_id": resolution_id,
            "version": 1,
            "status": "planned",
            "lanes": [{"feature_id": lane_id, "prompt": "rotate", "depends_on": []}],
        },
    )
    lanes_path = tmp_path / "feature_lanes.json"
    if lanes_path.exists():
        existing = json.loads(lanes_path.read_text(encoding="utf-8"))
        lanes = existing.get("lanes", []) if isinstance(existing, dict) else []
    else:
        lanes = []
    lanes.append(
        {
            "feature_id": lane_id,
            "status": "merged",
            "prompt": "rotate",
            "graph_id": graph_id,
            "resolution_id": resolution_id,
            "review_verdict_id": f"verdict-rotate-{round_idx}",
        }
    )
    _write_json(lanes_path, {"lanes": lanes})
    return graph_id


def test_target_track_uses_priority_policy_block_when_present(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    blueprint.write_text(
        """
# xmuse Initial Self-Evolution Blueprint

- `blueprint_set_id`: `xmuse-self-evolution-v0`

## Priority Policy

Track priority order:

1. `review_plane`
2. `graph_authority`

## Tracks

### graph_authority
### review_plane
""".strip()
        + "\n",
        encoding="utf-8",
    )
    graph_id = _seed_merged_run(tmp_path)

    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )
    lineage = controller.dry_run_from_graph(graph_id)
    assert lineage.target_track_ids == ["review_plane"]


def test_scope_summary_embeds_target_track(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_full_blueprint(blueprint)
    graph_id = _seed_merged_run(tmp_path)

    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )
    lineage = controller.dry_run_from_graph(graph_id)

    proposals = controller.store.list_proposals()
    landed = next(
        proposal for proposal in proposals
        if proposal.proposal_id == lineage.evolution_proposal_id
    )
    assert "graph_authority" in landed.scope_summary
