from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.settings import get_settings
from app.db.session import get_engine, get_session_factory
from app.main import create_app


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    runtime_root = Path(".test-runtime") / f"editor-ops-{uuid.uuid4().hex}"
    storage_dir = runtime_root / "storage"
    shutil.rmtree(runtime_root, ignore_errors=True)
    storage_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("STORAGE_DIR", str(storage_dir.resolve()))
    monkeypatch.setenv("UPLOAD_DIR", str((storage_dir / "uploads").resolve()))
    monkeypatch.setenv("ARTIFACT_DIR", str((storage_dir / "artifacts").resolve()))
    monkeypatch.setenv("KB_DIR", str((storage_dir / "kb").resolve()))
    monkeypatch.setenv("KB_SOURCE_PATHS", "./knowledge")
    monkeypatch.setenv("EMBEDDING_ENABLED", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    shutil.rmtree(runtime_root, ignore_errors=True)


def test_editor_operation_capabilities_and_registry(client: TestClient) -> None:
    response = client.get("/api/v1/editor-operations/capabilities")
    assert response.status_code == 200
    body = response.json()
    operation_types = {item["operation_type"] for item in body["capabilities"]["items"]}
    assert {
        "rename_selected_asset",
        "apply_static_mesh_basic_settings",
        "create_blueprint_asset",
        "add_blueprint_variable",
        "add_blueprint_component",
        "create_blueprint_event_stub",
        "compile_blueprint",
        "batch_rename_assets",
    }.issubset(operation_types)
    operation_items = {
        item["operation_type"]: item
        for item in body["capabilities"]["items"]
    }
    assert operation_items["add_blueprint_variable"]["frontend_status"] == "implemented_v1"
    assert operation_items["add_blueprint_component"]["frontend_status"] == "implemented_v1"
    assert operation_items["create_blueprint_event_stub"]["frontend_status"] == "implemented_v1"
    assert operation_items["compile_blueprint"]["frontend_status"] == "implemented_v1"
    assert operation_items["batch_rename_assets"]["frontend_status"] == "implemented_v1"
    assert body["capabilities"]["safety_policy"]["requires_frontend_confirmation"] is True

    capabilities = client.get("/api/v1/system/capabilities").json()
    tool_ids = {
        item["tool_id"]
        for item in capabilities["capabilities"]["tool_registry"]["tools"]
    }
    assert "editor_rename_asset" in tool_ids
    assert "editor_apply_static_mesh_settings" in tool_ids
    assert "editor_create_blueprint_asset" in tool_ids
    assert "editor_add_blueprint_variable" in tool_ids
    assert "editor_add_blueprint_component" in tool_ids
    assert "editor_create_blueprint_event_stub" in tool_ids
    assert "editor_compile_blueprint" in tool_ids
    assert "editor_batch_rename_assets" in tool_ids
    assert "mcp_get_blueprint_graph" in tool_ids
    assert "mcp_get_widget_tree" in tool_ids


def test_editor_operation_rename_proposal_confirm_and_result(client: TestClient) -> None:
    created = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "rename_selected_asset",
            "payload": {
                "asset_path": "/Game/Maps/NewMap",
                "new_name": "L_TestCombatArena",
            },
            "reason": "Default map name should be replaced before project review.",
            "requested_by": "integration_test",
        },
    )
    assert created.status_code == 200
    created_body = created.json()
    proposal_id = created_body["item"]["proposal_id"]
    assert created_body["item"]["proposal_type"] == "editor_operation"
    assert created_body["item"]["confirmation"]["state"] == "pending"
    assert created_body["operation"]["tool_id"] == "editor_rename_asset"
    assert created_body["operation"]["operation_payload"]["target_path"] == "/Game/Maps/L_TestCombatArena"

    confirmed = client.post(f"/api/v1/editor-operations/proposals/{proposal_id}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["proposal"]["confirmation"]["state"] == "confirmed"

    result = client.post(
        "/api/v1/editor-operations/results",
        json={
            "proposal_id": proposal_id,
            "operation_type": "rename_selected_asset",
            "execution_state": "completed",
            "success": True,
            "executed_by": "ue_plugin",
            "transaction_id": "tx_rename_001",
            "undo_hint": "Use editor undo or rename the asset back.",
            "result": {
                "final_asset_path": "/Game/Maps/L_TestCombatArena",
                "dirty": True,
            },
        },
    )
    assert result.status_code == 200
    result_body = result.json()
    assert result_body["item"]["success"] is True
    assert result_body["item"]["execution_state"] == "completed"
    assert result_body["proposal"]["dry_run_preview"]["operation_result"]["transaction_id"] == "tx_rename_001"


def test_editor_operation_result_requires_confirmation(client: TestClient) -> None:
    created = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "create_blueprint_asset",
            "payload": {
                "parent_class": "/Script/Engine.Character",
                "target_folder": "/Game/Blueprints",
                "asset_name": "BP_TestCharacter",
            },
        },
    )
    assert created.status_code == 200
    proposal_id = created.json()["item"]["proposal_id"]

    result = client.post(
        "/api/v1/editor-operations/results",
        json={
            "proposal_id": proposal_id,
            "operation_type": "create_blueprint_asset",
            "execution_state": "completed",
            "success": True,
        },
    )
    assert result.status_code == 409
    assert result.json()["errors"][0]["code"] == "proposal_must_be_confirmed_before_execution_result"


