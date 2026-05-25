import importlib.util
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
HARDENING_PATH = PROJECT / "xmuse" / "hermes_hardening.py"


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


def test_hardening_validate_master_state_delegates_to_core_schema(monkeypatch):
    hardening = load_hardening()
    sentinel_state = {"sentinel": True}
    sentinel_result = {"valid": True, "errors": ["from core"]}
    calls = []

    def fake_core_validate(state: dict) -> dict:
        calls.append(state)
        return sentinel_result

    monkeypatch.setattr(hardening, "_core_validate_master_state", fake_core_validate)

    result = hardening.validate_master_state(sentinel_state)

    assert result is sentinel_result
    assert calls == [sentinel_state]


def valid_feature_amendment(action: str = "create_feature") -> dict:
    return {
        "version": "1.0",
        "amendment_id": f"{action}-archive-rag-20260525T000000Z",
        "action": action,
        "status": "accepted",
        "recorded_by": "master-god",
        "recorded_at": "2026-05-25T00:00:00Z",
        "feature_ids": ["archive-rag"],
        "target_feature_id": "archive-rag",
        "reason": "Bound archive RAG exploration to an isolated feature lane.",
        "previous_state_ref": "xmuse/master_state.json@abc123",
        "policy_preserved": {
            "v1_fallback_preserved": True,
            "kernel_opt_in_preserved": True,
            "no_benchmark_score_targets": True,
            "no_gate_lowering": True,
        },
        "gate_effect": "no_gate_lowering",
        "artifacts": {
            "amendment": (
                "xmuse/master/amendments/"
                f"{action}-archive-rag-20260525T000000Z.json"
            )
        },
    }


def test_master_state_accepts_master_owned_dynamic_feature_amendment():
    hardening = load_hardening()
    state = base_master_state()
    state["feature_amendments"] = [
        valid_feature_amendment("create_feature"),
        valid_feature_amendment("request_rework"),
    ]

    result = hardening.validate_master_state(state)

    assert result["valid"] is True
    assert result["errors"] == []


def test_master_state_rejects_dynamic_feature_amendment_that_lowers_gates():
    hardening = load_hardening()
    state = base_master_state()
    amendment = valid_feature_amendment("rescope_feature")
    amendment["gate_effect"] = "skip_integrated_tests"
    amendment["policy_preserved"]["no_gate_lowering"] = False
    state["feature_amendments"] = [amendment]

    result = hardening.validate_master_state(state)

    assert result["valid"] is False
    assert (
        "feature_amendments[0] gate_effect must be no_gate_lowering"
        in result["errors"]
    )
    assert (
        "feature_amendments[0] policy_preserved.no_gate_lowering must be true"
        in result["errors"]
    )


def test_master_state_rejects_slave_or_feature_local_dynamic_amendment():
    hardening = load_hardening()
    state = base_master_state()
    amendment = valid_feature_amendment("archive_feature")
    amendment["recorded_by"] = "slave-god-archive-rag"
    amendment["artifacts"]["amendment"] = (
        "xmuse/work/features/archive-rag/blueprint_amendment.json"
    )
    state["feature_amendments"] = [amendment]

    result = hardening.validate_master_state(state)

    assert result["valid"] is False
    assert "feature_amendments[0] recorded_by must be master-god" in result["errors"]
    assert (
        "feature_amendments[0] amendment artifact must live under "
        "xmuse/master/amendments/"
        in result["errors"]
    )


