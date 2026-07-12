"""Add core memory tables

Revision ID: 0005_add_core_memory
Revises: 0004_add_episodes
Create Date: 2026-05-21
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0005_add_core_memory"
down_revision: str = "0004_add_episodes"
branch_labels: str | None = None
depends_on: str | None = None


def _table_names() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return set(inspector.get_table_names())


def upgrade() -> None:
    existing = _table_names()
    if "core_memory_blocks" not in existing:
        op.create_table(
            "core_memory_blocks",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("label", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("value", sa.Text(), nullable=False, server_default=""),
            sa.Column("limit_tokens", sa.Integer(), nullable=False),
            sa.Column("source_refs_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_by_event_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_core_memory_blocks_created",
            "core_memory_blocks",
            ["created_at"],
        )
    if "core_memory_history" not in existing:
        op.create_table(
            "core_memory_history",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("memory_id", sa.String(length=64), nullable=False),
            sa.Column("memory_type", sa.String(length=32), nullable=False),
            sa.Column("operation", sa.String(length=32), nullable=False),
            sa.Column("actor", sa.String(length=16), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("source_refs_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("before_json", sa.Text(), nullable=True),
            sa.Column("after_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_core_memory_history_memory_id",
            "core_memory_history",
            ["memory_id"],
        )
        op.create_index(
            "ix_core_memory_history_memory_created",
            "core_memory_history",
            ["memory_id", "created_at"],
        )


def downgrade() -> None:
    existing = _table_names()
    if "core_memory_history" in existing:
        op.drop_index("ix_core_memory_history_memory_created", table_name="core_memory_history")
        op.drop_index("ix_core_memory_history_memory_id", table_name="core_memory_history")
        op.drop_table("core_memory_history")
    if "core_memory_blocks" in existing:
        op.drop_index("ix_core_memory_blocks_created", table_name="core_memory_blocks")
        op.drop_table("core_memory_blocks")
