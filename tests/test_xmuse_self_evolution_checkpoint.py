import importlib.util
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
CHECKPOINT_MODULE_PATH = PROJECT / "xmuse" / "self_evolution_checkpoint.py"


def _load_checkpoint_module():
    spec = importlib.util.spec_from_file_location(
        "xmuse_self_evolution_checkpoint_test",
        CHECKPOINT_MODULE_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_checkpoint_includes_runbook_monitoring_fields(tmp_path: Path) -> None:
    xmuse_root = tmp_path / "xmuse"
    graph_id = "res-target-graph-v1"
    resolution_id = "res-target"
    _write_json(
        xmuse_root / "feature_lanes.json",
        {
            "lanes": [
                {
                    "feature_id": "lane-1",
                    "status": "dispatched",
                    "graph_id": graph_id,
                    "resolution_id": resolution_id,
                    "dispatched_at": 1,
                }
            ]
        },
    )
    _write_json(
        xmuse_root / "self_evolution" / "lineage.json",
        {
            "lineage": [
                {
                    "lineage_id": "lineage-1",
                    "source_run_id": "source-graph",
                    "spawned_conversation_id": "conv-target",
                    "spawned_proposal_id": "prop-target",
                    "spawned_resolution_id": resolution_id,
                    "spawned_graph_id": graph_id,
                }
            ]
        },
    )
    _write_json(
        xmuse_root / "self_evolution" / "budget_windows.json",
        {
            "budget_windows": [
                {
                    "window_id": "budget-1",
                    "origin_run_id": "source-graph",
                    "started_at": "2026-05-27T19:00:00Z",
                    "expires_at": "2026-05-28T05:00:00Z",
                    "status": "active",
                    "consumed_run_ids": [],
                }
            ]
        },
    )
    _write_json(
        xmuse_root / "self_evolution" / "latest_verification.json",
        {"command": "uv run pytest tests/test_xmuse_self_evolution.py -q", "exit_code": 0},
    )
    _write_json(xmuse_root / "lane_graphs" / f"{graph_id}.json", {"id": graph_id})

    checkpoint = _load_checkpoint_module().build_checkpoint(
        xmuse_root,
        "watch",
        "continue monitoring",
    )

    assert checkpoint["checkpoint_schema_version"] == 2
    assert checkpoint["elapsed_window"]["source"] == "budget_window"
    assert checkpoint["elapsed_window"]["elapsed_seconds"] >= 0
    assert checkpoint["spawned_links"] == {
        "conversation_id": "conv-target",
        "proposal_id": "prop-target",
        "resolution_id": resolution_id,
        "graph_id": graph_id,
    }
    assert checkpoint["lane_snapshots"][0]["feature_id"] == "lane-1"
    assert checkpoint["lane_snapshots"][0]["dispatched_age_s"] is not None
    assert checkpoint["latest_test_or_smoke_result"]["exit_code"] == 0
    assert f"lane_graphs/{graph_id}.json" in checkpoint["generated_artifacts"]
    assert "available" in checkpoint["notable_git_diff"]
