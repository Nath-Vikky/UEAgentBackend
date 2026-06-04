from __future__ import annotations

from app.services.editor_operations.result_user_view import (
    blueprint_graph_result_detail_block,
    generic_editor_operation_detail_block,
    operation_result_user_view,
    summarize_graph_node,
    summarize_graph_pin,
    summarize_limited_items,
    umg_result_detail_block,
)


def test_graph_summary_helpers_keep_stable_ids_and_limit_output() -> None:
    assert (
        summarize_graph_node(
            {
                "role": "entry",
                "node_name": "EventBeginPlay",
                "node_id": "ENTRY-GUID",
                "node_class": "K2Node_Event",
            }
        )
        == "entry: EventBeginPlay [K2Node_Event] (ENTRY-GUID)"
    )
    assert (
        summarize_graph_pin(
            {
                "source": {"node_name": "EventBeginPlay", "pin_name": "Then"},
                "target": {"node_name": "PrintString", "pin_name": "Exec"},
            }
        )
        == "EventBeginPlay.Then -> PrintString.Exec"
    )
    assert summarize_graph_pin({"summary": "A.Then -> B.Exec"}) == "A.Then -> B.Exec"

    limited = summarize_limited_items(["A", "B", "C"], lambda item: str(item), limit=2)
    assert limited == ["A", "B", "+1 more"]


def test_blueprint_graph_result_detail_block_uses_diagnostics_and_errors() -> None:
    block = blueprint_graph_result_detail_block(
        operation_result={
            "result": {
                "blueprint_path": "/Game/Blueprints/BP_Player",
                "graph_name": "EventGraph",
                "template_id": "print_string",
                "entry_node_id": "ENTRY-GUID",
                "entry_node_name": "EventBeginPlay",
                "created_node_id": "PRINT-GUID",
                "created_node_name": "K2Node_CallFunction_0",
                "created_nodes": [
                    {
                        "role": "print_string",
                        "node_name": "K2Node_CallFunction_0",
                        "node_id": "PRINT-GUID",
                        "node_class": "K2Node_CallFunction",
                    }
                ],
                "linked_pins": [
                    {
                        "source": {"node_name": "EventBeginPlay", "pin_name": "Then"},
                        "target": {"node_name": "K2Node_CallFunction_0", "pin_name": "execute"},
                    }
                ],
                "compile_status": "succeeded",
                "dirty_packages": ["/Game/Blueprints/BP_Player"],
            },
            "result_summary": {
                "operation_diagnostics": {
                    "category": "blueprint_graph",
                    "compile_status": "succeeded",
                },
                "failed_fields": [{"field": "linked_pins", "reason": "missing_expected_pin"}],
            },
            "errors": [{"code": "ue_warning", "message": "Pin was adjusted by UE"}],
        }
    )

    assert block is not None
    assert block["block_type"] == "editor_operation_graph_details"
    assert block["data"]["schema_version"] == "blueprint_graph_result_details_v1"
    items = block["data"]["items"]
    assert "Blueprint: /Game/Blueprints/BP_Player" in items
    assert "Entry node: EventBeginPlay (ENTRY-GUID)" in items
    assert "Created: print_string: K2Node_CallFunction_0 [K2Node_CallFunction] (PRINT-GUID)" in items
    assert "Linked pin: EventBeginPlay.Then -> K2Node_CallFunction_0.execute" in items
    assert "Failed field: linked_pins: missing_expected_pin" in items
    assert "UE error: ue_warning: Pin was adjusted by UE" in items


def test_umg_result_detail_block_uses_diagnostics_and_errors() -> None:
    block = umg_result_detail_block(
        operation_result={
            "operation_type": "set_umg_widget_text",
            "result": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "TitleText",
                "error_code": "widget_not_found",
            },
            "result_summary": {
                "operation_diagnostics": {
                    "category": "umg",
                    "operation_type": "set_umg_widget_text",
                    "execution_error_codes": ["widget_not_found"],
                },
                "dirty_packages": ["/Game/UI/WBP_MainHUD"],
                "failed_fields": [{"field": "widget_name", "reason": "widget_not_found"}],
            },
            "errors": [{"code": "widget_not_found", "message": "TitleText was not found"}],
        }
    )

    assert block is not None
    assert block["block_type"] == "editor_operation_umg_details"
    assert block["data"]["schema_version"] == "umg_result_details_v1"
    items = block["data"]["items"]
    assert "Widget Blueprint: /Game/UI/WBP_MainHUD" in items
    assert "Widget: TitleText" in items
    assert "Execution error: widget_not_found" in items
    assert "Dirty packages: /Game/UI/WBP_MainHUD" in items
    assert "Failed field: widget_name: widget_not_found" in items
    assert "UE error: widget_not_found: TitleText was not found" in items


