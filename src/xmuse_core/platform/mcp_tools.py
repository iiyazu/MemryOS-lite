from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from xmuse_core.platform.state_machine import (
    InvalidTransitionError,
    LaneStateMachine,
)
from xmuse_core.platform.state_validation import StateValidationError


def _query_terms(query: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-Z0-9_+-]+", query.lower()) if len(t) > 1}


def _text_for_search(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_text_for_search(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_text_for_search(v) for v in value)
    return str(value)


class McpToolHandler:
    def __init__(
        self,
        *,
        state_machine: LaneStateMachine,
        xmuse_root: Path,
        on_status_change=None,
    ) -> None:
        self._sm = state_machine
        self._root = xmuse_root
        self._on_status_change = on_status_change

    def call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        method = getattr(self, f"_tool_{tool_name}", None)
        if method is None:
            return {"error": f"unknown tool: {tool_name}"}
        try:
            return method(arguments)
        except Exception as exc:
            return {"error": str(exc)}

    def _tool_get_lane(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._sm.get_lane(args["lane_id"])

    def _tool_get_gate_report(self, args: dict[str, Any]) -> dict[str, Any]:
        lane_id = args["lane_id"]
        report_path = self._root / "logs" / "gates" / lane_id / "report.json"
        if not report_path.exists():
            return {"error": f"no gate report for {lane_id}"}
        return json.loads(report_path.read_text(encoding="utf-8"))

    def _tool_get_diff(self, args: dict[str, Any]) -> dict[str, Any]:
        lane = self._sm.get_lane(args["lane_id"])
        worktree = Path(lane.get("worktree", "."))
        if not worktree.exists():
            return {"error": f"worktree not found: {worktree}"}
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=worktree, capture_output=True, text=True, timeout=10,
        )
        return {"diff": result.stdout, "returncode": result.returncode}

    def _tool_query_knowledge(self, args: dict[str, Any]) -> dict[str, Any]:
        query = args.get("query", "")
        top_k = args.get("top_k", 3)
        ek_path = self._root / "error_knowledge.json"
        if not ek_path.exists():
            return {"query": query, "matches": []}
        data = json.loads(ek_path.read_text(encoding="utf-8"))
        entries = data.get("entries", [])
        terms = _query_terms(query)
        scored = []
        for entry in entries:
            haystack = _text_for_search(entry).lower()
            score = sum(1 for t in terms if t in haystack)
            if score:
                scored.append({"score": score, "entry": entry})
        scored.sort(key=lambda x: -x["score"])
        return {"query": query, "matches": scored[:top_k]}

    def _tool_update_lane_status(self, args: dict[str, Any]) -> dict[str, Any]:
        lane_id = args["lane_id"]
        status = args["status"]
        metadata = args.get("metadata")
        try:
            lane = self._sm.transition(lane_id, status, metadata=metadata)
            if self._on_status_change:
                self._on_status_change(lane_id, status)
            return lane
        except (InvalidTransitionError, StateValidationError, KeyError) as exc:
            return {"error": str(exc)}
