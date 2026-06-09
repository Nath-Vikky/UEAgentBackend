from __future__ import annotations

from typing import Any

from app.schemas.requests import UnifiedTaskRequest


AGENT_DAG_VERSION = "agent_dag_v2"


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
    """Build a framework-neutral runtime DAG for the single-process Agent chain."""

    intent = dict(routing.get("intent") or {})
    route = dict(routing.get("route") or {})
    intent_draft = dict(context_bundle.get("intent_draft") or {})
    llm_intent_draft = dict(context_bundle.get("llm_intent_draft") or {})
    verified_intent = dict(context_bundle.get("verified_intent") or {})
    context_resolution = dict(context_bundle.get("context_resolution") or {})
    tool_plan = dict(context_bundle.get("tool_plan_v1") or {})
    tool_plan_self_check = dict(
        context_bundle.get("tool_plan_self_check")
        or data.get("tool_plan_self_check")
        or debug_view.get("tool_plan_self_check")
        or {}
    )
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
                "route_type": intent.get("route_type"),
                "tool_id": selected_tool_id or None,
                "mode": tool_plan.get("mode"),
                "side_effect_level": tool_plan.get("side_effect_level"),
                "requires_proposal": tool_plan.get("requires_proposal"),
                "skill_id": skill_runtime.get("skill_id"),
                "self_check_status": tool_plan_self_check.get("status"),
                "self_check_error_count": tool_plan_self_check.get("error_count"),
                "self_check_warning_count": tool_plan_self_check.get("warning_count"),
                "self_check_failed_check_ids": tool_plan_self_check.get("failed_check_ids", []),
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
        "mode": "single_process_runtime_dag",
        "framework": "custom_lightweight",
        "nodes": nodes,
        "edges": _linear_edges([node["node_id"] for node in nodes]),
        "summary": {
            "node_count": len(nodes),
            "completed_count": len([node for node in nodes if node["status"] == "completed"]),
            "quality_pass_count": len([node for node in nodes if node["quality_gate"]["status"] == "pass"]),
            "quality_warning_count": len([node for node in nodes if node["quality_gate"]["status"] == "warning"]),
            "quality_blocked_count": len([node for node in nodes if node["quality_gate"]["status"] == "block"]),
            "blocking_flags": _blocking_flags(nodes),
            "run_status": _run_status(nodes, task_status=task_status, proposal_count=proposal_count),
            "route_type": intent.get("route_type"),
            "selected_tool_id": selected_tool_id or None,
            "proposal_count": proposal_count,
            "finish_reason": finish_reason,
        },
        "migration_notes": {
            "langgraph_ready": True,
            "node_ids_are_stable": True,
            "side_effects_stay_behind_proposals": True,
            "quality_gates_are_runtime_inputs": True,
        },
    }


