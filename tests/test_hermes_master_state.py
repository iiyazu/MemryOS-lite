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


def valid_approval_bundle(loop: Path, feature_id: str = "v1-quarantine") -> dict:
    write_gate_artifacts(loop, feature_id)
    review_ref = f".hermes-loop/master/features/{feature_id}/master_review.json"
    tests_ref = f".hermes-loop/master/features/{feature_id}/integrated_tests.json"
    hardening = load_hardening()
    review_digest = hardening.file_json_digest(loop.parent / review_ref)
    tests_digest = hardening.file_json_digest(loop.parent / tests_ref)
    policy_snapshot = {"feature_id": feature_id, "merge_strategy": "no_ff_merge_commit", "target_branch": "main"}
    policy_digest = hardening.canonical_json_digest(policy_snapshot)
    request = {
        "version": "1.0",
        "request_id": "v1-quarantine-20260524T000000Z",
        "feature_id": feature_id,
        "requested_by": "master-god",
        "requested_at": "2026-05-24T00:00:00Z",
        "head_commit": "abcdef123456",
        "base_commit": "123456abcdef",
        "approved_range": "123456abcdef..abcdef123456",
        "target_branch": "main",
        "master_review_ref": review_ref,
        "master_review_digest": review_digest,
        "integrated_tests_ref": tests_ref,
        "integrated_tests_digest": tests_digest,
        "merge_strategy": "no_ff_merge_commit",
        "policy_snapshot_ref": ".hermes-loop/master_state.json#features/v1-quarantine",
        "policy_snapshot_digest": policy_digest,
    }
    request["request_digest"] = hardening.canonical_json_digest(request, exclude_keys={"request_digest"})
    approval = {
        "version": "1.0",
        "feature_id": feature_id,
        "request_id": request["request_id"],
        "request_digest": request["request_digest"],
        "decision": "approved",
        "actor": "repo-maintainer",
        "actor_type": "human",
        "created_by": "external_to_master_and_slave",
        "approved_commit": request["head_commit"],
        "base_commit": request["base_commit"],
        "approved_range": request["approved_range"],
        "target_branch": "main",
        "master_review_ref": review_ref,
        "master_review_digest": review_digest,
        "integrated_tests_ref": tests_ref,
        "integrated_tests_digest": tests_digest,
        "merge_strategy": "no_ff_merge_commit",
        "policy_snapshot_ref": request["policy_snapshot_ref"],
        "policy_snapshot_digest": policy_digest,
        "verification": {
            "method": "signed_approval",
            "ref": "approval.sig",
            "digest": "sha256:external",
            "status": "verified",
        },
        "constraints": [],
        "timestamp": "2026-05-24T00:00:00Z",
    }
    write_json(loop / "approvals" / feature_id / "merge_approval_request.json", request)
    write_json(loop / "approvals" / feature_id / "merge_approval.json", approval)
    return {"request": request, "approval": approval}


