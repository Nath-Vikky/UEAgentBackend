from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils.time import now_utc


class TaskModel(Base):
    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("sessions.session_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    task_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(64), index=True)
    trace_id: Mapped[str] = mapped_column(String(128), index=True)
    intent_type: Mapped[str] = mapped_column(String(64))
    knowledge_relevance: Mapped[str] = mapped_column(String(32))
    route_type: Mapped[str] = mapped_column(String(64))
    route_reason: Mapped[str] = mapped_column(Text)
    selected_tool_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    candidate_tool_ids: Mapped[list] = mapped_column(JSON, default=list)
    planner_confidence: Mapped[float] = mapped_column(default=0.0)
    locale_json: Mapped[dict] = mapped_column(JSON, default=dict)
    user_view_json: Mapped[dict] = mapped_column(JSON, default=dict)
    debug_view_json: Mapped[dict] = mapped_column(JSON, default=dict)
    presentation_json: Mapped[dict] = mapped_column(JSON, default=dict)
    assistant_message: Mapped[str] = mapped_column(Text)
    data_json: Mapped[dict] = mapped_column(JSON, default=dict)
    usage_json: Mapped[dict] = mapped_column(JSON, default=dict)
    trace_summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    retrieval_trace_json: Mapped[dict] = mapped_column(JSON, default=dict)
    planner_diagnostics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    step_results_json: Mapped[list] = mapped_column(JSON, default=list)
    action_proposals_json: Mapped[list] = mapped_column(JSON, default=list)
    errors_json: Mapped[list] = mapped_column(JSON, default=list)
    raw_request_json: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_response_json: Mapped[dict] = mapped_column(JSON, default=dict)
    snapshot_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    output_complete: Mapped[bool] = mapped_column(default=True)
    finish_reason: Mapped[str] = mapped_column(String(64), default="completed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        onupdate=now_utc,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped["SessionModel"] = relationship(back_populates="tasks")
    events: Mapped[list["TaskEventModel"]] = relationship(back_populates="task")
    artifacts: Mapped[list["TaskArtifactModel"]] = relationship(back_populates="task")
    proposals: Mapped[list["ProposalModel"]] = relationship(back_populates="task")


class TaskEventModel(Base):
    __tablename__ = "task_events"

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.task_id", ondelete="CASCADE"),
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    task: Mapped["TaskModel"] = relationship(back_populates="events")


class TaskArtifactModel(Base):
    __tablename__ = "task_artifacts"

    artifact_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.task_id", ondelete="CASCADE"),
        index=True,
    )
    artifact_type: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(512))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    task: Mapped["TaskModel"] = relationship(back_populates="artifacts")
