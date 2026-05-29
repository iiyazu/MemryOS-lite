#!/usr/bin/env python3
"""REST API for the Xmuse dashboard frontend."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from xmuse_core.platform.final_action_gate import FinalActionGateStore
from xmuse_core.platform.state_normalizer import (
    normalize_lane_state,
    summarize_lane_states,
)
from xmuse_core.self_evolution.audit_writer import SelfEvolutionAuditWriter

DEFAULT_PORT = 8200
DEFAULT_BASE_DIR = Path(__file__).resolve().parent


class LaneCreate(BaseModel):
    model_config = ConfigDict(extra="allow")

    feature_id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    task_type: str = "execute"
    status: str = "pending"
    capabilities: list[str] = Field(default_factory=lambda: ["code"])


class LaneReject(BaseModel):
    reason: str | None = None
    rework: bool = False


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_path(base_dir: Path, name: str) -> Path:
    return base_dir / name


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"invalid JSON in {path.name}: {exc.msg}",
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"could not read {path.name}: {exc}",
        ) from exc


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _load_lanes(base_dir: Path) -> dict[str, Any]:
    data = _read_json(_json_path(base_dir, "feature_lanes.json"), {"lanes": []})
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="feature_lanes.json must contain an object")
    lanes = data.setdefault("lanes", [])
    if not isinstance(lanes, list):
        raise HTTPException(status_code=500, detail="feature_lanes.json lanes must be a list")
    return data


def _lane_with_status(lane: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(lane)
    state = normalize_lane_state(normalized)
    normalized["status"] = state.raw_status
    normalized["effective_status"] = state.normalized_status
    return normalized


def _find_lane(data: dict[str, Any], feature_id: str) -> dict[str, Any]:
    for lane in data.get("lanes", []):
        if isinstance(lane, dict) and lane.get("feature_id") == feature_id:
            return lane
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lane not found")


def _log_entries(base_dir: Path, feature_id: str) -> list[dict[str, str]]:
    logs_dir = base_dir / "logs"
    if not logs_dir.exists():
        return []

    entries: list[dict[str, str]] = []
    for path in sorted(p for p in logs_dir.rglob("*") if p.is_file()):
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if feature_id not in path.name and feature_id not in content:
            continue
        entries.append(
            {
                "path": path.relative_to(base_dir).as_posix(),
                "content": content,
            }
        )
    return entries


def _read_sessions(base_dir: Path) -> list[Any]:
    data = _read_json(_json_path(base_dir, "active_sessions.json"), {"sessions": []})
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        sessions = data.get("sessions", [])
        if isinstance(sessions, list):
            return sessions
        if isinstance(sessions, dict):
            normalized: list[Any] = []
            for feature_id, session in sessions.items():
                if isinstance(session, dict):
                    normalized.append({"feature_id": feature_id, **session})
            return normalized
        return []
    return []


def _read_errors(base_dir: Path) -> list[Any]:
    data = _read_json(_json_path(base_dir, "error_knowledge.json"), {"entries": []})
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("entries", "errors"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def _duration_seconds(lane: dict[str, Any]) -> float | None:
    duration = lane.get("duration_seconds")
    if isinstance(duration, int | float):
        return float(duration)

    started = _parse_timestamp(lane.get("started_at"))
    completed = _parse_timestamp(lane.get("completed_at") or lane.get("finished_at"))
    if started is None or completed is None:
        return None
    return max(0.0, (completed - started).total_seconds())


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _read_model_entries(base_dir: Path, file_name: str, key: str) -> list[Any]:
    data = _read_json(base_dir / "read_models" / file_name, {key: []})
    if not isinstance(data, dict):
        return []
    entries = data.get(key, [])
    return entries if isinstance(entries, list) else []


def _read_audit_events(
    base_dir: Path,
    *,
    event_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict[str, Any]]:
    """Load and filter audit events from ``audit_events.json``.

    Each event is expected to have at minimum:
    - ``event_id``: unique identifier
    - ``event_type``: string classifier (e.g. ``"lane.created"``)
    - ``timestamp``: ISO-8601 UTC string
    - ``metadata``: arbitrary dict of additional context

    Events that are missing a ``timestamp`` field are included unless a date
    range filter is active, in which case they are excluded.
    """
    data = _read_json(_json_path(base_dir, "audit_events.json"), {"events": []})
    if not isinstance(data, dict):
        return []
    raw = data.get("events", [])
    if not isinstance(raw, list):
        return []

    results: list[dict[str, Any]] = []
    for event in raw:
        if not isinstance(event, dict):
            continue

        # --- event_type filter ---
        if event_type is not None and event.get("event_type") != event_type:
            continue

        # --- date range filter ---
        if since is not None or until is not None:
            ts = _parse_timestamp(event.get("timestamp"))
            if ts is None:
                # No parseable timestamp – exclude when a range is requested
                continue
            if since is not None and ts < since:
                continue
            if until is not None and ts > until:
                continue

        results.append(event)

    return results


def _read_state_history(
    base_dir: Path,
    *,
    lane_id: str | None = None,
    state_key: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict[str, Any]]:
    """Load and filter state snapshots from ``state_history.json``.

    Each snapshot is expected to have at minimum:
    - ``snapshot_id``: unique identifier
    - ``lane_id``: the lane this snapshot belongs to
    - ``state_key``: the state value at the time of the snapshot (e.g. ``"dispatched"``)
    - ``timestamp``: ISO-8601 UTC string
    - ``metadata``: arbitrary dict of additional context

    Snapshots missing a ``timestamp`` are included unless a date range filter is
    active, in which case they are excluded.
    """
    data = _read_json(_json_path(base_dir, "state_history.json"), {"snapshots": []})
    if not isinstance(data, dict):
        return []
    raw = data.get("snapshots", [])
    if not isinstance(raw, list):
        return []

    results: list[dict[str, Any]] = []
    for snapshot in raw:
        if not isinstance(snapshot, dict):
            continue

        if lane_id is not None and snapshot.get("lane_id") != lane_id:
            continue

        if state_key is not None and snapshot.get("state_key") != state_key:
            continue

        if since is not None or until is not None:
            ts = _parse_timestamp(snapshot.get("timestamp"))
            if ts is None:
                continue
            if since is not None and ts < since:
                continue
            if until is not None and ts > until:
                continue

        results.append(snapshot)

    return results


def _read_lineage_records(base_dir: Path) -> list[dict[str, Any]]:
    """Load raw lineage records from ``self_evolution/lineage.json``."""
    data = _read_json(base_dir / "self_evolution" / "lineage.json", {"lineage": []})
    if not isinstance(data, dict):
        return []
    raw = data.get("lineage", [])
    return [r for r in raw if isinstance(r, dict)]


def _read_run_aggregations(base_dir: Path) -> list[dict[str, Any]]:
    data = _read_json(
        base_dir / "self_evolution" / "run_aggregations.json",
        {"aggregations": []},
    )
    if not isinstance(data, dict):
        return []
    raw = data.get("aggregations", [])
    return [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []


def _record_timestamp(record: dict[str, Any]) -> datetime:
    parsed = _parse_timestamp(record.get("created_at"))
    if parsed is None:
        return datetime.min.replace(tzinfo=UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _aggregation_status(aggregation: dict[str, Any] | None, *, default: str) -> str:
    if aggregation is None:
        return default
    status_value = aggregation.get("status")
    if not isinstance(status_value, str) or not status_value:
        return "unknown"
    if status_value == "in_progress":
        return "running"
    return status_value


def _aggregation_terminal(aggregation: dict[str, Any] | None) -> bool:
    if aggregation is None:
        return False
    terminal = aggregation.get("terminal")
    if isinstance(terminal, bool):
        return terminal
    return _aggregation_status(aggregation, default="unknown") in {
        "merged",
        "terminated",
        "blocked_for_input",
    }


def _aggregation_summary(aggregation: dict[str, Any] | None) -> dict[str, Any] | None:
    if aggregation is None:
        return None
    return {
        "aggregation_id": aggregation.get("aggregation_id"),
        "run_id": aggregation.get("run_id"),
        "resolution_id": aggregation.get("resolution_id"),
        "graph_id": aggregation.get("graph_id"),
        "status": _aggregation_status(aggregation, default="unknown"),
        "terminal": _aggregation_terminal(aggregation),
        "reason": aggregation.get("reason"),
        "created_at": aggregation.get("created_at"),
    }


def _read_lane_graph(base_dir: Path, graph_id: str | None) -> dict[str, Any] | None:
    if not graph_id:
        return None
    path = base_dir / "lane_graphs" / f"{graph_id}.json"
    if not path.exists():
        return None
    data = _read_json(path, {})
    return data if isinstance(data, dict) else None


def _graph_lane_ids(graph: dict[str, Any] | None) -> list[str]:
    if graph is None:
        return []
    lanes = graph.get("lanes", [])
    if not isinstance(lanes, list):
        return []
    lane_ids: list[str] = []
    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        feature_id = lane.get("feature_id")
        if isinstance(feature_id, str) and feature_id:
            lane_ids.append(feature_id)
    return lane_ids


def _lineage_lane_ids(
    graph_lane_ids: list[str],
    lane_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    ordered = list(graph_lane_ids)
    seen = set(ordered)
    changed = True
    while changed:
        changed = False
        for lane_id, lane in lane_by_id.items():
            source_lane_id = lane.get("source_lane_id")
            if source_lane_id in seen and lane_id not in seen:
                ordered.append(lane_id)
                seen.add(lane_id)
                changed = True
    return ordered


def _merge_verdict_lane_ids(base_dir: Path) -> set[str]:
    data = _read_json(base_dir / "review_plane.json", {"review_verdicts": []})
    if not isinstance(data, dict):
        return set()
    verdicts = data.get("review_verdicts", [])
    if not isinstance(verdicts, list):
        return set()
    lane_ids: set[str] = set()
    for verdict in verdicts:
        if not isinstance(verdict, dict):
            continue
        lane_id = verdict.get("lane_id")
        if (
            isinstance(lane_id, str)
            and str(verdict.get("decision", "")).lower() == "merge"
            and str(verdict.get("status", "finalized")).lower() == "finalized"
        ):
            lane_ids.add(lane_id)
    return lane_ids


def _lane_has_merge_verdict(
    lane_id: str,
    lane: dict[str, Any] | None,
    merge_verdict_lane_ids: set[str],
) -> bool:
    if lane_id in merge_verdict_lane_ids:
        return True
    if lane is None:
        return False
    return str(lane.get("review_decision", "")).lower() == "merge"


def _blocked_object_for_lane(lane: dict[str, Any]) -> dict[str, Any] | None:
    clarification = lane.get("clarification_request")
    if isinstance(clarification, dict):
        return {
            "lane_id": lane.get("feature_id"),
            "missing_input": clarification.get("missing_input", "unspecified"),
            "owner": clarification.get("owner", "human"),
            "resume_path": clarification.get(
                "resume_path",
                "provide information and reproject graph",
            ),
        }
    if lane.get("status") == "blocked_for_input":
        return {
            "lane_id": lane.get("feature_id"),
            "missing_input": lane.get("missing_input", "unspecified"),
            "owner": lane.get("input_owner", "human"),
            "resume_path": lane.get("resume_path", "provide information and resume lane"),
        }
    return None


def _final_action_hold_for_lane(lane: dict[str, Any]) -> dict[str, Any] | None:
    if lane.get("status") != "awaiting_final_action":
        return None
    hold: dict[str, Any] = {
        "lane_id": lane.get("feature_id"),
        "action": lane.get("final_action", "merge"),
        "verdict_id": lane.get("review_verdict_id"),
    }
    if lane.get("review_summary"):
        hold["summary"] = str(lane["review_summary"])[:160]
    return hold


def _derived_graph_state(base_dir: Path, graph_id: str | None) -> dict[str, Any] | None:
    """Compute current graph state from the authoritative lane graph and lanes.

    Stored run aggregations can lag the dashboard while a graph is still moving.
    This mirrors the self-evolution aggregation rules closely enough for health:
    lane graph membership is authoritative, ``source_lane_id`` descendants are
    part of the same lineage, and terminal failures without merge verdicts keep
    the graph in merge-coordination pending instead of silently terminalizing.
    """
    graph = _read_lane_graph(base_dir, graph_id)
    if graph is None:
        return None

    lane_data = _load_lanes(base_dir)
    lanes = [lane for lane in lane_data["lanes"] if isinstance(lane, dict)]
    lane_by_id = {
        str(lane["feature_id"]): lane
        for lane in lanes
        if isinstance(lane.get("feature_id"), str) and lane.get("feature_id")
    }
    lineage_ids = _lineage_lane_ids(_graph_lane_ids(graph), lane_by_id)
    merge_verdict_lane_ids = _merge_verdict_lane_ids(base_dir)

    lane_statuses: list[dict[str, Any]] = []
    blocked_objects: list[dict[str, Any]] = []
    final_action_holds: list[dict[str, Any]] = []
    merged_lineages: list[str] = []
    failed_lineages: list[str] = []
    open_lane_lineages: list[str] = []
    unmerged_terminal_lineages: list[str] = []

    for lane_id in lineage_ids:
        lane = lane_by_id.get(lane_id)
        if lane is None:
            lane_statuses.append(
                {
                    "feature_id": lane_id,
                    "raw_status": "unprojected",
                    "normalized_status": "waiting_dependency",
                    "terminal": False,
                }
            )
            open_lane_lineages.append(lane_id)
            continue

        normalized = normalize_lane_state(lane)
        has_merge_verdict = _lane_has_merge_verdict(
            lane_id,
            lane,
            merge_verdict_lane_ids,
        )
        lane_status = {
            "feature_id": lane_id,
            "raw_status": normalized.raw_status,
            "normalized_status": normalized.normalized_status,
            "terminal": normalized.is_terminal,
            "has_merge_verdict": has_merge_verdict,
        }
        lane_statuses.append(lane_status)

        blocked = _blocked_object_for_lane(lane)
        if blocked is not None and not normalized.is_terminal:
            blocked_objects.append(blocked)
        hold = _final_action_hold_for_lane(lane)
        if hold is not None:
            final_action_holds.append(hold)

        if not normalized.is_terminal:
            open_lane_lineages.append(lane_id)
        elif normalized.normalized_status == "merged" or has_merge_verdict:
            merged_lineages.append(lane_id)
        else:
            failed_lineages.append(lane_id)
            unmerged_terminal_lineages.append(lane_id)

    present_lanes = [lane_by_id[lane_id] for lane_id in lineage_ids if lane_id in lane_by_id]
    lane_counts = summarize_lane_states(present_lanes)

    if blocked_objects:
        merge_state = "blocked_for_input"
        terminal = True
        reason = "one or more lanes request clarification"
        graph_lineage_status = "blocked_for_input"
    elif not lane_statuses:
        merge_state = "running"
        terminal = False
        reason = "no graph lanes have been projected yet"
        graph_lineage_status = "open"
    elif final_action_holds:
        merge_state = "running"
        terminal = False
        reason = "one or more lanes are awaiting final-action approval"
        graph_lineage_status = "awaiting_final_action"
    elif open_lane_lineages:
        merge_state = "running"
        terminal = False
        reason = "at least one graph lineage lane is not terminal"
        graph_lineage_status = "open"
    elif all(item["normalized_status"] == "merged" for item in lane_statuses):
        merge_state = "merged"
        terminal = True
        reason = "all graph lineage lanes merged"
        graph_lineage_status = "merged"
    elif unmerged_terminal_lineages:
        merge_state = "running"
        terminal = False
        reason = "graph lineage merge coordination pending"
        graph_lineage_status = "incomplete_termination"
    else:
        merge_state = "terminated"
        terminal = True
        reason = "at least one graph lineage terminalized without merge"
        graph_lineage_status = "terminated"

    return {
        "source": "lane_graph",
        "status": merge_state,
        "terminal": terminal,
        "reason": reason,
        "graph_lineage_status": graph_lineage_status,
        "lane_counts": lane_counts,
        "lane_statuses": lane_statuses,
        "open_lane_lineages": open_lane_lineages,
        "failed_lineages": failed_lineages,
        "merged_lineages": merged_lineages,
        "unmerged_terminal_lineages": unmerged_terminal_lineages,
        "blocked_objects": blocked_objects,
        "final_action_holds": final_action_holds,
    }


def _latest_aggregation_for_graph(
    aggregations: list[dict[str, Any]],
    graph_id: str | None,
) -> dict[str, Any] | None:
    if not graph_id:
        return None
    matches = [
        aggregation
        for aggregation in aggregations
        if aggregation.get("graph_id") == graph_id or aggregation.get("run_id") == graph_id
    ]
    if not matches:
        return None
    return sorted(matches, key=_record_timestamp)[-1]


def _aggregation_by_id(
    aggregations: list[dict[str, Any]],
    aggregation_id: str | None,
) -> dict[str, Any] | None:
    if not aggregation_id:
        return None
    for aggregation in aggregations:
        if aggregation.get("aggregation_id") == aggregation_id:
            return aggregation
    return None


def _build_lineage_graph(
    records: list[dict[str, Any]],
    *,
    from_node: str | None = None,
    depth: int | None = None,
) -> dict[str, Any]:
    """Build a graph representation of execution lineage records.

    Each node represents a run or graph identified by its ``source_run_id`` or
    ``spawned_graph_id``.  Each edge represents one ``EvolutionLineageRecord``
    linking a source run to a spawned graph.

    Merge points are nodes that appear as the target of more than one edge
    (i.e. multiple lineage records converge on the same ``spawned_graph_id``).

    Parameters
    ----------
    records:
        Raw lineage record dicts loaded from the store.
    from_node:
        If provided, only nodes reachable from this node ID are included.
        The node ID may be a ``source_run_id`` or ``spawned_graph_id``.
    depth:
        Maximum traversal depth from ``from_node``.  ``None`` means unlimited.
        Ignored when ``from_node`` is ``None``.
    """
    # Build adjacency: source_run_id -> list of spawned_graph_id
    adjacency: dict[str, list[str]] = {}
    # Collect all node IDs and edge metadata
    edges: list[dict[str, Any]] = []
    node_ids: set[str] = set()

    for rec in records:
        src = rec.get("source_run_id")
        dst = rec.get("spawned_graph_id")
        if not src or not dst:
            continue
        node_ids.add(src)
        node_ids.add(dst)
        adjacency.setdefault(src, []).append(dst)
        edges.append(
            {
                "lineage_id": rec.get("lineage_id"),
                "source_node": src,
                "target_node": dst,
                "blueprint_set_id": rec.get("blueprint_set_id"),
                "target_track_ids": rec.get("target_track_ids", []),
                "evolution_proposal_id": rec.get("evolution_proposal_id"),
                "guardrail_decision_id": rec.get("guardrail_decision_id"),
                "created_at": rec.get("created_at"),
            }
        )

    # Identify merge points: nodes with in-degree > 1
    in_degree: dict[str, int] = {n: 0 for n in node_ids}
    for edge in edges:
        in_degree[edge["target_node"]] = in_degree.get(edge["target_node"], 0) + 1
    merge_points = [n for n, deg in in_degree.items() if deg > 1]

    # If from_node is given, restrict to reachable nodes via BFS
    if from_node is not None:
        reachable: set[str] = set()
        queue: list[tuple[str, int]] = [(from_node, 0)]
        while queue:
            current, current_depth = queue.pop(0)
            if current in reachable:
                continue
            reachable.add(current)
            if depth is not None and current_depth >= depth:
                continue
            for neighbor in adjacency.get(current, []):
                if neighbor not in reachable:
                    queue.append((neighbor, current_depth + 1))
        node_ids = node_ids & reachable
        edges = [
            e
            for e in edges
            if e["source_node"] in reachable and e["target_node"] in reachable
        ]
        merge_points = [n for n in merge_points if n in reachable]

    # Build node list with metadata from records
    # Prefer the most recent record for each node's metadata
    node_meta: dict[str, dict[str, Any]] = {}
    for rec in records:
        src = rec.get("source_run_id")
        dst = rec.get("spawned_graph_id")
        if src and src in node_ids:
            if src not in node_meta:
                node_meta[src] = {
                    "node_id": src,
                    "node_type": "run",
                    "is_merge_point": src in merge_points,
                }
        if dst and dst in node_ids:
            node_meta[dst] = {
                "node_id": dst,
                "node_type": "graph",
                "is_merge_point": dst in merge_points,
                "spawned_at": rec.get("created_at"),
                "blueprint_set_id": rec.get("blueprint_set_id"),
                "target_track_ids": rec.get("target_track_ids", []),
            }

    nodes = sorted(node_meta.values(), key=lambda n: n["node_id"])

    return {
        "nodes": nodes,
        "edges": edges,
        "merge_points": merge_points,
        "total_nodes": len(nodes),
        "total_edges": len(edges),
    }


def _graph_authority_state(base_dir: Path) -> dict[str, Any]:
    """Derive graph authority state from lineage and aggregation records.

    Returns a dict with:
    - ``authoritative_graph_id``: most-recently spawned graph ID, or None
    - ``merge_state``: actual state of that spawned graph's latest aggregation
    - ``lineage_terminated``: True when the latest lineage source run's
      terminal aggregation is terminal
    - ``lineage_status``: status from the lineage source terminal aggregation
    - ``open_lineage_count``: number of lineage records whose spawned graph has
      no terminal aggregation
    - ``latest_run_id``: source_run_id of the most-recent lineage record, or None
    - ``latest_lineage_id``: lineage_id of the most-recent record, or None
    """
    records = _read_lineage_records(base_dir)
    aggregations = _read_run_aggregations(base_dir)

    if not records:
        return {
            "authoritative_graph_id": None,
            "merge_state": "unknown",
            "lineage_terminated": False,
            "lineage_status": "unknown",
            "open_lineage_count": 0,
            "latest_run_id": None,
            "latest_lineage_id": None,
            "source_aggregation": None,
            "graph_aggregation": None,
            "graph_state_source": "none",
            "graph_lineage_status": "unknown",
            "graph_terminal": False,
            "graph_reason": None,
            "graph_lane_counts": {},
            "graph_lane_statuses": [],
            "open_lane_lineages": [],
            "failed_lineages": [],
            "merged_lineages": [],
            "unmerged_terminal_lineages": [],
            "blocked_objects": [],
            "final_action_holds": [],
        }

    # Sort by created_at descending; records without a timestamp sort last
    sorted_records = sorted(records, key=_record_timestamp, reverse=True)
    latest = sorted_records[0]
    authoritative_graph_id: str | None = latest.get("spawned_graph_id") or None
    latest_run_id: str | None = latest.get("source_run_id") or None
    latest_lineage_id: str | None = latest.get("lineage_id") or None
    source_aggregation = _aggregation_by_id(
        aggregations,
        latest.get("terminal_aggregation_ref"),
    )
    if source_aggregation is None:
        source_aggregation = _latest_aggregation_for_graph(aggregations, latest_run_id)

    graph_aggregation = _latest_aggregation_for_graph(aggregations, authoritative_graph_id)
    derived_graph = _derived_graph_state(base_dir, authoritative_graph_id)
    merge_state = (
        str(derived_graph["status"])
        if derived_graph is not None
        else _aggregation_status(
            graph_aggregation,
            default="running" if authoritative_graph_id else "unknown",
        )
    )
    lineage_status = _aggregation_status(source_aggregation, default="unknown")
    lineage_terminated = _aggregation_terminal(source_aggregation)

    # Count lineage records whose spawned graph has no terminal state. Prefer
    # current graph/lane derivation when available so stale aggregation rows do
    # not hide an open graph.
    open_lineage_count = sum(
        1
        for rec in records
        if (gid := rec.get("spawned_graph_id"))
        and not (
            derived["terminal"]
            if (derived := _derived_graph_state(base_dir, str(gid))) is not None
            else _aggregation_terminal(_latest_aggregation_for_graph(aggregations, str(gid)))
        )
    )

    return {
        "authoritative_graph_id": authoritative_graph_id,
        "merge_state": merge_state,
        "lineage_terminated": lineage_terminated,
        "lineage_status": lineage_status,
        "open_lineage_count": open_lineage_count,
        "latest_run_id": latest_run_id,
        "latest_lineage_id": latest_lineage_id,
        "source_aggregation": _aggregation_summary(source_aggregation),
        "graph_aggregation": _aggregation_summary(graph_aggregation),
        "graph_state_source": derived_graph["source"]
        if derived_graph is not None
        else "run_aggregation",
        "graph_lineage_status": derived_graph["graph_lineage_status"]
        if derived_graph is not None
        else (
            "merged"
            if _aggregation_status(graph_aggregation, default="unknown") == "merged"
            else "terminated"
            if _aggregation_terminal(graph_aggregation)
            else "open"
            if authoritative_graph_id
            else "unknown"
        ),
        "graph_terminal": bool(derived_graph["terminal"])
        if derived_graph is not None
        else _aggregation_terminal(graph_aggregation),
        "graph_reason": derived_graph["reason"]
        if derived_graph is not None
        else (
            graph_aggregation.get("reason")
            if graph_aggregation is not None
            else None
        ),
        "graph_lane_counts": derived_graph["lane_counts"]
        if derived_graph is not None
        else (
            graph_aggregation.get("lane_counts", {})
            if graph_aggregation is not None
            else {}
        ),
        "graph_lane_statuses": derived_graph["lane_statuses"]
        if derived_graph is not None
        else (
            graph_aggregation.get("lane_statuses", [])
            if graph_aggregation is not None
            else []
        ),
        "open_lane_lineages": derived_graph["open_lane_lineages"]
        if derived_graph is not None
        else (
            graph_aggregation.get("open_lineages", [])
            if graph_aggregation is not None
            else []
        ),
        "failed_lineages": derived_graph["failed_lineages"]
        if derived_graph is not None
        else [],
        "merged_lineages": derived_graph["merged_lineages"]
        if derived_graph is not None
        else [],
        "unmerged_terminal_lineages": derived_graph["unmerged_terminal_lineages"]
        if derived_graph is not None
        else [],
        "blocked_objects": derived_graph["blocked_objects"]
        if derived_graph is not None
        else (
            graph_aggregation.get("blocked_objects", [])
            if graph_aggregation is not None
            else []
        ),
        "final_action_holds": derived_graph["final_action_holds"]
        if derived_graph is not None
        else (
            graph_aggregation.get("final_action_holds", [])
            if graph_aggregation is not None
            else []
        ),
    }


def _read_self_evolution_entries(base_dir: Path, file_name: str, key: str) -> list[Any]:
    data = _read_json(base_dir / "self_evolution" / file_name, {key: []})
    if not isinstance(data, dict):
        return []
    entries = data.get(key, [])
    return entries if isinstance(entries, list) else []


def _resolve_pending_final_action(base_dir: Path, feature_id: str) -> tuple[str, str] | None:
    store = FinalActionGateStore(base_dir / "final_actions.json")
    for hold in store.list_actions():
        if hold.lane_id == feature_id and hold.status == "pending":
            action = hold.action
            store.resolve(hold.id, status="approved", resolved_by="human")
            if action == "merge":
                return "merged", hold.id
            if action == "terminate":
                return "failed", hold.id
            return None
    return None


def create_app(base_dir: Path | str = DEFAULT_BASE_DIR) -> FastAPI:
    root = Path(base_dir)
    app = FastAPI(title="Xmuse Dashboard API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        """Return system health including graph authority and lineage status.

        Response fields
        ---------------
        status : "ok" | "degraded"
            "degraded" when the authoritative graph is in a terminal-failure or
            blocked state, or when there are active error entries.
        version : str
            API version string.
        graph_authority : dict
            - authoritative_graph_id: most-recently spawned graph ID, or null
            - merge_state: "merged" | "running" | "terminated" |
              "blocked_for_input" | "unknown"
            - lineage_terminated: true when the latest aggregation is terminal
            - open_lineage_count: lineage records with no terminal aggregation
            - latest_run_id: source_run_id of the most-recent lineage record
            - latest_lineage_id: lineage_id of the most-recent lineage record
        lane_summary : dict
            Normalized lane state counts from the active feature_lanes.json.
        active_session_count : int
            Number of entries in active_sessions.json.
        error_count : int
            Number of entries in error_knowledge.json.
        """
        graph_auth = _graph_authority_state(root)

        # Lane summary
        try:
            lane_data = _load_lanes(root)
            lanes = [lane for lane in lane_data["lanes"] if isinstance(lane, dict)]
            lane_summary = summarize_lane_states(lanes)
        except HTTPException:
            lane_summary = {}

        # Session and error counts (best-effort; missing files return 0)
        active_session_count = len(_read_sessions(root))
        error_count = len(_read_errors(root))

        # Derive overall status
        degraded_terminal_states = {"terminated", "blocked_for_input"}
        degraded_lineage_states = {"incomplete_termination", "terminated", "blocked_for_input"}
        overall_status = (
            "degraded"
            if (
                graph_auth["merge_state"] in degraded_terminal_states
                or graph_auth["lineage_status"] in degraded_terminal_states
                or graph_auth["graph_lineage_status"] in degraded_lineage_states
                or error_count > 0
            )
            else "ok"
        )

        return {
            "status": overall_status,
            "version": "0.1.0",
            "graph_authority": graph_auth,
            "lane_summary": lane_summary,
            "active_session_count": active_session_count,
            "error_count": error_count,
        }

    @app.get("/api/lanes")
    def list_lanes() -> dict[str, list[dict[str, Any]]]:
        data = _load_lanes(root)
        return {
            "lanes": [
                _lane_with_status(lane)
                for lane in data["lanes"]
                if isinstance(lane, dict)
            ]
        }

    @app.get("/api/lanes/{feature_id}")
    def lane_detail(feature_id: str) -> dict[str, Any]:
        data = _load_lanes(root)
        lane = _lane_with_status(_find_lane(data, feature_id))
        logs = _log_entries(root, feature_id)
        return {
            "lane": lane,
            "execution_log": "".join(entry["content"] for entry in logs),
            "logs": logs,
        }

    @app.post("/api/lanes", status_code=status.HTTP_201_CREATED)
    def create_lane(request: LaneCreate) -> dict[str, Any]:
        data = _load_lanes(root)
        feature_id = request.feature_id.strip()
        if not feature_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="feature_id required",
            )
        if any(
            isinstance(lane, dict) and lane.get("feature_id") == feature_id
            for lane in data["lanes"]
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="lane already exists")

        lane = request.model_dump(exclude_none=True)
        lane["feature_id"] = feature_id
        lane["prompt"] = request.prompt.strip()
        lane["task_type"] = lane.get("task_type") or "execute"
        lane["status"] = lane.get("status") or "pending"
        data["lanes"].append(lane)
        _write_json(_json_path(root, "feature_lanes.json"), data)
        return lane

    @app.post("/api/lanes/{feature_id}/approve")
    def approve_lane(feature_id: str) -> dict[str, Any]:
        data = _load_lanes(root)
        lane = _find_lane(data, feature_id)
        status_value = lane.get("status") or "pending"
        if status_value == "awaiting_final_action":
            resolved = _resolve_pending_final_action(root, feature_id)
            if resolved is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="no pending final action hold for lane",
                )
            lane["status"], lane["final_action_hold_id"] = resolved
        elif status_value not in {"done", "merged"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="only completed lanes can be approved",
            )
        lane["approval_status"] = "approved"
        lane["approved_at"] = utc_now()
        _write_json(_json_path(root, "feature_lanes.json"), data)
        return _lane_with_status(lane)

    @app.post("/api/lanes/{feature_id}/reject")
    def reject_lane(feature_id: str, request: LaneReject | None = None) -> dict[str, Any]:
        data = _load_lanes(root)
        lane = _find_lane(data, feature_id)
        rejection = request or LaneReject()
        lane["approval_status"] = "rejected"
        lane["rejected_at"] = utc_now()
        if rejection.reason:
            lane["rejection_reason"] = rejection.reason
        lane["rework_requested"] = rejection.rework
        if rejection.rework:
            lane["status"] = "pending"
        _write_json(_json_path(root, "feature_lanes.json"), data)
        return _lane_with_status(lane)

    @app.get("/api/sessions")
    def list_sessions() -> dict[str, list[Any]]:
        return {"sessions": _read_sessions(root)}

    @app.get("/api/errors")
    def list_errors() -> dict[str, list[Any]]:
        return {"errors": _read_errors(root)}

    @app.get("/api/resolutions")
    def list_resolutions() -> dict[str, list[Any]]:
        return {"resolutions": _read_model_entries(root, "resolutions.json", "resolutions")}

    @app.get("/api/verdicts")
    def list_verdicts() -> dict[str, list[Any]]:
        return {"verdicts": _read_model_entries(root, "verdicts.json", "verdicts")}

    @app.get("/api/self-evolution")
    def list_self_evolution() -> dict[str, list[Any]]:
        return {
            "run_aggregations": _read_self_evolution_entries(
                root,
                "run_aggregations.json",
                "aggregations",
            ),
            "evidence_bundles": _read_self_evolution_entries(
                root,
                "evidence_bundles.json",
                "evidence_bundles",
            ),
            "proposals": _read_self_evolution_entries(root, "proposals.json", "proposals"),
            "review_decisions": _read_self_evolution_entries(
                root,
                "review_decisions.json",
                "review_decisions",
            ),
            "guardrail_decisions": _read_self_evolution_entries(
                root,
                "guardrail_decisions.json",
                "guardrail_decisions",
            ),
            "budget_windows": _read_self_evolution_entries(
                root,
                "budget_windows.json",
                "budget_windows",
            ),
            "dedup_records": _read_self_evolution_entries(
                root,
                "dedup_records.json",
                "dedup_records",
            ),
            "lineage": _read_self_evolution_entries(root, "lineage.json", "lineage"),
            "clarification_requests": _read_self_evolution_entries(
                root,
                "clarification_requests.json",
                "clarification_requests",
            ),
            "clarification_resolutions": _read_self_evolution_entries(
                root,
                "clarification_resolutions.json",
                "clarification_resolutions",
            ),
        }

    @app.get("/api/self-evolution/audit")
    def self_evolution_audit() -> dict[str, Any]:
        """Return a structured audit snapshot of all self-evolution runs.

        The snapshot joins lineage records with their proposals, run-terminal
        aggregations, and system-authored conversations so a human can review
        the full self-evolution history without reading raw store files.

        The read model is materialised on demand and cached in
        ``read_models/self_evolution_audit.json``.
        """
        store_root = root / "self_evolution"
        read_models_root = root / "read_models"
        writer = SelfEvolutionAuditWriter(
            store_root=store_root,
            read_models_root=read_models_root,
        )
        try:
            payload = writer.write()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"failed to build self-evolution audit: {exc}",
            ) from exc
        return payload

    @app.get("/api/self-evolution/conversations")
    def self_evolution_conversations() -> dict[str, Any]:
        """Return all system-authored self-evolution conversations.

        Each entry includes the conversation metadata joined with the
        corresponding proposal so the caller can see which blueprint track
        each conversation targets.
        """
        store_root = root / "self_evolution"
        read_models_root = root / "read_models"
        writer = SelfEvolutionAuditWriter(
            store_root=store_root,
            read_models_root=read_models_root,
        )
        try:
            writer.write()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"failed to build self-evolution conversations: {exc}",
            ) from exc
        data = _read_json(read_models_root / SelfEvolutionAuditWriter.CONVERSATIONS_FILE, {})
        if not isinstance(data, dict):
            return {"schema_version": "1", "conversations": []}
        return data

    @app.get("/api/self-evolution/clarifications")
    def self_evolution_clarifications() -> dict[str, Any]:
        """Return all clarification requests and resolutions.

        Each request entry is joined with its resolution (if one exists) so the
        caller can see the full lifecycle of a blocked run: what was missing,
        who provided the information, and which graph was spawned to resume.

        The read model is materialised on demand and cached in
        ``read_models/self_evolution_clarifications.json``.
        """
        store_root = root / "self_evolution"
        read_models_root = root / "read_models"
        writer = SelfEvolutionAuditWriter(
            store_root=store_root,
            read_models_root=read_models_root,
        )
        try:
            writer.write()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"failed to build self-evolution clarifications: {exc}",
            ) from exc
        data = _read_json(
            read_models_root / SelfEvolutionAuditWriter.CLARIFICATION_FILE, {}
        )
        if not isinstance(data, dict):
            return {
                "schema_version": "1",
                "clarification_requests": [],
                "clarification_resolutions": [],
            }
        return data

    @app.get("/api/dashboard/audit-events")
    def list_audit_events(
        event_type: str | None = None,
        since: str | None = None,
        until: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """Return paginated system events from the event bus audit log.

        Query parameters
        ----------------
        event_type : str, optional
            Filter to events whose ``event_type`` field matches exactly.
        since : str, optional
            ISO-8601 timestamp; only events at or after this time are returned.
        until : str, optional
            ISO-8601 timestamp; only events at or before this time are returned.
        page : int, default 1
            1-based page number.
        page_size : int, default 50
            Maximum number of events per page (capped at 500).
        """
        if page < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="page must be >= 1",
            )
        page_size = max(1, min(page_size, 500))

        since_dt: datetime | None = None
        until_dt: datetime | None = None
        if since is not None:
            since_dt = _parse_timestamp(since)
            if since_dt is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"invalid since timestamp: {since!r}",
                )
        if until is not None:
            until_dt = _parse_timestamp(until)
            if until_dt is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"invalid until timestamp: {until!r}",
                )

        events = _read_audit_events(
            root,
            event_type=event_type,
            since=since_dt,
            until=until_dt,
        )

        total = len(events)
        offset = (page - 1) * page_size
        page_events = events[offset : offset + page_size]

        return {
            "events": page_events,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, -(-total // page_size)),  # ceiling division
        }

    @app.get("/api/dashboard/state-history")
    def list_state_history(
        lane_id: str | None = None,
        state_key: str | None = None,
        since: str | None = None,
        until: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """Return paginated state snapshots from the state machine history log.

        Query parameters
        ----------------
        lane_id : str, optional
            Filter to snapshots for a specific lane.
        state_key : str, optional
            Filter to snapshots where the state equals this value (e.g. ``"dispatched"``).
        since : str, optional
            ISO-8601 timestamp; only snapshots at or after this time are returned.
        until : str, optional
            ISO-8601 timestamp; only snapshots at or before this time are returned.
        page : int, default 1
            1-based page number.
        page_size : int, default 50
            Maximum number of snapshots per page (capped at 500).
        """
        if page < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="page must be >= 1",
            )
        page_size = max(1, min(page_size, 500))

        since_dt: datetime | None = None
        until_dt: datetime | None = None
        if since is not None:
            since_dt = _parse_timestamp(since)
            if since_dt is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"invalid since timestamp: {since!r}",
                )
        if until is not None:
            until_dt = _parse_timestamp(until)
            if until_dt is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"invalid until timestamp: {until!r}",
                )

        snapshots = _read_state_history(
            root,
            lane_id=lane_id,
            state_key=state_key,
            since=since_dt,
            until=until_dt,
        )

        total = len(snapshots)
        offset = (page - 1) * page_size
        page_snapshots = snapshots[offset : offset + page_size]

        return {
            "snapshots": page_snapshots,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, -(-total // page_size)),  # ceiling division
        }

    @app.get("/api/dashboard/lineage")
    def execution_lineage(
        from_node: str | None = None,
        depth: int | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Return execution graph lineage with node relationships and merge points.

        The response describes a directed graph where each node is a run or
        spawned graph and each edge is an ``EvolutionLineageRecord`` that links
        a source run to the graph it spawned.

        Query parameters
        ----------------
        from_node : str, optional
            Start graph traversal from this node ID (``source_run_id`` or
            ``spawned_graph_id``).  Only nodes reachable from this node are
            returned.  When omitted the full lineage graph is returned.
        depth : int, optional
            Maximum traversal depth from ``from_node``.  Requires ``from_node``
            to be set; ignored otherwise.  Must be >= 1 when provided.
        run_id : str, optional
            Convenience alias for ``from_node`` when the caller wants to anchor
            the traversal on a specific run ID.  Ignored when ``from_node`` is
            also provided.
        """
        if depth is not None and depth < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="depth must be >= 1",
            )

        anchor = from_node or run_id
        records = _read_lineage_records(root)
        graph = _build_lineage_graph(records, from_node=anchor, depth=depth)
        return graph

    @app.get("/api/lane-graphs")
    def list_lane_graphs() -> dict[str, Any]:
        """Return all lane graph snapshots with their derived execution state.

        Each entry includes the full lane graph definition (id, conversation_id,
        resolution_id, version, status, lanes) plus a ``derived_state`` block
        computed from the current lane execution state.

        ``derived_state`` mirrors the shape produced by ``_derived_graph_state``
        and is the same source used by ``/api/health``.  When no lane graph
        files exist the response is an empty list.

        Response shape
        --------------
        graphs : list
            Each item:
            - id, conversation_id, resolution_id, version, status, lanes
            - derived_state: { status, terminal, reason, graph_lineage_status,
              lane_counts, lane_statuses, open_lane_lineages, failed_lineages,
              merged_lineages, blocked_objects, final_action_holds }
        total : int
            Number of graphs returned.
        """
        graphs_dir = root / "lane_graphs"
        if not graphs_dir.exists():
            return {"graphs": [], "total": 0}

        entries: list[dict[str, Any]] = []
        for path in sorted(graphs_dir.glob("*.json")):
            data = _read_json(path, {})
            if not isinstance(data, dict):
                continue
            graph_id = data.get("id") or path.stem
            derived = _derived_graph_state(root, str(graph_id))
            entry = dict(data)
            entry["derived_state"] = derived if derived is not None else {}
            entries.append(entry)

        # Sort newest-first by graph id (lexicographic; IDs are typically
        # timestamped or sequential so this gives a reasonable default order).
        entries.sort(key=lambda e: str(e.get("id", "")), reverse=True)
        return {"graphs": entries, "total": len(entries)}

    @app.get("/api/lane-graphs/{graph_id}")
    def lane_graph_detail(graph_id: str) -> dict[str, Any]:
        """Return a single lane graph snapshot with its derived execution state.

        Path parameters
        ---------------
        graph_id : str
            The graph ID (matches the filename stem under ``lane_graphs/``).

        Response shape
        --------------
        graph : dict
            Full lane graph definition plus ``derived_state``.
        lineage : dict | null
            The most-recent ``EvolutionLineageRecord`` that spawned this graph,
            or null when no lineage record references this graph_id.
        aggregation : dict | null
            The most-recent ``RunTerminalAggregation`` for this graph from the
            self-evolution store, or null when none exists.
        """
        path = root / "lane_graphs" / f"{graph_id}.json"
        if not path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"lane graph not found: {graph_id}",
            )
        data = _read_json(path, {})
        if not isinstance(data, dict):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"invalid lane graph file for: {graph_id}",
            )

        derived = _derived_graph_state(root, graph_id)
        graph = dict(data)
        graph["derived_state"] = derived if derived is not None else {}

        # Join the most-recent lineage record that spawned this graph
        lineage_records = _read_lineage_records(root)
        matching_lineage = [
            rec for rec in lineage_records if rec.get("spawned_graph_id") == graph_id
        ]
        latest_lineage: dict[str, Any] | None = None
        if matching_lineage:
            latest_lineage = sorted(matching_lineage, key=_record_timestamp)[-1]

        # Join the most-recent run aggregation for this graph
        aggregations = _read_run_aggregations(root)
        latest_aggregation = _latest_aggregation_for_graph(aggregations, graph_id)
        aggregation_summary = _aggregation_summary(latest_aggregation)

        return {
            "graph": graph,
            "lineage": latest_lineage,
            "aggregation": aggregation_summary,
        }

    @app.get("/api/metrics")
    def metrics() -> dict[str, int | float | None]:
        data = _load_lanes(root)
        lanes = [lane for lane in data["lanes"] if isinstance(lane, dict)]
        summary = summarize_lane_states(lanes)
        done = summary.get("merged", 0) + summary.get("done", 0)
        failed = max(0, summary.get("terminal", 0) - summary.get("merged", 0))
        pending = len(lanes) - done - failed
        durations = [
            duration
            for lane in lanes
            if (duration := _duration_seconds(lane)) is not None
        ]
        avg_time = round(sum(durations) / len(durations), 2) if durations else None
        return {
            "total": len(lanes),
            "done": done,
            "ready": summary.get("ready", 0),
            "requeued": summary.get("requeued", 0),
            "failed": failed,
            "pending": pending,
            "avg_time_seconds": avg_time,
        }

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=DEFAULT_PORT)
