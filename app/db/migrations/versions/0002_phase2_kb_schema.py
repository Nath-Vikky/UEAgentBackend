"""phase 2 knowledge base schema

Revision ID: 0002_phase2_kb_schema
Revises: 0001_phase1_initial
Create Date: 2026-04-17 00:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0002_phase2_kb_schema"
down_revision = "0001_phase1_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kb_import_jobs",
        sa.Column("job_id", sa.String(length=128), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_summary_json", sa.JSON(), nullable=False),
        sa.Column("stats_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("job_id"),
    )
    op.create_index("ix_kb_import_jobs_status", "kb_import_jobs", ["status"], unique=False)

    op.create_table(
        "kb_documents",
        sa.Column("doc_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=True),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column("source_path", sa.String(length=512), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("file_hash", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("doc_type", sa.String(length=64), nullable=False),
        sa.Column("module", sa.String(length=128), nullable=True),
        sa.Column("parser_name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("raw_storage_path", sa.String(length=512), nullable=True),
        sa.Column("normalized_storage_path", sa.String(length=512), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("doc_id"),
    )
    op.create_index("ix_kb_documents_domain", "kb_documents", ["domain"], unique=False)
    op.create_index("ix_kb_documents_file_hash", "kb_documents", ["file_hash"], unique=False)
    op.create_index("ix_kb_documents_project_id", "kb_documents", ["project_id"], unique=False)
    op.create_index("ix_kb_documents_source_path", "kb_documents", ["source_path"], unique=False)

    op.create_table(
        "kb_chunks",
        sa.Column("chunk_id", sa.String(length=128), nullable=False),
        sa.Column("doc_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=True),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column("source_path", sa.String(length=512), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("section_path", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("doc_type", sa.String(length=64), nullable=False),
        sa.Column("module", sa.String(length=128), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(length=128), nullable=False),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["doc_id"], ["kb_documents.doc_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chunk_id"),
    )
    op.create_index("ix_kb_chunks_doc_id", "kb_chunks", ["doc_id"], unique=False)
    op.create_index("ix_kb_chunks_domain", "kb_chunks", ["domain"], unique=False)
    op.create_index("ix_kb_chunks_project_id", "kb_chunks", ["project_id"], unique=False)
    op.create_index("ix_kb_chunks_text_hash", "kb_chunks", ["text_hash"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_kb_chunks_text_hash", table_name="kb_chunks")
    op.drop_index("ix_kb_chunks_project_id", table_name="kb_chunks")
    op.drop_index("ix_kb_chunks_domain", table_name="kb_chunks")
    op.drop_index("ix_kb_chunks_doc_id", table_name="kb_chunks")
    op.drop_table("kb_chunks")
    op.drop_index("ix_kb_documents_source_path", table_name="kb_documents")
    op.drop_index("ix_kb_documents_project_id", table_name="kb_documents")
    op.drop_index("ix_kb_documents_file_hash", table_name="kb_documents")
    op.drop_index("ix_kb_documents_domain", table_name="kb_documents")
    op.drop_table("kb_documents")
    op.drop_index("ix_kb_import_jobs_status", table_name="kb_import_jobs")
    op.drop_table("kb_import_jobs")
