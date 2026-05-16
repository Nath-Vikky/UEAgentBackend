from __future__ import annotations

from typing import Any

from app.agent.context_builder import build_context_summary
from app.schemas.requests import UnifiedTaskRequest
from app.tools.contracts import validate_tool_call_input, validate_tool_result
from app.tools.project_file import (
    project_file_candidate,
    project_file_candidate_from_result,
    should_read_project_file,
)
from app.tools.registry import free_chat_tool_ids, tool_capability_cards
from app.utils.json_tools import dumps_pretty


PROJECT_QA_INVENTORY_TOKENS = (
    "asset",
    "assets",
    "blueprint",
    "staticmesh",
    "static mesh",
    "skeletal",
    "material",
    "texture",
    "nanite",
    "lod",
    "code file",
    ".cpp",
    ".h",
    "module",
    "settings",
    "properties",
    "component",
    "components",
    "variable",
    "variables",
    "function",
    "functions",
    "graph",
    "graphs",
    "event graph",
    "selected asset",
    "current asset",
    "资产",
    "蓝图",
    "静态网格体",
    "材质",
    "贴图",
    "代码文件",
    "模块",
    "属性",
    "设置",
)

PROJECT_QA_KNOWLEDGE_TOKENS = (
    "why",
    "how",
    "should",
    "best practice",
    "rule",
    "guideline",
    "explain",
    "risk",
    "为什么",
    "怎么",
    "如何",
    "应该",
    "规范",
    "规则",
    "建议",
    "风险",
    "解释",
)


def build_project_qa_deterministic_tool_plan(
    *,
    query: str,
    routing: dict[str, Any],
) -> dict[str, Any]:
    selected_tool_id = routing["route"].get("selected_tool_id")
    query_lower = query.lower()
    use_inventory = selected_tool_id == "query_project_inventory" or any(
        token in query_lower or token in query for token in PROJECT_QA_INVENTORY_TOKENS
    )
    needs_knowledge = selected_tool_id != "query_project_inventory" or any(
        token in query_lower or token in query for token in PROJECT_QA_KNOWLEDGE_TOKENS
    )
    return {
        "selected_tool_id": selected_tool_id,
        "use_inventory": use_inventory,
        "use_knowledge": needs_knowledge,
        "reason": (
            "inventory_first"
            if selected_tool_id == "query_project_inventory"
            else "retrieval_backed_project_qa"
        ),
    }


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


def build_react_lite_tool_plan(
    *,
    request: UnifiedTaskRequest,
    query: str,
    deterministic_plan: dict[str, Any],
    chat_config: Any,
    llm_service: Any,
    output_language_label: str,
    rag_top_k: int,
) -> dict[str, Any]:
    allowed_tool_ids = free_chat_tool_ids()
    planner_decision = {
        "status": "skipped",
        "reason": "llm_unavailable_or_not_attempted",
        "requested_tool_ids": [],
        "confidence": 0.0,
        "error": "",
        "provider": "openai_compatible",
        "model": chat_config.model,
        "profile_id": chat_config.profile_id,
    }
    use_inventory = bool(deterministic_plan.get("use_inventory"))
    use_knowledge = bool(deterministic_plan.get("use_knowledge"))
    use_project_file = should_read_project_file(request=request, query=query)
    planner_inputs: dict[str, dict[str, Any]] = {}

    llm_available, _ = llm_service.availability(chat_config)
    if llm_available:
        decision = llm_service.complete_json_object(
            messages=build_react_planner_messages(
                query=query,
                context_summary=build_context_summary(request) or "(none)",
                deterministic_plan=deterministic_plan,
                allowed_tools=[
                    card
                    for card in tool_capability_cards()
                    if card["tool_id"] in allowed_tool_ids
                ],
                output_language_label=output_language_label,
            ),
            config=chat_config,
        )
        planner_decision.update(
            {
                "status": "completed" if decision.get("ok") else "skipped",
                "reason": decision.get("reason"),
                "error": decision.get("error") or "",
                "provider": decision.get("provider"),
                "model": decision.get("model"),
                "profile_id": decision.get("profile_id"),
            }
        )
        payload = decision.get("payload") if decision.get("ok") else None
        if isinstance(payload, dict):
            sanitized = sanitize_react_planner_payload(
                payload,
                allowed_tool_ids=set(allowed_tool_ids),
            )
            requested_tool_ids = sanitized["requested_tool_ids"]
            planner_inputs = sanitized["tool_inputs_by_id"]
            planner_decision["requested_tool_ids"] = requested_tool_ids
            planner_decision["tool_inputs_by_id"] = planner_inputs
            planner_decision["confidence"] = sanitized["confidence"]
            use_inventory = use_inventory or "query_project_inventory" in requested_tool_ids
            use_knowledge = use_knowledge or "retrieve_project_knowledge" in requested_tool_ids
            use_project_file = use_project_file or "read_project_file" in requested_tool_ids

    candidate = project_file_candidate(request) if use_project_file else {}
    project_file_input = (
        {
            "project_root": candidate["project_root"],
            "file_path": candidate["file_path"],
            "max_bytes": candidate["max_bytes"],
        }
        if candidate
        else None
    )
    tool_calls = build_project_qa_tool_calls(
        query=query,
        use_inventory=use_inventory,
        use_knowledge=use_knowledge,
        use_project_file=use_project_file,
        rag_top_k=rag_top_k,
        planner_inputs=planner_inputs,
        project_file_input=project_file_input,
    )
    input_contracts = [
        validate_tool_call_input(str(call.get("tool_id") or ""), dict(call.get("input") or {}))
        for call in tool_calls
    ]
    return {
        **deterministic_plan,
        "use_inventory": use_inventory,
        "use_knowledge": use_knowledge,
        "use_project_file": use_project_file,
        "tool_calls": tool_calls,
        "tool_call_sequence": tool_call_sequence(tool_calls),
        "input_contracts": input_contracts,
        "planner_decision": planner_decision,
        "reason": (
            "react_lite_llm_augmented"
            if planner_decision["status"] == "completed"
            else deterministic_plan.get("reason", "deterministic_fallback")
        ),
    }


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


