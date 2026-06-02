from __future__ import annotations

from typing import Any

from app.schemas.requests import UnifiedTaskRequest


ROLE_TRACE_VERSION = "multi_agent_lite_trace_v1"


def _role(
    *,
    role_id: str,
    status: str,
    responsibility: str,
    evidence: dict[str, Any] | None = None,
    next_role: str | None = None,
) -> dict[str, Any]:
    return {
        "role_id": role_id,
        "status": status,
        "responsibility": responsibility,
        "evidence": evidence or {},
        "next_role": next_role,
    }


def build_multi_agent_lite_trace(
    *,
    request: UnifiedTaskRequest,
    routing: dict[str, Any],
    context_pack: dict[str, Any],
    skill_runtime: dict[str, Any],
    retrieval_trace: dict[str, Any],
    data: dict[str, Any],
    debug_view: dict[str, Any],
    action_proposals: list[dict[str, Any]],
) -> dict[str, Any]:
    """Explain the current single-process Agent as framework-neutral roles."""

    intent = dict(routing.get("intent") or {})
    route = dict(routing.get("route") or {})
    context_summary = dict(context_pack.get("debug_summary") or {})
    memory_layer = dict(context_pack.get("memory_layer") or {})
    tool_layer = dict(context_pack.get("tool_layer") or {})
    retrieval_docs = list(retrieval_trace.get("retrieved_docs") or [])
    inventory = ((context_pack.get("project_layer") or {}).get("inventory") or {})
    selected_tool_id = route.get("selected_tool_id")
    has_tool_plan = bool(data.get("tool_plan") or debug_view.get("tool_plan"))
    has_proposal = bool(action_proposals)
    self_reflection = dict(data.get("self_reflection") or debug_view.get("self_reflection") or {})

    researcher_active = bool(
        retrieval_docs
        or inventory.get("query_candidate_count")
        or (memory_layer.get("selected_items") or [])
    )
    planner_active = bool(selected_tool_id or has_tool_plan or has_proposal or intent.get("requires_tool"))
    executor_status = "waiting_confirmation" if has_proposal else "skipped"
    reviewer_status = "completed" if self_reflection else "skipped"

    roles = [
        _role(
            role_id="coordinator",
            status="completed",
            responsibility="Classify user intent, decide route, and assemble compact context.",
            evidence={
                "task_type": request.task_type,
                "route_type": intent.get("route_type"),
                "actual_task_type": context_summary.get("actual_task_type"),
                "selected_tool_id": selected_tool_id,
            },
            next_role="researcher" if researcher_active else "planner",
        ),
        _role(
            role_id="researcher",
            status="completed" if researcher_active else "skipped",
            responsibility="Collect project evidence from RAG, grep, inventory, memory, or cached web evidence.",
            evidence={
                "retrieval_mode": retrieval_trace.get("mode"),
                "retrieved_count": len(retrieval_docs),
                "selected_memory_count": len(memory_layer.get("selected_items") or []),
                "inventory_candidate_count": inventory.get("query_candidate_count", 0),
            },
            next_role="planner",
        ),
        _role(
            role_id="planner",
            status="completed" if planner_active else "skipped",
            responsibility="Choose a built-in skill or create a safe tool/Proposal plan.",
            evidence={
                "skill_id": skill_runtime.get("skill_id"),
                "selected_tool_id": selected_tool_id,
                "has_tool_plan": has_tool_plan,
                "proposal_count": len(action_proposals),
            },
            next_role="executor" if has_proposal else "reviewer",
        ),
        _role(
            role_id="executor",
            status=executor_status,
            responsibility="Execute only confirmed write-side Proposals through UEAgentTool; read-only work is already completed.",
            evidence={
                "proposal_count": len(action_proposals),
                "proposal_policy": tool_layer.get("proposal_policy"),
            },
            next_role="reviewer",
        ),
        _role(
            role_id="reviewer",
            status=reviewer_status,
            responsibility="Run lightweight response self-checks and expose final diagnostics.",
            evidence={
                "self_reflection_status": self_reflection.get("status"),
                "grounding_level": self_reflection.get("grounding_level"),
                "recommendations": self_reflection.get("recommendations", []),
            },
            next_role=None,
        ),
    ]

    return {
        "version": ROLE_TRACE_VERSION,
        "mode": "single_process_multi_agent_lite",
        "framework": "framework_neutral",
        "roles": roles,
        "edges": [
            {"from": "coordinator", "to": "researcher"},
            {"from": "researcher", "to": "planner"},
            {"from": "planner", "to": "executor"},
            {"from": "executor", "to": "reviewer"},
        ],
        "summary": {
            "active_role_count": len([role for role in roles if role["status"] != "skipped"]),
            "route_type": intent.get("route_type"),
            "skill_id": skill_runtime.get("skill_id"),
            "proposal_count": len(action_proposals),
            "researcher_active": researcher_active,
            "planner_active": planner_active,
            "reviewer_active": reviewer_status == "completed",
        },
        "boundary": {
            "no_extra_llm_calls": True,
            "no_parallel_swarm": True,
            "proposal_safety_preserved": True,
        },
    }
