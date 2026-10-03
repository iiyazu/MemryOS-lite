"""Add version, occurrence, and scope columns for deterministic curation

Revision ID: 0011_curated_memory_versions
Revises: 0010_add_curator_tables
Create Date: 2026-10-02
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0011_curated_memory_versions"
down_revision: str = "0010_add_curator_tables"
branch_labels: str | None = None
depends_on: str | None = None

CURATED_COLUMNS = (
    ("version", sa.Integer(), "0"),
    ("occurrences", sa.Integer(), "1"),
)
NULLABLE_CURATED_COLUMNS = (
    ("scope_type", sa.String(length=32)),
    ("scope_id", sa.String(length=255)),
)
SESSION_COLUMNS = (
    ("scope_type", sa.String(length=32)),
    ("scope_id", sa.String(length=255)),
)


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in set(inspector.get_table_names()):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    curated = _columns("curated_memories")
    for name, type_, default in CURATED_COLUMNS:
        if curated and name not in curated:
            op.add_column(
                "curated_memories",
                sa.Column(name, type_, nullable=False, server_default=default),
            )
    for name, type_ in NULLABLE_CURATED_COLUMNS:
        if curated and name not in curated:
            op.add_column("curated_memories", sa.Column(name, type_, nullable=True))
    sessions = _columns("sessions")
    for name, type_ in SESSION_COLUMNS:
        if sessions and name not in sessions:
            op.add_column("sessions", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    curated = _columns("curated_memories")
    for name in ("scope_id", "scope_type", "occurrences", "version"):
        if name in curated:
            op.drop_column("curated_memories", name)
    sessions = _columns("sessions")
    for name in ("scope_id", "scope_type"):
        if name in sessions:
            op.drop_column("sessions", name)
