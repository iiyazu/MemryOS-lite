"""Callback enqueue mechanism for mid-execution agent communication.

Design reference: cat-cafe-tutorials/05-mcp-callback.md
Slaves use callbacks to push @mentions to the worklist during execution,
instead of independently launching agents (prevents dual-fire).

The key insight from F27: callback handlers no longer execute agents
independently. They append targets to the parent worklist and return.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from xmuse_core.routing.mentions import parse_mentions
from xmuse_core.routing.worklist import Worklist


@dataclass
class CallbackCredentials:
    """Dual-UUID token pair scoped to a single invocation."""

    invocation_id: str
    callback_token: str
    agent_id: str
    loop_id: str
    issued_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class CallbackRouter:
    """Routes callback messages through the unified worklist.

    Instead of independently dispatching agents on @mention detection,
    callbacks enqueue targets into the parent worklist. This is the
    core F27 fix that eliminates dual-fire and enables shared
    cancellation/depth-limiting.
    """

    def __init__(self, worklist: Worklist) -> None:
        self._worklist = worklist
        self._credentials: dict[str, CallbackCredentials] = {}
        self._log: list[dict[str, Any]] = []

    def register(self, creds: CallbackCredentials) -> None:
        self._credentials[creds.invocation_id] = creds

    def revoke(self, invocation_id: str) -> bool:
        return self._credentials.pop(invocation_id, None) is not None

    def validate(self, invocation_id: str, token: str) -> CallbackCredentials | None:
        creds = self._credentials.get(invocation_id)
        if creds is None or creds.callback_token != token:
            return None
        return creds

    def post_message(
        self, invocation_id: str, token: str, content: str
    ) -> dict[str, Any]:
        """Process a callback message. Parse @mentions and enqueue targets.

        Returns routing result with enqueued targets and any errors.
        """
        creds = self.validate(invocation_id, token)
        if creds is None:
            return {"ok": False, "error": "invalid_credentials", "enqueued": []}

        targets = parse_mentions(content, source_id=creds.agent_id)
        enqueued: list[str] = []
        for target in targets:
            if self._worklist.enqueue(target, source_id=creds.agent_id):
                enqueued.append(target)

        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "agent_id": creds.agent_id,
            "targets": targets,
            "enqueued": enqueued,
        }
        self._log.append(entry)
        return {"ok": True, "enqueued": enqueued, "targets": targets}

    def history(self) -> list[dict[str, Any]]:
        return list(self._log)
