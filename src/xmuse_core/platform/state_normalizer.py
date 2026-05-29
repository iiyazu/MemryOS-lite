"""Normalize legacy xmuse lane states for session-first consumers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NormalizedLaneState:
    feature_id: str
    raw_status: str
    normalized_status: str
    is_terminal: bool


_STATUS_MAP: dict[str, str] = {
    "pending": "ready",
    "dispatched": "dispatched",
    "executed": "executed",
    "gated": "under_review",
    "reviewed": "reviewed",
    "awaiting_final_action": "awaiting_final_action",
    "merged": "merged",
    "done": "merged",
    "completed": "merged",
    "rejected": "requeued",
    "reworking": "requeued",
    "exec_failed": "exec_failed",
    "gate_failed": "gate_failed",
    "aborted": "terminated",
}

_TERMINAL_STATUSES = {"merged", "terminated", "exec_failed", "gate_failed"}
RAW_LANE_STATUSES = frozenset(_STATUS_MAP) | {"failed"}
_RESERVED_SUMMARY_KEYS = {"total", "terminal"}


def _summary_bucket_name(normalized_status: str) -> str:
    if normalized_status in _RESERVED_SUMMARY_KEYS:
        return f"status_{normalized_status}"
    return normalized_status


def normalize_lane_state(lane: dict[str, Any]) -> NormalizedLaneState:
    raw_status = str(lane.get("status") or "pending")
    failure_reason = lane.get("failure_reason")

    if raw_status == "gate_failed" and failure_reason == "review_infra_unavailable":
        normalized_status = "review_infra_unavailable"
        is_terminal = False
    elif raw_status == "failed":
        normalized_status = (
            failure_reason if isinstance(failure_reason, str) else "terminated"
        )
        is_terminal = True
    else:
        normalized_status = _STATUS_MAP.get(raw_status, raw_status)
        is_terminal = normalized_status in _TERMINAL_STATUSES

    return NormalizedLaneState(
        feature_id=str(lane.get("feature_id") or ""),
        raw_status=raw_status,
        normalized_status=normalized_status,
        is_terminal=is_terminal,
    )


def summarize_lane_states(lanes: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {"total": len(lanes), "terminal": 0}

    for lane in lanes:
        normalized_lane = normalize_lane_state(lane)
        bucket_name = _summary_bucket_name(normalized_lane.normalized_status)
        summary[bucket_name] = summary.get(bucket_name, 0) + 1
        if normalized_lane.is_terminal:
            summary["terminal"] += 1

    return summary
