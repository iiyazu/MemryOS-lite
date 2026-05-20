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


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "episodes" in inspector.get_table_names():
        return

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
    op.create_index("ix_episodes_session_id", "episodes", ["session_id"])
    op.create_index("ix_episodes_message_id", "episodes", ["message_id"])
    op.create_index("ix_episodes_session_position", "episodes", ["session_id", "position"])
    op.create_index("ix_episodes_session_message", "episodes", ["session_id", "message_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "episodes" not in inspector.get_table_names():
        return

    op.drop_index("ix_episodes_session_message", table_name="episodes")
    op.drop_index("ix_episodes_session_position", table_name="episodes")
    op.drop_index("ix_episodes_message_id", table_name="episodes")
    op.drop_index("ix_episodes_session_id", table_name="episodes")
    op.drop_table("episodes")
