from __future__ import annotations

from typing import Any

MASTER_ACTIVATION_STATES = {
    "legacy_active",
    "master_pending",
    "master_active",
    "blocked",
}
MASTER_QUEUE_NAMES = {
    "planning_queue",
    "active_lanes",
    "master_review_queue",
    "merge_queue",
    "held",
    "blocked",
    "merged",
}
FEATURE_AMENDMENT_ACTIONS = {
    "create_feature",
    "split_feature",
    "combine_features",
    "rename_feature",
    "rescope_feature",
    "reorder_feature",
    "hold_feature",
    "resume_feature",
    "archive_feature",
    "request_bounded_repair",
    "request_rework",
}
REQUIRED_FEATURE_AMENDMENT_KEYS = {
    "version",
    "amendment_id",
    "action",
    "status",
    "recorded_by",
    "recorded_at",
    "feature_ids",
    "target_feature_id",
    "reason",
    "previous_state_ref",
    "policy_preserved",
    "gate_effect",
    "artifacts",
}
REQUIRED_MASTER_STATE_KEYS = {
    "version",
    "mode",
    "activation_state",
    "active",
    "history_baseline",
    "legacy_root_loop",
    "master_blueprint",
    "master_config",
    "prompts",
    "dispatch_contracts",
    "master_policy",
    "features",
    "queues",
    "decisions",
    "integration",
    "github",
    "last_updated",
}
REQUIRED_FEATURE_KEYS = {
    "id",
    "name",
    "state",
    "branch",
    "target_branch",
    "worktree",
    "slave_state_path",
    "slave_god",
    "blueprint_path",
    "artifacts",
    "merge",
    "policy_flags",
    "risk",
}
REQUIRED_FEATURE_ARTIFACT_KEYS = {
    "result",
    "ack",
    "review_verdict",
    "integrated_tests",
    "master_review",
    "merge_approval_request",
    "merge_approval",
    "post_merge_verification",
    "merge_decision",
    "next_action",
}
STATE_RANK = {
    "not_requested": 0,
    "planned": 0,
    "active": 1,
    "executing": 2,
    "repairing": 2,
    "reworking": 2,
    "feature_blocked": 2,
    "active_repair": 2,
    "review": 3,
    "ready_for_master_review": 4,
    "ready_for_merge": 5,
    "merge_requested": 6,
    "merged": 7,
    "held": 7,
    "held_after_merge": 7,
    "reverted_after_merge": 7,
    "repair_forward_open": 7,
    "manual_hold": 7,
    "blocked_external": 7,
    "approval_blocked": 7,
    "blocked_needs_master": 7,
    "blocked": 7,
    "rejected": 7,
}
FEATURE_LOCAL_ACTIVE_STATES = {
    "active",
    "executing",
    "review",
    "repairing",
    "reworking",
    "feature_blocked",
    "active_repair",
}
MASTER_HELD_STATES = {
    "held",
    "held_after_merge",
    "reverted_after_merge",
    "repair_forward_open",
    "manual_hold",
    "blocked_external",
    "approval_blocked",
    "rejected",
}
MASTER_BLOCKED_STATES = {"blocked", "blocked_needs_master"}
MASTER_REVIEW_STATES = {"ready_for_master_review"}
MERGE_REQUEST_STATES = {"ready_for_merge", "merge_requested"}
TARGET_BRANCH_STATES = MASTER_REVIEW_STATES | MERGE_REQUEST_STATES
FEATURE_PASS_STATES = {"acked", "ready_for_master_review", "ready_for_merge", "merged"}


def _append_missing(
    errors: list[str], payload: dict[str, Any], required: set[str], prefix: str
) -> None:
    for key in sorted(required - set(payload)):
        errors.append(f"{prefix} missing required key: {key}")


