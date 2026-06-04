from __future__ import annotations

from app.schemas.requests import EditorOperationResultRequest
from app.services.editor_operations.umg_result_diagnostics import (
    umg_execution_error_codes,
    umg_result_diagnostics,
)


def test_umg_execution_error_codes_collects_request_and_result_errors() -> None:
    codes = umg_execution_error_codes(
        request=EditorOperationResultRequest(
            proposal_id="proposal_umg_codes",
            operation_type="set_umg_widget_text",
            success=False,
            errors=[{"code": "widget_not_found"}],
        ),
        result={
            "error_code": "slot_type_not_supported",
            "failed_fields": [{"field": "parent_widget_name", "reason": "parent_widget_not_found"}],
        },
    )

    assert codes == ["widget_not_found", "parent_widget_not_found", "slot_type_not_supported"]


def test_umg_result_diagnostics_maps_errors_to_repair_advice() -> None:
    diagnostics = umg_result_diagnostics(
        request=EditorOperationResultRequest(
            proposal_id="proposal_umg_error",
            operation_type="set_umg_widget_text",
            success=False,
            errors=[{"code": "widget_not_found"}],
        ),
        preview={
            "operation_type": "set_umg_widget_text",
            "operation_payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "TitleText",
            },
        },
        result={"error_code": "widget_blueprint_load_failed"},
        dirty_packages=[],
    )

    assert diagnostics["schema_version"] == "umg_operation_diagnostics_v1"
    assert diagnostics["category"] == "umg"
    assert diagnostics["execution_error_codes"] == ["widget_not_found", "widget_blueprint_load_failed"]
    assert diagnostics["diagnostic_flags"] == ["umg_widget_unresolved", "umg_blueprint_unresolved"]
    action_ids = [item["action_id"] for item in diagnostics["repair_advice"]["actions"]]
    assert "inspect_umg_execution_errors" in action_ids
    assert "verify_umg_widget_name" in action_ids
    assert "verify_umg_blueprint_target" in action_ids
    assert diagnostics["needs_user_attention"] is True


def test_umg_result_diagnostics_returns_empty_for_non_umg_operation() -> None:
    diagnostics = umg_result_diagnostics(
        request=EditorOperationResultRequest(
            proposal_id="proposal_non_umg",
            operation_type="set_actor_transform",
            success=True,
        ),
        preview={"operation_type": "set_actor_transform"},
        result={},
        dirty_packages=[],
    )

    assert diagnostics == {}
