from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils.time import now_utc


class WebMemoryEntryModel(Base):
    __tablename__ = "web_memory_entries"

    entry_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    query: Mapped[str] = mapped_column(Text)
    query_terms_json: Mapped[list] = mapped_column(JSON, default=list)
    title: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(1024), index=True)
    domain: Mapped[str] = mapped_column(String(255), index=True)
    snippet: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(64), default="web")
    provider: Mapped[str] = mapped_column(String(64), default="unknown")
    source_score: Mapped[float] = mapped_column(Float, default=0.0)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    helpful_count: Mapped[int] = mapped_column(Integer, default=0)
    unhelpful_count: Mapped[int] = mapped_column(Integer, default=0)
    tags_json: Mapped[list] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_task_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    feedback: Mapped[list["WebMemoryFeedbackModel"]] = relationship(back_populates="entry")


class WebMemoryFeedbackModel(Base):
    __tablename__ = "web_memory_feedback"

    feedback_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    entry_id: Mapped[str] = mapped_column(
        ForeignKey("web_memory_entries.entry_id", ondelete="CASCADE"),
        index=True,
    )
    rating: Mapped[str] = mapped_column(String(32))
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    entry: Mapped[WebMemoryEntryModel] = relationship(back_populates="feedback")
