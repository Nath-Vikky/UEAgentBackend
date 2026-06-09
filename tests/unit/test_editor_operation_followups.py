from __future__ import annotations

import pytest

from app.services.editor_operations.followups import (
    entry_event_node_hint,
    first_node_identifier,
    follow_up_folder_slug,
    follow_up_quick_actions,
    materialize_follow_up_proposal_request,
    node_identifier,
    operation_follow_up_payload,
    redirector_follow_up_folders,
)


def test_redirector_follow_up_folders_extracts_unique_bounded_source_folders() -> None:
    folders = redirector_follow_up_folders(
        operation_type="move_assets",
        payload={
            "asset_paths": [
                "/Game/Blueprints/BP_Player",
                "/Game/Blueprints/BP_Enemy",
                "/Game/UI/WBP_MainHUD",
            ],
            "moves": [{"asset_path": "/Game/Materials/MI_Player"}],
        },
        result={},
    )

    assert folders == ["/Game/Materials", "/Game/Blueprints", "/Game/UI"]


def test_redirector_follow_up_folders_ignores_non_asset_operations() -> None:
    assert (
        redirector_follow_up_folders(
            operation_type="set_umg_widget_text",
            payload={"asset_path": "/Game/UI/WBP_MainHUD"},
            result={},
        )
        == []
    )


def test_follow_up_quick_actions_only_exposes_ready_candidates() -> None:
    actions = follow_up_quick_actions(
        proposal_id="proposal_123",
        follow_up={
            "candidates": [
                {
                    "candidate_id": "connect_expected_exec_pins",
                    "operation_type": "connect_blueprint_nodes",
                    "proposal_ready": True,
                    "missing_inputs": [],
                },
                {
                    "candidate_id": "retry_compile",
                    "operation_type": "compile_blueprint",
                    "proposal_ready": False,
                    "missing_inputs": ["blueprint_path"],
                },
            ]
        },
    )

    assert len(actions) == 1
    assert actions[0]["action_id"] == "create_editor_operation_follow_up_proposal_123_connect_expected_exec_pins"
    assert actions[0]["payload"]["endpoint"] == "/api/v1/editor-operations/proposals/proposal_123/follow-ups/proposal"
    assert actions[0]["payload"]["safety"]["auto_execute"] is False
    assert actions[0]["payload"]["safety"]["creates_pending_proposal_only"] is True


def test_follow_up_folder_slug_is_stable_and_bounded() -> None:
    assert follow_up_folder_slug("/Game/Blueprints/Characters") == "Game_Blueprints_Characters"
    assert follow_up_folder_slug("///") == "folder"


def test_follow_up_node_helpers_extract_stable_ids() -> None:
    assert node_identifier({"node_id": "NODE-GUID", "node_name": "DisplayName"}) == "NODE-GUID"
    assert first_node_identifier([{}, {"node_name": "PrintString"}]) == "PrintString"
    assert entry_event_node_hint("BeginPlay") == "EventBeginPlay"
    assert entry_event_node_hint("ActorBeginOverlap") == "EventActorBeginOverlap"


def test_operation_follow_up_payload_returns_not_ready_without_result() -> None:
    payload = operation_follow_up_payload(
        proposal_id="proposal_1",
        preview={"operation_type": "add_blueprint_node_template"},
        is_editor_operation=True,
    )

    assert payload["follow_up"]["status"] == "not_ready"
    assert payload["follow_up"]["reason"] == "operation_result_missing"


