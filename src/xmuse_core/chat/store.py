from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from xmuse_core.chat.models import (
    ChatMessage,
    Conversation,
    Proposal,
    ProposalStatus,
    ResolutionStatus,
    StructuredResolution,
)
from xmuse_core.chat.participant_store import (
    _PREDEFINED_TEMPLATES,
    _new_id as _ps_new_id,
)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ChatStore:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def create_conversation(self, title: str) -> Conversation:
        conversation = Conversation(
            id=self._new_id("conv"),
            title=title,
            created_at=_utc_now(),
        )
        with self._connect() as conn:
            conn.execute(
                "insert into conversations (id, title, created_at) values (?, ?, ?)",
                (conversation.id, conversation.title, conversation.created_at),
            )
        return conversation

    def list_conversations(self) -> list[Conversation]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select id, title, created_at
                from conversations
                order by rowid asc
                """
            ).fetchall()
        return [Conversation(**dict(row)) for row in rows]

    def add_message(
        self,
        conversation_id: str,
        author: str,
        role: str,
        content: str,
    ) -> ChatMessage:
        message = ChatMessage(
            id=self._new_id("msg"),
            conversation_id=conversation_id,
            author=author,
            role=role,
            content=content,
            created_at=_utc_now(),
        )
        with self._connect() as conn:
            conn.execute(
                """
                insert into messages (id, conversation_id, author, role, content, created_at)
                values (?, ?, ?, ?, ?, ?)
                """,
                (
                    message.id,
                    message.conversation_id,
                    message.author,
                    message.role,
                    message.content,
                    message.created_at,
                ),
            )
        return message

    def list_messages(self, conversation_id: str) -> list[ChatMessage]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select id, conversation_id, author, role, content, created_at
                from messages
                where conversation_id = ?
                order by rowid asc
                """,
                (conversation_id,),
            ).fetchall()
        return [ChatMessage(**dict(row)) for row in rows]

    def create_proposal(
        self,
        conversation_id: str,
        author: str,
        proposal_type: str,
        content: str,
        references: list[str],
    ) -> Proposal:
        proposal = Proposal(
            id=self._new_id("prop"),
            conversation_id=conversation_id,
            author=author,
            proposal_type=proposal_type,
            content=content,
            references=references,
            created_at=_utc_now(),
        )
        with self._connect() as conn:
            conn.execute(
                """
                insert into proposals (
                    id,
                    conversation_id,
                    author,
                    proposal_type,
                    content,
                    references_json,
                    status,
                    created_at,
                    accepted_resolution_id
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.id,
                    proposal.conversation_id,
                    proposal.author,
                    proposal.proposal_type,
                    proposal.content,
                    json.dumps(proposal.references),
                    proposal.status.value,
                    proposal.created_at,
                    proposal.accepted_resolution_id,
                ),
            )
        return proposal

    def get_proposal(self, proposal_id: str) -> Proposal:
        with self._connect() as conn:
            row = conn.execute("select * from proposals where id = ?", (proposal_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown proposal: {proposal_id}")
        return self._proposal_from_row(row)

    def approve_proposal(
        self,
        proposal_id: str,
        approved_by: list[str],
        approval_mode: str,
        goal_summary: str,
        content: dict | None = None,
    ) -> StructuredResolution:
        proposal = self.get_proposal(proposal_id)
        with self._connect() as conn:
            version = self._next_resolution_version(conn, proposal.conversation_id)
            resolution = StructuredResolution(
                id=self._new_id("res"),
                conversation_id=proposal.conversation_id,
                version=version,
                status=ResolutionStatus.APPROVED,
                derived_from_proposal_ids=[proposal.id],
                approved_by=approved_by,
                approval_mode=approval_mode,
                goal_summary=goal_summary,
                content=content or {},
                created_at=_utc_now(),
            )
            conn.execute(
                """
                insert into resolutions (
                    id,
                    conversation_id,
                    version,
                    status,
                    derived_from_proposal_ids_json,
                    approved_by_json,
                    approval_mode,
                    goal_summary,
                    content_json,
                    created_at,
                    superseded_by_resolution_id
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolution.id,
                    resolution.conversation_id,
                    resolution.version,
                    resolution.status.value,
                    json.dumps(resolution.derived_from_proposal_ids),
                    json.dumps(resolution.approved_by),
                    resolution.approval_mode,
                    resolution.goal_summary,
                    json.dumps(resolution.content),
                    resolution.created_at,
                    resolution.superseded_by_resolution_id,
                ),
            )
            conn.execute(
                """
                update proposals
                set status = ?, accepted_resolution_id = ?
                where id = ?
                """,
                (ProposalStatus.ACCEPTED.value, resolution.id, proposal.id),
            )
        return resolution

    def create_resolution_version(
        self,
        prior_resolution_id: str,
        approved_by: list[str],
        approval_mode: str,
        goal_summary: str,
        content: dict | None = None,
    ) -> StructuredResolution:
        prior = self.get_resolution(prior_resolution_id)
        with self._connect() as conn:
            resolution = StructuredResolution(
                id=self._new_id("res"),
                conversation_id=prior.conversation_id,
                version=prior.version + 1,
                status=ResolutionStatus.APPROVED,
                derived_from_proposal_ids=list(prior.derived_from_proposal_ids),
                approved_by=approved_by,
                approval_mode=approval_mode,
                goal_summary=goal_summary,
                content=prior.content if content is None else content,
                created_at=_utc_now(),
            )
            conn.execute(
                """
                insert into resolutions (
                    id,
                    conversation_id,
                    version,
                    status,
                    derived_from_proposal_ids_json,
                    approved_by_json,
                    approval_mode,
                    goal_summary,
                    content_json,
                    created_at,
                    superseded_by_resolution_id
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolution.id,
                    resolution.conversation_id,
                    resolution.version,
                    resolution.status.value,
                    json.dumps(resolution.derived_from_proposal_ids),
                    json.dumps(resolution.approved_by),
                    resolution.approval_mode,
                    resolution.goal_summary,
                    json.dumps(resolution.content),
                    resolution.created_at,
                    resolution.superseded_by_resolution_id,
                ),
            )
            conn.execute(
                """
                update resolutions
                set status = ?, superseded_by_resolution_id = ?
                where id = ?
                """,
                (ResolutionStatus.SUPERSEDED.value, resolution.id, prior.id),
            )
        return resolution

    def get_resolution(self, resolution_id: str) -> StructuredResolution:
        with self._connect() as conn:
            row = conn.execute("select * from resolutions where id = ?", (resolution_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown resolution: {resolution_id}")
        return self._resolution_from_row(row)

    def list_resolutions(self, conversation_id: str | None = None) -> list[StructuredResolution]:
        query = "select * from resolutions"
        params: tuple[str, ...] = ()
        if conversation_id is not None:
            query += " where conversation_id = ?"
            params = (conversation_id,)
        query += " order by conversation_id asc, version asc"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._resolution_from_row(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys = on")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                create table if not exists conversations (
                    id text primary key,
                    title text not null,
                    created_at text not null
                );

                create table if not exists messages (
                    id text primary key,
                    conversation_id text not null references conversations(id),
                    author text not null,
                    role text not null,
                    content text not null,
                    created_at text not null
                );

                create table if not exists proposals (
                    id text primary key,
                    conversation_id text not null references conversations(id),
                    author text not null,
                    proposal_type text not null,
                    content text not null,
                    references_json text not null,
                    status text not null,
                    created_at text not null,
                    accepted_resolution_id text
                );

                create table if not exists resolutions (
                    id text primary key,
                    conversation_id text not null references conversations(id),
                    version integer not null,
                    status text not null,
                    derived_from_proposal_ids_json text not null,
                    approved_by_json text not null,
                    approval_mode text not null,
                    goal_summary text not null,
                    content_json text not null default '{}',
                    created_at text not null,
                    superseded_by_resolution_id text,
                    unique(conversation_id, version)
                );

                create table if not exists participants (
                    participant_id text primary key,
                    conversation_id text not null references conversations(id),
                    role text not null,
                    display_name text not null,
                    cli_kind text not null,
                    model text not null,
                    role_template_id text,
                    status text not null,
                    last_seen_at text,
                    created_at text not null
                );

                create table if not exists role_templates (
                    id text primary key,
                    slug text not null unique,
                    display_name text not null,
                    prompt text not null,
                    cli_kind text not null,
                    default_model text not null,
                    predefined integer not null default 0,
                    created_at text not null,
                    updated_at text not null
                );
                """
            )
            self._ensure_column(conn, "resolutions", "content_json", "text not null default '{}'")
        self._seed_role_templates()

    def _seed_role_templates(self) -> None:
        """Insert the three predefined role templates if not already present."""
        now = _utc_now()
        with self._connect() as conn:
            for tpl in _PREDEFINED_TEMPLATES:
                existing = conn.execute(
                    "select id from role_templates where slug = ?",
                    (tpl["slug"],),
                ).fetchone()
                if existing is not None:
                    continue
                conn.execute(
                    """
                    insert into role_templates (
                        id, slug, display_name, prompt, cli_kind,
                        default_model, predefined, created_at, updated_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _ps_new_id("tmpl"),
                        tpl["slug"],
                        tpl["display_name"],
                        tpl["prompt"],
                        tpl["cli_kind"],
                        tpl["default_model"],
                        1,  # predefined = true
                        now,
                        now,
                    ),
                )

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

    def _next_resolution_version(self, conn: sqlite3.Connection, conversation_id: str) -> int:
        row = conn.execute(
            "select coalesce(max(version), 0) as max_version from resolutions where conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        return int(row["max_version"]) + 1

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex}"

    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        definition: str,
    ) -> None:
        rows = conn.execute(f"pragma table_info({table_name})").fetchall()
        existing = {str(row["name"]) for row in rows}
        if column_name not in existing:
            conn.execute(f"alter table {table_name} add column {column_name} {definition}")
