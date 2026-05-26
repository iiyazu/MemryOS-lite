#!/usr/bin/env python3
"""Xmuse error-pattern memory.

This module is intentionally kept under the runtime ``xmuse/`` directory
without making that directory an import package. Runtime integrations should
load it by file path.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
DEFAULT_STORE = Path(__file__).with_name("error_knowledge.json")
SLOTS = (
    "pit",
    "root_cause",
    "trigger",
    "fix",
    "verification",
    "lesson",
    "scope",
)
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "no",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
}


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9_]+", text.lower())
        if len(token) > 1 and token not in STOPWORDS
    }


def _compact(text: str, *, limit: int = 500) -> str:
    value = " ".join(line.strip() for line in text.splitlines() if line.strip())
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _extract_pit(error_output: str) -> str:
    lines = [line.strip() for line in error_output.splitlines() if line.strip()]
    for line in reversed(lines):
        if re.search(r"(?:[A-Za-z_]*Error|[A-Za-z_]*Exception|AssertionError):", line):
            return _compact(line, limit=240)
    if lines:
        return _compact(lines[-1], limit=240)
    return "Unknown failure"


def _extract_root_cause(pit: str, error_output: str) -> str:
    module_match = re.search(r"No module named ['\"]([^'\"]+)['\"]", pit)
    if module_match:
        return f"Missing Python module: {module_match.group(1)}"
    file_match = re.search(r"No such file or directory: ['\"]([^'\"]+)['\"]", pit)
    if file_match:
        return f"Missing required file: {file_match.group(1)}"
    if pit.startswith("AssertionError"):
        detail = pit.split(":", 1)[1].strip() if ":" in pit else ""
        return _compact(f"Assertion failed: {detail}" if detail else "Assertion failed")
    if "mypy" in error_output.lower():
        return "Static type check failed"
    if "pytest" in error_output.lower() and "failed" in error_output.lower():
        return "Test suite failure"
    return _compact(f"Unclassified failure: {pit}", limit=240)


def _entry_id(lane_id: str, pit: str, root_cause: str) -> str:
    digest = hashlib.sha256(f"{lane_id}\n{pit}\n{root_cause}".encode("utf-8")).hexdigest()
    return f"err-{digest[:16]}"


class ErrorKnowledge:
    """JSON-backed error pattern registry."""

    def __init__(self, path: str | Path = DEFAULT_STORE) -> None:
        self.path = Path(path)

    def record_failure(
        self,
        lane_id: str,
        error_output: str,
        fix_output: str | None = None,
    ) -> dict[str, Any]:
        """Record a failure and return the stored seven-slot entry."""

        data = self._load()
        pit = _extract_pit(error_output)
        root_cause = _extract_root_cause(pit, error_output)
        entry_id = _entry_id(lane_id, pit, root_cause)
        now = _utc_now()

        existing = self._find_entry(data, entry_id)
        if existing is not None:
            existing["occurrences"] = int(existing.get("occurrences", 1)) + 1
            existing["last_seen_at"] = now
            if fix_output and not existing.get("fix"):
                existing["fix"] = _compact(fix_output)
            self._save(data)
            return dict(existing)

        entry: dict[str, Any] = {
            "id": entry_id,
            "schema_version": SCHEMA_VERSION,
            "lane_id": lane_id,
            "resolved": False,
            "occurrences": 1,
            "created_at": now,
            "last_seen_at": now,
            "pit": pit,
            "root_cause": root_cause,
            "trigger": lane_id,
            "fix": _compact(fix_output or ""),
            "verification": "",
            "lesson": "",
            "scope": lane_id,
        }
        data["entries"].append(entry)
        self._save(data)
        return dict(entry)

    def find_relevant(self, prompt: str, top_k: int = 3) -> list[dict[str, Any]]:
        """Return entries whose keyword overlap is strongest for the prompt."""

        if top_k <= 0:
            return []
        data = self._load()
        prompt_tokens = _tokens(prompt)
        if not prompt_tokens:
            return []

        scored: list[tuple[int, str, dict[str, Any]]] = []
        for entry in data["entries"]:
            haystack = " ".join(str(entry.get(field, "")) for field in (*SLOTS, "lane_id"))
            entry_tokens = _tokens(haystack)
            score = len(prompt_tokens & entry_tokens)
            if entry.get("resolved") and entry.get("lesson"):
                score += len(prompt_tokens & _tokens(str(entry["lesson"])))
            if score > 0:
                scored.append((score, str(entry.get("last_seen_at", "")), entry))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [dict(entry) for _, _, entry in scored[:top_k]]

    def inject_context(self, prompt: str) -> str:
        """Prepend relevant lessons to a dispatch prompt."""

        entries = self.find_relevant(prompt)
        if not entries:
            return prompt

        lines = ["# Relevant Error Knowledge"]
        for entry in entries:
            lines.append(f"- Scope: {entry.get('scope', '')}")
            lines.append(f"  Pit: {entry.get('pit', '')}")
            lines.append(f"  Root cause: {entry.get('root_cause', '')}")
            if entry.get("fix"):
                lines.append(f"  Fix: {entry['fix']}")
            if entry.get("verification"):
                lines.append(f"  Verification: {entry['verification']}")
            if entry.get("lesson"):
                lines.append(f"  Lesson: {entry['lesson']}")
        return "\n".join(lines) + "\n\n---\n\n" + prompt

    def mark_resolved(
        self,
        entry_id: str,
        fix: str,
        verification: str,
        lesson: str,
    ) -> dict[str, Any]:
        """Fill resolution slots for an existing entry."""

        data = self._load()
        entry = self._find_entry(data, entry_id)
        if entry is None:
            raise KeyError(f"unknown error knowledge entry: {entry_id}")

        entry["fix"] = _compact(fix)
        entry["verification"] = _compact(verification)
        entry["lesson"] = _compact(lesson)
        entry["resolved"] = True
        entry["resolved_at"] = _utc_now()
        self._save(data)
        return dict(entry)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": SCHEMA_VERSION, "entries": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"schema_version": SCHEMA_VERSION, "entries": []}
        if not isinstance(data, dict):
            return {"schema_version": SCHEMA_VERSION, "entries": []}
        entries = data.get("entries")
        if not isinstance(entries, list):
            data["entries"] = []
        data.setdefault("schema_version", SCHEMA_VERSION)
        return data

    def _save(self, data: dict[str, Any]) -> None:
        data["schema_version"] = SCHEMA_VERSION
        _atomic_write_json(self.path, data)

    @staticmethod
    def _find_entry(data: dict[str, Any], entry_id: str) -> dict[str, Any] | None:
        for entry in data.get("entries", []):
            if isinstance(entry, dict) and entry.get("id") == entry_id:
                return entry
        return None
