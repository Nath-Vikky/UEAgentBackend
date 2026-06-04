from __future__ import annotations

import re
from typing import Any


CONTEXT_PACK_VERSION = "context_pack_v1"
DEFAULT_MEMORY_LIMIT = 5
DEFAULT_TOOL_LIMIT = 5


def _clip(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 3, 0)]}..."


def _tokens(value: Any) -> set[str]:
    text = str(value or "").lower()
    return {
        token
        for token in re.findall(r"[a-z0-9_./:-]+|[\u4e00-\u9fff]{2,}", text)
        if len(token) >= 2
    }


def _score_against_query(*, query: str, haystack: str, metadata: dict[str, Any] | None = None) -> float:
    query_text = str(query or "").lower().strip()
    haystack_text = str(haystack or "").lower()
    query_tokens = _tokens(query_text)
    haystack_tokens = _tokens(haystack_text)
    score = 0.0
    if query_text and query_text in haystack_text:
        score += 2.0
    if query_tokens:
        score += len(query_tokens & haystack_tokens) / max(len(query_tokens), 1)
    metadata = metadata or {}
    raw_score = metadata.get("score")
    if isinstance(raw_score, int | float):
        score += min(max(float(raw_score), 0.0), 1.0) * 0.25
    return round(score, 4)


def select_memory_items(
    memory_context: dict[str, Any],
    *,
    query: str,
    limit: int = DEFAULT_MEMORY_LIMIT,
) -> list[dict[str, Any]]:
    """Select compact memory snippets for prompt use without using an LLM."""

    ranked: list[tuple[float, int, dict[str, Any]]] = []
    for index, item in enumerate(list(memory_context.get("items") or [])):
        if not isinstance(item, dict):
            continue
        text = _clip(item.get("text") or item.get("snippet") or "", 420)
        title = item.get("title") or item.get("category") or item.get("domain") or item.get("provider_id")
        haystack = " ".join(str(part or "") for part in (title, text, item.get("retrieval_source")))
        score = _score_against_query(query=query, haystack=haystack, metadata=item)
        if score <= 0 and not text:
            continue
        ranked.append((score, index, item))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]))
    selected: list[dict[str, Any]] = []
    for score, _index, item in ranked[:limit]:
        selected.append(
            {
                "provider_id": item.get("provider_id"),
                "source_id": item.get("memory_id") or item.get("entry_id") or item.get("url"),
                "title": item.get("title") or item.get("category") or item.get("domain"),
                "score": score,
                "text": _clip(item.get("text") or item.get("snippet") or "", 420),
                "retrieval_source": item.get("retrieval_source") or item.get("provider_id"),
                "selection_reason": "lexical_overlap_or_existing_rank",
            }
        )
    return selected


def _compact_recent_messages(context_bundle: dict[str, Any], *, limit: int = 6) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for item in list(context_bundle.get("recent_messages") or [])[-limit:]:
        if not isinstance(item, dict):
            continue
        messages.append(
            {
                "role": item.get("role"),
                "content": _clip(item.get("content"), 500),
                "source": item.get("source"),
                "created_at": item.get("created_at"),
            }
        )
    return messages


def _compact_tool_summaries(context_bundle: dict[str, Any], *, limit: int = DEFAULT_TOOL_LIMIT) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for item in list(context_bundle.get("tool_context") or [])[:limit]:
        if not isinstance(item, dict):
            continue
        summaries.append(
            {
                "task_id": item.get("task_id"),
                "task_type": item.get("task_type"),
                "status": item.get("status"),
                "title": item.get("title"),
                "summary": _clip(item.get("summary"), 360),
                "created_at": item.get("created_at"),
            }
        )
    return summaries


def _compact_editor_operations(context_bundle: dict[str, Any], *, limit: int = 3) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    for item in list(context_bundle.get("recent_editor_operations") or [])[:limit]:
        if not isinstance(item, dict):
            continue
        operations.append(
            {
                "operation_type": item.get("operation_type"),
                "tool_id": item.get("tool_id"),
                "success": item.get("success"),
                "execution_state": item.get("execution_state"),
                "target": item.get("target") or {},
                "received_at": item.get("received_at"),
            }
        )
    return operations


