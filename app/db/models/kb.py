from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils.time import now_utc


class KBDocumentModel(Base):
    __tablename__ = "kb_documents"

    doc_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    domain: Mapped[str] = mapped_column(String(64), index=True)
    source_path: Mapped[str] = mapped_column(String(512), index=True)
    source_type: Mapped[str] = mapped_column(String(32), default="file")
    file_hash: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(255))
    language: Mapped[str] = mapped_column(String(32), default="auto")
    doc_type: Mapped[str] = mapped_column(String(64), default="reference")
    module: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parser_name: Mapped[str] = mapped_column(String(64), default="builtin")
    status: Mapped[str] = mapped_column(String(32), default="active")
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    raw_storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    normalized_storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    tags_json: Mapped[list] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        onupdate=now_utc,
    )

    chunks: Mapped[list["KBChunkModel"]] = relationship(back_populates="document")


class KBChunkModel(Base):
    __tablename__ = "kb_chunks"

    chunk_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    doc_id: Mapped[str] = mapped_column(
        ForeignKey("kb_documents.doc_id", ondelete="CASCADE"),
        index=True,
    )
    project_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    domain: Mapped[str] = mapped_column(String(64), index=True)
    source_path: Mapped[str] = mapped_column(String(512))
    title: Mapped[str] = mapped_column(String(255))
    section_path: Mapped[str] = mapped_column(String(255), default="")
    language: Mapped[str] = mapped_column(String(32), default="auto")
    doc_type: Mapped[str] = mapped_column(String(64), default="reference")
    module: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(128), index=True)
    tags_json: Mapped[list] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        onupdate=now_utc,
    )

    document: Mapped["KBDocumentModel"] = relationship(back_populates="chunks")


class KBImportJobModel(Base):
    __tablename__ = "kb_import_jobs"

    job_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    mode: Mapped[str] = mapped_column(String(32), default="refresh")
    status: Mapped[str] = mapped_column(String(32), index=True)
    source_summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    stats_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        onupdate=now_utc,
    )
