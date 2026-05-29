#!/usr/bin/env python3
"""Deterministically process Xmuse Master review queue items."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} root must be an object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _loop_path(loop: Path, ref: str | None) -> Path | None:
    if not ref:
        return None
    path = Path(ref)
    if path.is_absolute():
        return path
    prefix = loop.name + "/"
    if ref.startswith(prefix):
        return loop / ref[len(prefix) :]
    return loop / ref


def _optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        return _read_json(path)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return None


def _git_output(args: list[str], cwd: Path) -> str | None:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _worktree_dirty(worktree: Path) -> bool:
    status = _git_output(["git", "status", "--porcelain"], worktree)
    return status is None or bool(status)


def _feature_head(feature: dict[str, Any]) -> str | None:
    worktree = feature.get("worktree")
    if isinstance(worktree, str) and worktree:
        head = _git_output(["git", "rev-parse", "HEAD"], Path(worktree))
        if head:
            return head
    slave = feature.get("slave_god", {})
    if isinstance(slave, dict) and isinstance(slave.get("head_commit"), str):
        return slave["head_commit"]
    return None


def _artifact_ref(feature: dict[str, Any], name: str) -> str:
    feature_id = str(feature.get("id") or "")
    artifacts = feature.get("artifacts", {})
    if isinstance(artifacts, dict) and isinstance(artifacts.get(name), str):
        return artifacts[name]
    if name == "result":
        return f"xmuse/work/features/{feature_id}/result.md"
    return f"xmuse/work/features/{feature_id}/{name}.json"


def _file_digest(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_digests(loop: Path, feature: dict[str, Any]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for name in ("result", "ack", "review_verdict"):
        digest = _file_digest(_loop_path(loop, _artifact_ref(feature, name)))
        if digest:
            digests[name] = digest
    return digests


def _master_review_blockers(loop: Path, feature: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    feature_id = str(feature.get("id") or "<unknown>")
    result_path = _loop_path(loop, _artifact_ref(feature, "result"))
    ack = _optional_json(_loop_path(loop, _artifact_ref(feature, "ack")))
    review = _optional_json(_loop_path(loop, _artifact_ref(feature, "review_verdict")))

    if result_path is None or not result_path.is_file():
        blockers.append("missing Slave result.md")
    if not ack or str(ack.get("ack_level", "")).lower() != "usable":
        blockers.append("Slave ack.json is missing or not usable")
    if not review or str(review.get("verdict", "")).lower() != "pass":
        blockers.append("Slave review_verdict.json is missing or not PASS")
    if not feature.get("branch"):
        blockers.append("feature branch is not recorded")
    if not feature.get("target_branch") and not feature.get("merge", {}).get("target_branch"):
        blockers.append("target branch is not recorded")

    worktree_value = feature.get("worktree")
    if not isinstance(worktree_value, str) or not worktree_value:
        blockers.append("feature worktree is not recorded")
    else:
        worktree = Path(worktree_value)
        if not worktree.is_dir():
            blockers.append("feature worktree does not exist")
        elif _worktree_dirty(worktree):
            blockers.append(
                "feature worktree has uncommitted changes; Slave must commit or "
                "produce clean mergeable evidence before Master review can pass"
            )

    if feature.get("state") != "ready_for_master_review":
        blockers.append(f"feature {feature_id} is not in ready_for_master_review")
    return blockers


def _set_feature_rework(loop: Path, feature: dict[str, Any], reason: str) -> None:
    feature["state"] = "repairing"
    slave = feature.setdefault("slave_god", {})
    if isinstance(slave, dict):
        slave["dispatch_status"] = "rework_required"
        slave["last_dispatch_reason"] = reason
        slave["last_reported_at"] = _now()
    merge = feature.get("merge")
    if isinstance(merge, dict):
        merge["status"] = "not_requested"
    slave_state_path = _loop_path(loop, feature.get("slave_state_path"))
    slave_state = _optional_json(slave_state_path)
    if slave_state_path and slave_state:
        slave_state["state"] = "repairing"
        slave_state["last_dispatch_reason"] = reason
        slave_state["last_updated"] = _now()
        _write_json(slave_state_path, slave_state)


def _write_rework_request(loop: Path, feature: dict[str, Any], blockers: list[str]) -> None:
    feature_id = str(feature["id"])
    reason = "; ".join(blockers)
    target_branch = feature.get("target_branch") or feature.get("merge", {}).get("target_branch")
    payload = {
        "version": "1.0",
        "feature_id": feature_id,
        "decision": "request_rework",
        "recorded_by": "master-god",
        "recorded_at": _now(),
        "previous_state": "ready_for_master_review",
        "next_state": "repairing",
        "dispatch_status": "rework_required",
        "branch": feature.get("branch"),
        "target_branch": target_branch,
        "head_commit": _feature_head(feature),
        "blockers": blockers,
        "affected_artifacts": {
            "result": _artifact_ref(feature, "result"),
            "ack": _artifact_ref(feature, "ack"),
            "review_verdict": _artifact_ref(feature, "review_verdict"),
            "slave_state": feature.get("slave_state_path"),
        },
        "expected_next_evidence": [
            "clean feature worktree with committed feature changes or explicit hold rationale",
            "updated result.md, usable ack.json, and PASS review_verdict.json",
            "no benchmark score target or unsupported benchmark improvement claim",
        ],
        "policy_preserved": {
            "v3_default_preserved": True,
            "v1_fallback_preserved": True,
            "kernel_opt_in_preserved": True,
            "no_benchmark_score_targets": True,
            "requires_master_review": True,
            "requires_integrated_tests": True,
            "requires_external_approval": True,
            "requires_fresh_target_gate": True,
            "no_gate_lowering": True,
        },
    }
    _write_json(loop / "master" / "features" / feature_id / "rework_request.json", payload)
    _set_feature_rework(loop, feature, reason)


def _write_master_review(loop: Path, feature: dict[str, Any]) -> None:
    feature_id = str(feature["id"])
    branch = feature.get("branch")
    target_branch = feature.get("target_branch") or feature.get("merge", {}).get("target_branch")
    payload = {
        "version": "1.0",
        "feature_id": feature_id,
        "recorded_by": "master-god",
        "recorded_at": _now(),
        "status": "accepted",
        "branch": branch,
        "target_branch": target_branch,
        "head_commit": _feature_head(feature),
        "base_commit": _git_output(["git", "rev-parse", str(target_branch)], Path.cwd())
        if target_branch
        else None,
        "slave_result_ref": _artifact_ref(feature, "result"),
        "slave_ack_ref": _artifact_ref(feature, "ack"),
        "slave_review_ref": _artifact_ref(feature, "review_verdict"),
        "artifact_digests": _artifact_digests(loop, feature),
        "review_summary": (
            "Deterministic Master review accepted Slave usable ACK, PASS review, "
            "result artifact, recorded branches, and clean feature worktree."
        ),
        "blocking_findings": [],
        "merge_decision": "not_merged",
        "next_gate": "integrated_tests",
    }
    _write_json(loop / "master" / "features" / feature_id / "master_review.json", payload)
    policy = feature.get("policy_flags", {})
    quarantined = (
        isinstance(policy, dict)
        and policy.get("requires_control_plane_merge_quarantine") is True
    )
    if quarantined:
        feature["state"] = "blocked_needs_master"
        dispatch_status = "master_review_accepted_quarantined"
        reason = "Master review accepted; control-plane merge quarantine still applies"
        merge_status = "not_requested"
    else:
        feature["state"] = "ready_for_merge"
        dispatch_status = "ready_for_merge"
        reason = "Master review accepted; next gate is integrated tests"
        merge_status = "ready_for_merge"
    slave = feature.setdefault("slave_god", {})
    if isinstance(slave, dict):
        slave["dispatch_status"] = dispatch_status
        slave["last_dispatch_reason"] = reason
        slave["last_reported_at"] = _now()
    merge = feature.setdefault("merge", {})
    if isinstance(merge, dict):
        merge["status"] = merge_status
    slave_state_path = _loop_path(loop, feature.get("slave_state_path"))
    slave_state = _optional_json(slave_state_path)
    if slave_state_path and slave_state:
        slave_state["state"] = str(feature["state"])
        slave_state["dispatch_status"] = dispatch_status
        slave_state["last_dispatch_reason"] = reason
        slave_state["last_updated"] = _now()
        _write_json(slave_state_path, slave_state)


def _refresh_status(loop: Path, state: dict[str, Any]) -> None:
    module_path = loop / "hermes_hardening.py"
    if not module_path.exists():
        return
    spec = importlib.util.spec_from_file_location("hermes_hardening", module_path)
    module = importlib.util.module_from_spec(spec)
    if spec is None or spec.loader is None:
        return
    spec.loader.exec_module(module)
    module.write_master_status(loop, state)


def process_master_review_queue(loop: Path) -> dict[str, Any]:
    state_path = loop / "master_state.json"
    state = _read_json(state_path)
    reviewed: list[str] = []
    reworked: list[str] = []
    skipped: list[str] = []

    features = state.get("features", [])
    if not isinstance(features, list):
        raise ValueError("master_state.features must be a list")
    for feature in features:
        if not isinstance(feature, dict):
            continue
        feature_id = str(feature.get("id") or "")
        if feature.get("state") != "ready_for_master_review":
            continue
        blockers = _master_review_blockers(loop, feature)
        if blockers:
            _write_rework_request(loop, feature, blockers)
            reworked.append(feature_id)
        else:
            _write_master_review(loop, feature)
            reviewed.append(feature_id)
        if not feature_id:
            skipped.append("<missing-id>")

    state["last_updated"] = _now()
    _write_json(state_path, state)
    _refresh_status(loop, state)
    return {"reviewed": reviewed, "reworked": reworked, "skipped": skipped}


def main() -> dict[str, Any]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", default="xmuse")
    args = parser.parse_args()
    result = process_master_review_queue(Path(args.loop))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


if __name__ == "__main__":
    main()
