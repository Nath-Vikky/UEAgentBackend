from __future__ import annotations

from app.schemas.requests import EditorOperationResultRequest
from app.services.editor_operations.blueprint_result_diagnostics import (
    blueprint_graph_repair_advice,
    blueprint_graph_result_diagnostics,
    collection_count,
    first_non_empty_text,
)


def test_blueprint_result_helper_counts_and_text_selection() -> None:
    assert collection_count(None) == 0
    assert collection_count({}) == 0
    assert collection_count({"node_id": "A"}) == 1
    assert collection_count(["A", "B"]) == 2
    assert collection_count("Node") == 1
    assert first_non_empty_text("", None, " EventGraph ") == "EventGraph"


def test_blueprint_result_diagnostics_returns_empty_for_non_graph_operation() -> None:
    diagnostics = blueprint_graph_result_diagnostics(
        request=EditorOperationResultRequest(
            proposal_id="proposal_1",
            operation_type="set_umg_widget_text",
            success=True,
        ),
        preview={"operation_type": "set_umg_widget_text"},
        result={},
        dirty_packages=[],
    )

    assert diagnostics == {}


def test_blueprint_result_diagnostics_clean_template_result() -> None:
    diagnostics = blueprint_graph_result_diagnostics(
        request=EditorOperationResultRequest(
            proposal_id="proposal_2",
            operation_type="add_blueprint_node_template",
            success=True,
        ),
        preview={
            "operation_type": "add_blueprint_node_template",
            "operation_payload": {
                "blueprint_path": "/Game/Blueprints/BP_Player",
                "graph_name": "EventGraph",
                "template_id": "print_string",
                "compile_after_edit": True,
            },
            "expected_result_contract": {"operation_result_fields": ["dirty_packages"]},
        },
        result={
            "created_nodes": [{"node_id": "PrintString"}],
            "linked_pins": [{"source": "BeginPlay.Then", "target": "PrintString.Execute"}],
            "compile_status": "succeeded",
        },
        dirty_packages=["/Game/Blueprints/BP_Player"],
    )

    assert diagnostics["diagnostic_flags"] == []
    assert diagnostics["repair_advice"]["status"] == "not_needed"
    assert diagnostics["needs_user_attention"] is False
    assert diagnostics["created_node_count"] == 1
    assert diagnostics["linked_pin_count"] == 1


def test_blueprint_result_diagnostics_flags_missing_links_and_dirty_packages() -> None:
    diagnostics = blueprint_graph_result_diagnostics(
        request=EditorOperationResultRequest(
            proposal_id="proposal_3",
            operation_type="add_blueprint_node_template",
            success=True,
        ),
        preview={
            "operation_type": "add_blueprint_node_template",
            "operation_payload": {
                "blueprint_path": "/Game/Blueprints/BP_Player",
                "graph_name": "EventGraph",
                "template_id": "print_string",
            },
            "expected_result_contract": {"operation_result_fields": ["dirty_packages"]},
        },
        result={"created_nodes": [{"node_id": "PrintString"}]},
        dirty_packages=[],
    )

    assert diagnostics["diagnostic_flags"] == ["expected_linked_pins_missing", "dirty_packages_missing"]
    assert diagnostics["needs_user_attention"] is True
    action_ids = [item["action_id"] for item in diagnostics["repair_advice"]["actions"]]
    assert "connect_expected_exec_pins" in action_ids
    assert "report_dirty_packages" in action_ids


def test_blueprint_repair_advice_marks_failed_request_as_error() -> None:
    advice = blueprint_graph_repair_advice(
        operation_type="compile_blueprint",
        diagnostic_flags=["compile_failed"],
        request=EditorOperationResultRequest(
            proposal_id="proposal_4",
            operation_type="compile_blueprint",
            success=False,
        ),
        payload={"blueprint_path": "/Game/Blueprints/BP_Player"},
        result={"compile_status": "failed"},
        template_id="",
        compile_status="failed",
    )

    assert advice["status"] == "suggested"
    assert advice["severity"] == "error"
    action_ids = [item["action_id"] for item in advice["actions"]]
    assert "inspect_ue_execution_errors" in action_ids
    assert "open_blueprint_compile_results" in action_ids
