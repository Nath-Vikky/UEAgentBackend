from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils.time import now_utc


class ProposalModel(Base):
    __tablename__ = "proposals"

    proposal_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.task_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255))
    proposal_type: Mapped[str] = mapped_column(String(64))
    before_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_flags: Mapped[str] = mapped_column(String(16), default="LOW")
    dry_run_preview_json: Mapped[dict] = mapped_column(JSON, default=dict)
    display_hints_json: Mapped[dict] = mapped_column(JSON, default=dict)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=True)
    confirmation_state: Mapped[str] = mapped_column(String(32), default="pending")
    decision_endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        onupdate=now_utc,
    )

    task: Mapped["TaskModel"] = relationship(back_populates="proposals")
    decisions: Mapped[list["ProposalDecisionModel"]] = relationship(back_populates="proposal")


class ProposalDecisionModel(Base):
    __tablename__ = "proposal_decisions"

    decision_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(
        ForeignKey("proposals.proposal_id", ondelete="CASCADE"),
        index=True,
    )
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decision: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    proposal: Mapped["ProposalModel"] = relationship(back_populates="decisions")
