from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any

from memoryos_lite.observability import (
    current_observability_context,
    log_event,
    observability_context,
    timed_core_operation,
)
from xmuse_core.platform.state_validation import (
    StateTransition,
    StateTransitionValidator,
    StateValidationError,
)

MAX_RETRIES = 2
logger = logging.getLogger(__name__)

VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"dispatched"},
    "dispatched": {"executed", "exec_failed"},
    "executed": {"gated", "gate_failed"},
    "gated": {"reviewed", "rejected", "gate_failed"},
    "reviewed": {"merged", "failed", "awaiting_final_action"},
    "awaiting_final_action": {"merged", "failed"},
    "rejected": {"reworking", "failed"},
    "reworking": {"dispatched"},
    "exec_failed": {"failed", "reworking"},
    "gate_failed": {"failed", "reworking", "gated"},
}


class InvalidTransitionError(ValueError):
    pass


class LaneStateMachine:
    def __init__(self, lanes_path: Path) -> None:
        self._path = lanes_path
        self._validator = StateTransitionValidator(VALID_TRANSITIONS)

    def _read(self) -> dict[str, Any]:
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self._path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def get_lane(self, lane_id: str) -> dict[str, Any]:
        for lane in self._read().get("lanes", []):
            if lane.get("feature_id") == lane_id:
                return lane
        raise KeyError(f"lane not found: {lane_id}")

    def get_lanes(self, status: str | None = None) -> list[dict[str, Any]]:
        lanes = self._read().get("lanes", [])
        if status is None:
            return lanes
        return [lane for lane in lanes if lane.get("status") == status]

    def validate(self) -> None:
        self._validator.validate_state(self._read()).raise_if_invalid()

    def transition(
        self,
        lane_id: str,
        target_status: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with observability_context(lane_id=lane_id), timed_core_operation(
            component="state_machine",
            operation="transition",
            logger=logger,
            lane_id=lane_id,
            target_status=target_status,
        ):
            data = self._read()
            lanes = data.get("lanes", [])
            lane = None
            for lane_item in lanes:
                if lane_item.get("feature_id") == lane_id:
                    lane = lane_item
                    break
            if lane is None:
                raise KeyError(f"lane not found: {lane_id}")

            current = lane.get("status", "pending")
            lane.setdefault("status", current)
            before = copy.deepcopy(lane)
            allowed = VALID_TRANSITIONS.get(current, set())
            if target_status not in allowed:
                raise InvalidTransitionError(
                    f"cannot transition {lane_id} from {current} to {target_status}"
                )

            if target_status == "reworking":
                retries = lane.get("retry_count", 0)
                if retries >= MAX_RETRIES:
                    raise InvalidTransitionError(
                        f"lane {lane_id} exceeded max retries ({MAX_RETRIES})"
                    )
                lane["retry_count"] = retries + 1

            if metadata:
                lane.update(metadata)
            lane["status"] = target_status
            if target_status in {"reworking", "dispatched", "gated"}:
                lane.pop("failure_reason", None)
            lane.setdefault("trace_id", current_observability_context()["trace_id"])

            self._validator.validate_transition(
                StateTransition(
                    lane_id=lane_id,
                    source_status=str(current),
                    target_status=target_status,
                    before=before,
                    after=lane,
                ),
                state_after=data,
            ).raise_if_invalid()
            self._write(data)
            log_event(
                logger,
                logging.INFO,
                "lane_transitioned",
                lane_id=lane_id,
                from_status=current,
                to_status=target_status,
            )
            return lane

    def update_metadata(self, lane_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
        with observability_context(lane_id=lane_id), timed_core_operation(
            component="state_machine",
            operation="update_metadata",
            logger=logger,
            lane_id=lane_id,
        ):
            data = self._read()
            for lane in data.get("lanes", []):
                if lane.get("feature_id") == lane_id:
                    before = copy.deepcopy(lane)
                    if "status" in metadata and metadata["status"] != before.get("status"):
                        raise StateValidationError(
                            f"invariant_preservation: {lane_id}: "
                            "status cannot change during metadata update; use transition()"
                        )
                    lane.setdefault("trace_id", current_observability_context()["trace_id"])
                    lane.update(metadata)
                    self._validator.validate_lane(lane).raise_if_invalid()
                    self._validator.validate_state(data).raise_if_invalid()
                    if lane.get("feature_id") != before.get("feature_id"):
                        raise StateValidationError(
                            f"invariant_preservation: {lane_id}: "
                            "feature_id cannot change during metadata update"
                        )
                    for field_name in ("retry_count", "review_retry_count"):
                        previous = before.get(field_name, 0)
                        current = lane.get(field_name, 0)
                        if (
                            isinstance(previous, int)
                            and isinstance(current, int)
                            and not isinstance(previous, bool)
                            and not isinstance(current, bool)
                            and current < previous
                        ):
                            raise StateValidationError(
                                f"invariant_preservation: {lane_id}: "
                                f"{field_name} cannot decrease"
                            )
                    self._write(data)
                    log_event(
                        logger,
                        logging.DEBUG,
                        "lane_metadata_updated",
                        lane_id=lane_id,
                        metadata_keys=sorted(metadata),
                    )
                    return lane
            raise KeyError(f"lane not found: {lane_id}")

    def append_lane(self, lane: dict[str, Any]) -> dict[str, Any]:
        lane_id = str(lane.get("feature_id", "unknown"))
        with observability_context(lane_id=lane_id), timed_core_operation(
            component="state_machine",
            operation="append_lane",
            logger=logger,
            lane_id=lane_id,
        ):
            data = self._read()
            lanes = data.setdefault("lanes", [])
            if any(
                isinstance(item, dict) and item.get("feature_id") == lane.get("feature_id")
                for item in lanes
            ):
                return lane
            lane.setdefault("trace_id", current_observability_context()["trace_id"])
            lanes.append(lane)
            self._validator.validate_state(data).raise_if_invalid()
            self._write(data)
            log_event(logger, logging.INFO, "lane_appended", lane_id=lane_id)
            return lane
