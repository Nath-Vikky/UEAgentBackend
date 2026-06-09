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
    if route.get("selected_tool_id"):
        return (routing, _report("skipped", "selected_tool_already_present"))

    resolution = dict(context_bundle.get("context_resolution") or {})
    if resolution.get("status") != "resolved":
        return (routing, _report("skipped", "context_not_resolved"))

    target_kind = str(resolution.get("target_kind") or "")
    candidates = CONTEXT_TARGET_READ_TOOLS.get(target_kind, ())
    selected_tool_id = _first_allowed_read_tool(candidates, free_chat=free_chat)
    if not selected_tool_id:
        return (routing, _report("skipped", "no_allowed_read_tool", target_kind=target_kind))

    spec = get_tool_spec(selected_tool_id)
    route_type = spec.route_preference if spec and spec.route_preference in {"single_tool", "project_qa"} else "single_tool"
    reason = "Resolved active editor context selected a safe read-only inspection tool."
    refined = {
        "locale": dict(routing.get("locale") or {}),
        "intent": {
            **dict(routing.get("intent") or {}),
            "intent_type": "selected_context_question",
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


def _first_allowed_read_tool(candidates: tuple[str, ...], *, free_chat: bool) -> str | None:
    for tool_id in candidates:
        spec = get_tool_spec(tool_id)
        if not spec:
            continue
        if spec.side_effect_level != "read_only":
            continue
        if free_chat and not spec.allowed_in_free_chat:
            continue
        return tool_id
    return None


def _report(status: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "version": "context_route_refinement_v1",
        "status": status,
        "reason": reason,
        **extra,
    }


__all__ = ["CONTEXT_TARGET_READ_TOOLS", "refine_route_from_resolved_context"]
