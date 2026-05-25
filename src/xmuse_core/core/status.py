from __future__ import annotations

from collections.abc import Callable
from typing import Any

from xmuse_core.core.schema import (
    FEATURE_LOCAL_ACTIVE_STATES,
    MASTER_BLOCKED_STATES,
    MASTER_HELD_STATES,
    MASTER_QUEUE_NAMES,
    MERGE_REQUEST_STATES,
    STATE_RANK,
)

MergeGateValidator = Callable[[dict[str, Any]], dict[str, Any]]


def _empty_master_queues() -> dict[str, list[str]]:
    return {name: [] for name in sorted(MASTER_QUEUE_NAMES)}


def derive_master_queues(
    master_state: dict[str, Any],
    *,
    merge_gate_validator: MergeGateValidator | None = None,
    missing_validator_reason: str = "merge_gate_validator is required",
) -> dict[str, Any]:
    queues = _empty_master_queues()
    errors: list[str] = []

    for feature in master_state.get("features", []):
        feature_id = feature["id"]
        state = feature.get("state")
        merge_status = feature.get("merge", {}).get("status", state)

        if STATE_RANK.get(merge_status, 99) > STATE_RANK.get(state, -1) and state not in {
            "ready_for_merge",
            "merge_requested",
        }:
            queues["blocked"].append(feature_id)
            errors.append(
                f"merge.status {merge_status} is ahead of feature.state {state} for {feature_id}"
            )
            continue

        if state == "planned":
            queues["planning_queue"].append(feature_id)
        elif state in FEATURE_LOCAL_ACTIVE_STATES:
            queues["active_lanes"].append(feature_id)
        elif state == "ready_for_master_review":
            queues["master_review_queue"].append(feature_id)
        elif state in MERGE_REQUEST_STATES:
            if merge_gate_validator is None:
                queues["blocked"].append(feature_id)
                errors.append(f"merge gate failed for {feature_id}: {missing_validator_reason}")
                continue
            gate = merge_gate_validator(feature)
            if gate["valid"]:
                queues["merge_queue"].append(feature_id)
            else:
                queues["blocked"].append(feature_id)
                errors.append(f"merge gate failed for {feature_id}: " + "; ".join(gate["errors"]))
        elif state in MASTER_HELD_STATES:
            queues["held"].append(feature_id)
        elif state == "merged":
            queues["merged"].append(feature_id)
        elif state in MASTER_BLOCKED_STATES:
            queues["blocked"].append(feature_id)
        else:
            queues["blocked"].append(feature_id)
            errors.append(f"unknown feature state for {feature_id}: {state}")

    counts = {
        "total": len(master_state.get("features", [])),
        "reviewable": len(queues["master_review_queue"]),
        "mergeable": len(queues["merge_queue"]),
        "held": len(queues["held"]),
        "blocked": len(queues["blocked"]),
        "merged": len(queues["merged"]),
    }
    return {"queues": queues, "counts": counts, "errors": errors}


def build_master_status(
    master_state: dict[str, Any],
    *,
    merge_gate_validator: MergeGateValidator | None = None,
    missing_validator_reason: str = "merge_gate_validator is required",
) -> dict[str, Any]:
    derived = derive_master_queues(
        master_state,
        merge_gate_validator=merge_gate_validator,
        missing_validator_reason=missing_validator_reason,
    )
    return {
        "version": "1.0",
        "source": "xmuse/master_state.json",
        "activation_state": master_state.get("activation_state"),
        "counts": derived["counts"],
        "queues": derived["queues"],
        "errors": derived["errors"],
    }


def master_status_markdown(status: dict[str, Any]) -> str:
    lines = [
        "# Hermes Master Status",
        "",
        f"- activation_state: {status['activation_state']}",
        f"- total: {status['counts']['total']}",
        f"- reviewable: {status['counts']['reviewable']}",
        f"- mergeable: {status['counts']['mergeable']}",
        f"- held: {status['counts']['held']}",
        f"- blocked: {status['counts']['blocked']}",
        f"- merged: {status['counts']['merged']}",
        "",
    ]
    return "\n".join(lines)
