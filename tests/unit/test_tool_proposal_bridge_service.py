from __future__ import annotations

from app.services.tool_proposal_bridge_service import ToolProposalBridgeService


def test_prepare_confirmed_write_tool_as_editor_operation_proposal() -> None:
    bridge = ToolProposalBridgeService.prepare_proposal(
        tool_id="editor_arrange_actors_pattern",
        arguments={
            "actor_references": [
                {"actor_name": "BP_Enemy_01"},
                {"actor_name": "BP_Enemy_02"},
            ],
            "pattern": "line",
        },
        reason="Arrange enemies for a quick layout pass.",
        requested_by="unit_test",
    )

    assert bridge["status"] == "prepared"
    assert bridge["operation_type"] == "arrange_actors_pattern"
    assert bridge["requires_user_confirmation"] is True
    assert bridge["auto_execute"] is False
    assert bridge["direct_editor_write_allowed"] is False
    assert bridge["proposal_request_hint"]["path"] == "/api/v1/editor-operations/proposals"
    assert bridge["proposal_request"]["payload"]["pattern"] == "line"
    assert bridge["proposal_request"]["requested_by"] == "unit_test"


def test_prepare_blocks_readonly_tool() -> None:
    bridge = ToolProposalBridgeService.prepare_proposal(
        tool_id="mcp_get_blueprint_graph",
        arguments={"blueprint_path": "/Game/BP_Test"},
    )

    assert bridge["status"] == "blocked"
    assert bridge["block_reason"] == "tool_is_not_confirmed_write"
    assert bridge["auto_execute"] is False
    assert bridge["proposal_request_hint"] == {}


def test_prepare_blueprint_add_step_alias_normalizes_to_node_template() -> None:
    bridge = ToolProposalBridgeService.prepare_proposal(
        tool_id="editor_blueprint_add_step",
        arguments={
            "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
            "step_name": "PrintString",
            "graph_name": "EventGraph",
            "text": "Hello from alias",
            "entry_event": "BeginPlay",
            "compile_after_edit": True,
        },
        requested_by="unit_test",
    )

    assert bridge["status"] == "prepared"
    assert bridge["tool_id"] == "editor_blueprint_add_step"
    assert bridge["operation_type"] == "add_blueprint_node_template"
    payload = bridge["proposal_request"]["payload"]
    assert payload["template_id"] == "print_string"
    assert payload["message"] == "Hello from alias"
    assert "step_name" not in payload
    assert "text" not in payload


def test_prepare_blueprint_add_step_alias_uses_blueprint_context_defaults() -> None:
    bridge = ToolProposalBridgeService.prepare_proposal(
        tool_id="editor_blueprint_add_step",
        arguments={
            "step_name": "Print String",
            "text": "Hello from context",
        },
        context={
            "blueprint_edit_context": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "graph_name": "EventGraph",
            }
        },
        requested_by="unit_test",
    )

    assert bridge["status"] == "prepared"
    payload = bridge["proposal_request"]["payload"]
    assert payload["blueprint_path"] == "/Game/Blueprints/BP_PlayerCharacter"
    assert payload["graph_name"] == "EventGraph"
    assert payload["template_id"] == "print_string"
    assert payload["message"] == "Hello from context"


def test_prepare_blueprint_connect_nodes_uses_cursor_context_defaults() -> None:
    bridge = ToolProposalBridgeService.prepare_proposal(
        tool_id="editor_connect_blueprint_nodes",
        arguments={
            "target_node_id": "PrintString_1",
            "target_pin_name": "execute",
        },
        context={
            "blueprint_edit_context": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "graph_name": "EventGraph",
                "cursor_node": {
                    "node_id": "EventBeginPlay",
                    "pins": [
                        {"pin_name": "then", "direction": "output", "pin_type": "exec"},
                    ],
                },
            }
        },
        requested_by="unit_test",
    )

    assert bridge["status"] == "prepared"
    assert bridge["operation_type"] == "connect_blueprint_nodes"
    payload = bridge["proposal_request"]["payload"]
    assert payload["blueprint_path"] == "/Game/Blueprints/BP_PlayerCharacter"
    assert payload["graph_name"] == "EventGraph"
    assert payload["source_node_id"] == "EventBeginPlay"
    assert payload["source_pin_name"] == "then"
    assert payload["target_node_id"] == "PrintString_1"
    assert payload["target_pin_name"] == "execute"


def test_prepare_umg_set_text_uses_cursor_context_defaults() -> None:
    bridge = ToolProposalBridgeService.prepare_proposal(
        tool_id="editor_set_umg_widget_text",
        arguments={"text": "Mission Ready"},
        context={
            "umg_edit_context": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "cursor_widget": {
                    "widget_name": "TitleText",
                    "widget_class": "TextBlock",
                    "parent_widget_name": "RootCanvas",
                },
            }
        },
        requested_by="unit_test",
    )

    assert bridge["status"] == "prepared"
    assert bridge["operation_type"] == "set_umg_widget_text"
    payload = bridge["proposal_request"]["payload"]
    assert payload["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert payload["widget_name"] == "TitleText"
    assert payload["text"] == "Mission Ready"


def test_prepare_umg_add_widget_uses_context_parent_defaults() -> None:
    bridge = ToolProposalBridgeService.prepare_proposal(
        tool_id="editor_add_umg_widget",
        arguments={"widget_name": "SubtitleText", "widget_class": "TextBlock", "text": "Press Start"},
        context={
            "umg_edit_context": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "root_widget_name": "RootCanvas",
                "cursor_widget": {
                    "widget_name": "StatusPanel",
                    "widget_class": "HorizontalBox",
                },
            }
        },
        requested_by="unit_test",
    )

    assert bridge["status"] == "prepared"
    assert bridge["operation_type"] == "add_umg_widget"
    payload = bridge["proposal_request"]["payload"]
    assert payload["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert payload["parent_widget_name"] == "StatusPanel"
    assert payload["widget_name"] == "SubtitleText"
    assert payload["widget_class"] == "TextBlock"


def test_prepare_blocks_unknown_tool() -> None:
    bridge = ToolProposalBridgeService.prepare_proposal(
        tool_id="editor_delete_everything",
        arguments={},
    )

    assert bridge["status"] == "blocked"
    assert bridge["block_reason"] == "tool_not_registered"
    assert bridge["direct_editor_write_allowed"] is False
