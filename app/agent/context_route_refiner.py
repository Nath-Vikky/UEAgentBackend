from __future__ import annotations

from typing import Any

from app.tools.registry import get_tool_spec

CONTEXT_TARGET_READ_TOOLS: dict[str, tuple[str, ...]] = {
    "selected_asset": ("mcp_get_asset_details", "mcp_get_selected_assets", "query_project_inventory"),
    "asset": ("mcp_get_asset_details", "mcp_get_selected_assets", "query_project_inventory"),
    "current_blueprint": ("mcp_get_blueprint_graph", "mcp_get_blueprint_node_details", "query_project_inventory"),
    "blueprint": ("mcp_get_blueprint_graph", "mcp_get_blueprint_node_details", "query_project_inventory"),
    "widget": ("mcp_get_umg_widget_details", "mcp_get_widget_tree", "query_project_inventory"),
    "selected_actor": ("mcp_get_level_actor_details", "mcp_get_selected_actors", "query_project_inventory"),
    "level_actor": ("mcp_get_level_actor_details", "mcp_get_selected_actors", "query_project_inventory"),
    "selected_material_instance": (
        "mcp_get_material_instance_parameters",
        "mcp_get_material_parameter_details",
        "query_project_inventory",
    ),
    "material": (
        "mcp_get_material_instance_parameters",
        "mcp_get_material_parameter_details",
        "query_project_inventory",
    ),
    "current_code_file": ("read_project_file",),
}

COARSE_CONTEXT_READ_TOOLS = {
    "query_project_inventory",
    "mcp_get_selected_assets",
    "mcp_get_selected_actors",
    "mcp_get_widget_tree",
}