def _validate_feature_amendment(
    amendment: dict[str, Any], errors: list[str], index: int
) -> None:
    prefix = f"feature_amendments[{index}]"
    _append_missing(errors, amendment, REQUIRED_FEATURE_AMENDMENT_KEYS, prefix)

    if amendment.get("action") not in FEATURE_AMENDMENT_ACTIONS:
        errors.append(f"{prefix} unsupported action: {amendment.get('action')}")
    if amendment.get("status") not in {"proposed", "accepted", "applied", "rejected"}:
        errors.append(f"{prefix} unsupported status: {amendment.get('status')}")
    if amendment.get("recorded_by") != "master-god":
        errors.append(f"{prefix} recorded_by must be master-god")

    feature_ids = amendment.get("feature_ids")
    if not isinstance(feature_ids, list) or not feature_ids or not all(
        isinstance(feature_id, str) and feature_id for feature_id in feature_ids
    ):
        errors.append(f"{prefix} feature_ids must be a non-empty string list")
    if not isinstance(amendment.get("target_feature_id"), str) or not amendment.get(
        "target_feature_id"
    ):
        errors.append(f"{prefix} target_feature_id is required")

    policy = amendment.get("policy_preserved", {})
    if not isinstance(policy, dict):
        errors.append(f"{prefix} policy_preserved must be an object")
    else:
        for key in (
            "v1_fallback_preserved",
            "kernel_opt_in_preserved",
            "no_benchmark_score_targets",
            "no_gate_lowering",
        ):
            if policy.get(key) is not True:
                errors.append(f"{prefix} policy_preserved.{key} must be true")

    if amendment.get("gate_effect") != "no_gate_lowering":
        errors.append(f"{prefix} gate_effect must be no_gate_lowering")

    artifacts = amendment.get("artifacts", {})
    if not isinstance(artifacts, dict):
        errors.append(f"{prefix} artifacts must be an object")
        return
    artifact_ref = artifacts.get("amendment")
    if not isinstance(artifact_ref, str) or not artifact_ref.startswith(
        "xmuse/master/amendments/"
    ):
        errors.append(
            f"{prefix} amendment artifact must live under xmuse/master/amendments/"
        )


def validate_master_state(state: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    _append_missing(errors, state, REQUIRED_MASTER_STATE_KEYS, "master_state")

    activation_state = state.get("activation_state")
    if activation_state not in MASTER_ACTIVATION_STATES:
        errors.append(f"invalid activation_state: {activation_state}")

    active = state.get("active")
    if activation_state == "master_active" and active is not True:
        errors.append("active must be true when activation_state is master_active")
    if activation_state != "master_active" and active is not False:
        errors.append("active must be false unless activation_state is master_active")

    if state.get("mode") != "master_control":
        errors.append("mode must be master_control")

    prompts = state.get("prompts", {})
    if not isinstance(prompts, dict) or {"master", "slave"} - set(prompts):
        errors.append("prompts must include master and slave")

    dispatch_contracts = state.get("dispatch_contracts", {})
    if not isinstance(dispatch_contracts, dict) or {"master", "slave"} - set(
        dispatch_contracts
    ):
        errors.append("dispatch_contracts must include master and slave")

    queues = state.get("queues", {})
    if not isinstance(queues, dict):
        errors.append("queues must be an object")
    else:
        missing_queues = MASTER_QUEUE_NAMES - set(queues)
        if missing_queues:
            errors.append("queues missing required keys: " + ", ".join(sorted(missing_queues)))

    features = state.get("features", [])
    if not isinstance(features, list):
        errors.append("features must be a list")
    else:
        seen: set[str] = set()
        for feature in features:
            if not isinstance(feature, dict):
                errors.append("feature entries must be objects")
                continue
            feature_id = feature.get("id", "<missing>")
            if feature_id in seen:
                errors.append(f"duplicate feature id: {feature_id}")
            seen.add(feature_id)
            _append_missing(errors, feature, REQUIRED_FEATURE_KEYS, f"feature {feature_id}")
            artifacts = feature.get("artifacts", {})
            if not isinstance(artifacts, dict):
                errors.append(f"feature {feature_id} artifacts must be an object")
            else:
                _append_missing(
                    errors,
                    artifacts,
                    REQUIRED_FEATURE_ARTIFACT_KEYS,
                    f"feature {feature_id} artifacts",
                )

    amendments = state.get("feature_amendments", [])
    if not isinstance(amendments, list):
        errors.append("feature_amendments must be a list")
    else:
        seen_amendments: set[str] = set()
        for index, amendment in enumerate(amendments):
            if not isinstance(amendment, dict):
                errors.append(f"feature_amendments[{index}] must be an object")
                continue
            amendment_id = amendment.get("amendment_id")
            if isinstance(amendment_id, str) and amendment_id:
                if amendment_id in seen_amendments:
                    errors.append(f"duplicate feature amendment id: {amendment_id}")
                seen_amendments.add(amendment_id)
            _validate_feature_amendment(amendment, errors, index)

    return {"valid": not errors, "errors": errors}