def test_editor_operation_static_mesh_settings_are_whitelisted(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "apply_static_mesh_basic_settings",
            "payload": {
                "asset_path": "/Game/Props/SM_Crate",
                "settings": {
                    "nanite_enabled": True,
                    "material_override": "/Game/M_Test",
                },
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "settings_contains_unsupported_fields"
    assert body["errors"][0]["details"]["unsupported_fields"] == ["material_override"]


def test_blueprint_graph_variable_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "add_blueprint_variable",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "variable_name": "Health",
                "variable_type": "float",
                "category": "Combat",
                "default_value": "100.0",
            },
            "reason": "Expose a health value for designers.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "add_blueprint_variable"
    payload = body["operation"]["operation_payload"]
    assert payload["blueprint_path"] == "/Game/Blueprints/BP_PlayerCharacter"
    assert payload["variable_name"] == "Health"
    assert payload["variable_type"] == "float"
    assert payload["save_policy"] == "mark_dirty_only"
    assert body["item"]["confirmation"]["state"] == "pending"


def test_blueprint_graph_variable_type_aliases_match_ue_frontend(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "add_blueprint_variable",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "variable_name": "DisplayName",
                "variable_type": "string",
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()["operation"]["operation_payload"]
    assert payload["variable_type"] == "FString"


def test_blueprint_graph_event_stub_is_whitelisted(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "create_blueprint_event_stub",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "event_name": "CustomCombatEvent",
                "graph_name": "EventGraph",
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "event_name_not_supported_in_v1"
    assert "BeginPlay" in body["errors"][0]["details"]["allowed_events"]


def test_blueprint_compile_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "compile_blueprint",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
            },
            "reason": "Compile after generated graph changes.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "compile_blueprint"
    assert body["operation"]["tool_id"] == "editor_compile_blueprint"
    payload = body["operation"]["operation_payload"]
    assert payload["blueprint_path"] == "/Game/Blueprints/BP_PlayerCharacter"
    assert payload["compile_mode"] == "default"
    assert body["item"]["confirmation"]["state"] == "pending"


def test_batch_rename_assets_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "batch_rename_assets",
            "payload": {
                "renames": [
                    {"asset_path": "/Game/Props/Chair", "new_name": "SM_Chair_A"},
                    {"asset_path": "/Game/Props/Table", "new_name": "SM_Table_A"},
                ],
            },
            "reason": "Normalize asset naming for a content folder.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "batch_rename_assets"
    assert body["operation"]["tool_id"] == "editor_batch_rename_assets"
    payload = body["operation"]["operation_payload"]
    assert payload["item_count"] == 2
    assert payload["renames"][0]["target_path"] == "/Game/Props/SM_Chair_A"
    assert payload["renames"][1]["target_path"] == "/Game/Props/SM_Table_A"
    assert body["item"]["confirmation"]["state"] == "pending"


def test_batch_rename_rejects_duplicate_targets(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "batch_rename_assets",
            "payload": {
                "renames": [
                    {"asset_path": "/Game/Props/Chair", "new_name": "SM_Common"},
                    {"asset_path": "/Game/Props/Table", "new_name": "SM_Common"},
                ],
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "batch_rename_duplicate_target"


def test_assets_inspect_emits_rename_editor_operation_proposal(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks/assets-inspect",
        json={
            "task_type": "assets_inspect",
            "session": {
                "session_id": "asset_editor_operation_session",
                "messages": [{"role": "user", "content": "检查这个资产命名", "language": "auto"}],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "AssetInspector",
                "selected_assets": ["/Game/Maps/NewMap"],
            },
            "payload": {
                "user_query": "检查这个资产命名",
                "asset_items": [
                    {
                        "asset_name": "NewMap",
                        "asset_path": "/Game/Maps/NewMap",
                        "asset_type": "World",
                        "package_path": "/Game/Maps",
                        "dependencies": [],
                        "referencers": [],
                    }
                ],
            },
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "zh-CN",
                "return_debug_projection": True,
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["task"]["status"] == "waiting_confirmation"
    task_id = body["task"]["task_id"]
    proposal = body["action_proposals"][0]
    proposal_id = proposal["proposal_id"]
    assert proposal["proposal_type"] == "editor_operation"
    assert proposal["dry_run_preview"]["operation_type"] == "rename_selected_asset"
    assert proposal["dry_run_preview"]["operation_payload"]["asset_path"] == "/Game/Maps/NewMap"
    assert proposal["dry_run_preview"]["tool_id"] == "editor_rename_asset"

    confirmed = client.post(f"/api/v1/editor-operations/proposals/{proposal_id}/confirm")
    assert confirmed.status_code == 200
    result = client.post(
        "/api/v1/editor-operations/results",
        json={
            "proposal_id": proposal_id,
            "operation_type": "rename_selected_asset",
            "execution_state": "completed",
            "success": True,
            "executed_by": "ue_plugin",
            "transaction_id": f"ue_transaction_{proposal_id}",
            "undo_hint": "Use editor undo.",
            "result": {
                "final_asset_path": "/Game/Maps/L_NewMap",
                "dirty": True,
                "package_name": "/Game/Maps/L_NewMap",
            },
        },
    )
    assert result.status_code == 200
    task_detail = client.get(f"/api/v1/tasks/{task_id}").json()
    assert task_detail["data"]["editor_operation_results"][0]["success"] is True
    assert task_detail["debug_view"]["side_effects"][0]["operation_result"]["transaction_id"] == (
        f"ue_transaction_{proposal_id}"
    )


def test_agent_chat_can_create_blueprint_editor_operation_proposal(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_editor_operation_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "帮我创建一个角色蓝图 BP_TestCharacter",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
            },
            "payload": {"user_query": "帮我创建一个角色蓝图 BP_TestCharacter"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "zh-CN",
                "return_debug_projection": True,
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["task"]["status"] == "waiting_confirmation"
    assert body["data"]["editor_operation"]["proposal_created"] is True
    proposal = body["action_proposals"][0]
    assert proposal["proposal_type"] == "editor_operation"
    assert proposal["dry_run_preview"]["operation_type"] == "create_blueprint_asset"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["parent_class"] == "/Script/Engine.Character"
    assert payload["asset_name"] == "BP_TestCharacter"