def test_active_controller_uses_master_state_when_active(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
    state = base_master_state()
    write_json(loop / "master_state.json", state)

    result = hardening.resolve_active_controller(loop)

    assert result["source"] == "master"
    assert result["execution_allowed"] is True
    assert result["state"]["activation_state"] == "master_active"


def test_hardening_resolve_active_controller_delegates_to_core_state(
    tmp_path, monkeypatch
):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
    sentinel_result = {
        "source": "master",
        "path": str(loop / "master_state.json"),
        "state": {"activation_state": "master_active"},
        "execution_allowed": True,
        "errors": [],
    }
    calls = []

    def fake_core_resolve(loop_root: Path, *, audit: bool = False) -> dict:
        calls.append((loop_root, audit))
        return sentinel_result

    monkeypatch.setattr(hardening, "_core_resolve_active_controller", fake_core_resolve)

    result = hardening.resolve_active_controller(loop, audit=True)

    assert result is sentinel_result
    assert calls == [(loop, True)]


def test_active_controller_blocks_invalid_master_without_legacy_fallback(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
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
    loop = tmp_path / "xmuse"
    write_json(loop / "state.json", {"current_state": "DONE", "current_phase_idx": 18})

    result = hardening.resolve_active_controller(loop)

    assert result["source"] == "legacy_root"
    assert result["execution_allowed"] is True
    assert result["state"]["current_state"] == "DONE"


def test_active_controller_never_executes_isolated_legacy_without_audit(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
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
    loop = tmp_path / "xmuse"
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
    loop = tmp_path / "xmuse"
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
                        "result": "xmuse/work/features/v1-quarantine/result.md",
                        "ack": "xmuse/work/features/v1-quarantine/ack.json",
                        "review_verdict": (
                            "xmuse/work/features/v1-quarantine/review_verdict.json"
                        ),
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
    loop = tmp_path / "xmuse"
    write_legacy_inputs(loop)

    result = hardening.prepare_master_migration(loop)

    assert result["status"] == "prepared"
    master_state = json.loads((loop / "master_state.json").read_text())
    assert master_state["activation_state"] == "master_pending"
    assert master_state["active"] is False
    assert [feature["id"] for feature in master_state["features"]] == [
        "v1-quarantine",
        "archive-rag",
    ]
    assert (
        master_state["features"][0]["slave_state_path"]
        == "xmuse/work/features/v1-quarantine/slave_state.json"
    )
    assert (loop / "master_blueprint.md").exists()
    assert "Dynamic Feature Control" in (loop / "master_blueprint.md").read_text()
    assert (loop / "master_config.json").exists()
    assert (loop / "prompts" / "master_god_prompt.md").exists()
    assert (loop / "prompts" / "slave_god_prompt.md").exists()
    assert (loop / "codex_node_launcher.sh").exists()
    assert (loop / "contracts" / "master_dispatch_template.json").exists()
    assert (loop / "contracts" / "slave_dispatch_template.json").exists()
    assert (loop / "work" / "features" / "v1-quarantine" / "slave_state.json").exists()
    assert (loop / "approvals").is_dir()
    assert (loop / "state.json").exists()


def test_prepare_master_migration_does_not_synthesize_merge_approval(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
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


def write_gate_artifacts(loop: Path, feature_id: str = "v1-quarantine") -> None:
    feature = _master_feature_from_test(feature_id)
    write_json(loop / "work" / "features" / feature_id / "ack.json", {"ack_level": "usable"})
    write_json(loop / "work" / "features" / feature_id / "review_verdict.json", {"verdict": "PASS"})
    (loop / "work" / "features" / feature_id / "result.md").parent.mkdir(
        parents=True, exist_ok=True
    )
    (loop / "work" / "features" / feature_id / "result.md").write_text("result\n")
    write_json(
        loop / "work" / "features" / feature_id / "slave_state.json",
        {"version": "1.0", "feature_id": feature_id},
    )
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
            "artifact_digests": {
                "result": "sha256:r",
                "ack": "sha256:a",
                "review_verdict": "sha256:v",
            },
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
                    "artifact_ref": (
                        "xmuse/master/features/v1-quarantine/integrated_pytest.log"
                    ),
                    "artifact_digest": "sha256:log",
                }
            ],
            "worktree_clean": True,
            "artifact_digests": {},
        },
    )


def test_merge_queue_gate_accepts_master_owned_evidence(tmp_path, monkeypatch):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
    state = feature_for_gate()
    write_gate_artifacts(loop)
    monkeypatch.setattr(hardening, "_current_target_head", lambda _loop, _branch: "123456abcdef")

    result = hardening.validate_merge_queue_gate(loop, state["features"][0])

    assert result["valid"] is True
    assert result["errors"] == []


def test_merge_queue_gate_rejects_target_branch_outside_master_allowlist(
    tmp_path, monkeypatch
):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
    state = feature_for_gate()
    write_gate_artifacts(loop)
    write_json(
        loop / "master_config.json",
        {
            "version": "1.0",
            "allowed_target_branches": ["main"],
            "merge_strategy": "no_ff_merge_commit",
        },
    )
    feature = state["features"][0]
    feature["target_branch"] = "feat/phase-2.5-3-retrieval-agent"
    feature["merge"]["target_branch"] = "feat/phase-2.5-3-retrieval-agent"
    for artifact_ref in ("master_review", "integrated_tests"):
        path = loop / feature["artifacts"][artifact_ref].removeprefix("xmuse/")
        payload = json.loads(path.read_text())
        payload["target_branch"] = "feat/phase-2.5-3-retrieval-agent"
        write_json(path, payload)
    monkeypatch.setattr(hardening, "_current_target_head", lambda _loop, _branch: "123456abcdef")

    result = hardening.validate_merge_queue_gate(loop, feature)

    assert result["valid"] is False
    assert (
        "target_branch feat/phase-2.5-3-retrieval-agent is not allowed by master_config"
        in result["errors"]
    )


