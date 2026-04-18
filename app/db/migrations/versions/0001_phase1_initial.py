"""phase 1 initial schema

Revision ID: 0001_phase1_initial
Revises:
Create Date: 2026-04-17 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_phase1_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("audit_id", sa.String(length=128), nullable=False),
        sa.Column("task_id", sa.String(length=128), nullable=True),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("audit_id"),
    )
    op.create_index("ix_audit_logs_event_type", "audit_logs", ["event_type"], unique=False)
    op.create_index("ix_audit_logs_session_id", "audit_logs", ["session_id"], unique=False)
    op.create_index("ix_audit_logs_task_id", "audit_logs", ["task_id"], unique=False)

    op.create_table(
        "runtime_profiles",
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("chat_model", sa.String(length=128), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=False),
        sa.Column("rag_top_k", sa.Integer(), nullable=False),
        sa.Column("rerank_top_n", sa.Integer(), nullable=False),
        sa.Column("allow_streaming", sa.Boolean(), nullable=False),
        sa.Column("debug_mode", sa.Boolean(), nullable=False),
        sa.Column("tool_timeout_ms", sa.Integer(), nullable=False),
        sa.Column("cost_guard_usd", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("profile_id"),
    )

    op.create_table(
        "sessions",
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("preferred_output_language", sa.String(length=32), nullable=True),
        sa.Column("current_profile_id", sa.String(length=64), nullable=True),
        sa.Column("project_name", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("session_id"),
    )

    op.create_table(
        "messages",
        sa.Column("message_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.session_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("message_id"),
    )

    op.create_table(
        "tasks",
        sa.Column("task_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("intent_type", sa.String(length=64), nullable=False),
        sa.Column("knowledge_relevance", sa.String(length=32), nullable=False),
        sa.Column("route_type", sa.String(length=64), nullable=False),
        sa.Column("route_reason", sa.Text(), nullable=False),
        sa.Column("selected_tool_id", sa.String(length=128), nullable=True),
        sa.Column("candidate_tool_ids", sa.JSON(), nullable=False),
        sa.Column("planner_confidence", sa.Float(), nullable=False),
        sa.Column("locale_json", sa.JSON(), nullable=False),
        sa.Column("user_view_json", sa.JSON(), nullable=False),
        sa.Column("debug_view_json", sa.JSON(), nullable=False),
        sa.Column("presentation_json", sa.JSON(), nullable=False),
        sa.Column("assistant_message", sa.Text(), nullable=False),
        sa.Column("data_json", sa.JSON(), nullable=False),
        sa.Column("usage_json", sa.JSON(), nullable=False),
        sa.Column("trace_summary_json", sa.JSON(), nullable=False),
        sa.Column("retrieval_trace_json", sa.JSON(), nullable=False),
        sa.Column("planner_diagnostics_json", sa.JSON(), nullable=False),
        sa.Column("step_results_json", sa.JSON(), nullable=False),
        sa.Column("action_proposals_json", sa.JSON(), nullable=False),
        sa.Column("errors_json", sa.JSON(), nullable=False),
        sa.Column("raw_request_json", sa.JSON(), nullable=False),
        sa.Column("raw_response_json", sa.JSON(), nullable=False),
        sa.Column("snapshot_path", sa.String(length=512), nullable=True),
        sa.Column("output_complete", sa.Boolean(), nullable=False),
        sa.Column("finish_reason", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.session_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("task_id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index("ix_tasks_run_id", "tasks", ["run_id"], unique=True)
    op.create_index("ix_tasks_session_id", "tasks", ["session_id"], unique=False)
    op.create_index("ix_tasks_status", "tasks", ["status"], unique=False)
    op.create_index("ix_tasks_task_type", "tasks", ["task_type"], unique=False)
    op.create_index("ix_tasks_trace_id", "tasks", ["trace_id"], unique=False)

    op.create_table(
        "task_artifacts",
        sa.Column("artifact_id", sa.String(length=128), nullable=False),
        sa.Column("task_id", sa.String(length=128), nullable=False),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.task_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("artifact_id"),
    )
    op.create_index("ix_task_artifacts_task_id", "task_artifacts", ["task_id"], unique=False)

    op.create_table(
        "task_events",
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("task_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.task_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_task_events_task_id", "task_events", ["task_id"], unique=False)

    op.create_table(
        "proposals",
        sa.Column("proposal_id", sa.String(length=128), nullable=False),
        sa.Column("task_id", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("proposal_type", sa.String(length=64), nullable=False),
        sa.Column("before_summary", sa.Text(), nullable=True),
        sa.Column("after_summary", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("risk_flags", sa.String(length=16), nullable=False),
        sa.Column("dry_run_preview_json", sa.JSON(), nullable=False),
        sa.Column("display_hints_json", sa.JSON(), nullable=False),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False),
        sa.Column("confirmation_state", sa.String(length=32), nullable=False),
        sa.Column("decision_endpoint", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.task_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("proposal_id"),
    )
    op.create_index("ix_proposals_task_id", "proposals", ["task_id"], unique=False)

    op.create_table(
        "proposal_decisions",
        sa.Column("decision_id", sa.String(length=128), nullable=False),
        sa.Column("proposal_id", sa.String(length=128), nullable=False),
        sa.Column("task_id", sa.String(length=128), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.proposal_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("decision_id"),
    )
    op.create_index(
        "ix_proposal_decisions_proposal_id",
        "proposal_decisions",
        ["proposal_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_proposal_decisions_proposal_id", table_name="proposal_decisions")
    op.drop_table("proposal_decisions")
    op.drop_index("ix_proposals_task_id", table_name="proposals")
    op.drop_table("proposals")
    op.drop_index("ix_task_events_task_id", table_name="task_events")
    op.drop_table("task_events")
    op.drop_index("ix_task_artifacts_task_id", table_name="task_artifacts")
    op.drop_table("task_artifacts")
    op.drop_index("ix_tasks_trace_id", table_name="tasks")
    op.drop_index("ix_tasks_task_type", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_index("ix_tasks_session_id", table_name="tasks")
    op.drop_index("ix_tasks_run_id", table_name="tasks")
    op.drop_table("tasks")
    op.drop_table("messages")
    op.drop_table("sessions")
    op.drop_table("runtime_profiles")
    op.drop_index("ix_audit_logs_task_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_session_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_event_type", table_name="audit_logs")
    op.drop_table("audit_logs")

