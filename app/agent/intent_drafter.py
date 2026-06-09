from __future__ import annotations

from typing import Any

from app.agent.intent_models import IntentDraft
from app.agent.route_keyword_verifier import analyze_route_keywords, target_kind_from_keyword_report
from app.schemas.requests import UnifiedTaskRequest
from app.tools.registry import get_tool_spec


def _latest_user_message(request: UnifiedTaskRequest) -> str:
    text = str(
        request.payload.get("user_query")
        or request.payload.get("requirement_description")
        or ""
    ).strip()
    if text:
        return text
    for message in reversed(request.session.messages):
        if message.role == "user" and message.content.strip():
            return message.content.strip()
    return ""


def _route(context_bundle: dict[str, Any], routing: dict[str, Any]) -> dict[str, Any]:
    turn_route = dict((context_bundle.get("agent_turn_context") or {}).get("route") or {})
    route = dict(routing.get("route") or {})
    return {**route, **{key: value for key, value in turn_route.items() if value not in (None, "", [])}}


def _target_from_active_targets(active_targets: dict[str, Any]) -> tuple[str, str]:
    priority = ("asset", "blueprint", "widget", "level_actor", "material", "code", "log")
    for key in priority:
        target = dict(active_targets.get(key) or {})
        if not target.get("available"):
            continue
        if key == "asset":
            selected = list(target.get("selected_assets") or [])
            return ("selected_asset", str(selected[0] if selected else "selected_asset"))
        if key == "blueprint":
            return (
                "current_blueprint",
                str(target.get("current_blueprint_path") or target.get("current_graph_name") or "current_blueprint"),
            )
        if key == "widget":
            return (
                "widget",
                str(
                    target.get("current_widget_blueprint_path")
                    or target.get("selected_widget_name")
                    or target.get("current_widget_name")
                    or "current_widget"
                ),
            )
        if key == "level_actor":
            refs = list(target.get("selected_actor_references") or [])
            return ("selected_actor", str(target.get("current_actor_reference") or (refs[0] if refs else "selected_actor")))
        if key == "material":
            paths = list(target.get("selected_material_instance_paths") or [])
            return (
                "selected_material_instance",
                str(target.get("current_material_instance_path") or (paths[0] if paths else "selected_material")),
            )
        if key == "code":
            files = list(target.get("selected_files") or [])
            return ("current_code_file", str(target.get("current_file") or (files[0] if files else "current_file")))
        if key == "log":
            return ("current_log", str(target.get("log_file_path") or target.get("source") or "current_log"))
    return ("none", "")


def _target_from_tool(selected_tool_id: str | None) -> tuple[str, str] | None:
    if not selected_tool_id:
        return None
    if selected_tool_id == "editor_place_actor_in_level":
        return ("project_inventory", "")
    if selected_tool_id == "mcp_get_level_actors":
        return ("project_inventory", "")
    if "asset" in selected_tool_id:
        return ("asset", "")
    if "blueprint" in selected_tool_id:
        return ("blueprint", "")
    if "widget" in selected_tool_id or "umg" in selected_tool_id:
        return ("widget", "")
    if "material" in selected_tool_id:
        return ("material", "")
    if "actor" in selected_tool_id:
        return ("level_actor", "")
    if "knowledge" in selected_tool_id:
        return ("knowledge_base", "")
    if "inventory" in selected_tool_id:
        return ("project_inventory", "")
    if "file" in selected_tool_id:
        return ("project_file", "")
    return None


