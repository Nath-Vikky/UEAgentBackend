from __future__ import annotations

from typing import Any

from app.schemas.requests import UnifiedTaskRequest


def _payload_list(payload: dict[str, Any], *keys: str) -> list[Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _state_list(editor_state: dict[str, Any], *keys: str) -> list[Any]:
    for key in keys:
        value = editor_state.get(key)
        if isinstance(value, list):
            return value
    return []


def _payload_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _editor_state_text(editor_state: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = editor_state.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _looks_like_blueprint_path(value: str) -> bool:
    text = str(value or "").strip()
    leaf = text.rsplit("/", 1)[-1].split(".", 1)[0]
    return leaf.startswith(("BP_", "WBP_", "ABP_")) or "blueprint" in text.lower()


def _looks_like_material_instance_path(value: str) -> bool:
    text = str(value or "").strip()
    leaf = text.rsplit("/", 1)[-1].split(".", 1)[0]
    return leaf.startswith("MI_") or "material" in text.lower()


def _reference_from_item(value: Any, *keys: str) -> str:
    if isinstance(value, dict):
        for key in keys:
            text = str(value.get(key) or "").strip()
            if text:
                return text
        return ""
    return str(value or "").strip()


def _unique_texts(values: list[Any], *keys: str) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _reference_from_item(value, *keys)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(text)
    return items


def _current_blueprint_path(payload: dict[str, Any], selected_assets: list[str], editor_state: dict[str, Any]) -> str:
    explicit_path = _payload_text(
        payload,
        "blueprint_path",
        "current_blueprint_path",
        "widget_blueprint_path",
    ) or _editor_state_text(
        editor_state,
        "blueprint_path",
        "current_blueprint_path",
        "active_blueprint_path",
        "widget_blueprint_path",
    )
    if explicit_path:
        return explicit_path
    for asset_path in selected_assets:
        if _looks_like_blueprint_path(asset_path):
            return asset_path
    return ""


def _current_material_instance_path(
    payload: dict[str, Any],
    selected_assets: list[str],
    editor_state: dict[str, Any],
) -> str:
    explicit_path = _payload_text(
        payload,
        "material_instance_path",
        "current_material_instance_path",
    ) or _editor_state_text(
        editor_state,
        "material_instance_path",
        "current_material_instance_path",
        "active_material_instance_path",
    )
    if explicit_path:
        return explicit_path
    for asset_path in selected_assets:
        if _looks_like_material_instance_path(asset_path):
            return asset_path
    return ""


def build_active_context(
    *,
    request: UnifiedTaskRequest,
    routing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the compact, explainable context object used by tools and Debug View."""

    payload = dict(request.payload or {})
    route = dict((routing or {}).get("route") or {})
    context = request.context
    editor_state = dict(context.editor_state or {})
    selected_files = _payload_list(payload, "file_paths", "selected_files")
    current_file = _payload_text(payload, "current_file", "file_path") or context.current_file
    log_file_path = _payload_text(payload, "log_file_path", "attachment_path")
    log_text = _payload_text(payload, "selected_log_text", "log_excerpt", "log_text")
    inventory_snapshot_id = _payload_text(
        payload,
        "inventory_snapshot_id",
        "snapshot_id",
    )
    selected_assets = list(context.selected_assets or [])
    current_blueprint_path = _current_blueprint_path(payload, selected_assets, editor_state)
    selected_actor_references = _unique_texts(
        [
            *_payload_list(payload, "selected_actors", "actor_references"),
            *_state_list(editor_state, "selected_actors"),
        ],
        "actor_reference",
        "actor_label",
        "actor_name",
        "name",
        "label",
    )
    current_actor_reference = _payload_text(
        payload,
        "actor_reference",
        "current_actor_reference",
        "current_actor_label",
    ) or _editor_state_text(
        editor_state,
        "actor_reference",
        "current_actor_reference",
        "current_actor_label",
    )
    selected_material_instance_paths = _unique_texts(
        [
            *_payload_list(payload, "selected_material_instances", "material_instance_paths"),
            *_state_list(editor_state, "selected_material_instances"),
            *[asset for asset in selected_assets if _looks_like_material_instance_path(asset)],
        ],
        "material_instance_path",
        "asset_path",
        "path",
        "name",
    )
    current_material_instance_path = _current_material_instance_path(payload, selected_assets, editor_state)
    current_graph_name = _payload_text(
        payload,
        "graph_name",
        "current_graph_name",
        "current_blueprint_graph",
    ) or _editor_state_text(
        editor_state,
        "graph_name",
        "current_graph_name",
        "current_blueprint_graph",
        "active_graph_name",
    )
    current_graph_node = _payload_text(
        payload,
        "selected_node_id",
        "current_node_id",
        "current_blueprint_node_id",
    ) or _editor_state_text(
        editor_state,
        "selected_node_id",
        "current_node_id",
        "current_blueprint_node_id",
    )
    selected_panel = request.ui_state.selected_panel or context.selected_panel

    return {
        "version": "active_context_v1",
        "project": {
            "project_name": context.project_name,
            "project_root": context.project_root,
            "active_panel": context.active_panel,
            "selected_panel": selected_panel,
            "current_module": context.current_module,
            "ue_version": editor_state.get("ue_version"),
            "plugin_version": editor_state.get("plugin_version"),
        },
        "asset": {
            "selected_assets": selected_assets,
            "payload_asset_count": len(_payload_list(payload, "assets", "selected_assets", "asset_metadata")),
            "asset_type_filter": payload.get("asset_type"),
            "inventory_snapshot_id": inventory_snapshot_id or None,
        },
        "level_actor": {
            "selected_actor_references": selected_actor_references,
            "current_actor_reference": current_actor_reference or (selected_actor_references[0] if selected_actor_references else None),
            "selected_actor_count": len(selected_actor_references),
        },
        "material": {
            "selected_material_instance_paths": selected_material_instance_paths,
            "current_material_instance_path": current_material_instance_path
            or (selected_material_instance_paths[0] if selected_material_instance_paths else None),
            "selected_material_instance_count": len(selected_material_instance_paths),
        },
        "blueprint": {
            "current_blueprint_path": current_blueprint_path or None,
            "current_graph_name": current_graph_name or None,
            "entry_event": _payload_text(payload, "entry_event", "event_name") or None,
            "selected_node_id": current_graph_node or None,
            "selected_node_name": _payload_text(payload, "selected_node_name", "current_node_name")
            or _editor_state_text(editor_state, "selected_node_name", "current_node_name")
            or None,
            "has_blueprint_focus": bool(current_blueprint_path or current_graph_name or current_graph_node),
            "source": "payload_or_editor_state_or_selected_assets",
        },
        "code": {
            "current_file": current_file,
            "selected_files": selected_files,
            "selected_file_count": len(selected_files),
            "recent_open_files": context.recent_open_files,
            "has_inline_code": bool(_payload_text(payload, "code", "code_text", "diff_text")),
            "module_name": payload.get("module_name") or context.current_module,
            "class_name": payload.get("class_name"),
        },
        "log": {
            "source": payload.get("source") or payload.get("log_source"),
            "log_file_path": log_file_path or None,
            "has_log_text": bool(log_text),
            "log_text_chars": len(log_text),
            "attachment_paths": _payload_list(payload, "attachment_paths"),
        },
        "kb": {
            "domain_hints": list(context.kb_domains_hint or payload.get("domain_filters") or []),
            "selected_tool_id": route.get("selected_tool_id"),
            "requires_rag": bool((routing or {}).get("intent", {}).get("requires_rag")),
            "retrieval_mode_hint": payload.get("retrieval_mode"),
        },
        "editor_focus": {
            "active_view": request.ui_state.active_view,
            "selected_panel": selected_panel,
            "active_panel": context.active_panel,
            "current_blueprint_path": current_blueprint_path or None,
            "current_graph_name": current_graph_name or None,
        },
        "mcp": {
            "status": "disabled",
            "enabled": False,
            "available_tools": [],
            "note": "MCP is planned as an optional tool transport; HTTP remains the main UE frontend/backend protocol.",
        },
    }
