from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.utils.time import now_utc


class RuntimeProfileModel(Base):
    __tablename__ = "runtime_profiles"

    profile_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    chat_model: Mapped[str] = mapped_column(String(128))
    embedding_model: Mapped[str] = mapped_column(String(128))
    temperature: Mapped[float] = mapped_column(Float, default=0.2)
    max_tokens: Mapped[int] = mapped_column(Integer, default=1200)
    rag_top_k: Mapped[int] = mapped_column(Integer, default=8)
    rerank_top_n: Mapped[int] = mapped_column(Integer, default=20)
    allow_streaming: Mapped[bool] = mapped_column(Boolean, default=True)
    debug_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    tool_timeout_ms: Mapped[int] = mapped_column(Integer, default=30000)
    cost_guard_usd: Mapped[float] = mapped_column(Float, default=3.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        onupdate=now_utc,
    )

