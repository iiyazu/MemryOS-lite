import importlib.util
import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
HARDENING_PATH = PROJECT / ".hermes-loop" / "hermes_hardening.py"


def load_hardening():
    spec = importlib.util.spec_from_file_location("hermes_hardening", HARDENING_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def base_master_state() -> dict:
    return {
        "version": "1.0",
        "mode": "master_control",
        "activation_state": "master_active",
        "active": True,
        "history_baseline": ".hermes-loop/history/main_loop_phase0_18.json",
        "legacy_root_loop": ".hermes-loop/legacy/root-loop/",
        "master_blueprint": ".hermes-loop/master_blueprint.md",
        "master_config": ".hermes-loop/master_config.json",
        "prompts": {
            "master": ".hermes-loop/prompts/master_god_prompt.md",
            "slave": ".hermes-loop/prompts/slave_god_prompt.md",
        },
        "dispatch_contracts": {
            "master": ".hermes-loop/contracts/master_dispatch_template.json",
            "slave": ".hermes-loop/contracts/slave_dispatch_template.json",
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


def test_canonical_json_digest_ignores_key_order():
    hardening = load_hardening()

    left = {"b": 2, "a": {"z": 3, "y": [1, 2]}}
    right = {"a": {"y": [1, 2], "z": 3}, "b": 2}

    assert hardening.canonical_json_digest(left) == hardening.canonical_json_digest(right)
    assert hardening.canonical_json_digest(left).startswith("sha256:")


def test_master_state_rejects_active_flag_mismatch():
    hardening = load_hardening()
    state = base_master_state()
    state["activation_state"] = "master_pending"
    state["active"] = True

    result = hardening.validate_master_state(state)

    assert result["valid"] is False
    assert "active must be false unless activation_state is master_active" in result["errors"]


def test_master_state_accepts_pending_inactive_state():
    hardening = load_hardening()
    state = base_master_state()
    state["activation_state"] = "master_pending"
    state["active"] = False

    result = hardening.validate_master_state(state)

    assert result["valid"] is True
    assert result["errors"] == []


def test_active_controller_uses_master_state_when_active(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    state = base_master_state()
    write_json(loop / "master_state.json", state)

    result = hardening.resolve_active_controller(loop)

    assert result["source"] == "master"
    assert result["execution_allowed"] is True
    assert result["state"]["activation_state"] == "master_active"


def test_active_controller_blocks_invalid_master_without_legacy_fallback(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    bad = base_master_state()
    bad["activation_state"] = "master_pending"
    bad["active"] = True
    write_json(loop / "master_state.json", bad)
    write_json(loop / "state.json", {"current_state": "DONE"})

    result = hardening.resolve_active_controller(loop)

    assert result["source"] == "blocked"
    assert result["execution_allowed"] is False
    assert "active must be false unless activation_state is master_active" in result["errors"]


def test_active_controller_allows_legacy_before_master_exists(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    write_json(loop / "state.json", {"current_state": "DONE", "current_phase_idx": 18})

    result = hardening.resolve_active_controller(loop)

    assert result["source"] == "legacy_root"
    assert result["execution_allowed"] is True
    assert result["state"]["current_state"] == "DONE"


def test_active_controller_never_executes_isolated_legacy_without_audit(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    write_json(
        loop / "legacy" / "root-loop" / "state.json",
        {"current_state": "DONE", "current_phase_idx": 18},
    )

    result = hardening.resolve_active_controller(loop)

    assert result["source"] == "legacy_isolated"
    assert result["execution_allowed"] is False
    assert result["errors"] == ["isolated legacy root-loop is audit-only"]


def test_active_controller_can_read_isolated_legacy_for_explicit_audit(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    write_json(
        loop / "legacy" / "root-loop" / "state.json",
        {"current_state": "DONE", "current_phase_idx": 18},
    )

    result = hardening.resolve_active_controller(loop, audit=True)

    assert result["source"] == "legacy_isolated"
    assert result["execution_allowed"] is False
    assert result["state"]["current_state"] == "DONE"


def test_active_controller_reports_pending_master_as_prepare(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    pending = base_master_state()
    pending["activation_state"] = "master_pending"
    pending["active"] = False
    write_json(loop / "master_state.json", pending)
    write_json(loop / "state.json", {"current_state": "DONE", "current_phase_idx": 18})

    result = hardening.resolve_active_controller(loop)

    assert result["source"] == "master_pending"
    assert result["execution_allowed"] is False
    assert result["legacy_source"] == str(loop / "state.json")


def write_legacy_inputs(loop: Path) -> None:
    write_json(loop / "state.json", {"current_state": "DONE", "current_phase_idx": 18})
    write_json(
        loop / "feature_lanes.json",
        {
            "version": "1.0",
            "features": [
                {
                    "id": "v1-quarantine",
                    "name": "v1 Quarantine",
                    "state": "ready_for_master_review",
                    "branch": "feature/v1-quarantine",
                    "target_branch": "main",
                    "worktree": "../memoryOS-v1-quarantine",
                    "artifacts": {
                        "result": ".hermes-loop/work/features/v1-quarantine/result.md",
                        "ack": ".hermes-loop/work/features/v1-quarantine/ack.json",
                        "review_verdict": ".hermes-loop/work/features/v1-quarantine/review_verdict.json",
                    },
                    "merge": {"status": "ready_for_master_review", "target_branch": "main"},
                },
                {
                    "id": "archive-rag",
                    "name": "Archive RAG",
                    "state": "planned",
                    "branch": "feature/archive-rag",
                    "target_branch": "main",
                    "worktree": "../memoryOS-archive-rag",
                    "artifacts": {},
                    "merge": {"status": "planned", "target_branch": "main"},
                },
            ],
        },
    )
    write_json(loop / "config.json", {"phases": [], "reporter": {"enabled": True}})
    (loop / "blueprint.md").write_text("# Legacy Blueprint\n")
    (loop / "blueprint.zh.md").write_text("# Legacy Blueprint ZH\n")
    (loop / "god_loop_prompt.md").write_text("legacy prompt reads state.json\n")
    write_json(loop / "contracts" / "god_dispatch_template.json", {"legacy": True})


def test_prepare_master_migration_generates_pending_master_files(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    write_legacy_inputs(loop)

    result = hardening.prepare_master_migration(loop)

    assert result["status"] == "prepared"
    master_state = json.loads((loop / "master_state.json").read_text())
    assert master_state["activation_state"] == "master_pending"
    assert master_state["active"] is False
    assert [feature["id"] for feature in master_state["features"]] == ["v1-quarantine", "archive-rag"]
    assert (
        master_state["features"][0]["slave_state_path"]
        == ".hermes-loop/work/features/v1-quarantine/slave_state.json"
    )
    assert (loop / "master_blueprint.md").exists()
    assert (loop / "master_config.json").exists()
    assert (loop / "prompts" / "master_god_prompt.md").exists()
    assert (loop / "prompts" / "slave_god_prompt.md").exists()
    assert (loop / "contracts" / "master_dispatch_template.json").exists()
    assert (loop / "contracts" / "slave_dispatch_template.json").exists()
    assert (loop / "work" / "features" / "v1-quarantine" / "slave_state.json").exists()
    assert (loop / "approvals").is_dir()
    assert (loop / "state.json").exists()


def test_prepare_master_migration_does_not_synthesize_merge_approval(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    write_legacy_inputs(loop)

    hardening.prepare_master_migration(loop)

    assert not (loop / "approvals" / "v1-quarantine" / "merge_approval.json").exists()


def feature_for_gate(feature_id: str = "v1-quarantine") -> dict:
    state = base_master_state()
    feature = _master_feature_from_test(feature_id)
    state["features"] = [feature]
    return state


def _master_feature_from_test(feature_id: str) -> dict:
    return {
        "id": feature_id,
        "name": feature_id,
        "state": "ready_for_merge",
        "branch": f"feature/{feature_id}",
        "target_branch": "main",
        "worktree": f"../memoryOS-{feature_id}",
        "slave_state_path": f".hermes-loop/work/features/{feature_id}/slave_state.json",
        "slave_god": {
            "owner": f"slave-god-{feature_id}",
            "mode": "feature_local_single_god",
            "last_reported_at": "",
        },
        "blueprint_path": f".hermes-loop/work/features/{feature_id}/blueprint.md",
        "artifacts": {
            "result": f".hermes-loop/work/features/{feature_id}/result.md",
            "ack": f".hermes-loop/work/features/{feature_id}/ack.json",
            "review_verdict": f".hermes-loop/work/features/{feature_id}/review_verdict.json",
            "integrated_tests": f".hermes-loop/master/features/{feature_id}/integrated_tests.json",
            "master_review": f".hermes-loop/master/features/{feature_id}/master_review.json",
            "merge_approval_request": f".hermes-loop/approvals/{feature_id}/merge_approval_request.json",
            "merge_approval": f".hermes-loop/approvals/{feature_id}/merge_approval.json",
            "post_merge_verification": f".hermes-loop/approvals/{feature_id}/post_merge_verification.json",
            "merge_decision": f".hermes-loop/approvals/{feature_id}/merge_decision.json",
            "next_action": f".hermes-loop/approvals/{feature_id}/next_action.json",
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


def write_gate_artifacts(loop: Path, feature_id: str = "v1-quarantine") -> None:
    feature = _master_feature_from_test(feature_id)
    write_json(loop / "work" / "features" / feature_id / "ack.json", {"ack_level": "usable"})
    write_json(loop / "work" / "features" / feature_id / "review_verdict.json", {"verdict": "PASS"})
    (loop / "work" / "features" / feature_id / "result.md").parent.mkdir(parents=True, exist_ok=True)
    (loop / "work" / "features" / feature_id / "result.md").write_text("result\n")
    write_json(loop / "work" / "features" / feature_id / "slave_state.json", {"version": "1.0", "feature_id": feature_id})
    (loop / "work" / "features" / feature_id / "blueprint.md").write_text("blueprint\n")
    write_json(
        loop / "master" / "features" / feature_id / "master_review.json",
        {
            "version": "1.0",
            "feature_id": feature_id,
            "status": "accepted",
            "recorded_by": "master-god",
            "recorded_at": "2026-05-24T00:00:00Z",
            "branch": feature["branch"],
            "base_commit": "123456abcdef",
            "head_commit": "abcdef123456",
            "target_branch": "main",
            "slave_result_ref": feature["artifacts"]["result"],
            "slave_ack_ref": feature["artifacts"]["ack"],
            "slave_review_ref": feature["artifacts"]["review_verdict"],
            "artifact_digests": {"result": "sha256:r", "ack": "sha256:a", "review_verdict": "sha256:v"},
            "findings": [],
            "policy_checks": {
                "v1_fallback_preserved": True,
                "kernel_opt_in_preserved": True,
                "no_benchmark_leakage": True,
            },
        },
    )
    write_json(
        loop / "master" / "features" / feature_id / "integrated_tests.json",
        {
            "version": "1.0",
            "feature_id": feature_id,
            "status": "passed",
            "recorded_by": "master-god",
            "recorded_at": "2026-05-24T00:00:00Z",
            "branch": feature["branch"],
            "base_commit": "123456abcdef",
            "head_commit": "abcdef123456",
            "target_branch": "main",
            "commands": [
                {
                    "command": "uv run pytest tests/test_hermes_master_state.py -q",
                    "status": "passed",
                    "artifact_ref": ".hermes-loop/master/features/v1-quarantine/integrated_pytest.log",
                    "artifact_digest": "sha256:log",
                }
            ],
            "worktree_clean": True,
            "artifact_digests": {},
        },
    )


def test_merge_queue_gate_accepts_master_owned_evidence(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    state = feature_for_gate()
    write_gate_artifacts(loop)

    result = hardening.validate_merge_queue_gate(loop, state["features"][0])

    assert result["valid"] is True
    assert result["errors"] == []


def test_merge_queue_gate_rejects_feature_local_master_review(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    state = feature_for_gate()
    feature = state["features"][0]
    feature["artifacts"]["master_review"] = ".hermes-loop/work/features/v1-quarantine/master_review.json"
    write_gate_artifacts(loop)
    write_json(
        loop / "work" / "features" / "v1-quarantine" / "master_review.json",
        {"status": "accepted", "recorded_by": "master-god"},
    )

    result = hardening.validate_merge_queue_gate(loop, feature)

    assert result["valid"] is False
    assert "master_review must live under .hermes-loop/master/features/v1-quarantine/" in result["errors"]


def test_merge_queue_gate_rejects_failed_integrated_tests(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    state = feature_for_gate()
    write_gate_artifacts(loop)
    tests_path = loop / "master" / "features" / "v1-quarantine" / "integrated_tests.json"
    tests_payload = json.loads(tests_path.read_text())
    tests_payload["status"] = "failed"
    write_json(tests_path, tests_payload)

    result = hardening.validate_merge_queue_gate(loop, state["features"][0])

    assert result["valid"] is False
    assert "integrated_tests status must be passed" in result["errors"]
