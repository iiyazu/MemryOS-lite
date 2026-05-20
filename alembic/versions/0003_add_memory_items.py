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


def _index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _create_index_if_missing(index_name: str, columns: list[str]) -> None:
    if index_name not in _index_names("memory_items"):
        op.create_index(index_name, "memory_items", columns)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "memory_items" not in inspector.get_table_names():
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
    _create_index_if_missing("ix_memory_items_page_id", ["page_id"])
    _create_index_if_missing("ix_memory_items_session_id", ["session_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "memory_items" not in inspector.get_table_names():
        return

    existing_indexes = _index_names("memory_items")
    if "ix_memory_items_session_id" in existing_indexes:
        op.drop_index("ix_memory_items_session_id", table_name="memory_items")
    if "ix_memory_items_page_id" in existing_indexes:
        op.drop_index("ix_memory_items_page_id", table_name="memory_items")
    op.drop_table("memory_items")
