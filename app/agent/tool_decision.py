from __future__ import annotations

from typing import Any

from app.agent.intent_models import ToolPlan
from app.tools.registry import get_tool_spec


def build_tool_plan(
    *,
    intent_draft: dict[str, Any],
    verified_intent: dict[str, Any],
    context_resolution: dict[str, Any],
    routing: dict[str, Any],
) -> dict[str, Any]:
    selected_tool_id = verified_intent.get("selected_tool_id")
    selected_tool_id = str(selected_tool_id) if selected_tool_id else None
    spec = get_tool_spec(selected_tool_id)
    permission = dict(verified_intent.get("permission_decision") or {})
    target_status = str(context_resolution.get("status") or "not_required")
    side_effect_level = spec.side_effect_level if spec else "none"
    requires_proposal = bool(permission.get("requires_user_confirmation")) or side_effect_level not in {
        "none",
        "read_only",
        "plan_only",
    }

    mode = _mode(
        selected_tool_id=selected_tool_id,
        permission=permission,
        target_status=target_status,
        side_effect_level=side_effect_level,
    )
    arguments = _argument_draft(
        selected_tool_id=selected_tool_id,
        intent_draft=intent_draft,
        context_resolution=context_resolution,
    )
    candidate_tools = [
        str(item)
        for item in (
            (routing.get("route") or {}).get("candidate_tool_ids")
            or intent_draft.get("candidate_tools")
            or []
        )
        if item
    ]
    fallback_tools = [tool_id for tool_id in candidate_tools if tool_id != selected_tool_id]
    plan = ToolPlan(
        mode=mode,
        tool_id=selected_tool_id,
        side_effect_level=side_effect_level,
        arguments=arguments,
        fallback_tools=fallback_tools[:5],
        requires_proposal=requires_proposal,
        user_facing_goal=str(intent_draft.get("user_goal") or ""),
        permission_decision=permission,
    )
    return plan.model_dump()


def _mode(
    *,
    selected_tool_id: str | None,
    permission: dict[str, Any],
    target_status: str,
    side_effect_level: str,
) -> str:
    if target_status == "missing_active_context":
        return "ask_for_context"
    if not selected_tool_id:
        return "direct_answer"
    status = str(permission.get("status") or "")
    if status == "proposal" or side_effect_level not in {"none", "read_only", "plan_only"}:
        return "proposal"
    if status == "deny":
        return "blocked"
    if status == "ask":
        return "ask_for_confirmation"
    if side_effect_level == "plan_only":
        return "plan_only"
    return "read_only"


def _argument_draft(
    *,
    selected_tool_id: str | None,
    intent_draft: dict[str, Any],
    context_resolution: dict[str, Any],
) -> dict[str, Any]:
    query = str(intent_draft.get("user_goal") or "").strip()
    fields = dict(context_resolution.get("available_fields") or {})
    target_id = str(context_resolution.get("target_id") or "").strip()
    target_kind = str(context_resolution.get("target_kind") or "")
    args: dict[str, Any] = {}
    if query:
        args["query"] = query
    if not selected_tool_id:
        return args
    if "asset" in selected_tool_id and target_id:
        args["asset_path"] = target_id
    if "static_mesh" in selected_tool_id and target_id:
        args["asset_path"] = target_id
    if "blueprint" in selected_tool_id:
        blueprint_path = fields.get("asset_path") or target_id
        if blueprint_path:
            args["blueprint_path"] = blueprint_path
        if fields.get("graph_name"):
            args["graph_name"] = fields.get("graph_name")
    if "widget" in selected_tool_id or "umg" in selected_tool_id:
        widget_path = fields.get("asset_path") or target_id
        if widget_path:
            args["widget_blueprint_path"] = widget_path
        if fields.get("widget_name"):
            args["widget_name"] = fields.get("widget_name")
    if "material" in selected_tool_id and target_id:
        args["material_instance_path"] = target_id
    if "actor" in selected_tool_id:
        actor_reference = fields.get("actor_reference") or target_id
        if actor_reference:
            args["actor_reference"] = actor_reference
    if selected_tool_id == "query_project_inventory":
        args["fields"] = _inventory_fields_for_target(target_kind)
    return {key: value for key, value in args.items() if value not in (None, "", [], {})}


def _inventory_fields_for_target(target_kind: str) -> list[str]:
    if target_kind in {"selected_asset", "asset"}:
        return ["asset_type", "asset_path", "asset_class", "references", "dependencies", "static_mesh"]
    if target_kind in {"current_blueprint", "blueprint"}:
        return ["parent_class", "graphs", "components", "variables"]
    if target_kind in {"selected_actor", "level_actor"}:
        return ["actor_class", "components", "transform", "tags", "folder_path"]
    if target_kind in {"selected_material_instance", "material"}:
        return ["parent_material", "scalar_parameters", "vector_parameters", "texture_parameters"]
    return []


__all__ = ["build_tool_plan"]
