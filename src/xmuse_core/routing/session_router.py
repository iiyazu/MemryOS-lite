from __future__ import annotations

import json
from pathlib import Path
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
        messages = self.read_inbox(record.session_inbox_id)
        messages.append(
            {
                "sender_address": sender_address,
                "message_type": message_type,
                "payload": payload,
            }
        )
        inbox_path = self._inbox_path(record.session_inbox_id)
        inbox_path.parent.mkdir(parents=True, exist_ok=True)
        inbox_path.write_text(json.dumps(messages))
        return record

    def read_inbox(self, inbox_id: str) -> list[dict[str, Any]]:
        inbox_path = self._inbox_path(inbox_id)
        if not inbox_path.exists():
            return []
        return json.loads(inbox_path.read_text())

    def _inbox_path(self, inbox_id: str) -> Path:
        return self._inbox_root / f"{inbox_id}.json"
