#!/usr/bin/env python3
"""Run deterministic Master-owned integrated tests for merge-ready features."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MERGE_READY_STATES = {"ready_for_merge", "merge_requested"}


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


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_ref(feature: dict[str, Any], name: str) -> str:
    feature_id = str(feature.get("id") or "")
    artifacts = feature.get("artifacts", {})
    if isinstance(artifacts, dict) and isinstance(artifacts.get(name), str):
        return artifacts[name]
    if name == "result":
        return f"xmuse/work/features/{feature_id}/result.md"
    return f"xmuse/work/features/{feature_id}/{name}.json"


def _master_artifact_ref(feature: dict[str, Any], name: str) -> str:
    feature_id = str(feature["id"])
    artifacts = feature.get("artifacts", {})
    if isinstance(artifacts, dict) and isinstance(artifacts.get(name), str):
        return artifacts[name]
    return f"xmuse/master/features/{feature_id}/{name}.json"


def _load_hardening(loop: Path):
    module_path = loop / "hermes_hardening.py"
    if not module_path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("xmuse_hermes_hardening", module_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _refresh_status(loop: Path, state: dict[str, Any]) -> None:
    hardening = _load_hardening(loop)
    if hardening is None or not hasattr(hardening, "write_master_status"):
        return
    try:
        hardening.write_master_status(loop, state)
    except Exception:
        return


def _head_commit(worktree: Path) -> str | None:
    return _git_output(["git", "rev-parse", "HEAD"], worktree)


def _runnable_commands(ack: dict[str, Any] | None) -> list[str]:
    if not ack:
        return []
    commands = ack.get("verification_commands")
    if not isinstance(commands, list):
        return []
    runnable: list[str] = []
    for item in commands:
        if not isinstance(item, dict):
            continue
        command = item.get("command")
        if not isinstance(command, str) or not command.strip():
            continue
        if "..." in command:
            continue
        runnable.append(command)
    return runnable


def _run_command(command: str, *, cwd: Path, log_path: Path, timeout: int) -> dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=cwd,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    output = result.stdout
    if result.stderr:
        output += ("\n" if output else "") + result.stderr
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(output, encoding="utf-8")
    return {
        "command": command,
        "status": "passed" if result.returncode == 0 else "failed",
        "exit_code": result.returncode,
        "artifact_ref": f"xmuse/master/features/{log_path.parent.name}/{log_path.name}",
        "artifact_digest": _file_digest(log_path),
    }


def _set_rework(loop: Path, feature: dict[str, Any], blockers: list[str]) -> None:
    feature_id = str(feature["id"])
    reason = "; ".join(blockers)
    feature["state"] = "repairing"
    merge = feature.get("merge")
    if isinstance(merge, dict):
        merge["status"] = "not_requested"
    slave = feature.setdefault("slave_god", {})
    if isinstance(slave, dict):
        slave["dispatch_status"] = "rework_required"
        slave["last_dispatch_reason"] = reason
        slave["last_reported_at"] = _now()

    slave_state_path = _loop_path(loop, feature.get("slave_state_path"))
    slave_state = _optional_json(slave_state_path)
    if slave_state_path and slave_state:
        slave_state["state"] = "repairing"
        slave_state["dispatch_status"] = "rework_required"
        slave_state["last_dispatch_reason"] = reason
        slave_state["last_updated"] = _now()
        _write_json(slave_state_path, slave_state)

    payload = {
        "version": "1.0",
        "feature_id": feature_id,
        "decision": "request_rework",
        "recorded_by": "master-god",
        "recorded_at": _now(),
        "previous_state": "ready_for_merge",
        "next_state": "repairing",
        "dispatch_status": "rework_required",
        "branch": feature.get("branch"),
        "target_branch": feature.get("target_branch")
        or feature.get("merge", {}).get("target_branch"),
        "head_commit": None,
        "blockers": blockers,
        "expected_next_evidence": [
            "clean feature worktree",
            "updated usable ack.json, PASS review_verdict.json, and result.md",
            "verification_commands that can be rerun by Master integrated tests",
        ],
        "policy_preserved": {
            "requires_master_review": True,
            "requires_integrated_tests": True,
            "requires_external_approval": True,
            "no_gate_lowering": True,
        },
    }
    worktree_value = feature.get("worktree")
    if isinstance(worktree_value, str) and worktree_value:
        payload["head_commit"] = _head_commit(Path(worktree_value))
    _write_json(loop / "master" / "features" / feature_id / "rework_request.json", payload)


def _feature_ready_for_integrated_tests(feature: dict[str, Any]) -> bool:
    merge = feature.get("merge", {})
    merge_status = merge.get("status") if isinstance(merge, dict) else None
    return feature.get("state") in MERGE_READY_STATES and merge_status in MERGE_READY_STATES


def _process_feature(loop: Path, feature: dict[str, Any], *, timeout: int) -> str:
    feature_id = str(feature["id"])
    worktree_value = feature.get("worktree")
    if not isinstance(worktree_value, str) or not worktree_value:
        _set_rework(loop, feature, ["feature worktree is not recorded"])
        return "rework"
    worktree = Path(worktree_value)
    if not worktree.is_dir():
        _set_rework(loop, feature, ["feature worktree does not exist"])
        return "rework"
    if _worktree_dirty(worktree):
        _set_rework(loop, feature, ["feature worktree is dirty before integrated tests"])
        return "rework"

    master_review = _optional_json(_loop_path(loop, _master_artifact_ref(feature, "master_review")))
    if not master_review or master_review.get("status") != "accepted":
        _set_rework(loop, feature, ["missing accepted Master review"])
        return "rework"

    head = _head_commit(worktree)
    if head and master_review.get("head_commit") and head != master_review.get("head_commit"):
        _set_rework(loop, feature, ["feature worktree HEAD differs from Master review head_commit"])
        return "rework"

    ack = _optional_json(_loop_path(loop, _artifact_ref(feature, "ack")))
    commands = _runnable_commands(ack)
    if not commands:
        _set_rework(
            loop,
            feature,
            ["no runnable Slave verification_commands for Master integrated tests"],
        )
        return "rework"

    command_results: list[dict[str, Any]] = []
    feature_master_dir = loop / "master" / "features" / feature_id
    for idx, command in enumerate(commands, start=1):
        log_path = feature_master_dir / f"integrated_command_{idx}.log"
        try:
            command_result = _run_command(command, cwd=worktree, log_path=log_path, timeout=timeout)
        except subprocess.TimeoutExpired:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(f"command timed out after {timeout}s\n", encoding="utf-8")
            command_result = {
                "command": command,
                "status": "failed",
                "exit_code": None,
                "artifact_ref": f"xmuse/master/features/{feature_id}/{log_path.name}",
                "artifact_digest": _file_digest(log_path),
                "timeout_seconds": timeout,
            }
        command_results.append(command_result)
        if command_result["status"] != "passed":
            _set_rework(loop, feature, [f"integrated test command failed: {command}"])
            return "rework"

    if _worktree_dirty(worktree):
        _set_rework(loop, feature, ["feature worktree is dirty after integrated tests"])
        return "rework"

    payload = {
        "version": "1.0",
        "feature_id": feature_id,
        "status": "passed",
        "recorded_by": "master-god",
        "recorded_at": _now(),
        "branch": master_review.get("branch") or feature.get("branch"),
        "base_commit": master_review.get("base_commit"),
        "head_commit": master_review.get("head_commit") or head,
        "target_branch": master_review.get("target_branch")
        or feature.get("target_branch")
        or feature.get("merge", {}).get("target_branch"),
        "commands": command_results,
        "worktree_clean": True,
        "master_review_ref": _master_artifact_ref(feature, "master_review"),
        "slave_ack_ref": _artifact_ref(feature, "ack"),
        "artifact_digests": {
            "ack": _file_digest(_loop_path(loop, _artifact_ref(feature, "ack"))),
            "master_review": _file_digest(
                _loop_path(loop, _master_artifact_ref(feature, "master_review"))
            ),
        },
    }
    _write_json(_loop_path(loop, _master_artifact_ref(feature, "integrated_tests")), payload)
    return "passed"


def process_integrated_tests(loop_root: str | Path, *, timeout: int = 1200) -> dict[str, Any]:
    loop = Path(loop_root)
    state_path = loop / "master_state.json"
    state = _read_json(state_path)
    result: dict[str, Any] = {
        "passed": [],
        "rework": [],
        "skipped": [],
    }
    changed = False
    for feature in state.get("features", []):
        if not isinstance(feature, dict) or not feature.get("id"):
            continue
        feature_id = str(feature["id"])
        if not _feature_ready_for_integrated_tests(feature):
            result["skipped"].append(feature_id)
            continue
        integrated_path = _loop_path(loop, _master_artifact_ref(feature, "integrated_tests"))
        integrated = _optional_json(integrated_path)
        if integrated and integrated.get("status") == "passed":
            result["skipped"].append(feature_id)
            continue
        outcome = _process_feature(loop, feature, timeout=timeout)
        result[outcome].append(feature_id)
        changed = True
    if changed:
        state["last_updated"] = _now()
        _write_json(state_path, state)
    _refresh_status(loop, state)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", default="xmuse")
    parser.add_argument("--timeout", type=int, default=1200)
    args = parser.parse_args()
    result = process_integrated_tests(Path(args.loop), timeout=args.timeout)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
