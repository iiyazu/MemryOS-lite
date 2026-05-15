"""Add memory_items table

Revision ID: 0003_add_memory_items
Revises: 0002_add_superseded_by
Create Date: 2026-05-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0003_add_memory_items"
down_revision: str = "0002_add_superseded_by"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "memory_items",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("page_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("item_type", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_message_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_memory_items_page_id", "memory_items", ["page_id"])
    op.create_index("ix_memory_items_session_id", "memory_items", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_memory_items_session_id", table_name="memory_items")
    op.drop_index("ix_memory_items_page_id", table_name="memory_items")
    op.drop_table("memory_items")
