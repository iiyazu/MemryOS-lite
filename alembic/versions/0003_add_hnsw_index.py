"""Add HNSW index on memory_pages.embedding (Postgres only)

Revision ID: 0003_add_hnsw_index
Revises: 0002_add_superseded_by
Create Date: 2026-05-15

Adds an HNSW index for cosine similarity search on the embedding column.
Only applies to Postgres (pgvector); SQLite is a no-op.
CREATE INDEX CONCURRENTLY cannot run inside a transaction, so this migration
uses AUTOCOMMIT isolation.
"""

from __future__ import annotations

from sqlalchemy import text

from alembic import op

revision: str = "0003_add_hnsw_index"
down_revision: str = "0002_add_superseded_by"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    bind.execution_options(isolation_level="AUTOCOMMIT").execute(
        text(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_memory_pages_embedding_hnsw "
            "ON memory_pages USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    bind.execution_options(isolation_level="AUTOCOMMIT").execute(
        text("DROP INDEX CONCURRENTLY IF EXISTS ix_memory_pages_embedding_hnsw")
    )
