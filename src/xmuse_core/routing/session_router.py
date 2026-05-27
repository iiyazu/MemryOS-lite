from __future__ import annotations

import fcntl
import json
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from xmuse_core.agents.god_session_registry import GodSessionRecord, GodSessionRegistry


class SessionRouter:
    def __init__(self, registry: GodSessionRegistry, inbox_root: Path | str) -> None:
        self._registry = registry
        self._inbox_root = Path(inbox_root)

    def route(
        self,
        target_address: str,
        sender_address: str,
        message_type: str,
        payload: dict[str, Any],
    ) -> GodSessionRecord:
        record = self._registry.find_by_address(target_address)
        inbox_path = self._inbox_path(record.session_inbox_id)
        with self._locked_inbox(inbox_path):
            messages = self.read_inbox(record.session_inbox_id)
            messages.append(
                {
                    "sender_address": sender_address,
                    "message_type": message_type,
                    "payload": payload,
                }
            )
            self._write_inbox(inbox_path, messages)
        return record

    def read_inbox(self, inbox_id: str) -> list[dict[str, Any]]:
        inbox_path = self._inbox_path(inbox_id)
        if not inbox_path.exists():
            return []
        return json.loads(inbox_path.read_text())

    def _inbox_path(self, inbox_id: str) -> Path:
        self._validate_inbox_id(inbox_id)
        return self._inbox_root / f"{inbox_id}.json"

    def _write_inbox(self, inbox_path: Path, messages: list[dict[str, Any]]) -> None:
        inbox_path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=inbox_path.parent,
            prefix=f"{inbox_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(messages, handle)
            temp_path = Path(handle.name)
        temp_path.replace(inbox_path)

    def _validate_inbox_id(self, inbox_id: str) -> None:
        if "/" in inbox_id or "\\" in inbox_id or inbox_id in {".", ".."} or ".." in inbox_id.split("/"):
            raise ValueError(f"invalid inbox_id: {inbox_id}")

    @contextmanager
    def _locked_inbox(self, inbox_path: Path):
        lock_path = inbox_path.with_name(f"{inbox_path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
