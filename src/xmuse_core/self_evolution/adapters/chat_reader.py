from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from xmuse_core.chat.models import (
    Conversation,
    Proposal,
    ProposalStatus,
    ResolutionStatus,
    StructuredResolution,
)


class ChatReader:
    """Read-only adapter for xmuse chat.db."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)

    def get_resolution(self, id: str) -> StructuredResolution:
        with self._connect() as conn:
            row = conn.execute("select * from resolutions where id = ?", (id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown resolution: {id}")
        return self._resolution_from_row(row)

    def get_proposal(self, id: str) -> Proposal:
        with self._connect() as conn:
            row = conn.execute("select * from proposals where id = ?", (id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown proposal: {id}")
        return self._proposal_from_row(row)

    def list_conversations(self) -> list[Conversation]:
        if not self._db_path.exists():
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                select id, title, created_at
                from conversations
                order by rowid asc
                """
            ).fetchall()
        return [Conversation(**dict(row)) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys = on")
        return conn

    def _proposal_from_row(self, row: sqlite3.Row) -> Proposal:
        payload = dict(row)
        return Proposal(
            id=payload["id"],
            conversation_id=payload["conversation_id"],
            author=payload["author"],
            proposal_type=payload["proposal_type"],
            content=payload["content"],
            references=json.loads(payload["references_json"]),
            status=ProposalStatus(payload["status"]),
            created_at=payload["created_at"],
            accepted_resolution_id=payload["accepted_resolution_id"],
        )

    def _resolution_from_row(self, row: sqlite3.Row) -> StructuredResolution:
        payload = dict(row)
        return StructuredResolution(
            id=payload["id"],
            conversation_id=payload["conversation_id"],
            version=payload["version"],
            status=ResolutionStatus(payload["status"]),
            derived_from_proposal_ids=json.loads(payload["derived_from_proposal_ids_json"]),
            approved_by=json.loads(payload["approved_by_json"]),
            approval_mode=payload["approval_mode"],
            goal_summary=payload["goal_summary"],
            content=json.loads(payload.get("content_json") or "{}"),
            created_at=payload["created_at"],
            superseded_by_resolution_id=payload["superseded_by_resolution_id"],
        )