def _inventory_focus(context_bundle: dict[str, Any]) -> dict[str, Any]:
    inventory = dict(context_bundle.get("project_inventory_context") or {})
    summary = dict(inventory.get("summary") or {})
    query_summary = dict(inventory.get("query_summary") or {})
    return {
        "status": inventory.get("status"),
        "has_snapshot": bool(inventory.get("has_snapshot")),
        "snapshot_id": inventory.get("snapshot_id"),
        "project_id": inventory.get("project_id"),
        "summary": {
            "asset_count": summary.get("asset_count", 0),
            "code_file_count": summary.get("code_file_count", 0),
            "level_actor_count": summary.get("level_actor_count", 0),
            "material_instance_count": summary.get("material_instance_count", 0),
        },
        "selected_assets": list(inventory.get("selected_assets") or [])[:5],
        "query_candidate_count": len(inventory.get("query_candidates") or []),
        "query_summary": query_summary,
    }


def _compact_components(value: Any, *, limit: int = 8) -> list[dict[str, Any] | str]:
    components: list[dict[str, Any] | str] = []
    for item in list(value or [])[:limit]:
        if isinstance(item, dict):
            components.append(
                {
                    "component_name": item.get("component_name") or item.get("name"),
                    "component_class": item.get("component_class") or item.get("class"),
                }
            )
            continue
        if item:
            components.append(_clip(item, 120))
    return components


def _compact_parameter_preview(value: Any, *, limit: int = 6) -> list[dict[str, Any]]:
    parameters: list[dict[str, Any]] = []
    for item in list(value or [])[:limit]:
        if not isinstance(item, dict):
            continue
        compact = {"name": item.get("name") or item.get("parameter_name")}
        if "value" in item:
            compact["value"] = item.get("value")
        if "texture_path" in item:
            compact["texture_path"] = _clip(item.get("texture_path"), 180)
        parameters.append(compact)
    return parameters


def _compact_level_actor_inventory(value: Any) -> dict[str, Any]:
    item = dict(value or {})
    if not item:
        return {}
    return {
        "actor_label": item.get("actor_label"),
        "actor_class": item.get("actor_class"),
        "level_name": item.get("level_name"),
        "blueprint_path": item.get("blueprint_path"),
        "transform": item.get("transform") or {},
        "component_count": item.get("component_count", len(list(item.get("components") or []))),
        "components": _compact_components(item.get("components")),
    }


def _compact_level_actor_context(active_context: dict[str, Any]) -> dict[str, Any]:
    context = dict(active_context.get("level_actor") or {})
    if not context:
        return {}
    details = [
        compact
        for compact in (
            _compact_level_actor_inventory(item)
            for item in list(context.get("selected_actor_details") or [])[:3]
            if isinstance(item, dict)
        )
        if compact
    ]
    return {
        "selected_actor_references": list(context.get("selected_actor_references") or [])[:5],
        "current_actor_reference": context.get("current_actor_reference"),
        "selected_actor_count": context.get("selected_actor_count", 0),
        "current_actor_inventory": _compact_level_actor_inventory(context.get("current_actor_inventory")),
        "selected_actor_details": details,
    }


def _compact_material_instance_inventory(value: Any) -> dict[str, Any]:
    item = dict(value or {})
    if not item:
        return {}
    return {
        "material_instance_path": item.get("material_instance_path"),
        "material_instance_name": item.get("material_instance_name"),
        "parent_material": item.get("parent_material"),
        "scalar_parameter_count": item.get(
            "scalar_parameter_count",
            len(list(item.get("scalar_parameters") or [])),
        ),
        "vector_parameter_count": item.get(
            "vector_parameter_count",
            len(list(item.get("vector_parameters") or [])),
        ),
        "texture_parameter_count": item.get(
            "texture_parameter_count",
            len(list(item.get("texture_parameters") or [])),
        ),
        "static_switch_parameter_count": item.get(
            "static_switch_parameter_count",
            len(list(item.get("static_switch_parameters") or [])),
        ),
        "scalar_parameters": _compact_parameter_preview(item.get("scalar_parameters")),
        "vector_parameters": _compact_parameter_preview(item.get("vector_parameters")),
        "texture_parameters": _compact_parameter_preview(item.get("texture_parameters")),
        "static_switch_parameters": _compact_parameter_preview(item.get("static_switch_parameters")),
    }


