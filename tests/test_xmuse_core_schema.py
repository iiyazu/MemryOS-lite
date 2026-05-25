from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def base_master_state() -> dict:
    return {
        "version": "1.0",
        "mode": "master_control",
        "activation_state": "master_active",
        "active": True,
        "history_baseline": "xmuse/history/main_loop_phase0_18.json",
        "legacy_root_loop": "xmuse/legacy/root-loop/",
        "master_blueprint": "xmuse/master_blueprint.md",
        "master_config": "xmuse/master_config.json",
        "prompts": {
            "master": "xmuse/prompts/master_god_prompt.md",
            "slave": "xmuse/prompts/slave_god_prompt.md",
        },
        "dispatch_contracts": {
            "master": "xmuse/contracts/master_dispatch_template.json",
            "slave": "xmuse/contracts/slave_dispatch_template.json",
        },
        "master_policy": {
            "v1_fallback_preserved": True,
            "kernel_opt_in_preserved": True,
            "no_benchmark_score_targets": True,
        },
        "features": [],
        "queues": {
            "planning_queue": [],
            "active_lanes": [],
            "master_review_queue": [],
            "merge_queue": [],
            "held": [],
            "blocked": [],
            "merged": [],
        },
        "decisions": [],
        "integration": {},
        "github": {},
        "last_updated": "2026-05-24T00:00:00Z",
    }


def master_feature(feature_id: str = "v1-quarantine") -> dict:
    return {
        "id": feature_id,
        "name": feature_id,
        "state": "ready_for_merge",
        "branch": f"feature/{feature_id}",
        "target_branch": "main",
        "worktree": f"../memoryOS-{feature_id}",
        "slave_state_path": f"xmuse/work/features/{feature_id}/slave_state.json",
        "slave_god": {
            "owner": f"slave-god-{feature_id}",
            "mode": "feature_local_single_god",
            "last_reported_at": "",
        },
        "blueprint_path": f"xmuse/work/features/{feature_id}/blueprint.md",
        "artifacts": {
            "result": f"xmuse/work/features/{feature_id}/result.md",
            "ack": f"xmuse/work/features/{feature_id}/ack.json",
            "review_verdict": f"xmuse/work/features/{feature_id}/review_verdict.json",
            "integrated_tests": f"xmuse/master/features/{feature_id}/integrated_tests.json",
            "master_review": f"xmuse/master/features/{feature_id}/master_review.json",
            "merge_approval_request": (
                f"xmuse/approvals/{feature_id}/merge_approval_request.json"
            ),
            "merge_approval": f"xmuse/approvals/{feature_id}/merge_approval.json",
            "post_merge_verification": (
                f"xmuse/approvals/{feature_id}/post_merge_verification.json"
            ),
            "merge_decision": f"xmuse/approvals/{feature_id}/merge_decision.json",
            "next_action": f"xmuse/approvals/{feature_id}/next_action.json",
        },
        "merge": {
            "status": "ready_for_merge",
            "target_branch": "main",
            "strategy": "no_ff_merge_commit",
            "github_pr": None,
        },
        "policy_flags": {
            "requires_integrated_tests": True,
            "requires_explicit_merge_approval": True,
            "allows_github_evidence": True,
        },
        "risk": {"level": "medium", "notes": []},
    }


def test_xmuse_core_imports_without_turning_runtime_xmuse_into_package() -> None:
    import xmuse_core
    from xmuse_core.core import paths, schema, state, status

    project = Path(__file__).resolve().parents[1]

    assert xmuse_core.__all__ == ["core"]
    assert callable(paths.controller_path)
    assert callable(schema.validate_master_state)
    assert callable(state.resolve_active_controller)
    assert callable(status.derive_master_queues)
    assert not (project / "xmuse" / "__init__.py").exists()
    assert not (project / "src" / "xmuse").exists()


def test_importing_xmuse_core_modules_has_no_runtime_side_effects(tmp_path: Path) -> None:
    project = Path(__file__).resolve().parents[1]
    script = """
import importlib
import json
import sys
from pathlib import Path

before = sorted(path.name for path in Path.cwd().iterdir())
for module_name in (
    "xmuse_core",
    "xmuse_core.core.paths",
    "xmuse_core.core.schema",
    "xmuse_core.core.state",
    "xmuse_core.core.status",
):
    importlib.import_module(module_name)
after = sorted(path.name for path in Path.cwd().iterdir())
blocked_loaded = sorted(
    name
    for name in sys.modules
    if name == "subprocess"
    or name.startswith("memoryos_lite")
    or name.startswith("xmuse.hermes_reporter")
)
print(json.dumps({"before": before, "after": after, "blocked_loaded": blocked_loaded}))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project / "src")

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload == {"before": [], "after": [], "blocked_loaded": []}


def test_validate_master_state_accepts_pending_inactive_state() -> None:
    from xmuse_core.core.schema import validate_master_state

    state = base_master_state()
    state["activation_state"] = "master_pending"
    state["active"] = False

    result = validate_master_state(state)

    assert result["valid"] is True
    assert result["errors"] == []


def test_validate_master_state_preserves_key_error_semantics() -> None:
    from xmuse_core.core.schema import validate_master_state

    state = base_master_state()
    state["activation_state"] = "master_pending"
    state["active"] = True

    result = validate_master_state(state)

    assert result["valid"] is False
    assert "active must be false unless activation_state is master_active" in result["errors"]