def test_generic_editor_operation_detail_block_uses_contract_fields() -> None:
    block = generic_editor_operation_detail_block(
        operation_result={
            "operation_type": "set_material_instance_parameter",
            "result": {
                "material_instance_path": "/Game/Materials/MI_Player",
                "parameter_name": "Roughness",
                "dirty_packages": ["/Game/Materials/MI_Player"],
                "applied_fields": {"scalar_parameter": "Roughness"},
            },
            "result_summary": {
                "operation_diagnostics": {},
                "error_codes": ["material_parameter_not_found"],
            },
            "errors": [],
        }
    )

    assert block is not None
    assert block["block_type"] == "editor_operation_target_details"
    assert block["data"]["schema_version"] == "editor_operation_target_details_v1"
    items = block["data"]["items"]
    assert "Operation: set_material_instance_parameter" in items
    assert "material_instance_path: /Game/Materials/MI_Player" in items
    assert "parameter_name: Roughness" in items
    assert "Dirty packages: /Game/Materials/MI_Player" in items
    assert "Execution error: material_parameter_not_found" in items
    assert "Applied: scalar_parameter: Roughness" in items


def test_operation_result_user_view_adds_follow_up_and_attention_blocks() -> None:
    user_view = operation_result_user_view(
        operation_result={
            "operation_type": "add_blueprint_node_template",
            "result_summary": {
                "needs_user_attention": True,
                "operation_diagnostics": {"category": "blueprint_graph"},
            },
            "result": {"blueprint_path": "/Game/Blueprints/BP_Player"},
        },
        follow_up={"status": "suggested", "ready_candidate_count": 1},
        quick_actions=[{"action_id": "create_follow_up"}],
    )

    assert user_view["status_hint"] == "needs_attention"
    assert "1 safe follow-up Proposal action" in user_view["text"]
    block_types = [block["block_type"] for block in user_view["blocks"]]
    assert block_types == [
        "editor_operation_result_summary",
        "editor_operation_graph_details",
        "editor_operation_follow_ups",
    ]
    assert user_view["quick_actions"] == [{"action_id": "create_follow_up"}]


def test_operation_result_user_view_adds_umg_detail_block() -> None:
    user_view = operation_result_user_view(
        operation_result={
            "operation_type": "set_umg_widget_text",
            "result_summary": {
                "needs_user_attention": True,
                "operation_diagnostics": {
                    "category": "umg",
                    "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                    "widget_name": "TitleText",
                    "execution_error_codes": ["widget_not_found"],
                },
            },
            "result": {},
            "errors": [],
        },
        follow_up={},
        quick_actions=[],
    )

    assert user_view["status_hint"] == "needs_attention"
    block_types = [block["block_type"] for block in user_view["blocks"]]
    assert block_types == [
        "editor_operation_result_summary",
        "editor_operation_umg_details",
    ]


def test_operation_result_user_view_adds_generic_detail_block() -> None:
    user_view = operation_result_user_view(
        operation_result={
            "operation_type": "set_actor_transform",
            "result_summary": {
                "needs_user_attention": False,
                "operation_diagnostics": {},
            },
            "result": {
                "actor_reference": "BP_Enemy_C_0",
                "transform_mode": "delta",
                "dirty_packages": ["/Game/Maps/L_Test"],
            },
            "errors": [],
        },
        follow_up={},
        quick_actions=[],
    )

    assert user_view["status_hint"] == "completed"
    block_types = [block["block_type"] for block in user_view["blocks"]]
    assert block_types == [
        "editor_operation_result_summary",
        "editor_operation_target_details",
    ]