def _compact_material_context(active_context: dict[str, Any]) -> dict[str, Any]:
    context = dict(active_context.get("material") or {})
    if not context:
        return {}
    details = [
        compact
        for compact in (
            _compact_material_instance_inventory(item)
            for item in list(context.get("selected_material_instance_details") or [])[:3]
            if isinstance(item, dict)
        )
        if compact
    ]
    return {
        "selected_material_instance_paths": list(context.get("selected_material_instance_paths") or [])[:5],
        "current_material_instance_path": context.get("current_material_instance_path"),
        "selected_material_instance_count": context.get("selected_material_instance_count", 0),
        "current_material_instance_inventory": _compact_material_instance_inventory(
            context.get("current_material_instance_inventory")
        ),
        "selected_material_instance_details": details,
    }


def build_context_pack(
    context_bundle: dict[str, Any],
    *,
    memory_limit: int = DEFAULT_MEMORY_LIMIT,
) -> dict[str, Any]:
    """Project the raw context bundle into explicit prompt/debug layers."""

    input_summary = dict(context_bundle.get("input_summary") or {})
    active_context = dict(context_bundle.get("active_context") or {})
    editor_context = dict(context_bundle.get("editor_context") or {})
    memory_context = dict(context_bundle.get("memory") or {})
    query = str(input_summary.get("latest_user_message") or memory_context.get("query") or "")
    selected_memory = select_memory_items(memory_context, query=query, limit=memory_limit)
    tool_summaries = _compact_tool_summaries(context_bundle)
    editor_operations = _compact_editor_operations(context_bundle)
    inventory_focus = _inventory_focus(context_bundle)
    level_actor_focus = _compact_level_actor_context(active_context)
    material_focus = _compact_material_context(active_context)
    budget = dict(context_bundle.get("budget") or {})

    return {
        "version": CONTEXT_PACK_VERSION,
        "mode": "structured_compact_context",
        "system_layer": {
            "agent_boundary": "LLM may reason and draft plans; confirmed UE writes must go through Proposal execution.",
            "tool_policy": "Read-only context may be used directly. Write operations require user confirmation.",
            "output_language": (context_bundle.get("language_context") or {}).get("final_output_language"),
            "chain_of_thought_policy": "Expose concise thought_summary and plan_summary only, never raw chain-of-thought.",
        },
        "project_layer": {
            "project": active_context.get("project") or {},
            "editor_context": editor_context,
            "inventory": inventory_focus,
        },
        "active_layer": {
            "asset": active_context.get("asset") or {},
            "blueprint": active_context.get("blueprint") or {},
            "code": active_context.get("code") or {},
            "log": active_context.get("log") or {},
            "level_actor": level_actor_focus,
            "material": material_focus,
            "editor_focus": active_context.get("editor_focus") or {},
            "editor_operation": active_context.get("editor_operation") or {},
            "mcp": active_context.get("mcp") or {},
        },
        "conversation_layer": {
            "session_summary": context_bundle.get("session_summary") or {},
            "recent_messages": _compact_recent_messages(context_bundle),
            "recent_message_count": len(context_bundle.get("recent_messages") or []),
        },
        "knowledge_layer": {
            "kb": (active_context.get("kb") or {}),
            "retrieval_context": context_bundle.get("retrieval_context") or {},
            "project_inventory_context": inventory_focus,
        },
        "memory_layer": {
            "sources": list(memory_context.get("sources") or []),
            "selected_items": selected_memory,
            "selection_policy": {
                "mode": "lexical_manifest_first",
                "max_items": memory_limit,
                "fallback": "inject nothing when no compact evidence is available",
            },
        },
        "tool_layer": {
            "tool_observation_summary": tool_summaries,
            "recent_editor_operations": editor_operations,
            "proposal_policy": "Write-side editor actions remain pending Proposals until confirmed by the user.",
        },
        "budget_layer": {
            **budget,
            "selected_memory_count": len(selected_memory),
            "tool_observation_count": len(tool_summaries),
            "recent_editor_operation_count": len(editor_operations),
        },
        "debug_summary": {
            "route_type": input_summary.get("route_type"),
            "actual_task_type": input_summary.get("actual_task_type"),
            "selected_tool_id": input_summary.get("selected_tool_id"),
            "has_inventory_snapshot": inventory_focus.get("has_snapshot"),
            "has_level_actor_focus": bool(level_actor_focus.get("current_actor_inventory")),
            "has_material_focus": bool(material_focus.get("current_material_instance_inventory")),
            "selected_memory_count": len(selected_memory),
            "tool_observation_count": len(tool_summaries),
        },
    }


