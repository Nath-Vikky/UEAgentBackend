from __future__ import annotations

from typing import Any

from app.schemas.requests import UnifiedTaskRequest


def _latest_user_message(request: UnifiedTaskRequest) -> str:
    for item in reversed(request.session.messages):
        if item.role == "user" and item.content.strip():
            return item.content.strip()
    return str(request.payload.get("user_query") or "").strip()


def _decision(
    *,
    decision: str,
    reason: str,
    source: str,
    confidence: float | None = None,
    details: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "decision": decision,
        "reason": reason,
        "source": source,
        "confidence": confidence,
        "details": details or {},
        "warnings": warnings or [],
    }


def build_agent_decision_trace(
    *,
    request: UnifiedTaskRequest,
    routing: dict[str, Any],
    context_bundle: dict[str, Any],
    skill_runtime: dict[str, Any],
    retrieval_trace: dict[str, Any],
    user_view_payload: dict[str, Any],
    debug_view: dict[str, Any],
    data: dict[str, Any],
    task_status: str,
    finish_reason: str,
    output_complete: bool,
) -> dict[str, Any]:
    intent = dict(routing.get("intent") or {})
    route = dict(routing.get("route") or {})
    locale = dict(routing.get("locale") or {})
    context_budget = dict(context_bundle.get("budget") or {})
    session_summary = dict(context_bundle.get("session_summary") or {})
    long_term_memory = dict(context_bundle.get("long_term_memory") or {})
    tool_plan = dict(data.get("tool_plan") or debug_view.get("tool_plan") or {})
    self_reflection = dict(data.get("self_reflection") or debug_view.get("self_reflection") or {})
    memory_summary = dict(debug_view.get("memory_summary") or {})
    updated_memory = dict(memory_summary.get("updated_session_memory") or {})
    retrieval_mode = str(retrieval_trace.get("mode") or "not_used")
    retrieved_docs = list(retrieval_trace.get("retrieved_docs") or [])
    warnings = list(debug_view.get("warnings") or [])
    errors = list(debug_view.get("errors") or data.get("errors") or [])

    decisions = {
        "input_summary": _decision(
            decision=str(context_bundle.get("input_summary", {}).get("actual_task_type") or request.task_type),
            reason="Captured normalized request, latest user message, and editor context before execution.",
            source="context_manager",
            confidence=1.0,
            details={
                "requested_task_type": request.task_type,
                "latest_user_message": _latest_user_message(request),
                "active_panel": request.context.active_panel,
                "project_name": request.context.project_name,
            },
        ),
        "language_decision": _decision(
            decision=str(locale.get("final_output_language") or "zh-CN"),
            reason=f"Language source: {locale.get('language_source') or 'default'}.",
            source="router.locale",
            confidence=1.0,
            details=locale,
        ),
        "intent_decision": _decision(
            decision=str(intent.get("route_type") or "fallback"),
            reason=str(intent.get("reason") or ""),
            source=str(route.get("decision_source") or "router"),
            confidence=route.get("planner_confidence"),
            details={
                "intent_type": intent.get("intent_type"),
                "knowledge_relevance": intent.get("knowledge_relevance"),
                "requires_rag": intent.get("requires_rag"),
                "requires_tool": intent.get("requires_tool"),
                "selected_tool_id": route.get("selected_tool_id"),
                "project_signal_strength": route.get("project_signal_strength"),
            },
            warnings=list(route.get("warnings") or []),
        ),
        "context_decision": _decision(
            decision="use_compact_context_bundle",
            reason="Context Manager selected recent chat messages, session summary, editor context, and tool summaries.",
            source="context_manager",
            confidence=1.0,
            details={
                "context_bundle_version": context_bundle.get("version"),
                "recent_message_count": len(context_bundle.get("recent_messages") or []),
                "tool_context_count": len(context_bundle.get("tool_context") or []),
                "session_summary_status": session_summary.get("status"),
                "estimated_chars": context_budget.get("estimated_chars"),
                "char_budget": context_budget.get("char_budget"),
                "within_budget": context_budget.get("within_budget"),
            },
            warnings=list(context_budget.get("warnings") or []),
        ),
        "retrieval_decision": _decision(
            decision=retrieval_mode,
            reason="Retrieval was used only if the selected route or tool required project evidence.",
            source="retrieval_trace",
            confidence=None,
            details={
                "retrieved_count": len(retrieved_docs),
                "degraded_mode": retrieval_trace.get("degraded_mode", False),
                "tool_plan": tool_plan,
            },
            warnings=list(retrieval_trace.get("warnings") or []),
        ),
        "tool_decision": _decision(
            decision=str(skill_runtime.get("skill_id") or route.get("selected_tool_id") or "none"),
            reason="Mapped route and task type to a fixed built-in skill.",
            source="skill_registry",
            confidence=route.get("planner_confidence"),
            details=skill_runtime,
        ),
        "memory_decision": _decision(
            decision=str(long_term_memory.get("status") or updated_memory.get("status") or session_summary.get("status") or "not_available"),
            reason="Session summary and project-scoped long-term memory are injected as compact context when available.",
            source="memory_manager",
            confidence=1.0,
            details={
                "session_summary_status": session_summary.get("status"),
                "long_term_memory_status": long_term_memory.get("status"),
                "long_term_memory_count": long_term_memory.get("count", 0),
                "long_term_memory_items": long_term_memory.get("items", []),
                "updated_session_memory": updated_memory,
            },
        ),
        "fallback_decision": _decision(
            decision="fallback_used" if warnings or errors else "no_fallback",
            reason="Warnings or errors indicate degraded behavior; otherwise the normal route completed.",
            source="task_service",
            confidence=1.0,
            details={
                "warning_count": len(warnings),
                "error_count": len(errors),
                "warnings": warnings,
            },
            warnings=warnings,
        ),
        "self_reflection_decision": _decision(
            decision=str(self_reflection.get("status") or "not_available"),
            reason="Checked answer presence, grounding evidence, confidence, and degraded warnings after execution.",
            source="self_reflection",
            confidence=self_reflection.get("confidence"),
            details={
                "grounding_level": self_reflection.get("grounding_level"),
                "evidence_counts": self_reflection.get("evidence_counts", {}),
                "recommendations": self_reflection.get("recommendations", []),
            },
        ),
        "final_response_plan": _decision(
            decision=finish_reason,
            reason="Projected internal execution into user_view, debug_view, trace, and optional artifacts.",
            source="response_composer",
            confidence=1.0,
            details={
                "task_status": task_status,
                "finish_reason": finish_reason,
                "output_complete": output_complete,
                "user_view_block_count": len(user_view_payload.get("blocks") or []),
                "citation_count": len(data.get("citations") or []),
                "artifact_count": len(debug_view.get("artifacts") or []),
            },
        ),
    }
    return {
        "version": "agent_decision_trace_v1",
        "decisions": decisions,
        "summary": {
            "route_type": intent.get("route_type"),
            "skill_id": skill_runtime.get("skill_id"),
            "retrieval_mode": retrieval_mode,
            "memory_status": decisions["memory_decision"]["decision"],
            "finish_reason": finish_reason,
        },
    }
