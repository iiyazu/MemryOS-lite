from __future__ import annotations

import json
from pathlib import Path

from xmuse_core.self_evolution import SelfEvolutionController
from xmuse_core.self_evolution.watcher import TerminalRunWatcher


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
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _seed_merged_graph(tmp_path: Path, graph_id: str) -> str:
    resolution_id = graph_id.replace("-graph-v1", "")
    lane_id = f"lane-{graph_id}"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": f"conv-{graph_id}",
            "resolution_id": resolution_id,
            "version": 1,
            "status": "planned",
            "lanes": [{"feature_id": lane_id, "prompt": "go", "depends_on": []}],
        },
    )
    lanes_path = tmp_path / "feature_lanes.json"
    if lanes_path.exists():
        existing = json.loads(lanes_path.read_text())
        lanes = existing.get("lanes", []) if isinstance(existing, dict) else []
    else:
        lanes = []
    lanes.append(
        {
            "feature_id": lane_id,
            "status": "merged",
            "prompt": "go",
            "graph_id": graph_id,
            "resolution_id": resolution_id,
            "review_verdict_id": f"verdict-{graph_id}",
        }
    )
    _write_json(lanes_path, {"lanes": lanes})
    return graph_id


def test_watcher_spawns_for_unprocessed_merged_graph(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    _seed_merged_graph(tmp_path, "graph-fresh-1")

    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )
    watcher = TerminalRunWatcher(controller)

    outcomes = watcher.tick()

    assert len(outcomes) == 1
    assert outcomes[0].source_run_id == "graph-fresh-1"
    assert outcomes[0].spawned is not None
    assert outcomes[0].spawned.target_track_ids == ["graph_authority"]
    assert outcomes[0].skip_reason is None


def test_watcher_skips_graphs_already_used_as_source(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    _seed_merged_graph(tmp_path, "graph-original")

    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )
    watcher = TerminalRunWatcher(controller)

    first_pass = watcher.tick()
    assert len(first_pass) == 1
    assert first_pass[0].spawned is not None

    # Second tick should find only the spawned graph as candidate, not the original.
    second_pass = watcher.tick()
    candidate_sources = [out.source_run_id for out in second_pass]
    assert "graph-original" not in candidate_sources


def test_watcher_skips_non_terminal_graphs(tmp_path: Path) -> None:
    blueprint = tmp_path / "blueprint.md"
    _write_blueprint(blueprint)
    graph_id = "graph-pending-1"
    resolution_id = "graph-pending-1"
    _write_json(
        tmp_path / "lane_graphs" / f"{graph_id}.json",
        {
            "id": graph_id,
            "conversation_id": "conv",
            "resolution_id": resolution_id,
            "version": 1,
            "status": "planned",
            "lanes": [{"feature_id": "lane-pending", "prompt": "go", "depends_on": []}],
        },
    )
    _write_json(
        tmp_path / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-pending",
                    "status": "pending",
                    "graph_id": graph_id,
                    "resolution_id": resolution_id,
                }
            ]
        },
    )

    controller = SelfEvolutionController(
        xmuse_root=tmp_path,
        blueprint_path=blueprint,
    )
    watcher = TerminalRunWatcher(controller)

    outcomes = watcher.tick()

    assert len(outcomes) == 1
    assert outcomes[0].spawned is None
    assert outcomes[0].skip_reason and outcomes[0].skip_reason.startswith("not_terminal")