def refine_route_from_resolved_context(
    *,
    routing: dict[str, Any],
    context_bundle: dict[str, Any],
    free_chat: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Use resolved active context to fill a missing read-only tool choice.

    This is deliberately conservative: it never selects write tools and never
    runs if the router already chose a tool.
    """

    route = dict(routing.get("route") or {})
    selected_tool_id = str(route.get("selected_tool_id") or "")
    mcp_available = _mcp_available(context_bundle)
    if selected_tool_id.startswith("mcp_") and not mcp_available:
        fallback = _fallback_inventory_tool_for_unavailable_mcp(
            routing=routing,
            route=route,
            selected_tool_id=selected_tool_id,
            free_chat=free_chat,
        )
        if fallback is not None:
            return fallback

    resolution = dict(context_bundle.get("context_resolution") or {})
    if resolution.get("status") != "resolved":
        return (routing, _report("skipped", "context_not_resolved"))

    target_kind = str(resolution.get("target_kind") or "")
    if selected_tool_id:
        upgraded = _upgrade_existing_context_read_tool(
            routing=routing,
            route=route,
            selected_tool_id=selected_tool_id,
            target_kind=target_kind,
            free_chat=free_chat,
            mcp_available=mcp_available,
        )
        if upgraded is not None:
            return upgraded
        return (routing, _report("skipped", "selected_tool_already_present", selected_tool_id=selected_tool_id))

    candidates = CONTEXT_TARGET_READ_TOOLS.get(target_kind, ())
    selected_tool_id = _first_allowed_read_tool(candidates, free_chat=free_chat, mcp_available=mcp_available)
    if not selected_tool_id:
        return (routing, _report("skipped", "no_allowed_read_tool", target_kind=target_kind))

    spec = get_tool_spec(selected_tool_id)
    route_type = spec.route_preference if spec and spec.route_preference in {"single_tool", "project_qa"} else "single_tool"
    reason = "Resolved active editor context selected a safe read-only inspection tool."
    refined = {
        "locale": dict(routing.get("locale") or {}),
        "intent": {
            **dict(routing.get("intent") or {}),
            "intent_type": "task_request" if route_type == "single_tool" else "project_qa",
            "knowledge_relevance": "none",
            "requires_rag": False,
            "requires_tool": True,
            "route_type": route_type,
            "reason": reason,
        },
        "route": {
            **route,
            "route_type": route_type,
            "selected_tool_id": selected_tool_id,
            "candidate_tool_ids": list(candidates),
            "selected_context_query": True,
            "decision_source": "context_resolution_refinement",
            "planner_confidence": max(float(route.get("planner_confidence") or 0.0), 0.74),
            "route_reason": reason,
        },
    }
    return (
        refined,
        _report(
            "applied",
            "selected_read_only_tool_from_resolved_context",
            target_kind=target_kind,
            selected_tool_id=selected_tool_id,
        ),
    )


def _upgrade_existing_context_read_tool(
    *,
    routing: dict[str, Any],
    route: dict[str, Any],
    selected_tool_id: str,
    target_kind: str,
    free_chat: bool,
    mcp_available: bool,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Upgrade broad selected-context readers to detail readers when safe."""

    if selected_tool_id not in COARSE_CONTEXT_READ_TOOLS:
        return None

    candidates = CONTEXT_TARGET_READ_TOOLS.get(target_kind, ())
    upgraded_tool_id = _first_allowed_read_tool(candidates, free_chat=free_chat, mcp_available=mcp_available)
    if not upgraded_tool_id or upgraded_tool_id == selected_tool_id:
        return None

    selected_spec = get_tool_spec(selected_tool_id)
    upgraded_spec = get_tool_spec(upgraded_tool_id)
    if not selected_spec or not upgraded_spec:
        return None
    if selected_spec.side_effect_level != "read_only" or upgraded_spec.side_effect_level != "read_only":
        return None

    route_type = (
        upgraded_spec.route_preference
        if upgraded_spec.route_preference in {"single_tool", "project_qa"}
        else "single_tool"
    )
    reason = "Resolved active editor context upgraded a broad read-only tool to a focused detail tool."
    refined = {
        "locale": dict(routing.get("locale") or {}),
        "intent": {
            **dict(routing.get("intent") or {}),
            "intent_type": "task_request" if route_type == "single_tool" else "project_qa",
            "knowledge_relevance": "none",
            "requires_rag": False,
            "requires_tool": True,
            "route_type": route_type,
            "reason": reason,
        },
        "route": {
            **route,
            "route_type": route_type,
            "selected_tool_id": upgraded_tool_id,
            "previous_selected_tool_id": selected_tool_id,
            "candidate_tool_ids": list(dict.fromkeys([upgraded_tool_id, *candidates, selected_tool_id])),
            "selected_context_query": True,
            "decision_source": "context_resolution_tool_upgrade",
            "planner_confidence": max(float(route.get("planner_confidence") or 0.0), 0.78),
            "route_reason": reason,
        },
    }
    return (
        refined,
        _report(
            "applied",
            "upgraded_broad_read_tool_to_detail_tool",
            target_kind=target_kind,
            selected_tool_id=selected_tool_id,
            upgraded_tool_id=upgraded_tool_id,
        ),
    )


def _fallback_inventory_tool_for_unavailable_mcp(
    *,
    routing: dict[str, Any],
    route: dict[str, Any],
    selected_tool_id: str,
    free_chat: bool,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    selected_spec = get_tool_spec(selected_tool_id)
    fallback_spec = get_tool_spec("query_project_inventory")
    if not selected_spec or selected_spec.side_effect_level != "read_only":
        return None
    if not fallback_spec or fallback_spec.side_effect_level != "read_only":
        return None
    if free_chat and not fallback_spec.allowed_in_free_chat:
        return None

    route_type = (
        fallback_spec.route_preference
        if fallback_spec.route_preference in {"single_tool", "project_qa"}
        else "project_qa"
    )
    reason = "MCP transport is unavailable, so the read-only editor-context request falls back to Project Inventory."
    refined = {
        "locale": dict(routing.get("locale") or {}),
        "intent": {
            **dict(routing.get("intent") or {}),
            "intent_type": "project_qa" if route_type == "project_qa" else "task_request",
            "knowledge_relevance": "none",
            "requires_rag": False,
            "requires_tool": True,
            "route_type": route_type,
            "reason": reason,
        },
        "route": {
            **route,
            "route_type": route_type,
            "selected_tool_id": "query_project_inventory",
            "previous_selected_tool_id": selected_tool_id,
            "candidate_tool_ids": list(dict.fromkeys(["query_project_inventory", selected_tool_id])),
            "selected_context_query": True,
            "decision_source": "mcp_unavailable_inventory_fallback",
            "planner_confidence": max(float(route.get("planner_confidence") or 0.0), 0.72),
            "route_reason": reason,
        },
    }
    return (
        refined,
        _report(
            "applied",
            "mcp_unavailable_inventory_fallback",
            selected_tool_id=selected_tool_id,
            fallback_tool_id="query_project_inventory",
        ),
    )


def _first_allowed_read_tool(candidates: tuple[str, ...], *, free_chat: bool, mcp_available: bool) -> str | None:
    for tool_id in candidates:
        if tool_id.startswith("mcp_") and not mcp_available:
            continue
        spec = get_tool_spec(tool_id)
        if not spec:
            continue
        if spec.side_effect_level != "read_only":
            continue
        if free_chat and not spec.allowed_in_free_chat:
            continue
        return tool_id
    return None


def _mcp_available(context_bundle: dict[str, Any]) -> bool:
    active_context = dict(context_bundle.get("active_context") or {})
    mcp = dict(active_context.get("mcp") or {})
    return bool(mcp.get("enabled")) and str(mcp.get("status") or "").lower() in {"ready", "available"}


def _report(status: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "version": "context_route_refinement_v1",
        "status": status,
        "reason": reason,
        **extra,
    }


__all__ = ["CONTEXT_TARGET_READ_TOOLS", "refine_route_from_resolved_context"]
