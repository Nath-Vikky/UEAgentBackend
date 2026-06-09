from __future__ import annotations

from typing import Any

from app.schemas.requests import UnifiedTaskRequest
from app.tools.registry import iter_tool_specs


AGENT_TURN_CONTEXT_VERSION = "agent_turn_context_v1"


def _latest_user_message(request: UnifiedTaskRequest) -> str:
    payload_text = str(
        request.payload.get("user_query")
        or request.payload.get("requirement_description")
        or ""
    ).strip()
    if payload_text:
        return payload_text
    for message in reversed(request.session.messages):
        if message.role == "user" and message.content.strip():
            return message.content.strip()
    return ""


def _compact_tool_summaries(context_bundle: dict[str, Any], *, limit: int = 5) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw in list(context_bundle.get("tool_context") or [])[:limit]:
        if not isinstance(raw, dict):
            continue
        items.append(
            {
                "task_id": raw.get("task_id"),
                "task_type": raw.get("task_type"),
                "status": raw.get("status"),
                "title": raw.get("title"),
                "summary": raw.get("summary"),
                "created_at": raw.get("created_at"),
            }
        )
    return items


def _target_available(value: Any) -> bool:
    if not isinstance(value, dict):
        return bool(value)
    return any(item not in (None, "", [], {}) for item in value.values())


def _active_targets(active_context: dict[str, Any]) -> dict[str, Any]:
    asset = dict(active_context.get("asset") or {})
    blueprint = dict(active_context.get("blueprint") or {})
    level_actor = dict(active_context.get("level_actor") or {})
    material = dict(active_context.get("material") or {})
    code = dict(active_context.get("code") or {})
    log = dict(active_context.get("log") or {})
    targets = {
        "asset": {
            "available": bool(asset.get("selected_assets")),
            "selected_assets": list(asset.get("selected_assets") or [])[:8],
        },
        "blueprint": {
            "available": bool(blueprint.get("current_blueprint_path") or blueprint.get("current_graph_name")),
            "current_blueprint_path": blueprint.get("current_blueprint_path"),
            "current_graph_name": blueprint.get("current_graph_name"),
            "selected_node_id": blueprint.get("selected_node_id"),
            "last_successful_operation": blueprint.get("last_successful_operation"),
        },
        "level_actor": {
            "available": bool(
                level_actor.get("current_actor_reference")
                or level_actor.get("selected_actor_references")
                or level_actor.get("current_actor_inventory")
            ),
            "current_actor_reference": level_actor.get("current_actor_reference"),
            "selected_actor_references": list(level_actor.get("selected_actor_references") or [])[:8],
        },
        "material": {
            "available": bool(
                material.get("current_material_instance_path")
                or material.get("selected_material_instance_paths")
                or material.get("current_material_instance_inventory")
            ),
            "current_material_instance_path": material.get("current_material_instance_path"),
            "selected_material_instance_paths": list(material.get("selected_material_instance_paths") or [])[:8],
        },
        "code": {
            "available": bool(code.get("current_file") or code.get("selected_files")),
            "current_file": code.get("current_file"),
            "selected_files": list(code.get("selected_files") or [])[:8],
        },
        "log": {
            "available": bool(log.get("has_log_text") or log.get("log_file_path")),
            "source": log.get("source"),
            "log_file_path": log.get("log_file_path"),
            "log_text_chars": log.get("log_text_chars"),
        },
    }
    targets["has_any_active_target"] = any(
        _target_available(value) and bool(value.get("available"))
        for value in targets.values()
        if isinstance(value, dict)
    )
    return targets


def _available_tool_cards(*, free_chat_only: bool = False, limit: int = 40) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for spec in iter_tool_specs(include_disabled=False):
        if free_chat_only and not spec.allowed_in_free_chat:
            continue
        cards.append(
            {
                "tool_id": spec.tool_id,
                "title": spec.title,
                "category": spec.category,
                "transport": spec.transport,
                "side_effect_level": spec.side_effect_level,
                "requires_confirmation": spec.effective_requires_confirmation,
                "allowed_in_free_chat": spec.allowed_in_free_chat,
                "active_context_keys": list(spec.active_context_keys),
            }
        )
    return cards[:limit]


def build_agent_turn_context(
    *,
    request: UnifiedTaskRequest,
    routing: dict[str, Any],
    context_bundle: dict[str, Any],
) -> dict[str, Any]:
    active_context = dict(context_bundle.get("active_context") or {})
    inventory = dict(context_bundle.get("project_inventory_context") or {})
    retrieval = dict(context_bundle.get("retrieval_context") or {})
    locale = dict(routing.get("locale") or context_bundle.get("language_context") or {})
    route = dict(routing.get("route") or {})
    intent = dict(routing.get("intent") or {})
    active_targets = _active_targets(active_context)
    return {
        "version": AGENT_TURN_CONTEXT_VERSION,
        "session_id": request.session.session_id,
        "user_message": _latest_user_message(request),
        "output_language": locale.get("final_output_language"),
        "route": {
            "route_type": intent.get("route_type"),
            "intent_type": intent.get("intent_type"),
            "selected_tool_id": route.get("selected_tool_id"),
            "candidate_tool_ids": route.get("candidate_tool_ids", []),
            "planner_confidence": route.get("planner_confidence"),
            "decision_source": route.get("decision_source"),
        },
        "active_targets": active_targets,
        "context_sources": {
            "active_ue_context": bool(active_targets.get("has_any_active_target")),
            "project_inventory": bool(inventory.get("has_snapshot") or inventory.get("status") == "available"),
            "rag": bool(retrieval.get("retrieved_docs") or retrieval.get("status") == "available"),
            "session_memory": bool((context_bundle.get("session_summary") or {}).get("summary_text")),
            "tool_summaries": bool(context_bundle.get("tool_context")),
            "recent_editor_operations": bool(context_bundle.get("recent_editor_operations")),
        },
        "project_inventory_summary": {
            "status": inventory.get("status"),
            "has_snapshot": bool(inventory.get("has_snapshot")),
            "snapshot_id": inventory.get("snapshot_id"),
            "summary": inventory.get("summary", {}),
        },
        "rag_context": {
            "status": retrieval.get("status"),
            "mode": retrieval.get("mode"),
            "retrieved_count": len(retrieval.get("retrieved_docs") or []),
        },
        "mcp_provider_status": (active_context.get("mcp") or {}),
        "available_tools": _available_tool_cards(
            free_chat_only=request.task_type in {"agent_chat", "project_qa"},
        ),
        "previous_tool_summaries": _compact_tool_summaries(context_bundle),
        "previous_editor_operations": list(context_bundle.get("recent_editor_operations") or [])[:5],
        "budget": context_bundle.get("context_budget_report") or context_bundle.get("budget") or {},
    }


__all__ = ["AGENT_TURN_CONTEXT_VERSION", "build_agent_turn_context"]
