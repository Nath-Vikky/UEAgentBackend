from __future__ import annotations

from typing import Any

from app.schemas.requests import EditorOperationResultRequest
from app.services.editor_operations.blueprint_result_diagnostics import first_non_empty_text

UMG_RESULT_OPERATION_TYPES = {
    "add_umg_widget",
    "set_umg_widget_text",
    "set_umg_widget_layout",
    "set_umg_widget_visibility",
    "set_umg_widget_appearance",
    "set_umg_widget_brush",
    "set_umg_slot_layout_v2",
    "reparent_umg_widget",
    "duplicate_umg_widget",
    "delete_umg_widget",
}

UMG_EXECUTION_ERROR_FLAG_MAP = {
    "widget_blueprint_not_found": "umg_blueprint_unresolved",
    "widget_blueprint_load_failed": "umg_blueprint_unresolved",
    "target_widget_blueprint_missing": "umg_blueprint_unresolved",
    "widget_not_found": "umg_widget_unresolved",
    "target_widget_not_found": "umg_widget_unresolved",
    "source_widget_not_found": "umg_widget_unresolved",
    "parent_widget_not_found": "umg_parent_unresolved",
    "new_parent_widget_not_found": "umg_parent_unresolved",
    "widget_class_not_supported": "umg_widget_class_unsupported",
    "widget_class_not_supported_in_v1": "umg_widget_class_unsupported",
    "slot_type_not_supported": "umg_slot_unsupported",
    "slot_type_not_supported_in_v1": "umg_slot_unsupported",
    "brush_resource_not_found": "umg_brush_resource_unresolved",
    "brush_resource_type_not_supported": "umg_brush_resource_unresolved",
    "duplicate_widget_name": "umg_duplicate_name",
    "new_widget_name_exists": "umg_duplicate_name",
    "root_widget_delete_blocked": "umg_unsafe_widget_operation",
    "panel_widget_delete_blocked": "umg_unsafe_widget_operation",
    "widget_parent_must_differ_from_target": "umg_unsafe_widget_operation",
}


def _append_unique(values: list[str], item: str) -> None:
    if item and item not in values:
        values.append(item)


def _error_code_from_item(item: Any) -> str:
    if isinstance(item, dict):
        return first_non_empty_text(
            item.get("code"),
            item.get("reason"),
            item.get("error_code"),
            item.get("type"),
            item.get("message"),
        )
    return first_non_empty_text(item)


