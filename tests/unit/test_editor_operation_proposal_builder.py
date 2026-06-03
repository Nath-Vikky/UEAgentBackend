from __future__ import annotations

from app.services.editor_operations.catalog import OPERATION_SPECS
from app.services.editor_operations.proposal_builder import (
    build_editor_operation_action_proposal,
)


def test_build_editor_operation_action_proposal_keeps_confirmation_contract() -> None:
    proposal = build_editor_operation_action_proposal(
        proposal_id="proposal_1",
        operation_type="rename_selected_asset",
        spec=OPERATION_SPECS["rename_selected_asset"],
        normalized_payload={"asset_path": "/Game/Maps/OldMap", "new_name": "NewMap"},
        before_summary="Before",
        after_summary="After",
        rationale="Rename for clarity.",
        affected_targets=[{"kind": "asset", "action": "rename", "path": "/Game/Maps/OldMap"}],
        preflight_checks=[{"check": "asset_path", "status": "pass"}],
        expected_result_contract={"schema_version": "editor_operation_result_v1"},
        preview_summary={"operation_type": "rename_selected_asset"},
        source_task_id="task_1",
        context={"source": "test"},
    )

    assert proposal["proposal_id"] == "proposal_1"
    assert proposal["proposal_type"] == "editor_operation"
    assert proposal["requires_confirmation"] is True
    assert proposal["confirmation"]["state"] == "pending"
    assert proposal["display_hints"]["confirm_endpoint"].endswith("/proposal_1/confirm")
    assert proposal["display_hints"]["generic_decision_endpoint"].endswith("/proposal_1/decision")

    preview = proposal["dry_run_preview"]
    assert preview["operation_type"] == "rename_selected_asset"
    assert preview["transport"] == "http"
    assert preview["mcp_like"] is True
    assert preview["side_effect_level"] == "confirmed_write"
    assert preview["execution_contract"]["llm_direct_execution"] is False
    assert preview["execution_contract"]["undo_required"] is True
    assert preview["source_task_id"] == "task_1"
    assert preview["context"] == {"source": "test"}


def test_build_editor_operation_action_proposal_adds_blueprint_graph_policy() -> None:
    proposal = build_editor_operation_action_proposal(
        proposal_id="proposal_bp",
        operation_type="add_blueprint_node_template",
        spec=OPERATION_SPECS["add_blueprint_node_template"],
        normalized_payload={
            "blueprint_path": "/Game/Blueprints/BP_TestActor",
            "graph_name": "EventGraph",
            "template_id": "print_string",
            "entry_event": "BeginPlay",
            "message": "Hello",
        },
        before_summary="Before",
        after_summary="After",
        rationale="Add a debug print.",
        affected_targets=[{"kind": "blueprint_graph", "action": "add_node_template"}],
        preflight_checks=[],
        expected_result_contract={"schema_version": "editor_operation_result_v1"},
        preview_summary={"operation_type": "add_blueprint_node_template"},
        source_task_id=None,
        context={},
        policy_reason="Add Print String node to EventGraph BeginPlay",
    )

    graph_policy = proposal["dry_run_preview"]["blueprint_graph_policy"]

    assert graph_policy["schema_version"] == "blueprint_graph_policy_v1"
    assert graph_policy["graph_name"] == "EventGraph"
    assert graph_policy["entry_event"] == "BeginPlay"
    assert graph_policy["expected_behavior"]["connects_exec_pins"] is True
    assert graph_policy["warnings"] == []
