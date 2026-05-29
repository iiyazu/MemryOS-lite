#!/usr/bin/env python3
"""FastAPI MCP-over-HTTP server for xmuse control-plane operations."""

from __future__ import annotations

import json
import os
import re
import signal
import uuid
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

DEFAULT_XMUSE_ROOT = Path(__file__).resolve().parent
SERVER_NAME = "xmuse-mcp"
SERVER_VERSION = "0.1.0"


def _read_json_object(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return dict(default or {})
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} JSON root must be an object")
    return payload


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _content_json(payload: Any) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            }
        ],
        "structuredContent": payload,
        "isError": False,
    }


def _error_content(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _text_for_search(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_text_for_search(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_text_for_search(item) for item in value)
    return str(value)


def _query_terms(query: str) -> set[str]:
    return {term for term in re.findall(r"[a-zA-Z0-9_+-]+", query.lower()) if len(term) > 1}


class XmuseOperations:
    def __init__(self, xmuse_root: str | Path = DEFAULT_XMUSE_ROOT) -> None:
        self.xmuse_root = Path(xmuse_root)
        self.lanes_path = self.xmuse_root / "feature_lanes.json"
        self.sessions_path = self.xmuse_root / "active_sessions.json"
        self.error_knowledge_path = self.xmuse_root / "error_knowledge.json"
        self.logs_dir = self.xmuse_root / "logs"

    def list_lanes(self) -> dict[str, Any]:
        return _read_json_object(self.lanes_path, {"lanes": []})

    def enqueue_lane(
        self,
        *,
        feature_id: str,
        prompt: str,
        capabilities: list[str],
    ) -> dict[str, Any]:
        feature_id = feature_id.strip()
        prompt = prompt.strip()
        if not feature_id:
            raise ValueError("feature_id is required")
        if not prompt:
            raise ValueError("prompt is required")
        if not isinstance(capabilities, list) or not all(
            isinstance(item, str) and item.strip() for item in capabilities
        ):
            raise ValueError("capabilities must be a non-empty string list")

        payload = self.list_lanes()
        lanes = payload.setdefault("lanes", [])
        if not isinstance(lanes, list):
            raise ValueError("feature_lanes.json lanes must be a list")
        if any(isinstance(lane, dict) and lane.get("feature_id") == feature_id for lane in lanes):
            raise ValueError(f"lane already exists: {feature_id}")

        lane = {
            "feature_id": feature_id,
            "task_type": "execute",
            "prompt": prompt,
            "capabilities": [item.strip() for item in capabilities],
            "status": "pending",
        }
        lanes.append(lane)
        _atomic_write_json(self.lanes_path, payload)
        return lane

    def get_status(self, *, feature_id: str) -> dict[str, Any]:
        feature_id = feature_id.strip()
        if not feature_id:
            raise ValueError("feature_id is required")
        lane = self._find_lane(feature_id)
        active_session = self._find_active_session(feature_id)
        return {
            "feature_id": feature_id,
            "lane": lane or {"feature_id": feature_id, "status": "unknown"},
            "active_session": active_session,
        }

    def abort_lane(self, *, feature_id: str) -> dict[str, Any]:
        feature_id = feature_id.strip()
        if not feature_id:
            raise ValueError("feature_id is required")

        lane = self._set_lane_status(feature_id, "aborted")
        sessions = _read_json_object(self.sessions_path, {})
        active_session = self._find_active_session(feature_id, sessions=sessions)
        if active_session is not None:
            active_session["status"] = "aborted"
            active_session["abort_requested"] = True
            pid = active_session.get("pid")
            if isinstance(pid, int):
                try:
                    os.kill(pid, signal.SIGTERM)
                except (LookupError, PermissionError, ProcessLookupError):
                    active_session["signal_error"] = "process_not_signaled"
            self._replace_active_session(feature_id, active_session, sessions)
            _atomic_write_json(self.sessions_path, sessions)

        return {
            "feature_id": feature_id,
            "aborted": lane is not None or active_session is not None,
            "lane": lane or {"feature_id": feature_id, "status": "unknown"},
            "active_session": active_session,
        }

    def get_error_knowledge(self, *, query: str, top_k: int = 3) -> dict[str, Any]:
        query = query.strip()
        if not query:
            raise ValueError("query is required")
        if top_k < 1:
            raise ValueError("top_k must be at least 1")

        entries = self._error_entries()
        terms = _query_terms(query)
        matches: list[dict[str, Any]] = []
        for entry in entries:
            haystack = _text_for_search(entry).lower()
            score = sum(1 for term in terms if term in haystack)
            if score:
                matches.append({"score": score, "entry": entry})
        matches.sort(
            key=lambda item: (
                -int(item["score"]),
                str(item["entry"].get("entry_id") or item["entry"].get("id") or ""),
            )
        )
        return {"query": query, "matches": matches[:top_k]}

    def get_logs(self, *, feature_id: str, max_bytes: int = 200_000) -> dict[str, Any]:
        feature_id = feature_id.strip()
        if not feature_id:
            raise ValueError("feature_id is required")
        if max_bytes < 1:
            raise ValueError("max_bytes must be at least 1")

        logs: list[dict[str, str]] = []
        combined_parts: list[str] = []
        total_bytes = 0
        if self.logs_dir.exists():
            for path in sorted(self.logs_dir.glob(f"*{feature_id}*")):
                if not path.is_file():
                    continue
                content = path.read_text(encoding="utf-8", errors="replace")
                remaining = max_bytes - total_bytes
                if remaining <= 0:
                    break
                truncated = content[:remaining]
                total_bytes += len(truncated.encode("utf-8"))
                rel_path = path.relative_to(self.xmuse_root).as_posix()
                logs.append({"path": rel_path, "content": truncated})
                combined_parts.append(f"== {rel_path} ==\n{truncated}")
        return {
            "feature_id": feature_id,
            "logs": logs,
            "combined": "\n".join(combined_parts),
            "truncated": total_bytes >= max_bytes,
        }

    def _find_lane(self, feature_id: str) -> dict[str, Any] | None:
        for lane in self.list_lanes().get("lanes", []):
            if isinstance(lane, dict) and lane.get("feature_id") == feature_id:
                return dict(lane)
        return None

    def _set_lane_status(self, feature_id: str, status: str) -> dict[str, Any] | None:
        payload = self.list_lanes()
        lanes = payload.get("lanes", [])
        if not isinstance(lanes, list):
            raise ValueError("feature_lanes.json lanes must be a list")
        updated: dict[str, Any] | None = None
        for lane in lanes:
            if isinstance(lane, dict) and lane.get("feature_id") == feature_id:
                lane["status"] = status
                updated = dict(lane)
                break
        if updated is not None:
            _atomic_write_json(self.lanes_path, payload)
        return updated

    def _find_active_session(
        self,
        feature_id: str,
        *,
        sessions: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        payload = sessions if sessions is not None else _read_json_object(self.sessions_path, {})
        raw_sessions = payload.get("sessions", payload)
        if isinstance(raw_sessions, dict):
            session = raw_sessions.get(feature_id)
            if isinstance(session, dict):
                return dict(session)
            for item in raw_sessions.values():
                if isinstance(item, dict) and item.get("feature_id") == feature_id:
                    return dict(item)
        if isinstance(raw_sessions, list):
            for item in raw_sessions:
                if isinstance(item, dict) and item.get("feature_id") == feature_id:
                    return dict(item)
        return None

    def _replace_active_session(
        self,
        feature_id: str,
        session: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        raw_sessions = payload.setdefault("sessions", {})
        if isinstance(raw_sessions, dict):
            if feature_id in raw_sessions:
                raw_sessions[feature_id] = session
                return
            for key, item in raw_sessions.items():
                if isinstance(item, dict) and item.get("feature_id") == feature_id:
                    raw_sessions[key] = session
                    return
            raw_sessions[feature_id] = session
            return
        if isinstance(raw_sessions, list):
            for index, item in enumerate(raw_sessions):
                if isinstance(item, dict) and item.get("feature_id") == feature_id:
                    raw_sessions[index] = {"feature_id": feature_id, **session}
                    return
            raw_sessions.append({"feature_id": feature_id, **session})

    def _error_entries(self) -> list[dict[str, Any]]:
        payload = _read_json_object(self.error_knowledge_path, {})
        entries = payload.get("entries", payload.get("errors", []))
        if isinstance(entries, dict):
            entries = list(entries.values())
        if not isinstance(entries, list):
            entries = []
        aggregate_entries = [entry for entry in entries if isinstance(entry, dict)]
        if aggregate_entries:
            return aggregate_entries

        discovered: list[dict[str, Any]] = []
        knowledge_dir = self.xmuse_root / "knowledge"
        for path in sorted(knowledge_dir.glob("error_records/**/*.json")):
            try:
                entry = _read_json_object(path)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            entry.setdefault("source_path", path.relative_to(self.xmuse_root).as_posix())
            discovered.append(entry)
        return discovered


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "list_lanes",
        "description": "Return current xmuse feature_lanes.json content.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "enqueue_lane",
        "description": "Append a queued xmuse lane to feature_lanes.json.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "feature_id": {"type": "string"},
                "prompt": {"type": "string"},
                "capabilities": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["feature_id", "prompt", "capabilities"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_status",
        "description": "Return lane status and active session information.",
        "inputSchema": {
            "type": "object",
            "properties": {"feature_id": {"type": "string"}},
            "required": ["feature_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "abort_lane",
        "description": "Mark a lane/session aborted and signal the active process if present.",
        "inputSchema": {
            "type": "object",
            "properties": {"feature_id": {"type": "string"}},
            "required": ["feature_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_error_knowledge",
        "description": "Keyword-search xmuse error knowledge entries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 3},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_logs",
        "description": "Return per-round execution logs matching a feature id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "feature_id": {"type": "string"},
                "max_bytes": {"type": "integer", "default": 200000},
            },
            "required": ["feature_id"],
            "additionalProperties": False,
        },
    },
]

# Platform God tools (used by Execution God and Review God agents)
PLATFORM_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_lane",
        "description": "Get full lane details by feature_id.",
        "inputSchema": {
            "type": "object",
            "properties": {"lane_id": {"type": "string"}},
            "required": ["lane_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_gate_report",
        "description": "Get the most recent gate execution report for a lane.",
        "inputSchema": {
            "type": "object",
            "properties": {"lane_id": {"type": "string"}},
            "required": ["lane_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_diff",
        "description": "Get the git diff of a lane's worktree.",
        "inputSchema": {
            "type": "object",
            "properties": {"lane_id": {"type": "string"}},
            "required": ["lane_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "query_knowledge",
        "description": "Search error_knowledge for relevant past failures.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 3},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "update_lane_status",
        "description": "Update lane status (drives the state machine).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "lane_id": {"type": "string"},
                "status": {"type": "string"},
                "metadata": {"type": "object"},
            },
            "required": ["lane_id", "status"],
            "additionalProperties": False,
        },
    },
]


def _tool_result(ops: XmuseOperations, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "list_lanes":
        return _content_json(ops.list_lanes())
    if name == "enqueue_lane":
        return _content_json(ops.enqueue_lane(**arguments))
    if name == "get_status":
        return _content_json(ops.get_status(**arguments))
    if name == "abort_lane":
        return _content_json(ops.abort_lane(**arguments))
    if name == "get_error_knowledge":
        return _content_json(ops.get_error_knowledge(**arguments))
    if name == "get_logs":
        return _content_json(ops.get_logs(**arguments))
    # Platform God tools — delegate to McpToolHandler
    if name in ("get_lane", "get_gate_report", "get_diff", "query_knowledge", "update_lane_status"):
        from xmuse_core.platform.mcp_tools import McpToolHandler
        from xmuse_core.platform.state_machine import LaneStateMachine
        sm = LaneStateMachine(ops.lanes_path)
        handler = McpToolHandler(state_machine=sm, xmuse_root=ops.xmuse_root)
        return _content_json(handler.call(name, arguments))
    raise ValueError(f"unknown tool: {name}")


def _json_rpc_response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _json_rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


async def _handle_json_rpc(payload: dict[str, Any], ops: XmuseOperations) -> JSONResponse:
    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}
    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            }
            return JSONResponse(_json_rpc_response(request_id, result))
        if method == "notifications/initialized":
            return JSONResponse(_json_rpc_response(request_id, {}))
        if method == "tools/list":
            return JSONResponse(
                _json_rpc_response(
                    request_id,
                    {"tools": TOOL_SCHEMAS + PLATFORM_TOOL_SCHEMAS},
                )
            )
        if method == "tools/call":
            if not isinstance(params, dict):
                raise ValueError("params must be an object")
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not isinstance(name, str):
                raise ValueError("tool name is required")
            if not isinstance(arguments, dict):
                raise ValueError("arguments must be an object")
            return JSONResponse(_json_rpc_response(request_id, _tool_result(ops, name, arguments)))
        return JSONResponse(_json_rpc_error(request_id, -32601, f"method not found: {method}"))
    except Exception as exc:
        return JSONResponse(_json_rpc_response(request_id, _error_content(str(exc))))


def create_app(xmuse_root: str | Path = DEFAULT_XMUSE_ROOT) -> FastAPI:
    ops = XmuseOperations(xmuse_root)
    app = FastAPI(title="xmuse MCP Server", version=SERVER_VERSION)
    app.state.xmuse_ops = ops

    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "server": SERVER_NAME, "port": 8100}

    @app.get("/sse")
    def sse() -> StreamingResponse:
        session_id = uuid.uuid4().hex

        def events():
            yield f"event: endpoint\ndata: /messages?session_id={session_id}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.post("/messages")
    async def messages(request: Request) -> JSONResponse:
        payload = await request.json()
        if not isinstance(payload, dict):
            return JSONResponse(_json_rpc_error(None, -32600, "request must be an object"))
        return await _handle_json_rpc(payload, ops)

    @app.post("/mcp")
    async def mcp(request: Request) -> JSONResponse:
        payload = await request.json()
        if not isinstance(payload, dict):
            return JSONResponse(_json_rpc_error(None, -32600, "request must be an object"))
        return await _handle_json_rpc(payload, ops)

    return app


app = create_app()


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8100)


if __name__ == "__main__":
    main()
