from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from xmuse_core.structuring.models import LaneGraph, LaneNode

_COMPLETED_STATUSES = {"merged", "done", "completed"}


def project_ready_lanes(graph: LaneGraph, lanes_path: Path | str) -> list[dict[str, Any]]:
    path = Path(lanes_path)
    data = _read_lanes(path)
    existing = [
        lane for lane in data.get("lanes", [])
        if isinstance(lane, dict) and isinstance(lane.get("feature_id"), str)
    ]
    existing_ids = {str(lane["feature_id"]) for lane in existing}
    completed_ids = {
        str(lane["feature_id"])
        for lane in existing
        if lane.get("status") in _COMPLETED_STATUSES
    }

    projected: list[dict[str, Any]] = []
    for node in graph.lanes:
        if node.feature_id in existing_ids:
            continue
        if not _is_dependency_ready(node, completed_ids):
            continue
        payload = _lane_payload(graph, node)
        existing.append(payload)
        existing_ids.add(node.feature_id)
        projected.append(payload)

    data["lanes"] = existing
    _write_lanes(path, data)
    return projected


def _is_dependency_ready(node: LaneNode, completed_ids: set[str]) -> bool:
    return all(dep in completed_ids for dep in node.depends_on)


def _lane_payload(graph: LaneGraph, node: LaneNode) -> dict[str, Any]:
    return {
        "feature_id": node.feature_id,
        "task_type": node.task_type,
        "status": "pending",
        "prompt": node.prompt,
        "capabilities": list(node.capabilities),
        "priority": node.priority,
        "depends_on": list(node.depends_on),
        "conversation_id": graph.conversation_id,
        "resolution_id": graph.resolution_id,
        "graph_id": graph.id,
        "graph_version": graph.version,
        **({"gate_profile": node.gate_profile} if node.gate_profile else {}),
        **({"gate_profiles": list(node.gate_profiles)} if node.gate_profiles else {}),
        **({"source_lane_id": node.source_lane_id} if node.source_lane_id else {}),
        **({"feature_group": node.feature_group} if node.feature_group else {}),
    }


def _read_lanes(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"lanes": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_lanes(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
