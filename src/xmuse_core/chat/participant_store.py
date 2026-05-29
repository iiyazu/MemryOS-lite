"""SQLite-backed stores for chat participants and role templates.

Participant and RoleTemplate Pydantic models match the type signatures in
xmuse/FRONTEND_VISION.md (Layer 1 contract).  The stores share the same
chat.db connection that ChatStore uses; they are initialised by ChatStore._init_db
via two CREATE TABLE IF NOT EXISTS statements added there.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


# ---------------------------------------------------------------------------
# Pydantic models (match FRONTEND_VISION.md type signatures exactly)
# ---------------------------------------------------------------------------

class Participant(BaseModel):
    participant_id: str
    conversation_id: str
    role: str
    display_name: str
    cli_kind: Literal["claude", "codex"]
    model: str
    role_template_id: str | None
    status: Literal["active", "stopped"]
    last_seen_at: str | None
    created_at: str


class RoleTemplate(BaseModel):
    id: str
    slug: str
    display_name: str
    prompt: str
    cli_kind: Literal["claude", "codex"]
    default_model: str
    predefined: bool
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# ParticipantStore
# ---------------------------------------------------------------------------

class ParticipantStore:
    """CRUD store for the `participants` table in chat.db."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(
        self,
        *,
        conversation_id: str,
        role: str,
        display_name: str,
        cli_kind: Literal["claude", "codex"],
        model: str,
        role_template_id: str | None = None,
        status: Literal["active", "stopped"] = "active",
    ) -> Participant:
        participant = Participant(
            participant_id=_new_id("part"),
            conversation_id=conversation_id,
            role=role,
            display_name=display_name,
            cli_kind=cli_kind,
            model=model,
            role_template_id=role_template_id,
            status=status,
            last_seen_at=None,
            created_at=_utc_now(),
        )
        with self._connect() as conn:
            conn.execute(
                """
                insert into participants (
                    participant_id, conversation_id, role, display_name,
                    cli_kind, model, role_template_id, status,
                    last_seen_at, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    participant.participant_id,
                    participant.conversation_id,
                    participant.role,
                    participant.display_name,
                    participant.cli_kind,
                    participant.model,
                    participant.role_template_id,
                    participant.status,
                    participant.last_seen_at,
                    participant.created_at,
                ),
            )
        return participant

    def get(self, participant_id: str) -> Participant:
        with self._connect() as conn:
            row = conn.execute(
                "select * from participants where participant_id = ?",
                (participant_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown participant: {participant_id}")
        return self._from_row(row)

    def list_by_conversation(self, conversation_id: str) -> list[Participant]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select * from participants
                where conversation_id = ?
                order by rowid asc
                """,
                (conversation_id,),
            ).fetchall()
        return [self._from_row(r) for r in rows]

    def update_status(
        self,
        participant_id: str,
        status: Literal["active", "stopped"],
        last_seen_at: str | None = None,
    ) -> Participant:
        now = last_seen_at or _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                update participants
                set status = ?, last_seen_at = ?
                where participant_id = ?
                """,
                (status, now, participant_id),
            )
        return self.get(participant_id)

    def delete(self, participant_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "delete from participants where participant_id = ?",
                (participant_id,),
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys = on")
        return conn

    def _from_row(self, row: sqlite3.Row) -> Participant:
        d = dict(row)
        return Participant(
            participant_id=d["participant_id"],
            conversation_id=d["conversation_id"],
            role=d["role"],
            display_name=d["display_name"],
            cli_kind=d["cli_kind"],
            model=d["model"],
            role_template_id=d.get("role_template_id"),
            status=d["status"],
            last_seen_at=d.get("last_seen_at"),
            created_at=d["created_at"],
        )


# ---------------------------------------------------------------------------
# RoleTemplateStore
# ---------------------------------------------------------------------------

# Prompts for 'architect' and 'review' are sourced from
# xmuse_core/chat/driver.py:_ROLE_PROMPTS and kept here verbatim so the store
# can seed them without importing the driver.
#
# NOTE: 'execute' is NOT present in driver.py:_ROLE_PROMPTS (driver.py only
# defines architect and review).  The execute prompt below was authored here
# directly.  A future lane that wires ChatDriver to ParticipantStore should
# reconcile the two by adding 'execute' to driver.py:_ROLE_PROMPTS and
# sourcing it from there.
_PREDEFINED_TEMPLATES: list[dict] = [
    {
        "slug": "architect",
        "display_name": "Architect GOD",
        "prompt": (
            "You are the Architect GOD of xmuse, a multi-agent autonomous "
            "delivery system. You participate in a group chat with a human "
            "operator and other GODs (review, etc).\n\n"
            "Your job: read the conversation, understand what the human or "
            "another GOD is asking for, and respond. You may:\n"
            "- ask a clarifying question\n"
            "- propose a concrete next step\n"
            "- @mention another GOD if their input is needed\n"
            "- emit a structured proposal that, when approved, becomes a lane "
            "graph the platform will execute\n\n"
            "Output format (strict): emit ONE of:\n"
            '  {"type": "message", "text": "<reply text>"}\n'
            '  {"type": "mention", "to": "review", "text": "<reply text>"}\n'
            '  {"type": "proposal", "summary": "<short>", "lanes": [{"feature_id": "...", '
            '"prompt": "...", "depends_on": [], "capabilities": ["code"], '
            '"feature_group": "..."}]}\n\n'
            "Always output ONLY the JSON object, no markdown fence, no commentary. "
            "If unsure, emit type=message asking for clarification."
        ),
        "cli_kind": "claude",
        "default_model": "sonnet",
    },
    {
        "slug": "review",
        "display_name": "Review GOD",
        "prompt": (
            "You are the Review GOD of xmuse. You participate in the group "
            "chat to evaluate proposals from the architect or human.\n\n"
            "When you respond, emit ONE of:\n"
            '  {"type": "message", "text": "<reply text>"}\n'
            '  {"type": "verdict", "decision": "approve"|"narrow"|"reject", "rationale": "<short>"}\n\n'
            "Always output ONLY the JSON object, no markdown fence, no commentary."
        ),
        "cli_kind": "claude",
        "default_model": "sonnet",
    },
    {
        "slug": "execute",
        "display_name": "Execute GOD",
        "prompt": (
            "You are the Execute GOD of xmuse. You implement lanes inside the "
            "worktree. You do not escape the sandbox or run arbitrary shell "
            "commands outside the allowed tool set.\n\n"
            "When you respond, emit ONE of:\n"
            '  {"type": "message", "text": "<status update>"}\n'
            '  {"type": "done", "summary": "<what was implemented>"}\n\n'
            "Always output ONLY the JSON object, no markdown fence, no commentary."
        ),
        "cli_kind": "claude",
        "default_model": "sonnet",
    },
]


class RoleTemplateStore:
    """CRUD store for the `role_templates` table in chat.db.

    On first init the three predefined templates (architect, review, execute)
    are seeded automatically.  Predefined templates cannot be deleted via
    :meth:`delete` (raises ``ValueError``).
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._seed_predefined()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_all(self) -> list[RoleTemplate]:
        with self._connect() as conn:
            rows = conn.execute(
                "select * from role_templates order by rowid asc"
            ).fetchall()
        return [self._from_row(r) for r in rows]

    def get(self, template_id: str) -> RoleTemplate:
        with self._connect() as conn:
            row = conn.execute(
                "select * from role_templates where id = ?",
                (template_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown role_template: {template_id}")
        return self._from_row(row)

    def get_by_slug(self, slug: str) -> RoleTemplate | None:
        with self._connect() as conn:
            row = conn.execute(
                "select * from role_templates where slug = ?",
                (slug,),
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def create(
        self,
        *,
        slug: str,
        display_name: str,
        prompt: str,
        cli_kind: Literal["claude", "codex"],
        default_model: str,
    ) -> RoleTemplate:
        now = _utc_now()
        template = RoleTemplate(
            id=_new_id("tmpl"),
            slug=slug,
            display_name=display_name,
            prompt=prompt,
            cli_kind=cli_kind,
            default_model=default_model,
            predefined=False,
            created_at=now,
            updated_at=now,
        )
        with self._connect() as conn:
            conn.execute(
                """
                insert into role_templates (
                    id, slug, display_name, prompt, cli_kind,
                    default_model, predefined, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    template.id,
                    template.slug,
                    template.display_name,
                    template.prompt,
                    template.cli_kind,
                    template.default_model,
                    1 if template.predefined else 0,
                    template.created_at,
                    template.updated_at,
                ),
            )
        return template

    def update(
        self,
        template_id: str,
        *,
        display_name: str | None = None,
        prompt: str | None = None,
        cli_kind: Literal["claude", "codex"] | None = None,
        default_model: str | None = None,
    ) -> RoleTemplate:
        existing = self.get(template_id)
        now = _utc_now()
        new_display_name = display_name if display_name is not None else existing.display_name
        new_prompt = prompt if prompt is not None else existing.prompt
        new_cli_kind = cli_kind if cli_kind is not None else existing.cli_kind
        new_default_model = default_model if default_model is not None else existing.default_model
        with self._connect() as conn:
            conn.execute(
                """
                update role_templates
                set display_name = ?, prompt = ?, cli_kind = ?,
                    default_model = ?, updated_at = ?
                where id = ?
                """,
                (new_display_name, new_prompt, new_cli_kind, new_default_model, now, template_id),
            )
        return self.get(template_id)

    def delete(self, template_id: str) -> None:
        existing = self.get(template_id)
        if existing.predefined:
            raise ValueError(f"cannot delete predefined role template: {existing.slug!r}")
        with self._connect() as conn:
            conn.execute("delete from role_templates where id = ?", (template_id,))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys = on")
        return conn

    def _seed_predefined(self) -> None:
        """Insert the three builtin templates if they are not yet present."""
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
                        _new_id("tmpl"),
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

    def _from_row(self, row: sqlite3.Row) -> RoleTemplate:
        d = dict(row)
        return RoleTemplate(
            id=d["id"],
            slug=d["slug"],
            display_name=d["display_name"],
            prompt=d["prompt"],
            cli_kind=d["cli_kind"],
            default_model=d["default_model"],
            predefined=bool(d["predefined"]),
            created_at=d["created_at"],
            updated_at=d["updated_at"],
        )
