"""Add archival memory tables

Revision ID: 0006_add_archival_memory
Revises: 0005_add_core_memory
Create Date: 2026-05-21
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0006_add_archival_memory"
down_revision: str = "0005_add_core_memory"
branch_labels: str | None = None
depends_on: str | None = None


def _table_names() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return set(inspector.get_table_names())


def upgrade() -> None:
    existing = _table_names()
    if "archival_documents" not in existing:
        op.create_table(
            "archival_documents",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("archive_id", sa.String(length=64), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("source_id", sa.String(length=64), nullable=True),
            sa.Column("file_id", sa.String(length=64), nullable=True),
            sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("source_refs_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column(
                "producer",
                sa.String(length=32),
                nullable=False,
                server_default="explicit_document",
            ),
            sa.Column("legacy_page_id", sa.String(length=64), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "archival_chunks" not in existing:
        op.create_table(
            "archival_chunks",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("document_id", sa.String(length=64), nullable=False),
            sa.Column("archive_id", sa.String(length=64), nullable=True),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("start", sa.Integer(), nullable=False),
            sa.Column("end", sa.Integer(), nullable=False),
            sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("source_refs_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_archival_chunks_document_start",
            "archival_chunks",
            ["document_id", "start"],
        )
    if "archival_passages" not in existing:
        op.create_table(
            "archival_passages",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("document_id", sa.String(length=64), nullable=True),
            sa.Column("chunk_id", sa.String(length=64), nullable=True),
            sa.Column("archive_id", sa.String(length=64), nullable=True),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("citation_start", sa.Integer(), nullable=True),
            sa.Column("citation_end", sa.Integer(), nullable=True),
            sa.Column("source_id", sa.String(length=64), nullable=True),
            sa.Column("file_id", sa.String(length=64), nullable=True),
            sa.Column("scope_json", sa.Text(), nullable=True),
            sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("score", sa.Float(), nullable=True),
            sa.Column("source_refs_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("legacy_item_id", sa.String(length=64), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_archival_passages_archive_source",
            "archival_passages",
            ["archive_id", "source_id"],
        )
        op.create_index(
            "ix_archival_passages_archive_file",
            "archival_passages",
            ["archive_id", "file_id"],
        )
    if "archival_memories" not in existing:
        op.create_table(
            "archival_memories",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("archive_id", sa.String(length=64), nullable=True),
            sa.Column("memory_type", sa.String(length=32), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("identity_scope_json", sa.Text(), nullable=True),
            sa.Column("source_id", sa.String(length=64), nullable=True),
            sa.Column("file_id", sa.String(length=64), nullable=True),
            sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("source_refs_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("history_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("entity_links_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("legacy_item_id", sa.String(length=64), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_archival_memories_archive_type",
            "archival_memories",
            ["archive_id", "memory_type"],
        )
    if "archival_memory_history" not in existing:
        op.create_table(
            "archival_memory_history",
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
            "ix_archival_memory_history_memory_created",
            "archival_memory_history",
            ["memory_id", "created_at"],
        )
    if "archive_attachments" not in existing:
        op.create_table(
            "archive_attachments",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("archive_id", sa.String(length=64), nullable=False),
            sa.Column("scope_type", sa.String(length=16), nullable=False),
            sa.Column("scope_id", sa.String(length=64), nullable=False),
            sa.Column("source_refs_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_archive_attachments_scope",
            "archive_attachments",
            ["scope_type", "scope_id"],
        )


def downgrade() -> None:
    existing = _table_names()
    if "archive_attachments" in existing:
        op.drop_index("ix_archive_attachments_scope", table_name="archive_attachments")
        op.drop_table("archive_attachments")
    if "archival_memory_history" in existing:
        op.drop_index(
            "ix_archival_memory_history_memory_created",
            table_name="archival_memory_history",
        )
        op.drop_table("archival_memory_history")
    if "archival_memories" in existing:
        op.drop_index("ix_archival_memories_archive_type", table_name="archival_memories")
        op.drop_table("archival_memories")
    if "archival_passages" in existing:
        op.drop_index("ix_archival_passages_archive_file", table_name="archival_passages")
        op.drop_index("ix_archival_passages_archive_source", table_name="archival_passages")
        op.drop_table("archival_passages")
    if "archival_chunks" in existing:
        op.drop_index("ix_archival_chunks_document_start", table_name="archival_chunks")
        op.drop_table("archival_chunks")
    if "archival_documents" in existing:
        op.drop_table("archival_documents")
