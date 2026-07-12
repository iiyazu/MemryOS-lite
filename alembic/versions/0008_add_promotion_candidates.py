"""Add promotion candidates

Revision ID: 0008_add_promotion_candidates
Revises: 0007_add_core_block_read_only_tags
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0008_add_promotion_candidates"
down_revision: str = "0007_add_core_block_read_only_tags"
branch_labels: str | None = None
depends_on: str | None = None


def _table_names() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return set(inspector.get_table_names())


def _index_names(table_name: str) -> set[str]:
    if table_name not in _table_names():
        return set()
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    if "promotion_candidates" not in _table_names():
        op.create_table(
            "promotion_candidates",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("source_layer", sa.String(length=32), nullable=False),
            sa.Column("target_layer", sa.String(length=32), nullable=False),
            sa.Column("operation", sa.String(length=32), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column(
                "source_refs_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            ),
            sa.Column("identity_scope_json", sa.Text(), nullable=True),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("write_source", sa.String(length=32), nullable=False),
            sa.Column(
                "metadata_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    indexes = _index_names("promotion_candidates")
    if "ix_promotion_candidates_source_layer" not in indexes:
        op.create_index(
            "ix_promotion_candidates_source_layer",
            "promotion_candidates",
            ["source_layer"],
            unique=False,
        )
    if "ix_promotion_candidates_target_layer" not in indexes:
        op.create_index(
            "ix_promotion_candidates_target_layer",
            "promotion_candidates",
            ["target_layer"],
            unique=False,
        )
    if "ix_promotion_candidates_status" not in indexes:
        op.create_index(
            "ix_promotion_candidates_status",
            "promotion_candidates",
            ["status"],
            unique=False,
        )
    if "ix_promotion_candidates_status_created" not in indexes:
        op.create_index(
            "ix_promotion_candidates_status_created",
            "promotion_candidates",
            ["status", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    if "promotion_candidates" in _table_names():
        indexes = _index_names("promotion_candidates")
        if "ix_promotion_candidates_status_created" in indexes:
            op.drop_index(
                "ix_promotion_candidates_status_created",
                table_name="promotion_candidates",
            )
        if "ix_promotion_candidates_status" in indexes:
            op.drop_index(
                "ix_promotion_candidates_status",
                table_name="promotion_candidates",
            )
        if "ix_promotion_candidates_target_layer" in indexes:
            op.drop_index(
                "ix_promotion_candidates_target_layer",
                table_name="promotion_candidates",
            )
        if "ix_promotion_candidates_source_layer" in indexes:
            op.drop_index(
                "ix_promotion_candidates_source_layer",
                table_name="promotion_candidates",
            )
        op.drop_table("promotion_candidates")
