from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MAX_RETRIES = 2

VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"dispatched"},
    "dispatched": {"executed", "exec_failed"},
    "executed": {"gated"},
    "gated": {"reviewed", "rejected", "gate_failed"},
    "reviewed": {"merged", "failed"},
    "rejected": {"reworking", "failed"},
    "reworking": {"dispatched"},
    "exec_failed": {"failed", "reworking"},
    "gate_failed": {"failed", "reworking"},
}


class InvalidTransitionError(ValueError):
    pass


class LaneStateMachine:
    def __init__(self, lanes_path: Path) -> None:
        self._path = lanes_path

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
        return [l for l in lanes if l.get("status") == status]

    def transition(
        self,
        lane_id: str,
        target_status: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = self._read()
        lanes = data.get("lanes", [])
        lane = None
        for l in lanes:
            if l.get("feature_id") == lane_id:
                lane = l
                break
        if lane is None:
            raise KeyError(f"lane not found: {lane_id}")

        current = lane.get("status", "pending")
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

        lane["status"] = target_status
        if metadata:
            lane.update(metadata)

        self._write(data)
        return lane
