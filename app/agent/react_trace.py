from __future__ import annotations

from typing import Any

from app.schemas.requests import UnifiedTaskRequest


REACT_TRACE_VERSION = "react_v2_trace_v1"


def _step(
    *,
    step_id: str,
    phase: str,
    status: str,
    summary: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "phase": phase,
        "status": status,
        "summary": summary,
        "details": details or {},
    }


def build_react_v2_trace(
    *,
    request: UnifiedTaskRequest,
    routing: dict[str, Any],
    context_pack: dict[str, Any],
    skill_runtime: dict[str, Any],
    retrieval_trace: dict[str, Any],
    data: dict[str, Any],
    debug_view: dict[str, Any],
    action_proposals: list[dict[str, Any]],
    task_status: str,
    finish_reason: str,
) -> dict[str, Any]:
    """Build a display-safe ReAct trace without exposing raw chain-of-thought."""

    intent = dict(routing.get("intent") or {})
    route = dict(routing.get("route") or {})
    context_summary = dict(context_pack.get("debug_summary") or {})
    memory_layer = dict(context_pack.get("memory_layer") or {})
    tool_layer = dict(context_pack.get("tool_layer") or {})
    tool_plan = dict(data.get("tool_plan") or debug_view.get("tool_plan") or {})
    self_reflection = dict(data.get("self_reflection") or debug_view.get("self_reflection") or {})
    retrieved_docs = list(retrieval_trace.get("retrieved_docs") or [])
    observations = list(tool_layer.get("tool_observation_summary") or [])
    editor_operations = list(tool_layer.get("recent_editor_operations") or [])
    selected_memory = list(memory_layer.get("selected_items") or [])

    steps = [
        _step(
            step_id="input",
            phase="input",
            status="completed",
            summary="Captured request, locale, and active editor context.",
            details={
                "task_type": request.task_type,
                "actual_task_type": context_summary.get("actual_task_type"),
                "latest_user_message": context_summary.get("latest_user_message"),
            },
        ),
        _step(
            step_id="thought_summary",
            phase="thought_summary",
            status="completed",
            summary="Selected route and compact context; raw chain-of-thought is not exposed.",
            details={
                "route_type": intent.get("route_type"),
                "intent_reason": intent.get("reason"),
                "context_pack_version": context_pack.get("version"),
                "selected_tool_id": route.get("selected_tool_id"),
            },
        ),
        _step(
            step_id="plan_summary",
            phase="plan",
            status="completed" if tool_plan or route.get("selected_tool_id") or action_proposals else "skipped",
            summary="Prepared a bounded tool/skill plan or skipped tool planning when direct answering was enough.",
            details={
                "skill_id": skill_runtime.get("skill_id"),
                "tool_call_sequence": tool_plan.get("tool_call_sequence", []),
                "proposal_count": len(action_proposals),
                "write_policy": tool_layer.get("proposal_policy"),
            },
        ),
        _step(
            step_id="observation_summary",
            phase="observation",
            status="completed",
            summary="Collected compact observations from retrieval, memory, inventory, tool summaries, and editor operation history.",
            details={
                "retrieval_mode": retrieval_trace.get("mode"),
                "retrieved_count": len(retrieved_docs),
                "selected_memory_count": len(selected_memory),
                "tool_observation_count": len(observations),
                "recent_editor_operation_count": len(editor_operations),
            },
        ),
        _step(
            step_id="reflection_summary",
            phase="reflection",
            status="completed" if self_reflection else "skipped",
            summary="Ran lightweight response self-checks when available.",
            details={
                "self_reflection_status": self_reflection.get("status"),
                "grounding_level": self_reflection.get("grounding_level"),
                "recommendations": self_reflection.get("recommendations", []),
            },
        ),
        _step(
            step_id="final",
            phase="final",
            status=task_status,
            summary=f"Projected the execution into user_view/debug_view with finish_reason={finish_reason}.",
            details={
                "finish_reason": finish_reason,
                "assistant_message_present": bool(str(data.get("answer") or "").strip()),
            },
        ),
    ]

    return {
        "version": REACT_TRACE_VERSION,
        "mode": "display_safe_react_v2",
        "steps": steps,
        "summary": {
            "route_type": intent.get("route_type"),
            "skill_id": skill_runtime.get("skill_id"),
            "retrieval_mode": retrieval_trace.get("mode"),
            "proposal_count": len(action_proposals),
            "task_status": task_status,
            "finish_reason": finish_reason,
        },
        "boundary": {
            "raw_chain_of_thought_exposed": False,
            "max_write_proposals_per_turn": 1,
            "confirmed_write_required": True,
        },
    }