def test_operation_follow_up_payload_builds_connect_candidate_from_repair_advice() -> None:
    payload = operation_follow_up_payload(
        proposal_id="proposal_2",
        preview={
            "operation_type": "add_blueprint_node_template",
            "tool_id": "editor_add_blueprint_node_template",
            "operation_payload": {
                "blueprint_path": "/Game/Blueprints/BP_Player",
                "graph_name": "EventGraph",
                "entry_event": "BeginPlay",
            },
            "operation_result": {
                "success": True,
                "execution_state": "completed",
                "result": {
                    "created_nodes": [{"node_id": "PRINT-GUID"}],
                },
                "result_summary": {
                    "operation_diagnostics": {
                        "diagnostic_flags": ["expected_linked_pins_missing"],
                        "repair_advice": {
                            "status": "suggested",
                            "actions": [{"action_id": "connect_expected_exec_pins"}],
                        },
                    }
                },
            },
        },
        is_editor_operation=True,
    )

    follow_up = payload["follow_up"]
    assert follow_up["status"] == "suggested"
    assert follow_up["ready_candidate_count"] == 1
    candidate = follow_up["candidates"][0]
    assert candidate["operation_type"] == "connect_blueprint_nodes"
    assert candidate["payload"]["source_node_id"] == "EventBeginPlay"
    assert candidate["payload"]["target_node_id"] == "PRINT-GUID"
    assert candidate["create_request_hint"]["json"]["context"]["source_proposal_id"] == "proposal_2"
    assert candidate["auto_execute"] is False


def test_operation_follow_up_payload_adds_redirector_candidate_after_asset_move() -> None:
    payload = operation_follow_up_payload(
        proposal_id="proposal_3",
        preview={
            "operation_type": "move_assets",
            "tool_id": "editor_move_assets",
            "operation_payload": {"asset_paths": ["/Game/Blueprints/BP_Player"]},
            "operation_result": {
                "success": True,
                "execution_state": "completed",
                "result": {},
                "result_summary": {},
            },
        },
        is_editor_operation=True,
    )

    follow_up = payload["follow_up"]
    assert follow_up["status"] == "suggested"
    assert follow_up["candidates"][0]["operation_type"] == "fixup_redirectors"
    assert follow_up["candidates"][0]["payload"]["folder_path"] == "/Game/Blueprints"


def test_operation_follow_up_payload_builds_umg_missing_text_widget_candidate() -> None:
    payload = operation_follow_up_payload(
        proposal_id="proposal_umg_text",
        preview={
            "operation_type": "set_umg_widget_text",
            "tool_id": "editor_set_umg_widget_text",
            "operation_payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "TitleText",
                "text": "Ready",
            },
            "operation_result": {
                "success": False,
                "execution_state": "failed",
                "result": {
                    "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                    "widget_name": "TitleText",
                    "error_code": "widget_not_found",
                },
                "result_summary": {
                    "operation_diagnostics": {
                        "diagnostic_flags": ["umg_widget_unresolved"],
                        "repair_advice": {
                            "status": "suggested",
                            "actions": [{"action_id": "verify_umg_widget_name"}],
                        },
                    }
                },
            },
        },
        is_editor_operation=True,
    )

    follow_up = payload["follow_up"]
    assert follow_up["status"] == "suggested"
    assert follow_up["ready_candidate_count"] == 1
    candidate = follow_up["candidates"][0]
    assert candidate["candidate_id"] == "create_missing_umg_widget"
    assert candidate["operation_type"] == "add_umg_widget"
    assert candidate["proposal_ready"] is True
    assert candidate["payload"] == {
        "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
        "widget_name": "TitleText",
        "widget_class": "/Script/UMG.TextBlock",
        "parent_widget_name": "",
        "text": "Ready",
        "is_variable": True,
    }
    assert candidate["create_request_hint"]["json"]["context"]["source_proposal_id"] == "proposal_umg_text"
    assert candidate["auto_execute"] is False


def test_operation_follow_up_payload_keeps_umg_layout_candidate_manual_without_class() -> None:
    payload = operation_follow_up_payload(
        proposal_id="proposal_umg_layout",
        preview={
            "operation_type": "set_umg_widget_layout",
            "tool_id": "editor_set_umg_widget_layout",
            "operation_payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "UnknownPanel",
                "layout": {"position": {"x": 10, "y": 20}},
            },
            "operation_result": {
                "success": False,
                "execution_state": "failed",
                "result": {"error_code": "widget_not_found"},
                "result_summary": {
                    "operation_diagnostics": {
                        "diagnostic_flags": ["umg_widget_unresolved"],
                        "repair_advice": {
                            "status": "suggested",
                            "actions": [{"action_id": "verify_umg_widget_name"}],
                        },
                    }
                },
            },
        },
        is_editor_operation=True,
    )

    follow_up = payload["follow_up"]
    assert follow_up["status"] == "needs_manual_input"
    assert follow_up["ready_candidate_count"] == 0
    candidate = follow_up["candidates"][0]
    assert candidate["candidate_id"] == "create_missing_umg_widget"
    assert candidate["operation_type"] == "add_umg_widget"
    assert candidate["proposal_ready"] is False
    assert candidate["missing_inputs"] == ["widget_class"]
    assert follow_up_quick_actions(proposal_id="proposal_umg_layout", follow_up=follow_up) == []