def umg_execution_error_codes(*, request: EditorOperationResultRequest, result: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    for source in (
        request.errors,
        result.get("errors"),
        result.get("failed_fields"),
    ):
        if isinstance(source, list):
            for item in source:
                _append_unique(codes, _error_code_from_item(item).strip().lower())
        elif isinstance(source, dict):
            for item in source.values():
                _append_unique(codes, _error_code_from_item(item).strip().lower())
    for key in ("error_code", "reason", "failure_reason"):
        _append_unique(codes, first_non_empty_text(result.get(key)).strip().lower())
    return [item for item in codes if item]


def umg_result_diagnostics(
    *,
    request: EditorOperationResultRequest,
    preview: dict[str, Any],
    result: dict[str, Any],
    dirty_packages: list[str],
) -> dict[str, Any]:
    operation_type = str(preview.get("operation_type") or request.operation_type or "")
    if operation_type not in UMG_RESULT_OPERATION_TYPES:
        return {}

    payload = dict(preview.get("operation_payload") or {})
    execution_error_codes = umg_execution_error_codes(request=request, result=result)
    diagnostic_flags: list[str] = []
    for code in execution_error_codes:
        mapped_flag = UMG_EXECUTION_ERROR_FLAG_MAP.get(code)
        if mapped_flag:
            _append_unique(diagnostic_flags, mapped_flag)

    repair_advice = umg_repair_advice(
        operation_type=operation_type,
        diagnostic_flags=diagnostic_flags,
        request=request,
        payload=payload,
        result=result,
        execution_error_codes=execution_error_codes,
    )
    return {
        "schema_version": "umg_operation_diagnostics_v1",
        "category": "umg",
        "operation_type": operation_type,
        "widget_blueprint_path": first_non_empty_text(
            result.get("widget_blueprint_path"),
            payload.get("widget_blueprint_path"),
        ),
        "widget_name": first_non_empty_text(
            result.get("widget_name"),
            result.get("source_widget_name"),
            payload.get("widget_name"),
        ),
        "new_widget_name": first_non_empty_text(result.get("new_widget_name"), payload.get("new_widget_name")),
        "parent_widget_name": first_non_empty_text(
            result.get("parent_widget_name"),
            result.get("old_parent_name"),
            payload.get("parent_widget_name"),
        ),
        "dirty_package_count": len(dirty_packages),
        "execution_error_codes": execution_error_codes,
        "diagnostic_flags": diagnostic_flags,
        "needs_user_attention": (not request.success) or bool(diagnostic_flags),
        "repair_advice": repair_advice,
    }


def umg_repair_advice(
    *,
    operation_type: str,
    diagnostic_flags: list[str],
    request: EditorOperationResultRequest,
    payload: dict[str, Any],
    result: dict[str, Any],
    execution_error_codes: list[str] | None = None,
) -> dict[str, Any]:
    flag_set = set(diagnostic_flags)
    execution_error_codes = list(execution_error_codes or [])
    widget_blueprint_path = first_non_empty_text(result.get("widget_blueprint_path"), payload.get("widget_blueprint_path"))
    widget_name = first_non_empty_text(result.get("widget_name"), payload.get("widget_name"))
    actions: list[dict[str, Any]] = []

    if not request.success:
        actions.append(
            {
                "action_id": "inspect_umg_execution_errors",
                "severity": "error",
                "title": "Inspect UMG execution errors",
                "details": "UEAgentTool reported that the UMG editor operation did not complete successfully.",
                "next_step": "Check the target Widget Blueprint, selected widget name, and Unreal Output Log before retrying.",
                "context": {"execution_error_codes": execution_error_codes},
            }
        )
    if "umg_blueprint_unresolved" in flag_set:
        actions.append(
            {
                "action_id": "verify_umg_blueprint_target",
                "severity": "error",
                "title": "Verify Widget Blueprint target",
                "details": "UEAgentTool could not resolve or load the target Widget Blueprint.",
                "next_step": "Select the Widget Blueprint or retry with an explicit /Game/... WBP path.",
                "context": {"widget_blueprint_path": widget_blueprint_path},
            }
        )
    if "umg_widget_unresolved" in flag_set:
        actions.append(
            {
                "action_id": "verify_umg_widget_name",
                "severity": "warning",
                "title": "Verify UMG widget name",
                "details": "UEAgentTool could not find the target widget in the Widget Blueprint tree.",
                "next_step": "Open the Widget Blueprint, confirm the widget name, or refresh the widget tree snapshot.",
                "context": {"widget_blueprint_path": widget_blueprint_path, "widget_name": widget_name},
            }
        )
    if "umg_parent_unresolved" in flag_set:
        actions.append(
            {
                "action_id": "verify_umg_parent_widget",
                "severity": "warning",
                "title": "Verify UMG parent widget",
                "details": "UEAgentTool could not find the requested parent panel widget.",
                "next_step": "Use an existing panel widget as the parent, such as a CanvasPanel or HorizontalBox.",
                "context": {"widget_blueprint_path": widget_blueprint_path},
            }
        )
    if "umg_widget_class_unsupported" in flag_set:
        actions.append(
            {
                "action_id": "choose_supported_umg_widget_class",
                "severity": "warning",
                "title": "Choose a supported UMG widget class",
                "details": "The requested widget class is outside the backend/UEAgentTool safe allowlist.",
                "next_step": "Use TextBlock, Button, Image, Border, CanvasPanel, HorizontalBox, or VerticalBox.",
            }
        )
    if "umg_slot_unsupported" in flag_set:
        actions.append(
            {
                "action_id": "choose_supported_umg_slot",
                "severity": "warning",
                "title": "Choose a supported UMG slot type",
                "details": "The requested slot operation is outside the safe slot-layout allowlist.",
                "next_step": "Use CanvasPanelSlot, HorizontalBoxSlot, VerticalBoxSlot, or OverlaySlot.",
            }
        )
    if "umg_brush_resource_unresolved" in flag_set:
        actions.append(
            {
                "action_id": "verify_umg_brush_resource",
                "severity": "warning",
                "title": "Verify UMG brush resource",
                "details": "UEAgentTool could not resolve the requested texture or material brush resource.",
                "next_step": "Use an explicit /Game/... Texture2D, Material, or Material Instance path.",
            }
        )
    if "umg_duplicate_name" in flag_set:
        actions.append(
            {
                "action_id": "choose_unique_umg_widget_name",
                "severity": "warning",
                "title": "Choose a unique widget name",
                "details": "The requested target widget name already exists.",
                "next_step": "Retry with a new widget name that is unique inside the Widget Blueprint.",
            }
        )
    if "umg_unsafe_widget_operation" in flag_set:
        actions.append(
            {
                "action_id": "avoid_unsafe_umg_tree_operation",
                "severity": "error",
                "title": "Avoid unsafe UMG tree operation",
                "details": "UEAgentTool blocked an operation that could damage the Widget Blueprint tree.",
                "next_step": "Use a non-root, non-panel child widget or split the change into smaller confirmed operations.",
            }
        )

    if not actions:
        return {
            "schema_version": "umg_repair_advice_v1",
            "status": "not_needed",
            "severity": "info",
            "can_auto_retry": False,
            "safe_next_step": "none",
            "actions": [],
        }

    severity = "error" if any(item["severity"] == "error" for item in actions) else "warning"
    return {
        "schema_version": "umg_repair_advice_v1",
        "status": "suggested",
        "severity": severity,
        "can_auto_retry": False,
        "safe_next_step": "manual_review",
        "operation_type": operation_type,
        "actions": actions,
    }


__all__ = [
    "UMG_EXECUTION_ERROR_FLAG_MAP",
    "UMG_RESULT_OPERATION_TYPES",
    "umg_execution_error_codes",
    "umg_repair_advice",
    "umg_result_diagnostics",
]
