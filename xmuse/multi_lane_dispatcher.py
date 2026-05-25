#!/usr/bin/env python3
"""Build deterministic xmuse multi-lane dispatch plans without launching nodes."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

NODE_LAUNCHER = "xmuse/codex_node_launcher.sh"
SLAVE_PROMPT = "xmuse/prompts/slave_god_prompt.md"

ACTIVE_STATES = {"repairing", "reworking", "feature_blocked", "active_repair", "active"}
PLANNING_STATES = {"planned", "planning"}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} root must be an object")
    return payload


def _feature_job(feature: dict[str, Any], *, reason: str) -> dict[str, Any]:
    feature_id = feature["id"]
    worktree = feature.get("worktree")
    job_ref = f"xmuse/jobs/{feature_id}.json"
    prompt_file = f"xmuse/dispatch/features/{feature_id}/slave_dispatch_prompt.md"
    blockers: list[str] = []
    if not isinstance(worktree, str) or not worktree:
        blockers.append("feature worktree is not recorded")
    elif not Path(worktree).exists():
        blockers.append("feature worktree does not exist")
    return {
        "feature_id": feature_id,
        "node": "slave",
        "status": "blocked" if blockers else "queued",
        "reason": reason,
        "branch": feature.get("branch"),
        "worktree": worktree,
        "prompt_file": prompt_file,
        "env": {
            "XMUSE_FEATURE_ID": feature_id,
            "XMUSE_JOB_REF": job_ref,
        },
        "command": [
            "env",
            f"XMUSE_FEATURE_ID={feature_id}",
            f"XMUSE_JOB_REF={job_ref}",
            "bash",
            NODE_LAUNCHER,
            "slave",
            prompt_file,
        ],
        "blockers": blockers,
        "job_ref": job_ref,
        "prompt_text": _slave_dispatch_prompt(feature, job_ref=job_ref),
        "artifacts": {
            "slave_state": feature.get("slave_state_path"),
            "blueprint": feature.get("blueprint_path"),
        },
    }


def _slave_dispatch_prompt(feature: dict[str, Any], *, job_ref: str) -> str:
    feature_id = feature["id"]
    return "\n".join(
        [
            "# Xmuse Slave Dispatch",
            "",
            f"Assigned feature: {feature_id}",
            f"XMUSE_FEATURE_ID={feature_id}",
            f"XMUSE_JOB_REF={job_ref}",
            "",
            "Read these files before acting:",
            f"- {SLAVE_PROMPT}",
            f"- {feature.get('slave_state_path')}",
            f"- {feature.get('blueprint_path')}",
            "",
            f"Branch: {feature.get('branch')}",
            f"Worktree: {feature.get('worktree')}",
            "",
            "Run autonomously with the active yolo runner policy. Do not switch",
            "to another feature. If this assignment is ambiguous, write a",
            "feature-local blocker instead of asking the user.",
            "",
        ]
    )


def build_dispatch_plan(loop: Path) -> dict[str, Any]:
    state = _read_json(loop / "master_state.json")
    jobs: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    feature_ids: set[str] = set()

    for feature in state.get("features", []):
        if not isinstance(feature, dict) or not feature.get("id"):
            continue
        feature_ids.add(str(feature["id"]))
        feature_state = str(feature.get("state") or "")
        dispatch_status = str(feature.get("slave_god", {}).get("dispatch_status") or "")
        if feature_state in ACTIVE_STATES or dispatch_status == "rework_required":
            jobs.append(
                _feature_job(feature, reason="feature requires Slave repair or active work")
            )
        elif feature_state in PLANNING_STATES:
            jobs.append(_feature_job(feature, reason="feature is planned and needs Slave planning"))
        else:
            skipped.append(
                {
                    "feature_id": feature["id"],
                    "state": feature_state,
                    "dispatch_status": dispatch_status,
                    "reason": "not dispatchable by deterministic multi-lane dispatcher",
                }
            )

    orphan_blueprints: list[dict[str, str]] = []
    features_dir = loop / "work" / "features"
    if features_dir.exists():
        for blueprint in sorted(features_dir.glob("*/blueprint.md")):
            feature_id = blueprint.parent.name
            if feature_id not in feature_ids:
                orphan_blueprints.append(
                    {
                        "feature_id": feature_id,
                        "blueprint": f"xmuse/work/features/{feature_id}/blueprint.md",
                        "reason": (
                            "blueprint exists but feature is absent from master_state.features"
                        ),
                    }
                )

    return {
        "version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "xmuse/master_state.json",
        "runner": {
            "launcher": NODE_LAUNCHER,
            "command": "codex exec --yolo",
            "approval_policy": "never",
            "starts_processes": False,
        },
        "jobs": jobs,
        "skipped": skipped,
        "orphan_blueprints": orphan_blueprints,
        "counts": {
            "jobs": len(jobs),
            "queued": sum(1 for job in jobs if job["status"] == "queued"),
            "blocked_jobs": sum(1 for job in jobs if job["status"] == "blocked"),
            "skipped": len(skipped),
            "orphan_blueprints": len(orphan_blueprints),
        },
    }


def write_dispatch_plan(loop: Path, plan: dict[str, Any]) -> dict[str, str]:
    dispatch_dir = loop / "dispatch"
    jobs_dir = loop / "jobs"
    prompts_dir = dispatch_dir / "features"
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)

    plan_path = dispatch_dir / "multi_lane_dispatch.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    existing_runtime: dict[str, dict[str, Any]] = {}
    for existing_job in jobs_dir.glob("*.json"):
        payload = _read_json(existing_job)
        runtime = payload.get("runtime")
        if isinstance(runtime, dict):
            existing_runtime[existing_job.stem] = runtime
    for stale_job in jobs_dir.glob("*.json"):
        stale_job.unlink()
    for job in plan["jobs"]:
        job_path = jobs_dir / f"{job['feature_id']}.json"
        prompt_path = loop / job["prompt_file"].removeprefix("xmuse/")
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(job["prompt_text"], encoding="utf-8")
        job_payload = {key: value for key, value in job.items() if key != "prompt_text"}
        runtime = existing_runtime.get(str(job["feature_id"]))
        if runtime is not None:
            job_payload["runtime"] = runtime
        job_path.write_text(
            json.dumps(job_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return {
        "dispatch_plan": str(plan_path),
        "jobs_dir": str(jobs_dir),
        "prompts_dir": str(prompts_dir),
    }


def main() -> dict[str, Any]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", default="xmuse")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    loop = Path(args.loop)
    plan = build_dispatch_plan(loop)
    if args.write:
        plan["written"] = write_dispatch_plan(loop, plan)
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    return plan


if __name__ == "__main__":
    main()