def _node(
    node_id: str,
    role: str,
    status: str,
    responsibility: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    quality_gate = _quality_gate(node_id, status, evidence)
    return {
        "node_id": node_id,
        "role": role,
        "status": status,
        "responsibility": responsibility,
        "evidence": evidence,
        "quality_gate": quality_gate,
        "blocking_flags": list(quality_gate.get("blocking_flags") or []),
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


def _quality_gate(node_id: str, status: str, evidence: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    if node_id == "input":
        _add_check(checks, "request_normalized", bool(evidence.get("task_type")), "request_has_task_type")
    elif node_id == "intent_draft":
        _add_check(checks, "intent_available", bool(evidence.get("intent_type")), "intent_type_available")
        _add_check(checks, "target_kind_available", bool(evidence.get("target_kind")), "target_kind_available")
    elif node_id == "intent_verify":
        _add_check(checks, "route_available", bool(evidence.get("route_type")), "route_type_available")
    elif node_id == "context_resolve":
        context_status = str(evidence.get("status") or "")
        missing_context = context_status == "missing_active_context"
        _add_check(
            checks,
            "active_context_resolved_or_not_required",
            not missing_context,
            "missing_active_context" if missing_context else "context_resolved_or_not_required",
            severity="block" if missing_context else "pass",
        )
    elif node_id == "tool_plan":
        route_type = str(evidence.get("route_type") or "")
        requires_tool = route_type == "single_tool"
        self_check_status = str(evidence.get("self_check_status") or "")
        _add_check(
            checks,
            "tool_selected_when_required",
            bool(evidence.get("tool_id")) or not requires_tool,
            "single_tool_route_requires_tool_id",
            severity="block",
        )
        if self_check_status:
            _add_check(
                checks,
                "tool_plan_self_check_passed",
                self_check_status not in {"error", "warning"},
                _tool_plan_self_check_reason(evidence),
                severity="block" if self_check_status == "error" else "warning",
            )
    elif node_id == "evidence_or_tool":
        proposal_count = int(evidence.get("proposal_count") or 0)
        _add_check(
            checks,
            "proposal_waits_for_confirmation",
            status != "waiting_confirmation" or proposal_count > 0,
            "waiting_confirmation_requires_proposal",
            severity="block",
        )
    elif node_id == "response_synthesize":
        _add_check(
            checks,
            "user_view_ready",
            bool(evidence.get("user_view_ready")) or status == "skipped",
            "user_view_not_ready",
            severity="warning",
        )
    elif node_id == "response_critic":
        _add_check(
            checks,
            "answer_ok",
            evidence.get("answer_ok") is not False,
            "critic_answer_not_ok",
            severity="warning",
        )
        _add_check(
            checks,
            "no_internal_tooling_leak",
            not bool(evidence.get("remaining_internal_tooling")),
            "remaining_internal_tooling_detected",
            severity="block",
        )
    elif node_id == "finalize":
        _add_check(
            checks,
            "task_not_failed",
            str(evidence.get("task_status") or "") != "failed",
            "task_failed",
            severity="block",
        )

    if not checks:
        _add_check(checks, "node_observed", status in {"completed", "skipped", "fallback", "waiting_confirmation"}, "node_state_recorded")

    blocking_flags = [check["reason"] for check in checks if not check["passed"] and check["severity"] == "block"]
    warning_flags = [check["reason"] for check in checks if not check["passed"] and check["severity"] == "warning"]
    if blocking_flags:
        gate_status = "block"
    elif warning_flags:
        gate_status = "warning"
    else:
        gate_status = "pass"
    return {
        "status": gate_status,
        "checks": checks,
        "blocking_flags": blocking_flags,
        "warning_flags": warning_flags,
    }


def _add_check(
    checks: list[dict[str, Any]],
    check_id: str,
    passed: bool,
    reason: str,
    *,
    severity: str = "warning",
) -> None:
    checks.append(
        {
            "check_id": check_id,
            "passed": bool(passed),
            "reason": reason,
            "severity": "pass" if passed else severity,
        }
    )


def _tool_plan_self_check_reason(evidence: dict[str, Any]) -> str:
    failed = list(evidence.get("self_check_failed_check_ids") or [])
    for item in failed:
        text = str(item).strip()
        if text:
            return f"tool_plan_self_check:{text}"
    status = str(evidence.get("self_check_status") or "unknown")
    return f"tool_plan_self_check:{status}"


def _blocking_flags(nodes: list[dict[str, Any]]) -> list[str]:
    flags: list[str] = []
    for node in nodes:
        for flag in list(node.get("blocking_flags") or []):
            if flag not in flags:
                flags.append(str(flag))
    return flags


def _run_status(nodes: list[dict[str, Any]], *, task_status: str, proposal_count: int) -> str:
    if any(node["quality_gate"]["status"] == "block" for node in nodes):
        return "quality_blocked"
    if proposal_count:
        return "waiting_confirmation"
    if task_status in {"completed", "failed", "cancelled"}:
        return task_status
    return "running"
