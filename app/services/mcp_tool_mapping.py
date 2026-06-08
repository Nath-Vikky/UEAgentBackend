from __future__ import annotations

from typing import Any

WRITE_SIDE_EFFECT_LEVELS = {"confirmed_write", "reversible_write", "destructive_write"}

MCP_TOOL_NAME_TO_LOCAL_TOOL_ID: dict[str, str] = {
    # UMG-MCP style Blueprint graph aliases.
    "add_step": "editor_blueprint_add_step",
    "blueprint_add_step": "editor_blueprint_add_step",
    "connect_pins": "editor_connect_blueprint_nodes",
    "connect_blueprint_nodes": "editor_connect_blueprint_nodes",
    "compile_blueprint": "editor_compile_blueprint",
    "create_blueprint": "editor_create_blueprint_asset",
    "add_blueprint_variable": "editor_add_blueprint_variable",
    "add_blueprint_component": "editor_add_blueprint_component",
    "create_blueprint_event": "editor_create_blueprint_event_stub",
    # UMG aliases.
    "create_widget": "editor_add_umg_widget",
    "add_widget": "editor_add_umg_widget",
    "set_widget_text": "editor_set_umg_widget_text",
    "set_widget_layout": "editor_set_umg_widget_layout",
    "set_widget_visibility": "editor_set_umg_widget_visibility",
    "set_widget_appearance": "editor_set_umg_widget_appearance",
    "set_widget_brush": "editor_set_umg_widget_brush",
    "set_slot_layout": "editor_set_umg_slot_layout_v2",
    "reparent_widget": "editor_reparent_umg_widget",
    "duplicate_widget": "editor_duplicate_umg_widget",
    "delete_widget": "editor_delete_umg_widget",
    # Material aliases.
    "set_material_parameter": "editor_set_material_instance_parameter",
    "set_material_instance_parameter": "editor_set_material_instance_parameter",
    "set_material_texture": "editor_set_material_instance_texture_parameter",
    "set_material_texture_parameter": "editor_set_material_instance_texture_parameter",
    "set_material_static_switch": "editor_set_material_instance_static_switch",
    # Level / Actor aliases.
    "place_actor": "editor_place_actor_in_level",
    "place_actor_in_level": "editor_place_actor_in_level",
    "select_actors": "editor_select_level_actors",
    "select_level_actors": "editor_select_level_actors",
    "set_actor_transform": "editor_set_actor_transform",
    "arrange_actors": "editor_arrange_actors_pattern",
    "set_actor_metadata": "editor_set_actor_metadata",
    "set_actor_folder": "editor_set_actor_folder",
    "set_actor_tags": "editor_set_actor_tags",
    "set_actor_visibility": "editor_set_actor_visibility",
    # Asset aliases.
    "rename_asset": "editor_rename_asset",
    "batch_rename_assets": "editor_batch_rename_assets",
    "move_assets": "editor_move_assets",
    "duplicate_asset": "editor_duplicate_asset",
    "fixup_redirectors": "editor_fixup_redirectors",
    "apply_static_mesh_settings": "editor_apply_static_mesh_settings",
}

TOOL_ID_ANNOTATION_KEYS = (
    "tool_id",
    "local_tool_id",
    "ue_agent_tool_id",
    "ueagent_tool_id",
    "mapped_tool_id",
)

SIDE_EFFECT_ANNOTATION_KEYS = (
    "side_effect_level",
    "sideEffectLevel",
    "side_effect",
    "sideEffect",
    "effect",
    "ue_agent_side_effect_level",
)


def normalize_mcp_tool_name(value: Any) -> str:
    return str(value or "").strip()


def normalize_mcp_tool_alias(value: Any) -> str:
    text = normalize_mcp_tool_name(value).lower()
    for old, new in (("-", "_"), (" ", "_"), (".", "_"), (":", "_")):
        text = text.replace(old, new)
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_")


def resolve_local_tool_id_from_name(
    name: Any,
    *,
    local_tool_ids: set[str] | None = None,
    local_tool_name_to_tool_id: dict[str, str] | None = None,
) -> str:
    clean_name = normalize_mcp_tool_name(name)
    if not clean_name:
        return ""
    if local_tool_ids and clean_name in local_tool_ids:
        return clean_name
    if local_tool_name_to_tool_id and clean_name in local_tool_name_to_tool_id:
        return local_tool_name_to_tool_id[clean_name]
    alias = normalize_mcp_tool_alias(clean_name)
    return MCP_TOOL_NAME_TO_LOCAL_TOOL_ID.get(alias, "")


def resolve_local_tool_id_from_live_tool(
    tool: dict[str, Any],
    *,
    local_tool_ids: set[str],
    local_tool_name_to_tool_id: dict[str, str],
) -> str:
    annotations = tool.get("annotations") if isinstance(tool.get("annotations"), dict) else {}
    for key in TOOL_ID_ANNOTATION_KEYS:
        mapped = resolve_local_tool_id_from_name(
            annotations.get(key),
            local_tool_ids=local_tool_ids,
            local_tool_name_to_tool_id=local_tool_name_to_tool_id,
        )
        if mapped:
            return mapped
    return resolve_local_tool_id_from_name(
        tool.get("name"),
        local_tool_ids=local_tool_ids,
        local_tool_name_to_tool_id=local_tool_name_to_tool_id,
    )


def detect_live_tool_side_effect_level(tool: dict[str, Any], *, fallback: str = "") -> str:
    annotations = tool.get("annotations") if isinstance(tool.get("annotations"), dict) else {}
    for key in SIDE_EFFECT_ANNOTATION_KEYS:
        value = _normalize_side_effect_level(annotations.get(key))
        if value:
            return value
    if annotations.get("readOnlyHint") is True or annotations.get("read_only") is True:
        return "read_only"
    if annotations.get("destructiveHint") is True:
        return "destructive_write"
    if annotations.get("requiresConfirmation") is True or annotations.get("requires_confirmation") is True:
        return "confirmed_write"
    return _normalize_side_effect_level(fallback) or "unknown"


def is_write_side_effect_level(value: Any) -> bool:
    return _normalize_side_effect_level(value) in WRITE_SIDE_EFFECT_LEVELS


def live_tool_trust_state(
    tool: dict[str, Any],
    *,
    mapped_local_tool_id: str = "",
    mapped_side_effect_level: str = "",
) -> str:
    side_effect_level = detect_live_tool_side_effect_level(tool, fallback=mapped_side_effect_level)
    if mapped_local_tool_id:
        if is_write_side_effect_level(mapped_side_effect_level or side_effect_level):
            return "mapped_confirmed_write_proposal_only"
        return "mapped_read_only_or_plan_tool"
    if is_write_side_effect_level(side_effect_level):
        return "external_unmapped_write_blocked"
    return "external_unmapped"


def _normalize_side_effect_level(value: Any) -> str:
    text = normalize_mcp_tool_alias(value)
    if text in {"readonly", "read_only", "read"}:
        return "read_only"
    if text in {"plan", "plan_only", "draft"}:
        return "plan_only"
    if text in {"write", "confirmed_write", "confirmed", "requires_confirmation"}:
        return "confirmed_write"
    if text in {"reversible_write", "reversible"}:
        return "reversible_write"
    if text in {"destructive_write", "destructive", "delete"}:
        return "destructive_write"
    return ""
