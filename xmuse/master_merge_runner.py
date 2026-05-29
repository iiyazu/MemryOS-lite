#!/usr/bin/env python3
"""Process Xmuse Master merge decisions without external approval synthesis."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
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


def _load_hardening(loop: Path):
    module_path = loop / "hermes_hardening.py"
    if not module_path.is_file():
        module_path = Path(__file__).with_name("hermes_hardening.py")
    spec = importlib.util.spec_from_file_location("xmuse_hermes_hardening", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load hardening module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _controller_path(loop: Path, ref: str) -> Path:
    if ref.startswith(loop.name + "/"):
        return loop.parent / ref
    return loop / ref


def _git_output(args: list[str], cwd: Path) -> tuple[int, str, str]:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _target_worktree_clean(project: Path) -> tuple[bool, str]:
    code, stdout, stderr = _git_output(["git", "status", "--porcelain"], project)
    if code != 0:
        return False, stderr or stdout or "unable to read target git status"
    return not bool(stdout), stdout


def _artifact_digest(hardening: Any, loop: Path, ref: str) -> str | None:
    try:
        return hardening.file_json_digest(_controller_path(loop, ref))
    except Exception:
        return None


def _feature_head(feature: dict[str, Any]) -> str | None:
    slave = feature.get("slave_god", {})
    if isinstance(slave, dict) and isinstance(slave.get("head_commit"), str):
        return slave["head_commit"]
    return None


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in value)


def _target_branch(feature: dict[str, Any]) -> str | None:
    merge = feature.get("merge", {})
    if not isinstance(merge, dict):
        merge = {}
    target = feature.get("target_branch") or merge.get("target_branch")
    return str(target) if target else None


def _remediation_ref(feature_id: str) -> str:
    return f"xmuse/master/features/{feature_id}/held_remediation.json"


def _is_target_dirty_hold(feature: dict[str, Any]) -> bool:
    merge = feature.get("merge", {})
    if not isinstance(merge, dict):
        return False
    return (
        feature.get("state") == "held"
        and merge.get("status") == "held"
        and merge.get("blocked_gate") == "target_worktree_clean"
    )


def _remove_existing_worktree(project: Path, worktree: Path) -> None:
    if worktree.exists():
        _git_output(["git", "worktree", "remove", "--force", str(worktree)], project)
    if worktree.exists():
        shutil.rmtree(worktree)


def _write_target_dirty_remediation(
    loop: Path,
    project: Path,
    feature: dict[str, Any],
    *,
    dirty_status: str,
) -> dict[str, Any]:
    feature_id = str(feature["id"])
    target_branch = _target_branch(feature)
    feature_ref = str(feature.get("branch") or _feature_head(feature) or "")
    worktree = project.parent / f"{project.name}-xmuse-held-remediation-{_safe_name(feature_id)}"
    remediation: dict[str, Any] = {
        "version": "1.0",
        "feature_id": feature_id,
        "status": "failed",
        "recorded_by": "master-god",
        "recorded_at": _now(),
        "blocked_gate": "target_worktree_clean",
        "strategy": "isolated_target_worktree_merge_rehearsal",
        "target_worktree_dirty": True,
        "target_worktree_status": dirty_status,
        "target_branch": target_branch,
        "feature_ref": feature_ref,
        "worktree": str(worktree),
        "errors": [],
    }

    if not target_branch:
        remediation["errors"].append("target_branch is required for held remediation")
    if not feature_ref:
        remediation["errors"].append(
            "feature branch or head commit is required for held remediation"
        )
    if remediation["errors"]:
        _write_json(
            loop / "master" / "features" / feature_id / "held_remediation.json",
            remediation,
        )
        return remediation

    target_code, target_head, target_err = _git_output(
        ["git", "rev-parse", target_branch],
        project,
    )
    feature_code, feature_head, feature_err = _git_output(
        ["git", "rev-parse", feature_ref],
        project,
    )
    remediation["target_head"] = target_head if target_code == 0 else None
    remediation["feature_head"] = feature_head if feature_code == 0 else None
    if target_code != 0:
        remediation["errors"].append(target_err or f"unable to resolve {target_branch}")
    if feature_code != 0:
        remediation["errors"].append(feature_err or f"unable to resolve {feature_ref}")
    if remediation["errors"]:
        _write_json(
            loop / "master" / "features" / feature_id / "held_remediation.json",
            remediation,
        )
        return remediation

    _remove_existing_worktree(project, worktree)
    add_code, _add_out, add_err = _git_output(
        ["git", "worktree", "add", "--detach", str(worktree), target_head],
        project,
    )
    if add_code != 0:
        remediation["errors"].append(add_err or "unable to create isolated remediation worktree")
        _write_json(
            loop / "master" / "features" / feature_id / "held_remediation.json",
            remediation,
        )
        return remediation

    merge_code, merge_out, merge_err = _git_output(
        [
            "git",
            "-c",
            "user.name=Xmuse Master",
            "-c",
            "user.email=xmuse@example.invalid",
            "merge",
            "--no-ff",
            "--no-commit",
            feature_head,
        ],
        worktree,
    )
    remediation["merge_rehearsal_output"] = merge_out
    if merge_code == 0:
        remediation["status"] = "passed"
        remediation["next_action"] = (
            "target merge can proceed after current target checkout is clean "
            "or through an explicit isolated-worktree merge executor"
        )
        _git_output(["git", "merge", "--abort"], worktree)
    else:
        remediation["errors"].append(merge_err or merge_out or "isolated merge rehearsal failed")

    _write_json(loop / "master" / "features" / feature_id / "held_remediation.json", remediation)
    return remediation


def _write_external_hold(
    loop: Path,
    hardening: Any,
    feature: dict[str, Any],
    *,
    reasons: list[str],
) -> None:
    feature_id = str(feature["id"])
    artifacts = feature.get("artifacts", {})
    request_ref = artifacts.get("merge_approval_request")
    decision = {
        "version": "1.0",
        "feature_id": feature_id,
        "decision": "held",
        "approval_mode": "external",
        "external_approval_required": True,
        "recorded_by": "master-god",
        "recorded_at": _now(),
        "blocked_gate": "external_merge_approval",
        "reasons": reasons,
        "approval_request_ref": request_ref,
        "approval_request_digest": _artifact_digest(hardening, loop, request_ref)
        if isinstance(request_ref, str)
        else None,
        "master_review_ref": artifacts.get("master_review"),
        "integrated_tests_ref": artifacts.get("integrated_tests"),
        "branch": feature.get("branch"),
        "target_branch": _target_branch(feature),
        "head_commit": _feature_head(feature),
        "merge_strategy": feature.get("merge", {}).get("strategy"),
    }
    _write_json(loop / "approvals" / feature_id / "merge_decision.json", decision)


def _write_autonomous_approval(
    loop: Path,
    hardening: Any,
    feature: dict[str, Any],
    *,
    execute: bool,
    reasons: list[str] | None = None,
) -> None:
    feature_id = str(feature["id"])
    artifacts = feature.get("artifacts", {})
    master_review_ref = artifacts.get("master_review")
    integrated_tests_ref = artifacts.get("integrated_tests")
    decision = {
        "version": "1.0",
        "feature_id": feature_id,
        "decision": "approved_for_autonomous_merge",
        "approval_mode": "master_autonomous",
        "external_approval_required": False,
        "recorded_by": "master-god",
        "recorded_at": _now(),
        "gate_effect": "no_gate_lowering",
        "execution_requested": execute,
        "reasons": reasons
        or [
            "Master review accepted the feature evidence.",
            "Master-owned integrated tests passed on the current target head.",
            "Feature policy allows Master-autonomous merge decision.",
        ],
        "master_review_ref": master_review_ref,
        "master_review_digest": _artifact_digest(hardening, loop, master_review_ref)
        if isinstance(master_review_ref, str)
        else None,
        "integrated_tests_ref": integrated_tests_ref,
        "integrated_tests_digest": _artifact_digest(hardening, loop, integrated_tests_ref)
        if isinstance(integrated_tests_ref, str)
        else None,
        "branch": feature.get("branch"),
        "target_branch": _target_branch(feature),
        "head_commit": _feature_head(feature),
        "merge_strategy": feature.get("merge", {}).get("strategy"),
        "next_action": "execute_merge_when_target_worktree_is_clean"
        if execute
        else "ready_for_master_autonomous_merge_execution",
    }
    _write_json(loop / "approvals" / feature_id / "merge_decision.json", decision)


def _write_target_hold(
    loop: Path,
    hardening: Any,
    feature: dict[str, Any],
    *,
    dirty_status: str,
    remediation: dict[str, Any] | None = None,
) -> None:
    feature_id = str(feature["id"])
    remediation_ref = _remediation_ref(feature_id) if remediation else None
    decision = {
        "version": "1.0",
        "feature_id": feature_id,
        "decision": "held",
        "approval_mode": "master_autonomous",
        "external_approval_required": False,
        "recorded_by": "master-god",
        "recorded_at": _now(),
        "blocked_gate": "target_worktree_clean",
        "reasons": [
            "Master autonomous merge is allowed, but the target worktree has uncommitted changes.",
            "Merge execution must not overwrite unrelated user or concurrent agent work.",
        ],
        "target_worktree_status": dirty_status,
        "remediation_ref": remediation_ref,
        "remediation_digest": _artifact_digest(hardening, loop, remediation_ref)
        if remediation_ref
        else None,
        "remediation_status": remediation.get("status") if remediation else None,
        "branch": feature.get("branch"),
        "target_branch": _target_branch(feature),
        "head_commit": _feature_head(feature),
        "merge_strategy": feature.get("merge", {}).get("strategy"),
        "next_action": (
            "held_remediation_passed_clean_target_or_use_isolated_merge_executor"
            if remediation and remediation.get("status") == "passed"
            else "clean_or_isolate_target_worktree_then_rerun_master_merge_runner"
        ),
    }
    _write_json(loop / "approvals" / feature_id / "merge_decision.json", decision)


def process_merge_queue(loop_root: str | Path, *, execute: bool = False) -> dict[str, Any]:
    loop = Path(loop_root).resolve()
    project = loop.parent
    state = _read_json(loop / "master_state.json")
    hardening = _load_hardening(loop)
    result: dict[str, list[str]] = {
        "approved": [],
        "held": [],
        "remediated": [],
        "skipped": [],
        "merged": [],
    }

    for feature in state.get("features", []):
        if not isinstance(feature, dict) or not feature.get("id"):
            continue
        feature_id = str(feature["id"])
        merge = feature.get("merge", {})
        merge_status = merge.get("status") if isinstance(merge, dict) else None
        target_dirty_hold = _is_target_dirty_hold(feature)
        if feature.get("state") not in hardening.MERGE_REQUEST_STATES and not target_dirty_hold:
            result["skipped"].append(feature_id)
            continue
        if merge_status not in hardening.MERGE_REQUEST_STATES and not target_dirty_hold:
            result["skipped"].append(feature_id)
            continue

        gate = hardening.validate_merge_queue_gate(loop, feature)
        if not gate["valid"]:
            _write_external_hold(
                loop,
                hardening,
                feature,
                reasons=["local merge gate failed: " + "; ".join(gate["errors"])],
            )
            result["held"].append(feature_id)
            continue

        approval_mode = hardening.merge_approval_mode(feature)
        if approval_mode != "master_autonomous":
            _write_external_hold(
                loop,
                hardening,
                feature,
                reasons=["external merge approval artifact is required by feature policy"],
            )
            result["held"].append(feature_id)
            continue

        if execute:
            clean, status = _target_worktree_clean(project)
            if not clean:
                remediation = _write_target_dirty_remediation(
                    loop,
                    project,
                    feature,
                    dirty_status=status,
                )
                _write_target_hold(
                    loop,
                    hardening,
                    feature,
                    dirty_status=status,
                    remediation=remediation,
                )
                if remediation.get("status") == "passed":
                    result["remediated"].append(feature_id)
                else:
                    result["held"].append(feature_id)
                continue

        _write_autonomous_approval(loop, hardening, feature, execute=execute)
        result["approved"].append(feature_id)

    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", default="xmuse")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    result = process_merge_queue(Path(args.loop), execute=args.execute)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