def context_pack_prompt_excerpt(context_pack: dict[str, Any]) -> str:
    if not context_pack:
        return ""
    lines = ["Context Pack v1:"]
    project_layer = dict(context_pack.get("project_layer") or {})
    project = dict(project_layer.get("project") or {})
    inventory = dict(project_layer.get("inventory") or {})
    if project or inventory:
        inventory_summary = dict(inventory.get("summary") or {})
        lines.append(
            "- Project: "
            f"name={project.get('project_name')}, "
            f"active_panel={project.get('active_panel')}, "
            f"assets={inventory_summary.get('asset_count', 0)}, "
            f"code_files={inventory_summary.get('code_file_count', 0)}"
        )
    active = dict(context_pack.get("active_layer") or {})
    if active:
        lines.append(
            "- Active: "
            f"asset={active.get('asset')}, "
            f"blueprint={active.get('blueprint')}, "
            f"code={active.get('code')}, "
            f"log={active.get('log')}, "
            f"level_actor={active.get('level_actor')}, "
            f"material={active.get('material')}, "
            f"editor_focus={active.get('editor_focus')}"
        )
    conversation = dict(context_pack.get("conversation_layer") or {})
    session_summary = dict(conversation.get("session_summary") or {})
    if session_summary.get("status") == "available":
        lines.append(f"- Session summary: {session_summary.get('summary_text')}")
    recent_messages = list(conversation.get("recent_messages") or [])
    if recent_messages:
        lines.append("- Recent messages:")
        for item in recent_messages[-6:]:
            lines.append(f"  - {item.get('role')}: {item.get('content')}")
    memory = dict(context_pack.get("memory_layer") or {})
    selected_memory = list(memory.get("selected_items") or [])
    if selected_memory:
        has_web_memory = any(item.get("provider_id") == "web_memory" for item in selected_memory)
        title = "Selected memory and Web memory cached evidence" if has_web_memory else "Selected memory"
        lines.append(f"- {title}:")
        for item in selected_memory:
            source = item.get("retrieval_source") or item.get("provider_id")
            title = item.get("title") or item.get("source_id") or source
            lines.append(f"  - {title} ({source}, score={item.get('score')}): {item.get('text')}")
    tools = dict(context_pack.get("tool_layer") or {})
    observations = list(tools.get("tool_observation_summary") or [])
    if observations:
        lines.append("- Recent tool observations:")
        for item in observations:
            lines.append(f"  - {item.get('task_type')}[{item.get('status')}]: {item.get('summary')}")
    editor_operations = list(tools.get("recent_editor_operations") or [])
    if editor_operations:
        lines.append("- Recent confirmed editor operations:")
        for item in editor_operations:
            lines.append(
                "  - "
                f"{item.get('operation_type')}[{item.get('execution_state')}]: "
                f"target={item.get('target')}"
            )
    return "\n".join(lines)
