from __future__ import annotations

import json
from pathlib import Path

from xmuse_core.self_evolution import SelfEvolutionController
from xmuse_core.self_evolution.decomposer import (
    DeterministicMultiLaneDecomposer,
    SingleLaneDecomposer,
)
from xmuse_core.self_evolution.models import (
    RunTerminalStatus,
    StructuredEvidenceBundle,
)


def _evidence(bundle_id: str = "evbundle-1", source_run_id: str = "src-1") -> StructuredEvidenceBundle:
    return StructuredEvidenceBundle(
        bundle_id=bundle_id,
        source_run_id=source_run_id,
        source_resolution_id=source_run_id,
        selection_policy_id="test",
        selection_policy_version="0",
        summary="x",
        run_terminal_status=RunTerminalStatus.MERGED,
        verdict_refs=[],
        gate_report_refs=[],
        lineage_refs=[],
        artifact_refs=[],
        signal_refs=[],
        primary_refs=[],
        created_at="2026-05-28T00:00:00Z",
    )


def test_deterministic_multi_lane_decomposer_emits_three_lanes_with_dependency_chain() -> None:
    decomposer = DeterministicMultiLaneDecomposer()
    lanes = decomposer.decompose("graph_authority", _evidence())

    assert [lane["title"] for lane in lanes] == [
        "graph_authority design",
        "graph_authority impl",
        "graph_authority tests",
    ]
    assert lanes[0]["depends_on"] == []
    assert lanes[1]["depends_on"] == [lanes[0]["feature_id"]]
    assert lanes[2]["depends_on"] == [lanes[1]["feature_id"]]
    assert all(lane["feature_group"] == "graph_authority" for lane in lanes)


def test_deterministic_multi_lane_prompts_carry_track_and_evidence() -> None:
    decomposer = DeterministicMultiLaneDecomposer()
    lanes = decomposer.decompose("review_plane", _evidence(bundle_id="evbundle-X"))

    for lane in lanes:
        assert "review_plane" in lane["prompt"]
        assert "evbundle-X" in lane["prompt"]


def test_single_lane_decomposer_round_trip() -> None:
    decomposer = SingleLaneDecomposer(
        lane_id_factory=lambda evidence, track: f"lane-{track}-{evidence.source_run_id}",
        prompt_factory=lambda evidence, track: f"do {track} with {evidence.bundle_id}",
    )
    lanes = decomposer.decompose("clarification_recovery", _evidence())

    assert len(lanes) == 1
    assert lanes[0]["feature_id"] == "lane-clarification_recovery-src-1"
    assert lanes[0]["depends_on"] == []
    assert lanes[0]["feature_group"] == "clarification_recovery"


def test_controller_uses_injected_decomposer(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    blueprint.write_text(
        """
# xmuse Initial Self-Evolution Blueprint

- `blueprint_set_id`: `xmuse-self-evolution-v0`

## Tracks

### graph_authority
""".strip()
        + "\n",
        encoding="utf-8",
    )
    graph_id = "src-graph-v1"
    (tmp_path / "lane_graphs").mkdir()
    (tmp_path / "lane_graphs" / f"{graph_id}.json").write_text(
        json.dumps(
            {
                "id": graph_id,
                "conversation_id": "c",
                "resolution_id": graph_id,
                "version": 1,
                "status": "planned",
                "lanes": [{"feature_id": "src-lane", "prompt": "x", "depends_on": []}],
            }
        )
    )
    (tmp_path / "feature_lanes.json").write_text(
        json.dumps(
            {
                "lanes": [
                    {
                        "feature_id": "src-lane",
                        "status": "merged",
                        "prompt": "x",
                        "graph_id": graph_id,
                        "resolution_id": graph_id,
                    }
                ]
            }
        )
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
        decomposer=DeterministicMultiLaneDecomposer(),
    )
    lineage = controller.dry_run_from_graph(graph_id)

    spawned_graph_path = tmp_path / "lane_graphs" / f"{lineage.spawned_graph_id}.json"
    spawned_graph = json.loads(spawned_graph_path.read_text())
    assert len(spawned_graph["lanes"]) == 3
    assert spawned_graph["lanes"][0]["depends_on"] == []
    assert spawned_graph["lanes"][1]["depends_on"] == [spawned_graph["lanes"][0]["feature_id"]]
    assert spawned_graph["lanes"][2]["depends_on"] == [spawned_graph["lanes"][1]["feature_id"]]


def test_multi_lane_projection_is_dependency_aware(tmp_path: Path) -> None:
    """Only dependency-ready lanes should be projected into feature_lanes.json."""
    blueprint = tmp_path / "blueprint.md"
    blueprint.write_text(
        """
# xmuse Initial Self-Evolution Blueprint

- `blueprint_set_id`: `xmuse-self-evolution-v0`

## Tracks

### graph_authority
""".strip()
        + "\n",
        encoding="utf-8",
    )
    graph_id = "src-graph-v1"
    (tmp_path / "lane_graphs").mkdir()
    (tmp_path / "lane_graphs" / f"{graph_id}.json").write_text(
        json.dumps(
            {
                "id": graph_id,
                "conversation_id": "c",
                "resolution_id": graph_id,
                "version": 1,
                "status": "planned",
                "lanes": [{"feature_id": "src-lane", "prompt": "x", "depends_on": []}],
            }
        )
    )
    (tmp_path / "feature_lanes.json").write_text(
        json.dumps(
            {
                "lanes": [
                    {
                        "feature_id": "src-lane",
                        "status": "merged",
                        "prompt": "x",
                        "graph_id": graph_id,
                        "resolution_id": graph_id,
                    }
                ]
            }
        )
    )
    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
        decomposer=DeterministicMultiLaneDecomposer(),
    )
    lineage = controller.dry_run_from_graph(graph_id)

    lanes_data = json.loads((tmp_path / "feature_lanes.json").read_text())
    spawned_lanes = [
        lane for lane in lanes_data["lanes"] if lane.get("graph_id") == lineage.spawned_graph_id
    ]
    # Only the design lane (no deps) should be projected initially.
    assert len(spawned_lanes) == 1
    assert spawned_lanes[0]["depends_on"] == []
    assert spawned_lanes[0]["feature_group"] == "graph_authority"
    assert spawned_lanes[0]["feature_id"].endswith("-design")