def tool_call_input(tool_plan: dict[str, Any], tool_id: str) -> dict[str, Any]:
    for call in list(tool_plan.get("tool_calls") or []):
        if call.get("tool_id") == tool_id and isinstance(call.get("input"), dict):
            return dict(call["input"])
    return {}


def build_react_lite_trace(
    *,
    query: str,
    tool_plan: dict[str, Any],
    qa_result: dict[str, Any],
    inventory_result: dict[str, Any],
    project_file_result: dict[str, Any],
    answer_generation_mode: str,
    rag_top_k: int,
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = [
        {
            "phase": "thought",
            "text": "Decide whether the user needs current project facts, knowledge evidence, an explicit file read, or a direct answer.",
            "details": {
                "query": query,
                "selected_tool_id": tool_plan.get("selected_tool_id"),
                "use_inventory": tool_plan.get("use_inventory"),
                "use_knowledge": tool_plan.get("use_knowledge"),
                "use_project_file": tool_plan.get("use_project_file"),
                "planner_decision": tool_plan.get("planner_decision", {}),
            },
        }
    ]
    if tool_plan.get("use_inventory"):
        steps.extend(
            [
                {
                    "phase": "action",
                    "tool_id": "query_project_inventory",
                    "input": {"query": query, "limit": 8},
                },
                {
                    "phase": "observation",
                    "tool_id": "query_project_inventory",
                    "summary": f"Matched {len(inventory_result.get('items') or [])} project inventory item(s).",
                    "details": inventory_result.get("summary", {}),
                },
            ]
        )
    if tool_plan.get("use_knowledge"):
        steps.extend(
            [
                {
                    "phase": "action",
                    "tool_id": "retrieve_project_knowledge",
                    "input": {"query": query, "top_k": rag_top_k},
                },
                {
                    "phase": "observation",
                    "tool_id": "retrieve_project_knowledge",
                    "summary": f"Retrieved {len(qa_result.get('retrieved_docs') or [])} knowledge chunk(s).",
                    "details": {
                        "confidence": qa_result.get("confidence"),
                        "sources": qa_result.get("sources", []),
                    },
                },
            ]
        )
    if tool_plan.get("use_project_file"):
        steps.extend(
            [
                {
                    "phase": "action",
                    "tool_id": "read_project_file",
                    "input": project_file_candidate_from_result(project_file_result),
                },
                {
                    "phase": "observation",
                    "tool_id": "read_project_file",
                    "summary": f"Read project file status: {project_file_result.get('status')}.",
                    "details": {
                        "status": project_file_result.get("status"),
                        "reason": project_file_result.get("reason"),
                        "file_path": project_file_result.get("file_path"),
                        "resolved_path": project_file_result.get("resolved_path"),
                        "bytes_read": project_file_result.get("bytes_read"),
                        "truncated": project_file_result.get("truncated"),
                    },
                },
            ]
        )
    steps.append(
        {
            "phase": "final",
            "text": "Compose the final answer from the collected observations.",
            "details": {"answer_generation_mode": answer_generation_mode},
        }
    )
    return {
        "mode": "react_lite",
        "max_iterations": 3,
        "iterations_used": sum(1 for item in steps if item.get("phase") == "action"),
        "stop_reason": "agent_decided_done",
        "planner_status": tool_plan.get("planner_decision", {}).get("status", "skipped"),
        "tool_call_sequence": tool_call_sequence(list(tool_plan.get("tool_calls") or [])),
        "steps": steps,
    }


def build_project_qa_result_contracts(
    *,
    tool_plan: dict[str, Any],
    qa_result: dict[str, Any],
    inventory_result: dict[str, Any],
    project_file_result: dict[str, Any],
) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    if tool_plan.get("use_knowledge"):
        contracts.append(validate_tool_result("retrieve_project_knowledge", qa_result))
    if qa_result.get("web_search"):
        contracts.append(validate_tool_result("web_search_knowledge", qa_result["web_search"]))
    if tool_plan.get("use_inventory"):
        contracts.append(validate_tool_result("query_project_inventory", inventory_result))
    if tool_plan.get("use_project_file"):
        contracts.append(validate_tool_result("read_project_file", project_file_result))
    return contracts


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
    "build_project_qa_deterministic_tool_plan",
    "build_project_qa_result_contracts",
    "build_project_qa_tool_calls",
    "build_react_lite_tool_plan",
    "build_react_lite_trace",
    "build_react_planner_messages",
    "sanitize_react_planner_payload",
    "tool_call_input",
    "tool_call_sequence",
]
