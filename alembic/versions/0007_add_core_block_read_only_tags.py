"""Add read_only and tags to core memory blocks

Revision ID: 0007_add_core_block_read_only_tags
Revises: 0006_add_archival_memory
Create Date: 2026-05-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0007_add_core_block_read_only_tags"
down_revision: str = "0006_add_archival_memory"
branch_labels: str | None = None
depends_on: str | None = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in set(inspector.get_table_names()):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _column_names("core_memory_blocks")
    if "read_only" not in columns:
        op.add_column(
            "core_memory_blocks",
            sa.Column(
                "read_only",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    if "tags_json" not in columns:
        op.add_column(
            "core_memory_blocks",
            sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"),
        )


def downgrade() -> None:
    columns = _column_names("core_memory_blocks")
    if "tags_json" in columns:
        op.drop_column("core_memory_blocks", "tags_json")
    if "read_only" in columns:
        op.drop_column("core_memory_blocks", "read_only")