def test_operation_follow_up_payload_builds_umg_missing_parent_candidate() -> None:
    payload = operation_follow_up_payload(
        proposal_id="proposal_umg_parent",
        preview={
            "operation_type": "add_umg_widget",
            "tool_id": "editor_add_umg_widget",
            "operation_payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "TitleText",
                "widget_class": "/Script/UMG.TextBlock",
                "parent_widget_name": "RootCanvas",
            },
            "operation_result": {
                "success": False,
                "execution_state": "failed",
                "result": {"parent_widget_name": "RootCanvas", "error_code": "parent_widget_not_found"},
                "result_summary": {
                    "operation_diagnostics": {
                        "diagnostic_flags": ["umg_parent_unresolved"],
                        "repair_advice": {
                            "status": "suggested",
                            "actions": [{"action_id": "verify_umg_parent_widget"}],
                        },
                    }
                },
            },
        },
        is_editor_operation=True,
    )

    follow_up = payload["follow_up"]
    assert follow_up["status"] == "suggested"
    candidate = follow_up["candidates"][0]
    assert candidate["candidate_id"] == "create_missing_umg_parent_widget"
    assert candidate["operation_type"] == "add_umg_widget"
    assert candidate["proposal_ready"] is True
    assert candidate["payload"]["widget_name"] == "RootCanvas"
    assert candidate["payload"]["widget_class"] == "/Script/UMG.CanvasPanel"
    assert candidate["payload"]["parent_widget_name"] == ""


def test_materialize_follow_up_proposal_request_keeps_proposal_pending_and_contextual() -> None:
    follow_up = operation_follow_up_payload(
        proposal_id="proposal_4",
        preview={
            "operation_type": "move_assets",
            "tool_id": "editor_move_assets",
            "operation_payload": {"asset_paths": ["/Game/Blueprints/BP_Player"]},
            "operation_result": {
                "success": True,
                "execution_state": "completed",
                "result": {},
                "result_summary": {},
            },
        },
        is_editor_operation=True,
    )["follow_up"]
    candidate = follow_up["candidates"][0]

    materialized = materialize_follow_up_proposal_request(
        source_proposal_id="proposal_4",
        candidate=candidate,
        requested_by="unit_test",
        context={"smoke_case": "redirector_follow_up"},
    )

    assert materialized["schema_version"] == "editor_operation_follow_up_materialization_v1"
    assert materialized["tool_id"] == "editor_fixup_redirectors"
    assert materialized["auto_execute"] is False
    assert materialized["requires_user_confirmation"] is True
    proposal_request = materialized["proposal_request"]
    assert proposal_request["operation_type"] == "fixup_redirectors"
    assert proposal_request["requested_by"] == "unit_test"
    assert proposal_request["context"]["source_proposal_id"] == "proposal_4"
    assert proposal_request["context"]["smoke_case"] == "redirector_follow_up"
    assert proposal_request["context"]["follow_up_materialization"]["auto_execute"] is False


def test_materialize_follow_up_proposal_request_rejects_unready_candidate() -> None:
    with pytest.raises(ValueError, match="follow_up_candidate_not_ready_for_proposal"):
        materialize_follow_up_proposal_request(
            source_proposal_id="proposal_5",
            candidate={
                "candidate_id": "retry_compile_blueprint",
                "proposal_ready": False,
                "missing_inputs": ["blueprint_path"],
                "create_request_hint": {
                    "json": {
                        "operation_type": "compile_blueprint",
                        "payload": {"blueprint_path": ""},
                    }
                },
            },
        )
