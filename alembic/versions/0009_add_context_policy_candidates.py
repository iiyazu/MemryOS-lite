"""Add context policy candidates

Revision ID: 0009_add_context_policy_candidates
Revises: 0008_add_promotion_candidates
Create Date: 2026-06-03
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0009_add_context_policy_candidates"
down_revision: str = "0008_add_promotion_candidates"
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
    if "context_policy_candidates" not in _table_names():
        op.create_table(
            "context_policy_candidates",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("session_id", sa.String(length=64), nullable=False),
            sa.Column("policy_type", sa.String(length=32), nullable=False),
            sa.Column("feedback_type", sa.String(length=64), nullable=False),
            sa.Column("suggested_action", sa.Text(), nullable=False),
            sa.Column(
                "source_refs_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            ),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("fingerprint", sa.String(length=128), nullable=False),
            sa.Column(
                "metadata_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    indexes = _index_names("context_policy_candidates")
    if "ix_context_policy_candidates_session_id" not in indexes:
        op.create_index(
            "ix_context_policy_candidates_session_id",
            "context_policy_candidates",
            ["session_id"],
            unique=False,
        )
    if "ix_context_policy_candidates_policy_type" not in indexes:
        op.create_index(
            "ix_context_policy_candidates_policy_type",
            "context_policy_candidates",
            ["policy_type"],
            unique=False,
        )
    if "ix_context_policy_candidates_feedback_type" not in indexes:
        op.create_index(
            "ix_context_policy_candidates_feedback_type",
            "context_policy_candidates",
            ["feedback_type"],
            unique=False,
        )
    if "ix_context_policy_candidates_status" not in indexes:
        op.create_index(
            "ix_context_policy_candidates_status",
            "context_policy_candidates",
            ["status"],
            unique=False,
        )
    if "ix_context_policy_candidates_fingerprint" not in indexes:
        op.create_index(
            "ix_context_policy_candidates_fingerprint",
            "context_policy_candidates",
            ["fingerprint"],
            unique=True,
        )
    if "ix_context_policy_candidates_status_created" not in indexes:
        op.create_index(
            "ix_context_policy_candidates_status_created",
            "context_policy_candidates",
            ["status", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    if "context_policy_candidates" in _table_names():
        for index_name in (
            "ix_context_policy_candidates_status_created",
            "ix_context_policy_candidates_fingerprint",
            "ix_context_policy_candidates_status",
            "ix_context_policy_candidates_feedback_type",
            "ix_context_policy_candidates_policy_type",
            "ix_context_policy_candidates_session_id",
        ):
            if index_name in _index_names("context_policy_candidates"):
                op.drop_index(index_name, table_name="context_policy_candidates")
        op.drop_table("context_policy_candidates")
