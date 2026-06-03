from __future__ import annotations

from app.schemas.requests import EditorOperationResultRequest
from app.services.editor_operations.result_recording import (
    apply_operation_result_to_task_payloads,
    build_operation_result_payload,
)


def test_build_operation_result_payload_preserves_result_contract_fields() -> None:
    request = EditorOperationResultRequest(
        proposal_id="proposal_1",
        operation_type="rename_selected_asset",
        execution_state="completed",
        success=True,
        executed_by="ue_plugin",
        transaction_id="tx_001",
        undo_hint="Undo in editor",
        result={"dirty_packages": ["/Game/Blueprints/BP_Player"]},
        errors=[],
        metadata={"duration_ms": 42},
    )

    payload = build_operation_result_payload(
        request=request,
        preview={
            "operation_type": "rename_selected_asset",
            "tool_id": "editor_rename_selected_asset",
        },
        result_summary={"dirty_packages": ["/Game/Blueprints/BP_Player"]},
        received_at="2026-06-03T12:00:00+00:00",
    )

    assert payload["received_at"] == "2026-06-03T12:00:00+00:00"
    assert payload["proposal_id"] == "proposal_1"
    assert payload["operation_type"] == "rename_selected_asset"
    assert payload["tool_id"] == "editor_rename_selected_asset"
    assert payload["execution_state"] == "completed"
    assert payload["success"] is True
    assert payload["transaction_id"] == "tx_001"
    assert payload["result"]["dirty_packages"] == ["/Game/Blueprints/BP_Player"]
    assert payload["result_summary"]["dirty_packages"] == ["/Game/Blueprints/BP_Player"]
    assert payload["metadata"]["duration_ms"] == 42


def test_apply_operation_result_to_task_payloads_updates_existing_side_effect_and_action() -> None:
    operation_result = {
        "proposal_id": "proposal_1",
        "operation_type": "rename_selected_asset",
        "execution_state": "completed",
        "success": True,
        "transaction_id": "tx_001",
    }
    preview = {
        "operation_type": "rename_selected_asset",
        "tool_id": "editor_rename_selected_asset",
        "operation_result": operation_result,
    }

    updated = apply_operation_result_to_task_payloads(
        data={"editor_operation": {"operation_type": "rename_selected_asset"}},
        debug_view={
            "side_effects": [
                {
                    "proposal_id": "proposal_1",
                    "execution_state": "confirmed",
                    "written_by_backend": True,
                }
            ]
        },
        raw_response={"data": {}, "debug_view": {}, "action_proposals": []},
        action_proposals=[{"proposal_id": "proposal_1", "dry_run_preview": {"old": True}}],
        proposal_id="proposal_1",
        proposal_type="editor_operation",
        preview=preview,
        operation_result=operation_result,
        execution_state="completed",
    )

    assert updated["data"]["editor_operation"]["operation_result"] == operation_result
    assert updated["data"]["editor_operation_results"] == [operation_result]
    side_effect = updated["debug_view"]["side_effects"][0]
    assert side_effect["execution_state"] == "completed"
    assert side_effect["written_by_backend"] is False
    assert side_effect["operation_result"] == operation_result
    assert updated["action_proposals"][0]["dry_run_preview"] == preview
    assert updated["raw_response"]["data"] == updated["data"]
    assert updated["raw_response"]["debug_view"] == updated["debug_view"]
    assert updated["raw_response"]["action_proposals"] == updated["action_proposals"]


def test_apply_operation_result_to_task_payloads_appends_missing_side_effect() -> None:
    operation_result = {
        "proposal_id": "proposal_2",
        "operation_type": "compile_blueprint",
        "execution_state": "failed",
        "success": False,
    }
    preview = {
        "operation_type": "compile_blueprint",
        "tool_id": "editor_compile_blueprint",
    }

    updated = apply_operation_result_to_task_payloads(
        data={},
        debug_view={},
        raw_response={},
        action_proposals=[],
        proposal_id="proposal_2",
        proposal_type="editor_operation",
        preview=preview,
        operation_result=operation_result,
        execution_state="failed",
    )

    assert updated["data"]["editor_operation"]["proposal_created"] is True
    assert updated["data"]["editor_operation"]["operation_result"] == operation_result
    assert updated["raw_response"] == {}
    assert updated["debug_view"]["side_effects"] == [
        {
            "proposal_id": "proposal_2",
            "proposal_type": "editor_operation",
            "operation_type": "compile_blueprint",
            "tool_id": "editor_compile_blueprint",
            "side_effect_level": "confirmed_write",
            "execution_state": "failed",
            "written_by_backend": False,
            "operation_result": operation_result,
        }
    ]
