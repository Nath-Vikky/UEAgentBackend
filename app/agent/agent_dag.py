from __future__ import annotations

from typing import Any

from app.schemas.requests import UnifiedTaskRequest


AGENT_DAG_VERSION = "agent_dag_v1"


def build_agent_dag_projection(
    *,
    request: UnifiedTaskRequest,
    routing: dict[str, Any],
    context_bundle: dict[str, Any],
    skill_runtime: dict[str, Any],
    retrieval_trace: dict[str, Any],
    data: dict[str, Any],
    debug_view: dict[str, Any],
    action_proposals: list[dict[str, Any]],
    task_status: str,
    finish_reason: str,
) -> dict[str, Any]:
    """Project the single-process Agent chain as a framework-neutral DAG."""

    intent = dict(routing.get("intent") or {})
    route = dict(routing.get("route") or {})
    intent_draft = dict(context_bundle.get("intent_draft") or {})
    llm_intent_draft = dict(context_bundle.get("llm_intent_draft") or {})
    verified_intent = dict(context_bundle.get("verified_intent") or {})
    context_resolution = dict(context_bundle.get("context_resolution") or {})
    tool_plan = dict(context_bundle.get("tool_plan_v1") or {})
    response_synthesizer = dict(data.get("response_synthesizer") or debug_view.get("response_synthesizer") or {})
    response_critic = dict(data.get("response_critic") or debug_view.get("response_critic") or {})
    retrieved_docs = list(retrieval_trace.get("retrieved_docs") or [])
    selected_tool_id = str(route.get("selected_tool_id") or tool_plan.get("tool_id") or "")
    proposal_count = len(action_proposals)

    nodes = [
        _node(
            "input",
            "InputNormalizer",
            "completed",
            "Normalize request, latest user message, task type, locale, and editor context.",
            {
                "task_type": request.task_type,
                "active_panel": request.context.active_panel,
                "project_name": request.context.project_name,
            },
        ),
        _node(
            "intent_draft",
            "IntentDrafter",
            "completed" if intent_draft else "fallback",
            "Draft user intent, target kind, and candidate tools.",
            {
                "intent_type": intent_draft.get("intent_type") or intent.get("intent_type"),
                "target_kind": intent_draft.get("target_kind"),
                "confidence": intent_draft.get("confidence"),
                "draft_source": intent_draft.get("source"),
                "llm_drafter_status": llm_intent_draft.get("status"),
                "llm_drafter_applied": llm_intent_draft.get("applied"),
            },
        ),
        _node(
            "intent_verify",
            "IntentVerifier",
            "completed" if verified_intent else "fallback",
            "Verify draft intent with deterministic rules and safety constraints.",
            {
                "route_type": intent.get("route_type"),
                "selected_tool_id": route.get("selected_tool_id"),
                "correction_count": len(verified_intent.get("corrections") or []),
                "safety_flags": verified_intent.get("safety_flags", []),
            },
        ),
        _node(
            "context_resolve",
            "ContextResolver",
            "completed" if context_resolution else "skipped",
            "Resolve references such as this asset, selected actor, current Blueprint, or widget.",
            {
                "target_kind": context_resolution.get("target_kind"),
                "status": context_resolution.get("status"),
                "source": context_resolution.get("source"),
            },
        ),
        _node(
            "tool_plan",
            "ToolPlanner",
            "completed" if tool_plan or selected_tool_id else "skipped",
            "Project verified intent into a read-only tool, retrieval path, or confirmed-write Proposal plan.",
            {
                "tool_id": selected_tool_id or None,
                "mode": tool_plan.get("mode"),
                "side_effect_level": tool_plan.get("side_effect_level"),
                "requires_proposal": tool_plan.get("requires_proposal"),
                "skill_id": skill_runtime.get("skill_id"),
            },
        ),
        _node(
            "evidence_or_tool",
            "EvidenceAndToolExecutor",
            _evidence_status(retrieval_trace, selected_tool_id, proposal_count),
            "Run retrieval, inventory read, live sensing, deterministic handler, or create pending Proposals.",
            {
                "retrieval_mode": retrieval_trace.get("mode"),
                "retrieved_count": len(retrieved_docs),
                "proposal_count": proposal_count,
                "selected_tool_id": selected_tool_id or None,
            },
        ),
        _node(
            "response_synthesize",
            "ResponseSynthesizer",
            "completed" if response_synthesizer else "skipped",
            "Normalize user_view and assistant_message before final projection.",
            {
                "title_source": response_synthesizer.get("title_source"),
                "text_source": response_synthesizer.get("text_source"),
                "assistant_message_source": response_synthesizer.get("assistant_message_source"),
                "user_view_ready": response_synthesizer.get("user_view_ready"),
            },
        ),
        _node(
            "response_critic",
            "ResponseCritic",
            "completed" if response_critic else "skipped",
            "Remove internal-tooling leakage from User View while preserving Debug View diagnostics.",
            {
                "answer_ok": response_critic.get("answer_ok"),
                "leaked_internal_tooling": response_critic.get("leaked_internal_tooling"),
                "remaining_internal_tooling": response_critic.get("remaining_internal_tooling"),
            },
        ),
        _node(
            "finalize",
            "ResponseComposer",
            "completed" if task_status in {"completed", "failed", "cancelled"} else task_status,
            "Build the persisted UnifiedTaskResponse, events, artifacts, and trace summary.",
            {
                "task_status": task_status,
                "finish_reason": finish_reason,
            },
        ),
    ]

    return {
        "version": AGENT_DAG_VERSION,
        "mode": "single_process_framework_neutral_dag",
        "framework": "custom_lightweight",
        "nodes": nodes,
        "edges": _linear_edges([node["node_id"] for node in nodes]),
        "summary": {
            "node_count": len(nodes),
            "completed_count": len([node for node in nodes if node["status"] == "completed"]),
            "route_type": intent.get("route_type"),
            "selected_tool_id": selected_tool_id or None,
            "proposal_count": proposal_count,
            "finish_reason": finish_reason,
        },
        "migration_notes": {
            "langgraph_ready": True,
            "node_ids_are_stable": True,
            "side_effects_stay_behind_proposals": True,
        },
    }


def _node(
    node_id: str,
    role: str,
    status: str,
    responsibility: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "role": role,
        "status": status,
        "responsibility": responsibility,
        "evidence": evidence,
    }


def _linear_edges(node_ids: list[str]) -> list[dict[str, str]]:
    return [
        {"from": source, "to": target}
        for source, target in zip(node_ids, node_ids[1:], strict=False)
    ]


def _evidence_status(retrieval_trace: dict[str, Any], selected_tool_id: str, proposal_count: int) -> str:
    if proposal_count:
        return "waiting_confirmation"
    if selected_tool_id:
        return "completed"
    if str(retrieval_trace.get("mode") or "not_used") != "not_used":
        return "completed"
    return "skipped"
