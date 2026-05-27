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
