"""Add episodes table

Revision ID: 0004_add_episodes
Revises: 0003_add_memory_items
Create Date: 2026-05-20
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0004_add_episodes"
down_revision: str = "0003_add_memory_items"
branch_labels: str | None = None
depends_on: str | None = None


def _index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _create_index_if_missing(index_name: str, columns: list[str]) -> None:
    if index_name not in _index_names("episodes"):
        op.create_index(index_name, "episodes", columns)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "episodes" not in inspector.get_table_names():
        op.create_table(
            "episodes",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("session_id", sa.String(length=64), nullable=False),
            sa.Column("message_id", sa.String(length=64), nullable=False),
            sa.Column("role", sa.String(length=32), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("index_text", sa.Text(), nullable=False),
            sa.Column("benchmark_session_id", sa.String(length=64), nullable=True),
            sa.Column("benchmark_date", sa.String(length=32), nullable=True),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("source_message_ids_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("embedding", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    _create_index_if_missing("ix_episodes_session_id", ["session_id"])
    _create_index_if_missing("ix_episodes_message_id", ["message_id"])
    _create_index_if_missing("ix_episodes_session_position", ["session_id", "position"])
    _create_index_if_missing("ix_episodes_session_message", ["session_id", "message_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "episodes" not in inspector.get_table_names():
        return

    existing_indexes = _index_names("episodes")
    if "ix_episodes_session_message" in existing_indexes:
        op.drop_index("ix_episodes_session_message", table_name="episodes")
    if "ix_episodes_session_position" in existing_indexes:
        op.drop_index("ix_episodes_session_position", table_name="episodes")
    if "ix_episodes_message_id" in existing_indexes:
        op.drop_index("ix_episodes_message_id", table_name="episodes")
    if "ix_episodes_session_id" in existing_indexes:
        op.drop_index("ix_episodes_session_id", table_name="episodes")
    op.drop_table("episodes")
