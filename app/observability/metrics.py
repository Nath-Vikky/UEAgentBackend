from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.audit import AuditLogModel
from app.db.models.proposal import ProposalDecisionModel, ProposalModel
from app.db.models.task import TaskModel


def default_usage() -> dict[str, Any]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost_usd": 0.0,
        "latency_ms": 0,
    }


def summarize_usage(usage: Mapping[str, Any] | None) -> dict[str, Any]:
    base = default_usage()
    if usage:
        base.update(dict(usage))
    return base


def _metric_lines(name: str, value: int | float, labels: dict[str, str] | None = None) -> str:
    if not labels:
        return f"{name} {value}"
    label_text = ",".join(f'{key}="{val}"' for key, val in sorted(labels.items()))
    return f"{name}{{{label_text}}} {value}"


def render_prometheus_metrics(db: Session) -> str:
    lines = [
        "# HELP agent_tasks_total Total tasks grouped by type and status.",
        "# TYPE agent_tasks_total gauge",
    ]
    task_rows = db.execute(
        select(TaskModel.task_type, TaskModel.status, func.count()).group_by(TaskModel.task_type, TaskModel.status)
    ).all()
    for task_type, status, count in task_rows:
        lines.append(
            _metric_lines(
                "agent_tasks_total",
                count,
                {"task_type": str(task_type), "status": str(status)},
            )
        )

    pending_total = db.scalar(
        select(func.count()).select_from(ProposalModel).where(ProposalModel.confirmation_state == "pending")
    ) or 0
    lines.extend(
        [
            "# HELP agent_proposals_pending_total Total proposals waiting for user confirmation.",
            "# TYPE agent_proposals_pending_total gauge",
            _metric_lines("agent_proposals_pending_total", pending_total),
        ]
    )

    decision_rows = db.execute(
        select(ProposalDecisionModel.decision, func.count()).group_by(ProposalDecisionModel.decision)
    ).all()
    lines.extend(
        [
            "# HELP agent_proposal_decisions_total Total proposal decisions grouped by outcome.",
            "# TYPE agent_proposal_decisions_total gauge",
        ]
    )
    for decision, count in decision_rows:
        lines.append(
            _metric_lines(
                "agent_proposal_decisions_total",
                count,
                {"decision": str(decision)},
            )
        )

    audit_rows = db.execute(
        select(AuditLogModel.event_type, func.count()).group_by(AuditLogModel.event_type)
    ).all()
    lines.extend(
        [
            "# HELP agent_audit_logs_total Total audit log entries grouped by event type.",
            "# TYPE agent_audit_logs_total gauge",
        ]
    )
    for event_type, count in audit_rows:
        lines.append(
            _metric_lines(
                "agent_audit_logs_total",
                count,
                {"event_type": str(event_type)},
            )
        )

    waiting_total = db.scalar(
        select(func.count()).select_from(TaskModel).where(TaskModel.status == "waiting_confirmation")
    ) or 0
    lines.extend(
        [
            "# HELP agent_waiting_confirmation_total Total tasks paused for confirmation.",
            "# TYPE agent_waiting_confirmation_total gauge",
            _metric_lines("agent_waiting_confirmation_total", waiting_total),
        ]
    )
    return "\n".join(lines) + "\n"
