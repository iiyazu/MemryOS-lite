"""Add curator tables

Revision ID: 0010_add_curator_tables
Revises: 0009_add_context_policy_candidates
Create Date: 2026-10-02
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0010_add_curator_tables"
down_revision: str = "0009_add_context_policy_candidates"
branch_labels: str | None = None
depends_on: str | None = None


def _table_names() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return set(inspector.get_table_names())


def _index_names(table_name: str) -> set[str]:
    if table_name not in _table_names():
        return set()
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    if "curated_memories" not in _table_names():
        op.create_table(
            "curated_memories",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("session_id", sa.String(length=64), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("topic_key", sa.String(length=255), nullable=False),
            sa.Column("statement", sa.Text(), nullable=False),
            sa.Column("sources_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
            sa.Column("supersedes_id", sa.String(length=64), nullable=True),
            sa.Column("superseded_by_id", sa.String(length=64), nullable=True),
            sa.Column("run_id", sa.String(length=64), nullable=False),
            sa.Column("model", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    curated_indexes = _index_names("curated_memories")
    if "ix_curated_memories_session_id" not in curated_indexes:
        op.create_index(
            "ix_curated_memories_session_id",
            "curated_memories",
            ["session_id"],
            unique=False,
        )
    if "ix_curated_memories_session_status" not in curated_indexes:
        op.create_index(
            "ix_curated_memories_session_status",
            "curated_memories",
            ["session_id", "status"],
            unique=False,
        )
    if "ix_curated_memories_session_created" not in curated_indexes:
        op.create_index(
            "ix_curated_memories_session_created",
            "curated_memories",
            ["session_id", "created_at"],
            unique=False,
        )

    if "curator_state" not in _table_names():
        op.create_table(
            "curator_state",
            sa.Column("session_id", sa.String(length=64), primary_key=True),
            sa.Column(
                "last_message_seq",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error_code", sa.String(length=64), nullable=True),
            sa.Column("runs", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("proposals", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "rejected_grounding",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "rejected_schema",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column("llm_errors", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    if "curator_state" in _table_names():
        op.drop_table("curator_state")
    if "curated_memories" in _table_names():
        for index_name in (
            "ix_curated_memories_session_created",
            "ix_curated_memories_session_status",
            "ix_curated_memories_session_id",
        ):
            if index_name in _index_names("curated_memories"):
                op.drop_index(index_name, table_name="curated_memories")
        op.drop_table("curated_memories")
