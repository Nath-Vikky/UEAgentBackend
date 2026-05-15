"""web memory schema

Revision ID: 0003_web_memory_schema
Revises: 0002_phase2_kb_schema
Create Date: 2026-05-15 18:20:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0003_web_memory_schema"
down_revision = "0002_phase2_kb_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "web_memory_entries",
        sa.Column("entry_id", sa.String(length=128), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("query_terms_json", sa.JSON(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("source_score", sa.Float(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("helpful_count", sa.Integer(), nullable=False),
        sa.Column("unhelpful_count", sa.Integer(), nullable=False),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("source_task_id", sa.String(length=128), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("entry_id"),
    )
    op.create_index("ix_web_memory_entries_domain", "web_memory_entries", ["domain"], unique=False)
    op.create_index("ix_web_memory_entries_expires_at", "web_memory_entries", ["expires_at"], unique=False)
    op.create_index("ix_web_memory_entries_source_task_id", "web_memory_entries", ["source_task_id"], unique=False)
    op.create_index("ix_web_memory_entries_url", "web_memory_entries", ["url"], unique=False)

    op.create_table(
        "web_memory_feedback",
        sa.Column("feedback_id", sa.String(length=128), nullable=False),
        sa.Column("entry_id", sa.String(length=128), nullable=False),
        sa.Column("rating", sa.String(length=32), nullable=False),
        sa.Column("task_id", sa.String(length=128), nullable=True),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["web_memory_entries.entry_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("feedback_id"),
    )
    op.create_index("ix_web_memory_feedback_entry_id", "web_memory_feedback", ["entry_id"], unique=False)
    op.create_index("ix_web_memory_feedback_task_id", "web_memory_feedback", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_web_memory_feedback_task_id", table_name="web_memory_feedback")
    op.drop_index("ix_web_memory_feedback_entry_id", table_name="web_memory_feedback")
    op.drop_table("web_memory_feedback")
    op.drop_index("ix_web_memory_entries_url", table_name="web_memory_entries")
    op.drop_index("ix_web_memory_entries_source_task_id", table_name="web_memory_entries")
    op.drop_index("ix_web_memory_entries_expires_at", table_name="web_memory_entries")
    op.drop_index("ix_web_memory_entries_domain", table_name="web_memory_entries")
    op.drop_table("web_memory_entries")
