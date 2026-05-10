from __future__ import annotations

from typing import Any

from app.utils.json_tools import dumps_pretty


def build_react_planner_messages(
    *,
    query: str,
    context_summary: str,
    deterministic_plan: dict[str, Any],
    allowed_tools: list[dict[str, Any]],
    output_language_label: str,
) -> list[dict[str, str]]:
    """Build the bounded ReAct Lite planning prompt for Project QA."""
    system_prompt = (
        "You are a safe ReAct planner for UE Agent Project QA. "
        "Choose up to 3 read-only tools from the provided tool registry. "
        "Only choose tools that are necessary for the user question. "
        "Never request file writes, shell commands, destructive actions, or tools outside the registry. "
        f"Write reasons in {output_language_label}. "
        'Return JSON only with schema: {"tool_calls":[{"tool_id":"retrieve_project_knowledge","reason":"...","input":{}}],"stop_reason":"agent_decided_done","confidence":0.0}.'
    )
    user_prompt = "\n\n".join(
        [
            f"User question:\n{query}",
            f"Context summary:\n{context_summary or '(none)'}",
            f"Deterministic fallback plan:\n{dumps_pretty(deterministic_plan)}",
            f"Available tools:\n{dumps_pretty(allowed_tools)}",
        ]
    )
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]


def sanitize_react_planner_payload(
    payload: dict[str, Any],
    *,
    allowed_tool_ids: set[str],
    max_tool_calls: int = 3,
) -> dict[str, Any]:
    """Keep only allowed read-only tool ids and safe input hints."""
    requested_tool_ids: list[str] = []
    tool_inputs_by_id: dict[str, dict[str, Any]] = {}
    for raw_call in list(payload.get("tool_calls") or [])[:max_tool_calls]:
        if not isinstance(raw_call, dict):
            continue
        tool_id = str(raw_call.get("tool_id") or "").strip()
        if tool_id not in allowed_tool_ids or tool_id in requested_tool_ids:
            continue
        requested_tool_ids.append(tool_id)
        tool_inputs_by_id[tool_id] = _sanitize_tool_input(
            tool_id,
            raw_call.get("input") if isinstance(raw_call.get("input"), dict) else {},
        )

    try:
        confidence = max(0.0, min(float(payload.get("confidence") or 0.0), 1.0))
    except (TypeError, ValueError):
        confidence = 0.0

    return {
        "requested_tool_ids": requested_tool_ids,
        "tool_inputs_by_id": tool_inputs_by_id,
        "confidence": confidence,
    }


def build_project_qa_tool_calls(
    *,
    query: str,
    use_inventory: bool,
    use_knowledge: bool,
    use_project_file: bool,
    rag_top_k: int,
    planner_inputs: dict[str, dict[str, Any]] | None = None,
    project_file_input: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build executable Project QA tool calls after policy gating."""
    planner_inputs = planner_inputs or {}
    tool_calls: list[dict[str, Any]] = []
    if use_inventory:
        inventory_input = {
            "query": query,
            "limit": 8,
            **planner_inputs.get("query_project_inventory", {}),
        }
        inventory_input["query"] = str(inventory_input.get("query") or query)
        inventory_input["limit"] = _bounded_int(inventory_input.get("limit"), default=8, low=1, high=200)
        tool_calls.append({"tool_id": "query_project_inventory", "input": inventory_input})
    if use_knowledge:
        knowledge_input = {
            "query": query,
            "top_k": rag_top_k,
            **planner_inputs.get("retrieve_project_knowledge", {}),
        }
        knowledge_input["query"] = str(knowledge_input.get("query") or query)
        knowledge_input["top_k"] = _bounded_int(
            knowledge_input.get("top_k"),
            default=rag_top_k,
            low=1,
            high=20,
        )
        tool_calls.append({"tool_id": "retrieve_project_knowledge", "input": knowledge_input})
    if use_project_file and project_file_input:
        tool_calls.append({"tool_id": "read_project_file", "input": dict(project_file_input)})
    return tool_calls[:3]


def tool_call_sequence(tool_calls: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("tool_id") or "") for item in tool_calls if item.get("tool_id")]


def _sanitize_tool_input(tool_id: str, raw_input: dict[str, Any]) -> dict[str, Any]:
    if tool_id == "query_project_inventory":
        fields = raw_input.get("fields")
        return {
            key: value
            for key, value in {
                "query": _optional_str(raw_input.get("query") or raw_input.get("user_query")),
                "project_id": _optional_str(raw_input.get("project_id")),
                "asset_path": _optional_str(raw_input.get("asset_path")),
                "asset_type": _optional_str(raw_input.get("asset_type")),
                "fields": [str(item) for item in fields[:12]] if isinstance(fields, list) else None,
                "limit": _bounded_int(raw_input.get("limit"), default=8, low=1, high=200),
            }.items()
            if _is_present(value)
        }
    if tool_id == "retrieve_project_knowledge":
        return {
            key: value
            for key, value in {
                "query": _optional_str(raw_input.get("query") or raw_input.get("user_query")),
                "top_k": _bounded_int(raw_input.get("top_k"), default=4, low=1, high=20),
            }.items()
            if _is_present(value)
        }
    return {}


def _optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _bounded_int(value: Any, *, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(parsed, high))


def _is_present(value: Any) -> bool:
    return value is not None and value != "" and value != []


__all__ = [
    "build_project_qa_tool_calls",
    "build_react_planner_messages",
    "sanitize_react_planner_payload",
    "tool_call_sequence",
]
