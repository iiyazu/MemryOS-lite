from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from memoryos_lite.observability import (
    log_event,
    observability_context,
    timed_core_operation,
)
from xmuse_core.platform.state_normalizer import normalize_lane_state, summarize_lane_states
from xmuse_core.structuring.graph_store import LaneGraphStore
from xmuse_core.structuring.projection import project_ready_lanes

logger = logging.getLogger(__name__)


@runtime_checkable
class _LaneStateMachine(Protocol):
    _path: Path

    def get_lane(self, lane_id: str) -> dict[str, Any]: ...

    def update_metadata(self, lane_id: str, metadata: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class AggregatedStatus:
    graph_id: str
    status: str
    terminal: bool
    reason: str
    lane_counts: dict[str, int]
    lane_statuses: list[dict[str, Any]]


async def reproject_dependents_if_needed(
    lane_id: str,
    *,
    sm: _LaneStateMachine,
    graph_store: LaneGraphStore,
) -> None:
    lane = sm.get_lane(lane_id)
    graph_id = _lane_graph_id(lane)
    with observability_context(
        lane_id=lane_id,
        graph_id=graph_id,
    ), timed_core_operation(
        component="projection",
        operation="reproject_dependents",
        logger=logger,
        lane_id=lane_id,
    ):
        if lane.get("dependency_projection_processed_at"):
            return

        if not graph_id:
            return

        try:
            graph = graph_store.get(graph_id)
        except KeyError:
            log_event(
                logger,
                logging.WARNING,
                "lane_graph_not_found",
                lane_id=lane_id,
                graph_id=graph_id,
            )
            return

        projected = project_ready_lanes(graph, _lanes_path(sm))
        sm.update_metadata(
            lane_id,
            {
                "dependency_projection_processed_at": time.time(),
                "dependency_projection_count": len(projected),
            },
        )


def aggregate_status(lanes: list[dict[str, Any]], graph_id: str) -> AggregatedStatus:
    graph_lanes = [
        lane
        for lane in lanes
        if isinstance(lane, dict) and str(lane.get("graph_id") or "") == graph_id
    ]
    lane_statuses = [_lane_status(lane) for lane in graph_lanes]
    lane_counts = summarize_lane_states(graph_lanes)

    if not lane_statuses:
        return AggregatedStatus(
            graph_id=graph_id,
            status="in_progress",
            terminal=False,
            reason="no graph lanes have been projected yet",
            lane_counts=lane_counts,
            lane_statuses=lane_statuses,
        )

    if any(not item["terminal"] for item in lane_statuses):
        return AggregatedStatus(
            graph_id=graph_id,
            status="in_progress",
            terminal=False,
            reason="at least one graph lane is not terminal",
            lane_counts=lane_counts,
            lane_statuses=lane_statuses,
        )

    if all(item["normalized_status"] == "merged" for item in lane_statuses):
        return AggregatedStatus(
            graph_id=graph_id,
            status="merged",
            terminal=True,
            reason="all graph lanes merged",
            lane_counts=lane_counts,
            lane_statuses=lane_statuses,
        )

    return AggregatedStatus(
        graph_id=graph_id,
        status="terminated",
        terminal=True,
        reason="at least one graph lane terminalized without merge",
        lane_counts=lane_counts,
        lane_statuses=lane_statuses,
    )


def _lane_graph_id(lane: dict[str, Any] | None) -> str | None:
    graph_id = lane.get("graph_id") if isinstance(lane, dict) else None
    return str(graph_id) if graph_id else None


def _lanes_path(sm: _LaneStateMachine) -> Path:
    path = getattr(sm, "_path", None)
    if not isinstance(path, Path):
        raise TypeError("state machine must expose a pathlib.Path _path")
    return path


def _lane_status(lane: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_lane_state(lane)
    return {
        "lane_id": normalized.feature_id,
        "raw_status": normalized.raw_status,
        "normalized_status": normalized.normalized_status,
        "terminal": normalized.is_terminal,
    }