def test_merge_queue_gate_rejects_feature_local_master_review(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
    state = feature_for_gate()
    feature = state["features"][0]
    feature["artifacts"]["master_review"] = (
        "xmuse/work/features/v1-quarantine/master_review.json"
    )
    write_gate_artifacts(loop)
    write_json(
        loop / "work" / "features" / "v1-quarantine" / "master_review.json",
        {"status": "accepted", "recorded_by": "master-god"},
    )

    result = hardening.validate_merge_queue_gate(loop, feature)

    assert result["valid"] is False
    assert (
        "master_review must live under xmuse/master/features/v1-quarantine/"
        in result["errors"]
    )


def test_merge_queue_gate_rejects_failed_integrated_tests(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
    state = feature_for_gate()
    write_gate_artifacts(loop)
    tests_path = loop / "master" / "features" / "v1-quarantine" / "integrated_tests.json"
    tests_payload = json.loads(tests_path.read_text())
    tests_payload["status"] = "failed"
    write_json(tests_path, tests_payload)

    result = hardening.validate_merge_queue_gate(loop, state["features"][0])

    assert result["valid"] is False
    assert "integrated_tests status must be passed" in result["errors"]


def test_merge_queue_gate_rejects_stale_target_base_commit(tmp_path, monkeypatch):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
    state = feature_for_gate()
    write_gate_artifacts(loop)
    monkeypatch.setattr(hardening, "_current_target_head", lambda _loop, _branch: "current123")

    result = hardening.validate_merge_queue_gate(loop, state["features"][0])

    assert result["valid"] is False
    assert "gate evidence base_commit does not match current target HEAD" in result["errors"]


def test_merge_queue_gate_rejects_unresolved_target_branch(tmp_path, monkeypatch):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
    state = feature_for_gate()
    write_gate_artifacts(loop)
    monkeypatch.setattr(hardening, "_current_target_head", lambda _loop, _branch: None)

    result = hardening.validate_merge_queue_gate(loop, state["features"][0])

    assert result["valid"] is False
    assert "unable to resolve current target HEAD" in result["errors"]


def valid_approval_bundle(loop: Path, feature_id: str = "v1-quarantine") -> dict:
    write_gate_artifacts(loop, feature_id)
    review_ref = f"xmuse/master/features/{feature_id}/master_review.json"
    tests_ref = f"xmuse/master/features/{feature_id}/integrated_tests.json"
    hardening = load_hardening()
    review_digest = hardening.file_json_digest(loop.parent / review_ref)
    tests_digest = hardening.file_json_digest(loop.parent / tests_ref)
    policy_snapshot = {
        "feature_id": feature_id,
        "merge_strategy": "no_ff_merge_commit",
        "target_branch": "main",
    }
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
        "policy_snapshot_ref": "xmuse/master_state.json#features/v1-quarantine",
        "policy_snapshot_digest": policy_digest,
    }
    request["request_digest"] = hardening.canonical_json_digest(
        request, exclude_keys={"request_digest"}
    )
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
    loop = tmp_path / "xmuse"
    bundle = valid_approval_bundle(loop)

    result = hardening.validate_merge_approval(
        loop,
        "xmuse/approvals/v1-quarantine/merge_approval_request.json",
        "xmuse/approvals/v1-quarantine/merge_approval.json",
        policy_snapshot_digest=bundle["request"]["policy_snapshot_digest"],
    )

    assert result["schema_valid"] is True
    assert result["valid"] is False
    assert result["errors"] == []
    assert result["provenance_scope"] == "schema_level_only"
    assert result["provenance_verified"] is False


def test_approval_validation_rejects_changed_review_artifact(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
    bundle = valid_approval_bundle(loop)
    review_path = loop / "master" / "features" / "v1-quarantine" / "master_review.json"
    review = json.loads(review_path.read_text())
    review["findings"] = ["changed after approval"]
    write_json(review_path, review)

    result = hardening.validate_merge_approval(
        loop,
        "xmuse/approvals/v1-quarantine/merge_approval_request.json",
        "xmuse/approvals/v1-quarantine/merge_approval.json",
        policy_snapshot_digest=bundle["request"]["policy_snapshot_digest"],
    )

    assert result["valid"] is False
    assert "current master_review digest does not match approval request" in result["errors"]


def test_approval_validation_rejects_allowlist_only_provenance(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
    bundle = valid_approval_bundle(loop)
    approval_path = loop / "approvals" / "v1-quarantine" / "merge_approval.json"
    approval = json.loads(approval_path.read_text())
    approval["verification"]["method"] = "maintainer_allowlist"
    write_json(approval_path, approval)

    result = hardening.validate_merge_approval(
        loop,
        "xmuse/approvals/v1-quarantine/merge_approval_request.json",
        "xmuse/approvals/v1-quarantine/merge_approval.json",
        policy_snapshot_digest=bundle["request"]["policy_snapshot_digest"],
    )

    assert result["valid"] is False
    assert "maintainer_allowlist cannot be sole provenance verification" in result["errors"]


def test_approval_validation_rejects_missing_external_provenance_ref_or_digest(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
    bundle = valid_approval_bundle(loop)
    approval_path = loop / "approvals" / "v1-quarantine" / "merge_approval.json"
    approval = json.loads(approval_path.read_text())
    approval["verification"].pop("ref")
    approval["verification"].pop("digest")
    write_json(approval_path, approval)

    result = hardening.validate_merge_approval(
        loop,
        "xmuse/approvals/v1-quarantine/merge_approval_request.json",
        "xmuse/approvals/v1-quarantine/merge_approval.json",
        policy_snapshot_digest=bundle["request"]["policy_snapshot_digest"],
    )

    assert result["valid"] is False
    assert "approval verification ref is required" in result["errors"]
    assert "approval verification digest is required" in result["errors"]


def test_merge_decision_requires_merge_commit_for_merged(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
    decision = {
        "version": "1.0",
        "feature_id": "v1-quarantine",
        "decision": "merged",
        "final_state": "merged",
        "approved_head": "abcdef123456",
        "target_branch": "main",
        "merge_strategy": "no_ff_merge_commit",
        "approval_ref": "xmuse/approvals/v1-quarantine/merge_approval.json",
        "approval_digest": "sha256:a",
        "approval_request_ref": "xmuse/approvals/v1-quarantine/merge_approval_request.json",
        "approval_request_digest": "sha256:r",
        "integrated_tests_ref": "xmuse/master/features/v1-quarantine/integrated_tests.json",
        "post_merge_verification_refs": [
            "xmuse/approvals/v1-quarantine/post_merge_verification.json"
        ],
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
        "approval_ref": "xmuse/approvals/v1-quarantine/merge_approval.json",
        "approval_digest": "sha256:a",
        "approval_request_ref": "xmuse/approvals/v1-quarantine/merge_approval_request.json",
        "approval_request_digest": "sha256:r",
        "failed_post_merge_verification_ref": (
            "xmuse/approvals/v1-quarantine/post_merge_verification.json"
        ),
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
        "approval_ref": "xmuse/approvals/v1-quarantine/merge_approval.json",
        "approval_digest": "sha256:approval",
        "approval_request_ref": "xmuse/approvals/v1-quarantine/merge_approval_request.json",
        "approval_request_digest": "sha256:request",
        "ancestry_check": {
            "command": "git merge-base --is-ancestor abcdef123456 fedcba654321",
            "status": "passed",
        },
        "verification_commands": [
            {
                "command": "uv run pytest tests/test_hermes_master_state.py -q",
                "status": status,
                "artifact_ref": "xmuse/approvals/v1-quarantine/post_merge_pytest.log",
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
    loop = tmp_path / "xmuse"
    payload = write_post_merge_verification(loop, status="passed")
    digest = hardening.canonical_json_digest(payload)

    result = hardening.validate_post_merge_verification(
        loop,
        "xmuse/approvals/v1-quarantine/post_merge_verification.json",
        expected_digest=digest,
        expected_status="passed",
    )

    assert result["valid"] is True
    assert result["errors"] == []


def test_post_merge_verification_rejects_digest_mismatch(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
    write_post_merge_verification(loop, status="passed")

    result = hardening.validate_post_merge_verification(
        loop,
        "xmuse/approvals/v1-quarantine/post_merge_verification.json",
        expected_digest="sha256:stale",
        expected_status="passed",
    )

    assert result["valid"] is False
    assert "post_merge_verification digest mismatch" in result["errors"]


def test_post_merge_verification_failed_requires_merge_execution_passed(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
    payload = write_post_merge_verification(loop, status="failed")
    path = loop / "approvals" / "v1-quarantine" / "post_merge_verification.json"
    payload["merge_execution_status"] = "failed"
    write_json(path, payload)

    result = hardening.validate_post_merge_verification(
        loop,
        "xmuse/approvals/v1-quarantine/post_merge_verification.json",
        expected_digest=hardening.canonical_json_digest(payload),
        expected_status="failed",
    )

    assert result["valid"] is False
    assert "post_merge_verification merge_execution_status must be passed" in result["errors"]


def test_merge_decision_validates_post_merge_verification_digest(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
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
        "approval_ref": "xmuse/approvals/v1-quarantine/merge_approval.json",
        "approval_digest": "sha256:approval",
        "approval_request_ref": "xmuse/approvals/v1-quarantine/merge_approval_request.json",
        "approval_request_digest": "sha256:request",
        "integrated_tests_ref": "xmuse/master/features/v1-quarantine/integrated_tests.json",
        "post_merge_verification_refs": [
            "xmuse/approvals/v1-quarantine/post_merge_verification.json"
        ],
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
    loop = tmp_path / "xmuse"
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


def test_hardening_derive_master_queues_delegates_to_core_with_merge_gate(
    tmp_path, monkeypatch
):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
    state = base_master_state()
    feature = _master_feature_from_test("v1-quarantine")
    state["features"] = [feature]
    gate_calls = []

    def fake_merge_gate(loop_root: Path, candidate: dict) -> dict:
        gate_calls.append((loop_root, candidate["id"]))
        return {"valid": True, "errors": []}

    def fake_core_derive(
        master_state: dict,
        *,
        merge_gate_validator=None,
        missing_validator_reason: str,
    ) -> dict:
        assert master_state is state
        assert missing_validator_reason == "loop_root is required"
        assert merge_gate_validator is not None
        gate = merge_gate_validator(feature)
        assert gate == {"valid": True, "errors": []}
        return {
            "queues": {
                "planning_queue": [],
                "active_lanes": [],
                "master_review_queue": [],
                "merge_queue": ["v1-quarantine"],
                "held": [],
                "blocked": [],
                "merged": [],
            },
            "counts": {
                "total": 1,
                "reviewable": 0,
                "mergeable": 1,
                "held": 0,
                "blocked": 0,
                "merged": 0,
            },
            "errors": [],
        }

    monkeypatch.setattr(hardening, "validate_merge_queue_gate", fake_merge_gate)
    monkeypatch.setattr(hardening, "_core_derive_master_queues", fake_core_derive)

    result = hardening.derive_master_queues(state, loop_root=loop)

    assert result["queues"]["merge_queue"] == ["v1-quarantine"]
    assert gate_calls == [(loop, "v1-quarantine")]


def test_feature_local_repair_states_remain_active_for_slave_autonomy():
    hardening = load_hardening()
    state = base_master_state()
    features = []
    for feature_state in ("repairing", "reworking", "feature_blocked"):
        feature = _master_feature_from_test(feature_state)
        feature["state"] = feature_state
        feature["merge"]["status"] = "not_requested"
        features.append(feature)
    state["features"] = features

    result = hardening.derive_master_queues(state)

    assert result["queues"]["active_lanes"] == ["repairing", "reworking", "feature_blocked"]
    assert result["queues"]["blocked"] == []
    assert result["errors"] == []


def test_master_level_blocked_states_do_not_enter_slave_active_queue():
    hardening = load_hardening()
    state = base_master_state()
    needs_master = _master_feature_from_test("needs-master")
    needs_master["state"] = "blocked_needs_master"
    needs_master["merge"]["status"] = "not_requested"
    external = _master_feature_from_test("external")
    external["state"] = "blocked_external"
    external["merge"]["status"] = "not_requested"
    state["features"] = [needs_master, external]

    result = hardening.derive_master_queues(state)

    assert result["queues"]["active_lanes"] == []
    assert result["queues"]["blocked"] == ["needs-master"]
    assert result["queues"]["held"] == ["external"]
    assert result["errors"] == []


def test_reconcile_classifies_failed_feature_local_review_as_repairing(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
    feature = _master_feature_from_test("xmuse-console")
    feature["state"] = "active"
    feature["slave_god"]["dispatch_status"] = "running"
    feature["slave_god"]["head_commit"] = "oldhead"
    feature["artifacts"]["ack"] = "xmuse/work/features/xmuse-console/ack.json"
    feature["artifacts"]["review_verdict"] = (
        "xmuse/work/features/xmuse-console/review_verdict.json"
    )
    write_json(
        loop / "work" / "features" / "xmuse-console" / "ack.json",
        {"feature_id": "xmuse-console", "ack_level": "partial", "head_commit": "newhead"},
    )
    write_json(
        loop / "work" / "features" / "xmuse-console" / "review_verdict.json",
        {"feature_id": "xmuse-console", "verdict": "FAIL", "head_commit": "newhead"},
    )

    result = hardening.classify_feature_reconcile_state(loop, feature)

    assert result["state"] == "repairing"
    assert result["dispatch_status"] == "rework_required"
    assert result["head_commit"] == "newhead"


def test_reconcile_classifies_passed_integrated_gate_without_approval_as_approval_blocked(
    tmp_path, monkeypatch
):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
    feature = _master_feature_from_test("memoryos-redis-cache-probe")
    feature["state"] = "active"
    feature["slave_god"]["dispatch_status"] = "running"
    write_gate_artifacts(loop, "memoryos-redis-cache-probe")
    monkeypatch.setattr(hardening, "_current_target_head", lambda _loop, _branch: "123456abcdef")

    result = hardening.classify_feature_reconcile_state(loop, feature)

    assert result["state"] == "approval_blocked"
    assert result["dispatch_status"] == "approval_required"
    assert result["head_commit"] == "abcdef123456"


def test_merge_status_ahead_of_feature_state_blocks_feature():
    hardening = load_hardening()
    state = base_master_state()
    feature = _master_feature_from_test("v1-quarantine")
    feature["state"] = "planned"
    feature["merge"]["status"] = "ready_for_merge"
    state["features"] = [feature]

    result = hardening.derive_master_queues(state)

    assert result["queues"]["blocked"] == ["v1-quarantine"]
    assert (
        "merge.status ready_for_merge is ahead of feature.state planned for v1-quarantine"
        in result["errors"]
    )


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


def test_not_requested_merge_status_keeps_planned_feature_in_planning_queue():
    hardening = load_hardening()
    state = base_master_state()
    feature = _master_feature_from_test("archive-rag")
    feature["state"] = "planned"
    feature["merge"]["status"] = "not_requested"
    state["features"] = [feature]

    result = hardening.derive_master_queues(state)

    assert result["queues"]["planning_queue"] == ["archive-rag"]
    assert result["queues"]["blocked"] == []
    assert result["errors"] == []


def test_activate_master_migration_moves_legacy_files_and_marks_master_active(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
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
    loop = tmp_path / "xmuse"
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
    loop = tmp_path / "xmuse"
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
    loop = tmp_path / "xmuse"
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
    launcher = (PROJECT / "xmuse" / "god_launcher.sh").read_text()

    assert "master_state.json" in launcher
    assert "prompts/master_god_prompt.md" in launcher
    assert "contracts/master_dispatch_template.json" in launcher
    assert "codex exec --yolo" in launcher
    assert "approval_policy=never" in launcher
    assert "god_loop_prompt.md" not in launcher
    assert "contracts/god_dispatch_template.json" not in launcher


def test_all_active_nodes_have_yolo_launcher_policy():
    node_launcher = (PROJECT / "xmuse" / "codex_node_launcher.sh").read_text()
    prompts = {
        name: (PROJECT / "xmuse" / "prompts" / name).read_text()
        for name in (
            "master_god_prompt.md",
            "slave_god_prompt.md",
            "plan_agent.md",
            "execute_agent.md",
            "review_agent.md",
        )
    }
    master_contract = json.loads(
        (PROJECT / "xmuse" / "contracts" / "master_dispatch_template.json").read_text()
    )
    slave_contract = json.loads(
        (PROJECT / "xmuse" / "contracts" / "slave_dispatch_template.json").read_text()
    )

    assert "codex exec --yolo" in node_launcher
    assert "approval_policy=never" in node_launcher
    for node in ("master", "slave", "plan", "execute", "review"):
        assert node in node_launcher

    for prompt in prompts.values():
        assert "Autonomous Yolo Runner Policy" in prompt
        assert "codex exec --yolo" in prompt
        assert "approval_policy=never" in prompt
        assert "do not wait for human confirmation" in prompt

    for contract in (master_contract, slave_contract):
        assert contract["runner_policy"]["command"] == "codex exec --yolo"
        assert contract["runner_policy"]["approval_policy"] == "never"
        assert contract["runner_policy"]["skip_human_confirmation"] is True
        assert "external merge approval" in contract["runner_policy"]["human_gate_exceptions"]


def test_master_and_slave_prompts_define_active_multi_god_authority():
    master_blueprint = (PROJECT / "xmuse" / "master_blueprint.md").read_text()
    master_prompt = (PROJECT / "xmuse" / "prompts" / "master_god_prompt.md").read_text()
    slave_prompt = (PROJECT / "xmuse" / "prompts" / "slave_god_prompt.md").read_text()

    assert "Dynamic Feature Control" in master_blueprint
    assert "no_gate_lowering" in master_blueprint

    assert "Master God" in master_prompt
    assert "master_state.json" in master_prompt
    assert "manage Slave Gods" in master_prompt
    assert "create, split, combine, rename, re-scope, reorder, hold, resume, archive" in (
        master_prompt
    )
    assert "xmuse/master/amendments/" in master_prompt
    assert "no_gate_lowering" in master_prompt
    assert "Feature-local FAIL review or non-usable ACK is a rework signal" in master_prompt
    assert "request_rework" in master_prompt
    assert "external merge approval" in master_prompt
    assert "must not merge" in master_prompt

    assert "Slave God" in slave_prompt
    assert "root God authority inside one feature boundary" in slave_prompt
    assert "plan/execute/review" in slave_prompt
    assert "continue autonomous repair" in slave_prompt
    assert "not benchmark score targets" in slave_prompt
    assert "propose feature amendments" in slave_prompt
    assert "must not edit master_state.json" in slave_prompt
    assert "ack.json" in slave_prompt


def test_plan_execute_review_prompts_are_active_feature_local_nodes():
    prompts = {
        name: (PROJECT / "xmuse" / "prompts" / name).read_text()
        for name in ("plan_agent.md", "execute_agent.md", "review_agent.md")
    }

    for prompt in prompts.values():
        assert "DEPRECATED" not in prompt
        assert "feature-local" in prompt
        assert "slave_state.json" in prompt

    assert "writes only planning artifacts" in prompts["plan_agent.md"]
    assert "may modify only the assigned feature worktree" in prompts["execute_agent.md"]
    assert "execute_goal.md" in prompts["execute_agent.md"]
    assert "`/goal`" in prompts["execute_agent.md"]
    assert "Max repair cycles" in prompts["execute_agent.md"]
    assert "Required artifacts" in prompts["execute_agent.md"]
    assert "Benchmark scores are diagnostic evidence only, not goal constraints" in (
        prompts["execute_agent.md"]
    )
    assert "read-only" in prompts["review_agent.md"]


def test_master_and_slave_dispatch_contracts_are_substantive():
    master = json.loads(
        (PROJECT / "xmuse" / "contracts" / "master_dispatch_template.json").read_text()
    )
    slave = json.loads(
        (PROJECT / "xmuse" / "contracts" / "slave_dispatch_template.json").read_text()
    )

    assert master["role"] == "master_god"
    assert slave["role"] == "slave_god"
    for payload in (master, slave):
        assert payload["version"] == "1.0"
        assert payload["required_inputs"]
        assert payload["allowed_writes"]
        assert payload["forbidden_actions"]
        assert payload["required_artifacts"]

    assert "master_review" in master["gates"]
    assert "dynamic_feature_amendment" in master["gates"]
    assert "rework_request" in master["gates"]
    assert "merge" in master["gates"]
    assert "xmuse/master/features/<feature-id>/rework_request.json" in master["allowed_writes"]
    assert "xmuse/master/amendments/<amendment-id>.json" in master["allowed_writes"]
    assert "feature_boundary" in slave["gates"]
    assert "autonomous_repair" in slave["gates"]
    assert "execute_goal" in slave["gates"]
    assert "execute_goal" in slave["required_artifacts"]
    assert any("/goal" in item for item in slave["gates"]["execute_goal"])
    assert "usable_ack" in slave["gates"]
    assert "feature_amendment_proposal" in slave["gates"]


def test_xmuse_core_state_extraction_has_control_plane_merge_quarantine():
    blueprint = (
        PROJECT / "xmuse" / "work" / "features" / "xmuse-core-state-extraction" / "blueprint.md"
    ).read_text()
    slave_state = json.loads(
        (
            PROJECT
            / "xmuse"
            / "work"
            / "features"
            / "xmuse-core-state-extraction"
            / "slave_state.json"
        ).read_text()
    )
    master_state = json.loads((PROJECT / "xmuse" / "master_state.json").read_text())
    feature = next(
        feature
        for feature in master_state["features"]
        if feature["id"] == "xmuse-core-state-extraction"
    )

    assert "Control-Plane Merge Quarantine" in blueprint
    assert "migration_active is not merge readiness" in blueprint
    assert "merge.status must remain `not_requested`" in blueprint
    assert "ordinary lane semantic equivalence" in blueprint
    assert feature["policy_flags"]["requires_control_plane_merge_quarantine"] is True
    assert feature["merge"]["status"] == "not_requested"
    assert feature["merge"]["locked_until"] == (
        "migration_active_master_review_integrated_tests_external_approval_fresh_target_gate"
    )
    assert slave_state["constraints"]["requires_control_plane_merge_quarantine"] is True


def test_prepare_master_migration_seeds_substantive_prompts_and_contracts(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
    write_legacy_inputs(loop)

    result = hardening.prepare_master_migration(loop)

    master_prompt = (loop / "prompts" / "master_god_prompt.md").read_text()
    slave_prompt = (loop / "prompts" / "slave_god_prompt.md").read_text()
    node_launcher = (loop / "codex_node_launcher.sh").read_text()
    master_contract = json.loads((loop / "contracts" / "master_dispatch_template.json").read_text())
    slave_contract = json.loads((loop / "contracts" / "slave_dispatch_template.json").read_text())
    assert result["status"] == "prepared"
    assert "manage Slave Gods" in master_prompt
    assert "root God authority inside one feature boundary" in slave_prompt
    assert "codex exec --yolo" in node_launcher
    assert "approval_policy=never" in node_launcher
    assert master_contract["required_inputs"]
    assert slave_contract["required_inputs"]


def test_xmuse_console_is_not_control_plane_merge_quarantined():
    master_state = json.loads((PROJECT / "xmuse" / "master_state.json").read_text())
    feature = next(
        feature for feature in master_state["features"] if feature["id"] == "xmuse-console"
    )

    assert feature["policy_flags"].get("control_plane_migration") is not True
    assert "locked_until" not in feature["merge"]


def test_dispatcher_produces_deterministic_no_launch_plan():
    dispatcher = (PROJECT / "xmuse" / "multi_lane_dispatcher.py").read_text()
    master_state = json.loads((PROJECT / "xmuse" / "master_state.json").read_text())

    assert "xmuse/codex_node_launcher.sh" in dispatcher
    assert "subprocess.Popen" not in dispatcher
    assert "os.system" not in dispatcher
    active_ids = [
        feature["id"]
        for feature in master_state["features"]
        if feature["state"] in {"repairing", "reworking", "feature_blocked", "active_repair"}
    ]
    assert active_ids


def test_dispatcher_writes_feature_jobs_and_surfaces_orphan_blueprints(tmp_path):
    module_path = PROJECT / "xmuse" / "multi_lane_dispatcher.py"
    spec = importlib.util.spec_from_file_location("multi_lane_dispatcher", module_path)
    dispatcher = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(dispatcher)
    loop = tmp_path / "xmuse"
    state = base_master_state()
    active = _master_feature_from_test("active-feature")
    active["state"] = "repairing"
    active["merge"]["status"] = "not_requested"
    active_worktree = tmp_path / "memoryOS-active-feature"
    active_worktree.mkdir()
    active["worktree"] = str(active_worktree)
    held = _master_feature_from_test("held-feature")
    held["state"] = "approval_blocked"
    held["merge"]["status"] = "not_requested"
    state["features"] = [active, held]
    write_json(loop / "master_state.json", state)
    (loop / "work" / "features" / "orphan-feature").mkdir(parents=True)
    (loop / "work" / "features" / "orphan-feature" / "blueprint.md").write_text(
        "# orphan\n",
        encoding="utf-8",
    )

    plan = dispatcher.build_dispatch_plan(loop)
    written = dispatcher.write_dispatch_plan(loop, plan)

    assert [job["feature_id"] for job in plan["jobs"]] == ["active-feature"]
    assert plan["jobs"][0]["status"] == "queued"
    assert plan["jobs"][0]["env"]["XMUSE_FEATURE_ID"] == "active-feature"
    assert plan["jobs"][0]["env"]["XMUSE_JOB_REF"] == "xmuse/jobs/active-feature.json"
    assert (
        plan["jobs"][0]["prompt_file"]
        == "xmuse/dispatch/features/active-feature/slave_dispatch_prompt.md"
    )
    assert plan["jobs"][0]["command"] == [
        "env",
        "XMUSE_FEATURE_ID=active-feature",
        "XMUSE_JOB_REF=xmuse/jobs/active-feature.json",
        "bash",
        "xmuse/codex_node_launcher.sh",
        "slave",
        "xmuse/dispatch/features/active-feature/slave_dispatch_prompt.md",
    ]
    assert plan["orphan_blueprints"] == [
        {
            "feature_id": "orphan-feature",
            "blueprint": "xmuse/work/features/orphan-feature/blueprint.md",
            "reason": "blueprint exists but feature is absent from master_state.features",
        }
    ]
    assert (Path(written["dispatch_plan"])).exists()
    assert (loop / "jobs" / "active-feature.json").exists()
    prompt = (
        loop / "dispatch" / "features" / "active-feature" / "slave_dispatch_prompt.md"
    ).read_text(encoding="utf-8")
    assert "Assigned feature: active-feature" in prompt
    assert "XMUSE_FEATURE_ID=active-feature" in prompt


def test_dispatcher_removes_stale_job_files_on_write(tmp_path):
    module_path = PROJECT / "xmuse" / "multi_lane_dispatcher.py"
    spec = importlib.util.spec_from_file_location("multi_lane_dispatcher", module_path)
    dispatcher = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(dispatcher)
    loop = tmp_path / "xmuse"
    state = base_master_state()
    active = _master_feature_from_test("active-feature")
    active["state"] = "repairing"
    active["merge"]["status"] = "not_requested"
    active_worktree = tmp_path / "memoryOS-active-feature"
    active_worktree.mkdir()
    active["worktree"] = str(active_worktree)
    state["features"] = [active]
    write_json(loop / "master_state.json", state)
    stale_job = loop / "jobs" / "old-feature.json"
    write_json(stale_job, {"feature_id": "old-feature", "status": "queued"})

    plan = dispatcher.build_dispatch_plan(loop)
    dispatcher.write_dispatch_plan(loop, plan)

    assert not stale_job.exists()
    assert (loop / "jobs" / "active-feature.json").exists()


def test_dispatcher_blocks_feature_when_worktree_is_missing(tmp_path):
    module_path = PROJECT / "xmuse" / "multi_lane_dispatcher.py"
    spec = importlib.util.spec_from_file_location("multi_lane_dispatcher", module_path)
    dispatcher = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(dispatcher)
    loop = tmp_path / "xmuse"
    state = base_master_state()
    feature = _master_feature_from_test("missing-worktree")
    feature["state"] = "planned"
    feature["merge"]["status"] = "not_requested"
    feature["worktree"] = str(tmp_path / "does-not-exist")
    state["features"] = [feature]
    write_json(loop / "master_state.json", state)

    plan = dispatcher.build_dispatch_plan(loop)

    assert plan["jobs"][0]["feature_id"] == "missing-worktree"
    assert plan["jobs"][0]["status"] == "blocked"
    assert plan["jobs"][0]["blockers"] == ["feature worktree does not exist"]
    assert plan["counts"]["queued"] == 0
    assert plan["counts"]["blocked_jobs"] == 1


def test_prepare_then_activate_preserves_feature_statuses(tmp_path):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
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


def test_hardening_write_master_status_uses_core_markdown_builder(
    tmp_path, monkeypatch
):
    hardening = load_hardening()
    loop = tmp_path / "xmuse"
    state = base_master_state()
    sentinel_status = {
        "version": "1.0",
        "source": "xmuse/master_state.json",
        "activation_state": "master_active",
        "counts": {
            "total": 0,
            "reviewable": 0,
            "mergeable": 0,
            "held": 0,
            "blocked": 0,
            "merged": 0,
        },
        "queues": {},
        "errors": [],
    }
    calls = []

    def fake_core_build(master_state: dict, **kwargs) -> dict:
        assert master_state is state
        assert kwargs["merge_gate_validator"] is not None
        calls.append("build")
        return sentinel_status

    def fake_core_markdown(status: dict) -> str:
        assert status is sentinel_status
        calls.append("markdown")
        return "core markdown\n"

    monkeypatch.setattr(hardening, "_core_build_master_status", fake_core_build)
    monkeypatch.setattr(hardening, "_core_master_status_markdown", fake_core_markdown)

    result = hardening.write_master_status(loop, state)

    assert result is sentinel_status
    assert (loop / "master_status.md").read_text(encoding="utf-8") == "core markdown\n"
    assert calls == ["build", "markdown"]
