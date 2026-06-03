from __future__ import annotations

from app.services.editor_operations.followups import (
    follow_up_folder_slug,
    follow_up_quick_actions,
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
