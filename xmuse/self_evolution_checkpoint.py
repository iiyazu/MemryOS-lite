#!/usr/bin/env python3
"""Write one xmuse self-evolution monitoring checkpoint."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from xmuse_core.platform.final_action_gate import FinalActionGateStore
from xmuse_core.platform.state_normalizer import summarize_lane_states

PROJECT_ROOT = Path(__file__).resolve().parents[1]
XMUSE_ROOT = PROJECT_ROOT / "xmuse"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def process_lines() -> list[str]:
    result = subprocess.run(
        ["pgrep", "-af", "xmuse/(mcp_server|platform_runner)|codex exec"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def git_diff_summary(repo_root: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["git", "diff", "--stat", "--", "xmuse", "src/xmuse_core", "docs/superpowers", "tests"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return {
        "available": result.returncode == 0,
        "stat": result.stdout.strip().splitlines()[-30:] if result.returncode == 0 else [],
        "error": result.stderr.strip() if result.returncode != 0 else "",
    }


def newest(collection_path: Path, key: str) -> dict[str, Any] | None:
    data = read_json(collection_path, {key: []})
    rows = data.get(key, []) if isinstance(data, dict) else []
    if not isinstance(rows, list) or not rows:
        return None
    last = rows[-1]
    return last if isinstance(last, dict) else None


def newest_checkpoint(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    last_line = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            last_line = line
    if not last_line:
        return None
    payload = json.loads(last_line)
    return payload if isinstance(payload, dict) else None


def generated_artifacts(xmuse_root: Path, graph_id: str | None) -> list[str]:
    refs = [
        "feature_lanes.json",
        "self_evolution/run_aggregations.json",
        "self_evolution/evidence_bundles.json",
        "self_evolution/proposals.json",
        "self_evolution/review_decisions.json",
        "self_evolution/guardrail_decisions.json",
        "self_evolution/lineage.json",
        "self_evolution/checkpoints.jsonl",
    ]
    if graph_id:
        refs.append(f"lane_graphs/{graph_id}.json")
    return [ref for ref in refs if (xmuse_root / ref).exists()]


def latest_verification(xmuse_root: Path) -> dict[str, Any] | None:
    payload = read_json(xmuse_root / "self_evolution" / "latest_verification.json", None)
    return payload if isinstance(payload, dict) else None


def elapsed_window(
    *,
    now: datetime,
    latest_budget_window: dict[str, Any] | None,
    latest_proposal: dict[str, Any] | None,
) -> dict[str, Any] | None:
    source = "budget_window"
    started_at = (
        latest_budget_window.get("started_at")
        if latest_budget_window is not None
        else None
    )
    expires_at = (
        latest_budget_window.get("expires_at")
        if latest_budget_window is not None
        else None
    )
    if started_at is None and latest_proposal is not None:
        source = "proposal"
        started_at = latest_proposal.get("created_at")
    started = parse_utc(started_at)
    expires = parse_utc(expires_at)
    if started is None:
        return None
    elapsed_seconds = max(0, int((now - started).total_seconds()))
    remaining_seconds = (
        max(0, int((expires - now).total_seconds())) if expires is not None else None
    )
    return {
        "source": source,
        "started_at": started_at,
        "expires_at": expires_at,
        "elapsed_seconds": elapsed_seconds,
        "remaining_seconds": remaining_seconds,
    }


def lane_snapshot(lane: dict[str, Any], now_epoch: float) -> dict[str, Any]:
    dispatched_at = lane.get("dispatched_at")
    dispatched_age_s = None
    if isinstance(dispatched_at, int | float):
        dispatched_age_s = max(0, round(now_epoch - float(dispatched_at), 1))
    return {
        "feature_id": lane.get("feature_id"),
        "source_lane_id": lane.get("source_lane_id"),
        "status": lane.get("status"),
        "normalized_state_fields": {
            "failure_reason": lane.get("failure_reason"),
            "review_decision": lane.get("review_decision"),
            "gate_passed": lane.get("gate_passed"),
            "retry_count": lane.get("retry_count"),
            "review_retry_count": lane.get("review_retry_count"),
        },
        "dispatched_age_s": dispatched_age_s,
    }


def build_checkpoint(xmuse_root: Path, incident_level: str, next_action: str) -> dict[str, Any]:
    now = datetime.now(UTC).replace(microsecond=0)
    lanes = read_json(xmuse_root / "feature_lanes.json", {"lanes": []}).get("lanes", [])
    lanes = [lane for lane in lanes if isinstance(lane, dict)]
    self_evolution_root = xmuse_root / "self_evolution"
    latest_lineage = newest(self_evolution_root / "lineage.json", "lineage")
    latest_aggregation = newest(self_evolution_root / "run_aggregations.json", "aggregations")
    latest_proposal = newest(self_evolution_root / "proposals.json", "proposals")
    latest_guardrail = newest(
        self_evolution_root / "guardrail_decisions.json",
        "guardrail_decisions",
    )
    latest_review = newest(self_evolution_root / "review_decisions.json", "review_decisions")
    latest_evidence = newest(self_evolution_root / "evidence_bundles.json", "evidence_bundles")
    latest_budget_window = newest(self_evolution_root / "budget_windows.json", "budget_windows")
    final_actions = [
        hold.model_dump(mode="json")
        for hold in FinalActionGateStore(xmuse_root / "final_actions.json").list_actions()
        if hold.status == "pending"
    ]
    spawned_resolution_id = (
        latest_lineage.get("spawned_resolution_id") if latest_lineage is not None else None
    )
    spawned_graph_id = (
        latest_lineage.get("spawned_graph_id") if latest_lineage is not None else None
    )
    related_lanes = [
        lane for lane in lanes
        if lane.get("resolution_id") == spawned_resolution_id
        or lane.get("graph_id") == spawned_graph_id
    ]
    now_epoch = now.timestamp()
    return {
        "checkpoint_schema_version": 2,
        "timestamp": now.isoformat().replace("+00:00", "Z"),
        "incident_level": incident_level,
        "elapsed_window": elapsed_window(
            now=now,
            latest_budget_window=latest_budget_window,
            latest_proposal=latest_proposal,
        ),
        "current_run_id": spawned_graph_id,
        "source_run_id": latest_lineage.get("source_run_id") if latest_lineage else None,
        "resolution_id": spawned_resolution_id,
        "graph_id": spawned_graph_id,
        "spawned_links": {
            "conversation_id": (
                latest_lineage.get("spawned_conversation_id") if latest_lineage else None
            ),
            "proposal_id": (
                latest_lineage.get("spawned_proposal_id") if latest_lineage else None
            ),
            "resolution_id": spawned_resolution_id,
            "graph_id": spawned_graph_id,
        },
        "lane_counts": summarize_lane_states(related_lanes),
        "lane_snapshots": [lane_snapshot(lane, now_epoch) for lane in related_lanes],
        "open_lane_lineages": [
            {
                "feature_id": lane.get("feature_id"),
                "source_lane_id": lane.get("source_lane_id"),
                "status": lane.get("status"),
            }
            for lane in related_lanes
            if lane.get("status") not in {"merged", "failed", "done"}
        ],
        "newest_verdict": latest_review,
        "open_final_action_holds": final_actions,
        "open_blocked_objects": (
            latest_aggregation.get("blocked_objects", []) if latest_aggregation else []
        ),
        "newest_self_evolution_proposal": latest_proposal,
        "guardrail_decision": latest_guardrail,
        "evidence_bundle_id": latest_evidence.get("bundle_id") if latest_evidence else None,
        "latest_test_or_smoke_result": latest_verification(xmuse_root),
        "generated_artifacts": generated_artifacts(xmuse_root, spawned_graph_id),
        "notable_git_diff": git_diff_summary(xmuse_root.parent),
        "processes": process_lines(),
        "next_action": next_action,
    }


def append_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(checkpoint, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Write one xmuse self-evolution checkpoint")
    parser.add_argument("--xmuse-root", type=Path, default=XMUSE_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--incident-level", default="watch", choices=["watch", "recover", "stop"])
    parser.add_argument("--next-action", default="continue monitoring self-evolution run")
    args = parser.parse_args()

    output = args.output or args.xmuse_root / "self_evolution" / "checkpoints.jsonl"
    previous_checkpoint = newest_checkpoint(output)
    checkpoint = build_checkpoint(args.xmuse_root, args.incident_level, args.next_action)
    previous_timestamp = (
        previous_checkpoint.get("timestamp") if previous_checkpoint is not None else None
    )
    previous_time = parse_utc(previous_timestamp)
    current_time = parse_utc(checkpoint["timestamp"])
    checkpoint["monitoring_gap_seconds"] = (
        int((current_time - previous_time).total_seconds())
        if current_time is not None and previous_time is not None
        else None
    )
    append_checkpoint(output, checkpoint)
    print(json.dumps(checkpoint, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
