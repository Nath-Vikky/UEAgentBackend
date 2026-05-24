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


def test_prepare_blocks_unknown_tool() -> None:
    bridge = ToolProposalBridgeService.prepare_proposal(
        tool_id="editor_delete_everything",
        arguments={},
    )

    assert bridge["status"] == "blocked"
    assert bridge["block_reason"] == "tool_not_registered"
    assert bridge["direct_editor_write_allowed"] is False
