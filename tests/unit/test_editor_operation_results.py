from __future__ import annotations

from typing import Any

from app.schemas.requests import EditorOperationResultRequest
from app.services.editor_operations.results import as_string_list, normalize_result_summary


def test_as_string_list_accepts_scalar_list_and_empty_values() -> None:
    assert as_string_list(None) == []
    assert as_string_list(" /Game/Maps/L_Test ") == ["/Game/Maps/L_Test"]
    assert as_string_list(["", "A", None, "B"]) == ["A", "B"]


def test_normalize_result_summary_counts_fields_and_uses_diagnostics_builder() -> None:
    captured: dict[str, Any] = {}

    def diagnostics_builder(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "needs_user_attention": True,
            "repair_advice": {"status": "suggested"},
        }

    request = EditorOperationResultRequest(
        proposal_id="proposal_test",
        operation_type="set_umg_widget_text",
        execution_state="completed",
        success=True,
        result={
            "dirty_package": "/Game/UI/WBP_MainHUD",
            "applied_fields": {"text": "Ready"},
            "failed_fields": ["font_size"],
            "save_policy": "manual",
            "dirty": True,
        },
        errors=[{"code": "font_size_unsupported"}],
    )
    preview = {"preview_summary": {"target_count": 1}}

    summary = normalize_result_summary(
        request=request,
        preview=preview,
        diagnostics_builder=diagnostics_builder,
    )

    assert captured["request"] is request
    assert captured["preview"] == preview
    assert captured["dirty_packages"] == ["/Game/UI/WBP_MainHUD"]
    assert summary["schema_version"] == "editor_operation_result_summary_v1"
    assert summary["target_count"] == 1
    assert summary["applied_field_count"] == 1
    assert summary["failed_field_count"] == 1
    assert summary["dirty_packages"] == ["/Game/UI/WBP_MainHUD"]
    assert summary["error_codes"] == ["font_size_unsupported"]
    assert summary["repair_advice"]["status"] == "suggested"
    assert summary["needs_user_attention"] is True


def test_normalize_result_summary_marks_failed_request_attention_without_diagnostics() -> None:
    request = EditorOperationResultRequest(
        proposal_id="proposal_failed",
        operation_type="compile_blueprint",
        execution_state="failed",
        success=False,
        result={"package_name": "/Game/Blueprints/BP_Player"},
        errors=[],
    )

    summary = normalize_result_summary(
        request=request,
        preview={},
        diagnostics_builder=lambda **_: {},
    )

    assert summary["dirty_packages"] == ["/Game/Blueprints/BP_Player"]
    assert summary["error_count"] == 0
    assert summary["needs_user_attention"] is True
