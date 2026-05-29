from __future__ import annotations

from typing import Any

from xmuse_core.structuring.models import LaneGraph, LaneNode


def build_lane_graph(resolution: Any) -> LaneGraph:
    lanes_payload = _extract_lanes_payload(resolution)
    if not lanes_payload:
        lanes = [
            LaneNode(
                feature_id=f"{resolution.id}-lane-1",
                prompt=str(getattr(resolution, "goal_summary", "")).strip() or resolution.id,
            )
        ]
    else:
        lanes = [LaneNode(**_normalize_lane_payload(item)) for item in lanes_payload]

    return LaneGraph(
        id=f"{resolution.id}-graph-v{resolution.version}",
        conversation_id=resolution.conversation_id,
        resolution_id=resolution.id,
        version=resolution.version,
        status="planned",
        lanes=lanes,
    )


def _extract_lanes_payload(resolution: Any) -> list[dict[str, Any]]:
    content = getattr(resolution, "content", None)
    if isinstance(content, dict):
        lanes = content.get("lanes", [])
        if isinstance(lanes, list):
            return [item for item in lanes if isinstance(item, dict)]
    return []


def _normalize_lane_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized.setdefault("prompt", normalized.get("title") or normalized.get("feature_id", "lane"))
    normalized.setdefault("priority", 0)
    normalized.setdefault("capabilities", ["code"])
    normalized.setdefault("depends_on", [])
    normalized.setdefault("task_type", "execute")
    normalized.setdefault("feature_group", None)
    return normalized