def _text_suggests_selected_target(text: str) -> tuple[str, str] | None:
    lowered = text.lower()
    if any(token in lowered for token in ("this asset", "selected asset", "current asset")) or any(
        token in text for token in ("这个资产", "该资产", "当前资产", "选中的资产", "它")
    ):
        return ("selected_asset", "")
    if any(token in lowered for token in ("this mesh", "selected mesh", "current mesh")):
        return ("selected_asset", "")
    if any(token in lowered for token in ("this actor", "selected actor", "current actor")) or any(
        token in text for token in ("这个Actor", "这个 actor", "该Actor", "当前Actor", "选中Actor")
    ):
        return ("selected_actor", "")
    if any(token in lowered for token in ("this blueprint", "current blueprint")) or any(
        token in text for token in ("这个蓝图", "当前蓝图", "该蓝图")
    ):
        return ("current_blueprint", "")
    if any(token in lowered for token in ("this widget", "current widget", "this ui", "current ui")) or any(
        token in text for token in ("这个控件", "当前控件", "这个UI", "这个 UI")
    ):
        return ("widget", "")
    if any(token in lowered for token in ("this material", "selected material")) or any(
        token in text for token in ("这个材质", "当前材质", "该材质")
    ):
        return ("selected_material_instance", "")
    return None


def _is_write_tool(tool_id: str | None) -> bool:
    spec = get_tool_spec(tool_id)
    if not spec:
        return False
    return spec.side_effect_level not in {"read_only", "plan_only"}


def build_intent_draft(
    *,
    request: UnifiedTaskRequest,
    routing: dict[str, Any],
    context_bundle: dict[str, Any],
) -> dict[str, Any]:
    """Project the current route into a structured draft.

    This is intentionally deterministic for now. A future LLM drafter can emit
    the same schema and let the verifier keep the safety boundary.
    """

    user_goal = _latest_user_message(request)
    intent = dict(routing.get("intent") or {})
    route = _route(context_bundle, routing)
    keyword_report = analyze_route_keywords(user_goal)
    selected_tool_id = route.get("selected_tool_id")
    candidate_tools = [
        str(item)
        for item in (route.get("candidate_tool_ids") or ([selected_tool_id] if selected_tool_id else []))
        if item
    ]
    turn_context = dict(context_bundle.get("agent_turn_context") or {})
    active_targets = dict(turn_context.get("active_targets") or {})
    selected_context_query = bool(route.get("selected_context_query") or keyword_report.get("active_context_reference"))

    target_kind, target_reference = ("none", "")
    if selected_context_query:
        target_kind, target_reference = _target_from_active_targets(active_targets)
        if target_kind == "none":
            target_kind, target_reference = _text_suggests_selected_target(user_goal) or (
                target_kind_from_keyword_report(keyword_report),
                "",
            )
    else:
        text_target = _text_suggests_selected_target(user_goal)
        if text_target:
            target_kind, target_reference = text_target
        else:
            tool_target = _target_from_tool(str(selected_tool_id or ""))
            if tool_target:
                target_kind, target_reference = tool_target

    requested_write = _is_write_tool(str(selected_tool_id or "")) or bool(keyword_report.get("hard_write_signal"))
    needs_project_context = bool(
        intent.get("route_type") == "project_qa"
        or route.get("project_inventory_query")
        or selected_context_query
        or bool(keyword_report.get("active_context_reference"))
        or target_kind.startswith("selected_")
        or target_kind.startswith("current_")
    )
    needs_live_editor_context = bool(
        str(selected_tool_id or "").startswith("mcp_")
        or selected_context_query
        or bool(keyword_report.get("active_context_reference"))
        or target_kind in {"selected_asset", "selected_actor", "current_blueprint", "selected_material_instance"}
    )
    needs_knowledge = bool(intent.get("requires_rag") or selected_tool_id == "retrieve_project_knowledge")
    draft = IntentDraft(
        user_goal=user_goal,
        intent_type=str(intent.get("intent_type") or "unknown"),
        target_kind=target_kind,
        target_reference=target_reference,
        needs_project_context=needs_project_context,
        needs_live_editor_context=needs_live_editor_context,
        needs_knowledge=needs_knowledge,
        requested_write=requested_write,
        candidate_tools=candidate_tools,
        confidence=float(route.get("planner_confidence") or 0.0),
        rationale=str(route.get("route_reason") or intent.get("reason") or ""),
    )
    dumped = draft.model_dump()
    dumped["route_keyword_verifier"] = keyword_report
    return dumped


__all__ = ["build_intent_draft"]
