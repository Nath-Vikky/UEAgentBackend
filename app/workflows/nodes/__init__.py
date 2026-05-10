from __future__ import annotations

from typing import Any

from app.schemas.requests import ContextInput
from app.services.kb_service import KnowledgeBaseService
from app.tools.retrieval import retrieve_support_notes
from app.workflows.state import WorkflowState


def append_step_result_node(
    state: WorkflowState,
    *,
    step_id: str,
    title: str,
    summary: str,
    status: str = "completed",
    details: dict[str, Any] | None = None,
) -> WorkflowState:
    """Append a normalized workflow step result and return the same state."""
    state.step_results.append(
        {
            "step_id": step_id,
            "title": title,
            "status": status,
            "summary": summary,
            "details": details or {},
        }
    )
    return state


def record_tool_output_node(
    state: WorkflowState,
    *,
    tool_id: str,
    output: dict[str, Any],
) -> WorkflowState:
    """Record a tool output under its tool id."""
    state.tool_outputs[tool_id] = output
    return state


def retrieve_support_notes_node(
    state: WorkflowState,
    *,
    kb_service: KnowledgeBaseService,
    query: str,
    context: ContextInput,
    output_language: str,
    domain_filters: list[str],
    extra_payload: dict[str, Any] | None = None,
) -> WorkflowState:
    """Reusable KB retrieval node for legacy graph-style workflows."""
    guidance = retrieve_support_notes(
        kb_service,
        query=query,
        context=context,
        output_language=output_language,
        domain_filters=domain_filters,
        extra_payload=extra_payload,
    )
    state.retrieved_context = guidance
    return append_step_result_node(
        state,
        step_id="retrieve_support_notes",
        title="Retrieve Support Notes",
        summary=f"Retrieved {len(guidance.get('retrieved_docs') or [])} support chunk(s).",
        details=guidance.get("retrieval_trace") or {},
    )


def aggregate_step_results_node(state: WorkflowState) -> WorkflowState:
    """Store a compact workflow summary derived from step statuses."""
    status_counts: dict[str, int] = {}
    for step in state.step_results:
        status = str(step.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    state.tool_outputs["workflow_summary"] = {
        "step_count": len(state.step_results),
        "status_counts": status_counts,
        "warning_count": len(state.warnings),
    }
    return state


__all__ = [
    "aggregate_step_results_node",
    "append_step_result_node",
    "record_tool_output_node",
    "retrieve_support_notes_node",
]
