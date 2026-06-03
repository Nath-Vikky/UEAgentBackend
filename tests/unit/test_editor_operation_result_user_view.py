from __future__ import annotations

from app.services.editor_operations.result_user_view import (
    blueprint_graph_result_detail_block,
    operation_result_user_view,
    summarize_graph_node,
    summarize_graph_pin,
    summarize_limited_items,
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
