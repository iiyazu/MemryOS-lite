"""Add superseded_by column to memory_pages

Revision ID: 0002_add_superseded_by
Revises: 0001_m2_baseline
Create Date: 2026-05-15

Adds a nullable ``superseded_by`` column to ``memory_pages`` to track page
supersession at the DB level, enabling efficient filtering without loading
all pages into memory. Backfills existing values from ``content_json``.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_add_superseded_by"
down_revision: str = "0001_m2_baseline"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "memory_pages",
        sa.Column("superseded_by", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_memory_pages_superseded_by", "memory_pages", ["superseded_by"])

    # Backfill from content_json
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            text(
                "UPDATE memory_pages SET superseded_by = content_json::json->>'superseded_by' "
                "WHERE content_json IS NOT NULL "
                "AND content_json::json->>'superseded_by' IS NOT NULL"
            )
        )
    else:  # SQLite
        op.execute(
            text(
                "UPDATE memory_pages SET superseded_by = json_extract(content_json, '$.superseded_by') "
                "WHERE content_json IS NOT NULL "
                "AND json_extract(content_json, '$.superseded_by') IS NOT NULL"
            )
        )


def downgrade() -> None:
    op.drop_index("ix_memory_pages_superseded_by", table_name="memory_pages")
    op.drop_column("memory_pages", "superseded_by")
