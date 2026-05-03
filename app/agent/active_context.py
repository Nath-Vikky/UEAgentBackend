from __future__ import annotations

from typing import Any

from app.schemas.requests import UnifiedTaskRequest


def _payload_list(payload: dict[str, Any], *keys: str) -> list[Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _payload_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
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
    selected_files = _payload_list(payload, "file_paths", "selected_files")
    current_file = _payload_text(payload, "current_file", "file_path") or context.current_file
    log_file_path = _payload_text(payload, "log_file_path", "attachment_path")
    log_text = _payload_text(payload, "selected_log_text", "log_excerpt", "log_text")
    inventory_snapshot_id = _payload_text(
        payload,
        "inventory_snapshot_id",
        "snapshot_id",
    )

    return {
        "version": "active_context_v1",
        "project": {
            "project_name": context.project_name,
            "project_root": context.project_root,
            "active_panel": context.active_panel,
            "selected_panel": request.ui_state.selected_panel or context.selected_panel,
            "current_module": context.current_module,
            "ue_version": (context.editor_state or {}).get("ue_version"),
            "plugin_version": (context.editor_state or {}).get("plugin_version"),
        },
        "asset": {
            "selected_assets": context.selected_assets,
            "payload_asset_count": len(_payload_list(payload, "assets", "selected_assets", "asset_metadata")),
            "asset_type_filter": payload.get("asset_type"),
            "inventory_snapshot_id": inventory_snapshot_id or None,
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
        "mcp": {
            "status": "disabled",
            "enabled": False,
            "available_tools": [],
            "note": "MCP is planned as an optional tool transport; HTTP remains the main UE frontend/backend protocol.",
        },
    }

