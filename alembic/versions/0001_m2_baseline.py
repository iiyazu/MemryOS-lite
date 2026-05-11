"""M2 baseline schema

Revision ID: 0001_m2_baseline
Revises:
Create Date: 2025-05-11

Captures the full pre-enhancement schema plus the ``content_json`` and
``embedding`` columns needed for M2's hybrid retrieval. Single baseline
migration because the project had no prior revisions.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_m2_baseline"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


EMBEDDING_DIM = 1536


def _embedding_column() -> sa.Column[Any]:
    """Return an embedding column typed per dialect.

    Postgres gets ``vector(1536)`` via pgvector; SQLite falls back to ``TEXT``
    holding a JSON-encoded array so dev/test stays single-file.
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from pgvector.sqlalchemy import Vector  # imported lazily to keep SQLite envs lean

        return sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True)
    return sa.Column("embedding", sa.Text(), nullable=True)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"])
    op.create_index("ix_messages_session_created", "messages", ["session_id", "created_at"])

    op.create_table(
        "memory_pages",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("page_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=True),
        sa.Column("source_message_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        _embedding_column(),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_memory_pages_session_id", "memory_pages", ["session_id"])
    op.create_index("ix_memory_pages_page_type", "memory_pages", ["page_type"])
    op.create_index("ix_memory_pages_session_type", "memory_pages", ["session_id", "page_type"])
    op.create_index("ix_memory_pages_created", "memory_pages", ["created_at"])

    op.create_table(
        "memory_patches",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("target_page_id", sa.String(length=64), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("verified", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "trace_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trace_events_session_id", "trace_events", ["session_id"])
    op.create_index("ix_trace_events_event_type", "trace_events", ["event_type"])
    op.create_index(
        "ix_trace_events_session_type_created",
        "trace_events",
        ["session_id", "event_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_trace_events_session_type_created", table_name="trace_events")
    op.drop_index("ix_trace_events_event_type", table_name="trace_events")
    op.drop_index("ix_trace_events_session_id", table_name="trace_events")
    op.drop_table("trace_events")

    op.drop_table("memory_patches")

    op.drop_index("ix_memory_pages_created", table_name="memory_pages")
    op.drop_index("ix_memory_pages_session_type", table_name="memory_pages")
    op.drop_index("ix_memory_pages_page_type", table_name="memory_pages")
    op.drop_index("ix_memory_pages_session_id", table_name="memory_pages")
    op.drop_table("memory_pages")

    op.drop_index("ix_messages_session_created", table_name="messages")
    op.drop_index("ix_messages_session_id", table_name="messages")
    op.drop_table("messages")

    op.drop_table("sessions")
