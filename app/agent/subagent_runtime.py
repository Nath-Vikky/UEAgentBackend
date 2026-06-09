from __future__ import annotations

from typing import Any


SUBAGENT_RUNTIME_VERSION = "subagent_runtime_v1"


def build_subagent_runtime(agent_dag: dict[str, Any]) -> dict[str, Any]:
    """Derive lightweight role runtime state from the framework-neutral DAG.

    This is a projection only: it does not schedule work, call LLMs, or execute
    tools. It makes the current single-process chain easier to inspect and test.
    """

    nodes = [dict(item) for item in list(agent_dag.get("nodes") or []) if isinstance(item, dict)]
    states = [_state_from_node(node) for node in nodes]
    return {
        "version": SUBAGENT_RUNTIME_VERSION,
        "mode": "dag_projection_runtime_state",
        "framework": agent_dag.get("framework") or "custom_lightweight",
        "states": states,
        "edges": list(agent_dag.get("edges") or []),
        "summary": {
            "state_count": len(states),
            "completed_count": len([item for item in states if item["status"] == "completed"]),
            "waiting_count": len([item for item in states if item["status"] == "waiting_confirmation"]),
            "failed_count": len([item for item in states if item["status"] == "failed"]),
            "skipped_count": len([item for item in states if item["status"] == "skipped"]),
            "current_focus": _current_focus(states),
        },
        "boundary": {
            "projection_only": True,
            "no_extra_llm_calls": True,
            "no_parallel_execution": True,
            "proposal_safety_preserved": True,
        },
    }


def _state_from_node(node: dict[str, Any]) -> dict[str, Any]:
    evidence = dict(node.get("evidence") or {})
    status = str(node.get("status") or "skipped")
    return {
        "node_id": str(node.get("node_id") or ""),
        "role": str(node.get("role") or ""),
        "status": status,
        "input_summary": _input_summary(node, evidence),
        "output_summary": _output_summary(node, evidence),
        "recent_activities": _activities(node, evidence),
        "error": _error_for_status(status, evidence),
    }


def _input_summary(node: dict[str, Any], evidence: dict[str, Any]) -> str:
    node_id = str(node.get("node_id") or "")
    if node_id == "input":
        return f"task={evidence.get('task_type')}, panel={evidence.get('active_panel')}"
    if node_id == "intent_draft":
        return "latest user message and route signals"
    if node_id == "intent_verify":
        return f"draft target={evidence.get('target_kind') or 'unknown'}"
    if node_id == "context_resolve":
        return f"target={evidence.get('target_kind') or 'none'}"
    if node_id == "tool_plan":
        return f"selected_tool={evidence.get('tool_id') or 'none'}"
    if node_id == "evidence_or_tool":
        return f"mode={evidence.get('retrieval_mode') or 'not_used'}"
    if node_id == "response_synthesize":
        return "handler output, data.answer, and user_view blocks"
    if node_id == "response_critic":
        return "user-facing text and internal-tooling leakage checks"
    if node_id == "finalize":
        return "final task status and finish reason"
    return str(node.get("responsibility") or "")


def _output_summary(node: dict[str, Any], evidence: dict[str, Any]) -> str:
    node_id = str(node.get("node_id") or "")
    status = str(node.get("status") or "skipped")
    if node_id == "intent_draft":
        return f"intent={evidence.get('intent_type')}, target={evidence.get('target_kind')}"
    if node_id == "intent_verify":
        return f"route={evidence.get('route_type')}, corrections={evidence.get('correction_count', 0)}"
    if node_id == "context_resolve":
        return f"status={evidence.get('status')}, source={evidence.get('source')}"
    if node_id == "tool_plan":
        return f"mode={evidence.get('mode')}, proposal={bool(evidence.get('requires_proposal'))}"
    if node_id == "evidence_or_tool":
        return f"tool={evidence.get('selected_tool_id') or 'none'}, proposals={evidence.get('proposal_count', 0)}"
    if node_id == "response_synthesize":
        return f"user_view_ready={bool(evidence.get('user_view_ready'))}"
    if node_id == "response_critic":
        return f"answer_ok={evidence.get('answer_ok')}, leaked={bool(evidence.get('leaked_internal_tooling'))}"
    if node_id == "finalize":
        return f"task_status={evidence.get('task_status')}, finish={evidence.get('finish_reason')}"
    return f"status={status}"


def _activities(node: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
    activities = [str(node.get("responsibility") or "").strip()]
    for key in (
        "selected_tool_id",
        "tool_id",
        "route_type",
        "status",
        "source",
        "retrieval_mode",
        "proposal_count",
        "finish_reason",
    ):
        value = evidence.get(key)
        if value not in (None, "", [], {}):
            activities.append(f"{key}={value}")
    return [item for item in activities if item][:5]


def _error_for_status(status: str, evidence: dict[str, Any]) -> str | None:
    if status != "failed":
        return None
    return str(evidence.get("error") or evidence.get("reason") or "subagent_node_failed")


def _current_focus(states: list[dict[str, Any]]) -> str:
    for status in ("failed", "waiting_confirmation", "running"):
        for state in states:
            if state["status"] == status:
                return str(state.get("node_id") or "")
    completed = [state for state in states if state["status"] == "completed"]
    if completed:
        return str(completed[-1].get("node_id") or "")
    return ""


__all__ = ["SUBAGENT_RUNTIME_VERSION", "build_subagent_runtime"]
