from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.schemas.requests import EditorOperationResultRequest


ResultDiagnosticsBuilder = Callable[..., dict[str, Any]]


def as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item or "").strip()]
    text = str(value or "").strip()
    return [text] if text else []


def normalize_result_summary(
    *,
    request: EditorOperationResultRequest,
    preview: dict[str, Any],
    diagnostics_builder: ResultDiagnosticsBuilder,
) -> dict[str, Any]:
    result = dict(request.result or {})
    errors = list(request.errors or [])
    applied_fields = result.get("applied_fields") or {}
    failed_fields = result.get("failed_fields") or []
    dirty_packages = (
        as_string_list(result.get("dirty_packages"))
        or as_string_list(result.get("dirty_package"))
        or as_string_list(result.get("package_name"))
    )
    error_codes = [
        str(item.get("code") or item.get("reason") or item.get("message") or "unknown_error")
        for item in errors
        if isinstance(item, dict)
    ]
    error_codes.extend(str(item) for item in errors if not isinstance(item, dict))
    target_count = int(dict(preview.get("preview_summary") or {}).get("target_count") or 0)
    if isinstance(applied_fields, dict):
        applied_field_count = len(applied_fields)
    elif isinstance(applied_fields, list):
        applied_field_count = len(applied_fields)
    else:
        applied_field_count = 0
    if isinstance(failed_fields, dict):
        failed_field_count = len(failed_fields)
    elif isinstance(failed_fields, list):
        failed_field_count = len(failed_fields)
    else:
        failed_field_count = 0
    operation_diagnostics = diagnostics_builder(
        request=request,
        preview=preview,
        result=result,
        dirty_packages=dirty_packages,
    )
    return {
        "schema_version": "editor_operation_result_summary_v1",
        "execution_state": request.execution_state,
        "success": request.success,
        "target_count": target_count,
        "applied_field_count": applied_field_count,
        "failed_field_count": failed_field_count,
        "dirty_packages": dirty_packages,
        "save_policy": result.get("save_policy"),
        "dirty": bool(result.get("dirty") or result.get("level_dirty")),
        "applied_fields": applied_fields,
        "failed_fields": failed_fields,
        "error_count": len(error_codes),
        "error_codes": error_codes,
        "operation_diagnostics": operation_diagnostics,
        "repair_advice": dict(operation_diagnostics.get("repair_advice") or {}),
        "needs_user_attention": (
            (not request.success)
            or bool(error_codes)
            or failed_field_count > 0
            or bool(operation_diagnostics.get("needs_user_attention"))
        ),
    }


__all__ = [
    "as_string_list",
    "normalize_result_summary",
]