def test_approval_validation_treats_schema_only_approval_as_not_merge_valid(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    bundle = valid_approval_bundle(loop)

    result = hardening.validate_merge_approval(
        loop,
        ".hermes-loop/approvals/v1-quarantine/merge_approval_request.json",
        ".hermes-loop/approvals/v1-quarantine/merge_approval.json",
        policy_snapshot_digest=bundle["request"]["policy_snapshot_digest"],
    )

    assert result["schema_valid"] is True
    assert result["valid"] is False
    assert result["errors"] == []
    assert result["provenance_scope"] == "schema_level_only"
    assert result["provenance_verified"] is False


def test_approval_validation_rejects_changed_review_artifact(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    bundle = valid_approval_bundle(loop)
    review_path = loop / "master" / "features" / "v1-quarantine" / "master_review.json"
    review = json.loads(review_path.read_text())
    review["findings"] = ["changed after approval"]
    write_json(review_path, review)

    result = hardening.validate_merge_approval(
        loop,
        ".hermes-loop/approvals/v1-quarantine/merge_approval_request.json",
        ".hermes-loop/approvals/v1-quarantine/merge_approval.json",
        policy_snapshot_digest=bundle["request"]["policy_snapshot_digest"],
    )

    assert result["valid"] is False
    assert "current master_review digest does not match approval request" in result["errors"]


def test_approval_validation_rejects_allowlist_only_provenance(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    bundle = valid_approval_bundle(loop)
    approval_path = loop / "approvals" / "v1-quarantine" / "merge_approval.json"
    approval = json.loads(approval_path.read_text())
    approval["verification"]["method"] = "maintainer_allowlist"
    write_json(approval_path, approval)

    result = hardening.validate_merge_approval(
        loop,
        ".hermes-loop/approvals/v1-quarantine/merge_approval_request.json",
        ".hermes-loop/approvals/v1-quarantine/merge_approval.json",
        policy_snapshot_digest=bundle["request"]["policy_snapshot_digest"],
    )

    assert result["valid"] is False
    assert "maintainer_allowlist cannot be sole provenance verification" in result["errors"]


def test_approval_validation_rejects_missing_external_provenance_ref_or_digest(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    bundle = valid_approval_bundle(loop)
    approval_path = loop / "approvals" / "v1-quarantine" / "merge_approval.json"
    approval = json.loads(approval_path.read_text())
    approval["verification"].pop("ref")
    approval["verification"].pop("digest")
    write_json(approval_path, approval)

    result = hardening.validate_merge_approval(
        loop,
        ".hermes-loop/approvals/v1-quarantine/merge_approval_request.json",
        ".hermes-loop/approvals/v1-quarantine/merge_approval.json",
        policy_snapshot_digest=bundle["request"]["policy_snapshot_digest"],
    )

    assert result["valid"] is False
    assert "approval verification ref is required" in result["errors"]
    assert "approval verification digest is required" in result["errors"]


def test_merge_decision_requires_merge_commit_for_merged(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    decision = {
        "version": "1.0",
        "feature_id": "v1-quarantine",
        "decision": "merged",
        "final_state": "merged",
        "approved_head": "abcdef123456",
        "target_branch": "main",
        "merge_strategy": "no_ff_merge_commit",
        "approval_ref": ".hermes-loop/approvals/v1-quarantine/merge_approval.json",
        "approval_digest": "sha256:a",
        "approval_request_ref": ".hermes-loop/approvals/v1-quarantine/merge_approval_request.json",
        "approval_request_digest": "sha256:r",
        "integrated_tests_ref": ".hermes-loop/master/features/v1-quarantine/integrated_tests.json",
        "post_merge_verification_refs": [".hermes-loop/approvals/v1-quarantine/post_merge_verification.json"],
        "post_merge_verification_digests": ["sha256:p"],
        "recorded_by": "master-god",
        "recorded_at": "2026-05-24T00:00:00Z",
    }

    result = hardening.validate_merge_decision(loop, decision)

    assert result["valid"] is False
    assert "merged decision requires merge_commit" in result["errors"]


def test_held_after_merge_requires_next_action_ref():
    hardening = load_hardening()
    decision = {
        "version": "1.0",
        "feature_id": "v1-quarantine",
        "decision": "held_after_merge",
        "final_state": "held_after_merge",
        "blocked_gate": "post_merge_verification",
        "reasons": ["Post-merge verification failed."],
        "target_branch": "main",
        "approved_head": "abcdef123456",
        "merge_strategy": "no_ff_merge_commit",
        "merge_commit": "fedcba654321",
        "approval_ref": ".hermes-loop/approvals/v1-quarantine/merge_approval.json",
        "approval_digest": "sha256:a",
        "approval_request_ref": ".hermes-loop/approvals/v1-quarantine/merge_approval_request.json",
        "approval_request_digest": "sha256:r",
        "failed_post_merge_verification_ref": ".hermes-loop/approvals/v1-quarantine/post_merge_verification.json",
        "failed_post_merge_verification_digest": "sha256:p",
        "next_action": "repair_forward",
        "recorded_by": "master-god",
        "recorded_at": "2026-05-24T00:00:00Z",
    }

    result = hardening.validate_merge_decision(Path("."), decision)

    assert result["valid"] is False
    assert "held_after_merge requires next_action_ref" in result["errors"]


def write_post_merge_verification(loop: Path, status: str = "passed") -> dict:
    payload = {
        "version": "1.0",
        "feature_id": "v1-quarantine",
        "target_branch": "main",
        "pre_merge_head": "123456abcdef",
        "approved_head": "abcdef123456",
        "post_merge_head": "fedcba654321",
        "merge_commit": "fedcba654321",
        "merge_strategy": "no_ff_merge_commit",
        "merge_execution_status": "passed",
        "github_pr": None,
        "approval_ref": ".hermes-loop/approvals/v1-quarantine/merge_approval.json",
        "approval_digest": "sha256:approval",
        "approval_request_ref": ".hermes-loop/approvals/v1-quarantine/merge_approval_request.json",
        "approval_request_digest": "sha256:request",
        "ancestry_check": {
            "command": "git merge-base --is-ancestor abcdef123456 fedcba654321",
            "status": "passed",
        },
        "verification_commands": [
            {
                "command": "uv run pytest tests/test_hermes_master_state.py -q",
                "status": status,
                "artifact_ref": ".hermes-loop/approvals/v1-quarantine/post_merge_pytest.log",
                "artifact_digest": "sha256:log",
            }
        ],
        "status": status,
        "recorded_by": "master-god",
        "recorded_at": "2026-05-24T00:00:00Z",
    }
    write_json(loop / "approvals" / "v1-quarantine" / "post_merge_verification.json", payload)
    return payload


def test_post_merge_verification_accepts_passed_no_ff_artifact(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    payload = write_post_merge_verification(loop, status="passed")
    digest = hardening.canonical_json_digest(payload)

    result = hardening.validate_post_merge_verification(
        loop,
        ".hermes-loop/approvals/v1-quarantine/post_merge_verification.json",
        expected_digest=digest,
        expected_status="passed",
    )

    assert result["valid"] is True
    assert result["errors"] == []


def test_post_merge_verification_rejects_digest_mismatch(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    write_post_merge_verification(loop, status="passed")

    result = hardening.validate_post_merge_verification(
        loop,
        ".hermes-loop/approvals/v1-quarantine/post_merge_verification.json",
        expected_digest="sha256:stale",
        expected_status="passed",
    )

    assert result["valid"] is False
    assert "post_merge_verification digest mismatch" in result["errors"]


def test_post_merge_verification_failed_requires_merge_execution_passed(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    payload = write_post_merge_verification(loop, status="failed")
    path = loop / "approvals" / "v1-quarantine" / "post_merge_verification.json"
    payload["merge_execution_status"] = "failed"
    write_json(path, payload)

    result = hardening.validate_post_merge_verification(
        loop,
        ".hermes-loop/approvals/v1-quarantine/post_merge_verification.json",
        expected_digest=hardening.canonical_json_digest(payload),
        expected_status="failed",
    )

    assert result["valid"] is False
    assert "post_merge_verification merge_execution_status must be passed" in result["errors"]


def test_merge_decision_validates_post_merge_verification_digest(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    write_post_merge_verification(loop, status="passed")
    decision = {
        "version": "1.0",
        "feature_id": "v1-quarantine",
        "decision": "merged",
        "final_state": "merged",
        "approved_head": "abcdef123456",
        "target_branch": "main",
        "merge_strategy": "no_ff_merge_commit",
        "merge_commit": "fedcba654321",
        "approval_ref": ".hermes-loop/approvals/v1-quarantine/merge_approval.json",
        "approval_digest": "sha256:approval",
        "approval_request_ref": ".hermes-loop/approvals/v1-quarantine/merge_approval_request.json",
        "approval_request_digest": "sha256:request",
        "integrated_tests_ref": ".hermes-loop/master/features/v1-quarantine/integrated_tests.json",
        "post_merge_verification_refs": [".hermes-loop/approvals/v1-quarantine/post_merge_verification.json"],
        "post_merge_verification_digests": ["sha256:stale"],
        "recorded_by": "master-god",
        "recorded_at": "2026-05-24T00:00:00Z",
    }

    result = hardening.validate_merge_decision(loop, decision)

    assert result["valid"] is False
    assert "post_merge_verification digest mismatch" in result["errors"]


def test_ready_for_master_review_is_reviewable_not_mergeable():
    hardening = load_hardening()
    state = base_master_state()
    feature = _master_feature_from_test("v1-quarantine")
    feature["state"] = "ready_for_master_review"
    feature["merge"]["status"] = "ready_for_master_review"
    state["features"] = [feature]

    result = hardening.derive_master_queues(state)

    assert result["queues"]["master_review_queue"] == ["v1-quarantine"]
    assert result["queues"]["merge_queue"] == []
    assert result["counts"]["reviewable"] == 1
    assert result["counts"]["mergeable"] == 0


def test_ready_for_merge_without_gate_evidence_is_blocked(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    state = base_master_state()
    feature = _master_feature_from_test("v1-quarantine")
    feature["state"] = "ready_for_merge"
    feature["merge"]["status"] = "ready_for_merge"
    state["features"] = [feature]

    result = hardening.derive_master_queues(state, loop_root=loop)

    assert result["queues"]["merge_queue"] == []
    assert result["queues"]["blocked"] == ["v1-quarantine"]
    assert result["counts"]["mergeable"] == 0
    assert "merge gate failed for v1-quarantine" in result["errors"][0]


def test_merge_status_ahead_of_feature_state_blocks_feature():
    hardening = load_hardening()
    state = base_master_state()
    feature = _master_feature_from_test("v1-quarantine")
    feature["state"] = "planned"
    feature["merge"]["status"] = "ready_for_merge"
    state["features"] = [feature]

    result = hardening.derive_master_queues(state)

    assert result["queues"]["blocked"] == ["v1-quarantine"]
    assert "merge.status ready_for_merge is ahead of feature.state planned for v1-quarantine" in result["errors"]


def test_held_after_merge_maps_to_held_not_merged():
    hardening = load_hardening()
    state = base_master_state()
    feature = _master_feature_from_test("v1-quarantine")
    feature["state"] = "held_after_merge"
    feature["merge"]["status"] = "held_after_merge"
    state["features"] = [feature]

    result = hardening.derive_master_queues(state)

    assert result["queues"]["held"] == ["v1-quarantine"]
    assert result["queues"]["merged"] == []
    assert result["counts"]["held"] == 1
    assert result["counts"]["merged"] == 0


def test_activate_master_migration_moves_legacy_files_and_marks_master_active(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    write_legacy_inputs(loop)
    hardening.prepare_master_migration(loop)

    result = hardening.activate_master_migration(loop)

    assert result["status"] == "activated"
    state = json.loads((loop / "master_state.json").read_text())
    assert state["activation_state"] == "master_active"
    assert state["active"] is True
    assert not (loop / "state.json").exists()
    assert (loop / "legacy" / "root-loop" / "state.json").exists()
    assert (loop / "legacy" / "root-loop" / "feature_lanes.json").exists()
    assert (loop / "legacy" / "root-loop" / "config.json").exists()
    assert (loop / "legacy" / "root-loop" / "god_loop_prompt.md").exists()
    assert (loop / "legacy" / "root-loop" / "contracts" / "god_dispatch_template.json").exists()


def test_activate_master_migration_refuses_invalid_pending_state(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    write_legacy_inputs(loop)
    hardening.prepare_master_migration(loop)
    state_path = loop / "master_state.json"
    state = json.loads(state_path.read_text())
    state["features"][0].pop("slave_state_path")
    write_json(state_path, state)

    result = hardening.activate_master_migration(loop)

    assert result["status"] == "blocked"
    assert (loop / "state.json").exists()
    assert not (loop / "legacy" / "root-loop" / "state.json").exists()


def test_activate_master_migration_rolls_back_mid_move_failure(tmp_path, monkeypatch):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    write_legacy_inputs(loop)
    hardening.prepare_master_migration(loop)
    original_move = hardening._move_if_exists
    calls = {"count": 0}

    def fail_after_first_move(source, destination):
        calls["count"] += 1
        original_move(source, destination)
        if calls["count"] == 1:
            raise RuntimeError("simulated move failure")

    monkeypatch.setattr(hardening, "_move_if_exists", fail_after_first_move)

    result = hardening.activate_master_migration(loop)

    state = json.loads((loop / "master_state.json").read_text())
    assert result["status"] == "blocked"
    assert "simulated move failure" in result["errors"][0]
    assert state["activation_state"] == "master_pending"
    assert state["active"] is False
    assert (loop / "state.json").exists()
    assert not (loop / "legacy" / "root-loop" / "state.json").exists()


def test_activate_master_migration_rolls_back_status_on_late_failure(tmp_path, monkeypatch):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    write_legacy_inputs(loop)
    hardening.prepare_master_migration(loop)
    write_json(loop / "master_status.json", {"activation_state": "master_pending"})
    (loop / "master_status.md").write_text("pending status\n")
    original_replace = Path.replace

    def fail_master_replace(self, target):
        if self.name == "master_state.json.active.tmp":
            raise RuntimeError("simulated master replace failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_master_replace)

    result = hardening.activate_master_migration(loop)

    state = json.loads((loop / "master_state.json").read_text())
    status = json.loads((loop / "master_status.json").read_text())
    assert result["status"] == "blocked"
    assert "simulated master replace failure" in result["errors"][0]
    assert state["activation_state"] == "master_pending"
    assert status["activation_state"] == "master_pending"
    assert (loop / "master_status.md").read_text() == "pending status\n"


def test_launcher_uses_master_prompt_and_master_state_after_migration():
    launcher = (PROJECT / ".hermes-loop" / "god_launcher.sh").read_text()

    assert "master_state.json" in launcher
    assert "prompts/master_god_prompt.md" in launcher
    assert "contracts/master_dispatch_template.json" in launcher
    assert "god_loop_prompt.md" not in launcher
    assert "contracts/god_dispatch_template.json" not in launcher


def test_prepare_then_activate_preserves_feature_statuses(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / ".hermes-loop"
    write_legacy_inputs(loop)

    prepare = hardening.prepare_master_migration(loop)
    activate = hardening.activate_master_migration(loop)
    controller = hardening.resolve_active_controller(loop)
    status = hardening.write_master_status(loop, controller["state"])

    assert prepare["status"] == "prepared"
    assert activate["status"] == "activated"
    assert controller["source"] == "master"
    assert status["counts"]["reviewable"] == 1
    assert status["counts"]["mergeable"] == 0
    assert status["queues"]["master_review_queue"] == ["v1-quarantine"]
    assert status["queues"]["planning_queue"] == ["archive-rag"]
    assert (loop / "legacy" / "root-loop" / "state.json").exists()
    assert (loop / "master_status.json").exists()
    assert (loop / "master_status.md").exists()
