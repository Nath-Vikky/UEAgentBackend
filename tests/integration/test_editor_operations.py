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
        "add_blueprint_node_template",
        "compile_blueprint",
        "batch_rename_assets",
        "move_assets",
        "add_umg_widget",
        "set_umg_widget_text",
        "set_umg_widget_layout",
        "set_umg_widget_visibility",
        "place_actor_in_level",
        "set_actor_transform",
        "set_material_instance_parameter",
        "set_material_instance_texture_parameter",
    }.issubset(operation_types)
    operation_items = {
        item["operation_type"]: item
        for item in body["capabilities"]["items"]
    }
    assert operation_items["add_blueprint_variable"]["frontend_status"] == "implemented_v1"
    assert operation_items["add_blueprint_component"]["frontend_status"] == "implemented_v1"
    assert operation_items["create_blueprint_event_stub"]["frontend_status"] == "implemented_v1"
    assert operation_items["add_blueprint_node_template"]["frontend_status"] == "implemented_v1"
    assert operation_items["compile_blueprint"]["frontend_status"] == "implemented_v1"
    assert operation_items["batch_rename_assets"]["frontend_status"] == "implemented_v1"
    assert operation_items["move_assets"]["frontend_status"] == "implemented_v1"
    assert operation_items["add_umg_widget"]["frontend_status"] == "implemented_v1"
    assert operation_items["set_umg_widget_text"]["frontend_status"] == "implemented_v1"
    assert operation_items["set_umg_widget_layout"]["frontend_status"] == "implemented_v1"
    assert operation_items["set_umg_widget_visibility"]["frontend_status"] == "implemented_v1"
    assert operation_items["place_actor_in_level"]["frontend_status"] == "implemented_v1"
    assert operation_items["set_actor_transform"]["frontend_status"] == "implemented_v1"
    assert operation_items["set_material_instance_parameter"]["frontend_status"] == "implemented_v1"
    assert operation_items["set_material_instance_texture_parameter"]["frontend_status"] == "implemented_v1"
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
    assert "editor_add_blueprint_node_template" in tool_ids
    assert "editor_compile_blueprint" in tool_ids
    assert "editor_batch_rename_assets" in tool_ids
    assert "editor_move_assets" in tool_ids
    assert "mcp_get_blueprint_graph" in tool_ids
    assert "mcp_get_widget_tree" in tool_ids
    assert "editor_add_umg_widget" in tool_ids
    assert "editor_set_umg_widget_text" in tool_ids
    assert "editor_set_umg_widget_layout" in tool_ids
    assert "editor_set_umg_widget_visibility" in tool_ids
    assert "editor_place_actor_in_level" in tool_ids
    assert "editor_set_actor_transform" in tool_ids
    assert "editor_set_material_instance_parameter" in tool_ids
    assert "editor_set_material_instance_texture_parameter" in tool_ids
    tools_by_id = {
        item["tool_id"]: item
        for item in capabilities["capabilities"]["tool_registry"]["tools"]
    }
    blueprint_graph_schema = tools_by_id["mcp_get_blueprint_graph"]["output_schema"]["properties"][
        "structuredContent"
    ]["properties"]
    assert "graph_schema_version" in blueprint_graph_schema
    assert "graph_metrics" in blueprint_graph_schema
    assert "graphs" in blueprint_graph_schema


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
    assert created_body["operation"]["preview_summary"]["target_count"] == 1
    assert created_body["operation"]["affected_targets"][0]["target_path"] == "/Game/Maps/L_TestCombatArena"
    assert created_body["operation"]["preflight_checks"][0]["status"] == "passed"
    assert created_body["operation"]["expected_result_contract"]["schema_version"] == "editor_operation_result_v1"

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
                "dirty_packages": ["/Game/Maps/L_TestCombatArena"],
                "applied_fields": {"asset_name": "L_TestCombatArena"},
            },
        },
    )
    assert result.status_code == 200
    result_body = result.json()
    assert result_body["item"]["success"] is True
    assert result_body["item"]["execution_state"] == "completed"
    assert result_body["item"]["result_summary"]["dirty_packages"] == ["/Game/Maps/L_TestCombatArena"]
    assert result_body["item"]["result_summary"]["applied_field_count"] == 1
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


def test_editor_operation_history_returns_preview_and_result_summary(client: TestClient) -> None:
    created = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "set_umg_widget_visibility",
            "payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "TitleText",
                "visibility": "hidden",
            },
            "requested_by": "integration_test",
        },
    )
    assert created.status_code == 200
    proposal_id = created.json()["item"]["proposal_id"]
    assert client.post(f"/api/v1/editor-operations/proposals/{proposal_id}/confirm").status_code == 200
    recorded = client.post(
        "/api/v1/editor-operations/results",
        json={
            "proposal_id": proposal_id,
            "operation_type": "set_umg_widget_visibility",
            "execution_state": "completed",
            "success": True,
            "executed_by": "ue_plugin",
            "result": {
                "dirty": True,
                "dirty_packages": ["/Game/UI/WBP_MainHUD"],
                "applied_fields": {"visibility": "hidden"},
            },
        },
    )
    assert recorded.status_code == 200

    history = client.get("/api/v1/editor-operations/history", params={"operation_type": "set_umg_widget_visibility"})
    assert history.status_code == 200
    body = history.json()
    assert body["summary"]["item_count"] >= 1
    item = body["items"][0]
    assert item["proposal_id"] == proposal_id
    assert item["operation_type"] == "set_umg_widget_visibility"
    assert item["preview_summary"]["target_count"] == 1
    assert item["result_summary"]["dirty_packages"] == ["/Game/UI/WBP_MainHUD"]
    assert item["result_summary"]["applied_field_count"] == 1


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


def test_blueprint_node_template_print_string_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "add_blueprint_node_template",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "template_id": "print_string",
                "graph_name": "EventGraph",
                "message": "Hello from UEAgent",
                "duration": 1.5,
                "entry_event": "BeginPlay",
                "node_position": {"x": 320, "y": 160},
                "compile_after_edit": True,
            },
            "reason": "Add a debug print node for a quick smoke test.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "add_blueprint_node_template"
    assert body["operation"]["tool_id"] == "editor_add_blueprint_node_template"
    payload = body["operation"]["operation_payload"]
    assert payload["template_id"] == "print_string"
    assert payload["message"] == "Hello from UEAgent"
    assert payload["duration"] == 1.5
    assert payload["entry_event"] == "BeginPlay"
    assert payload["compile_after_edit"] is True
    assert payload["node_position"] == {"x": 320.0, "y": 160.0}
    assert body["operation"]["affected_targets"][0]["template_id"] == "print_string"
    assert body["operation"]["affected_targets"][0]["entry_event"] == "BeginPlay"
    assert "created_nodes" in body["operation"]["expected_result_contract"]["operation_result_fields"]
    assert "linked_pins" in body["operation"]["expected_result_contract"]["operation_result_fields"]


def test_blueprint_node_template_branch_print_string_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "add_blueprint_node_template",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "template_id": "branch_print_string",
                "graph_name": "EventGraph",
                "message": "False branch reached",
                "condition_default": False,
                "branch_path": "false",
                "compile_after_edit": True,
            },
            "reason": "Add BeginPlay -> Branch -> PrintString for a safe graph smoke test.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    payload = body["operation"]["operation_payload"]
    assert payload["template_id"] == "branch_print_string"
    assert payload["entry_event"] == "BeginPlay"
    assert payload["condition_default"] is False
    assert payload["branch_path"] == "false"
    assert body["operation"]["affected_targets"][0]["branch_path"] == "false"
    result_fields = body["operation"]["expected_result_contract"]["operation_result_fields"]
    assert "condition_default" in result_fields
    assert "branch_path" in result_fields
    assert "linked_pins" in result_fields


def test_blueprint_node_template_sequence_print_strings_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "add_blueprint_node_template",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "template_id": "sequence_print_strings",
                "graph_name": "EventGraph",
                "messages": ["Sequence A", "Sequence B"],
                "compile_after_edit": True,
            },
            "reason": "Add BeginPlay -> Sequence -> two PrintString nodes.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    payload = body["operation"]["operation_payload"]
    assert payload["template_id"] == "sequence_print_strings"
    assert payload["entry_event"] == "BeginPlay"
    assert payload["messages"] == ["Sequence A", "Sequence B"]
    assert payload["sequence_output_count"] == 2
    assert body["operation"]["affected_targets"][0]["sequence_output_count"] == 2
    result_fields = body["operation"]["expected_result_contract"]["operation_result_fields"]
    assert "sequence_output_count" in result_fields
    assert "messages" in result_fields
    assert "linked_pins" in result_fields


def test_blueprint_node_template_set_variable_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "add_blueprint_node_template",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "template_id": "set_variable",
                "graph_name": "EventGraph",
                "variable_name": "Health",
                "variable_value": "100.0",
                "compile_after_edit": True,
            },
            "reason": "Add BeginPlay -> Set Health node.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    payload = body["operation"]["operation_payload"]
    assert payload["template_id"] == "set_variable"
    assert payload["entry_event"] == "BeginPlay"
    assert payload["variable_name"] == "Health"
    assert payload["variable_scope"] == "self"
    assert payload["variable_value"] == "100.0"
    assert body["operation"]["affected_targets"][0]["variable_name"] == "Health"
    result_fields = body["operation"]["expected_result_contract"]["operation_result_fields"]
    assert "variable_name" in result_fields
    assert "variable_value" in result_fields
    assert "linked_pins" in result_fields


def test_blueprint_node_template_get_variable_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "add_blueprint_node_template",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "template_id": "get_variable",
                "graph_name": "EventGraph",
                "variable_name": "Health",
            },
            "reason": "Add a Get Health node for graph authoring.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    payload = body["operation"]["operation_payload"]
    assert payload["template_id"] == "get_variable"
    assert payload["entry_event"] == ""
    assert payload["variable_name"] == "Health"
    assert payload["variable_scope"] == "self"
    assert body["operation"]["affected_targets"][0]["variable_name"] == "Health"


def test_blueprint_node_template_call_function_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "add_blueprint_node_template",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "template_id": "call_function",
                "graph_name": "EventGraph",
                "function_name": "RefreshHud",
            },
            "reason": "Add BeginPlay -> RefreshHud call node.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    payload = body["operation"]["operation_payload"]
    assert payload["template_id"] == "call_function"
    assert payload["entry_event"] == "BeginPlay"
    assert payload["function_name"] == "RefreshHud"
    assert payload["function_target"] == "self"
    assert body["operation"]["affected_targets"][0]["function_name"] == "RefreshHud"
    result_fields = body["operation"]["expected_result_contract"]["operation_result_fields"]
    assert "function_name" in result_fields
    assert "function_target" in result_fields
    assert "linked_pins" in result_fields


def test_blueprint_node_template_enhanced_input_action_event_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "add_blueprint_node_template",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "template_id": "enhanced_input_action_event",
                "graph_name": "EventGraph",
                "input_action_path": "/Game/Input/IA_Jump",
            },
            "reason": "Add Enhanced Input Action event node.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    payload = body["operation"]["operation_payload"]
    assert payload["template_id"] == "enhanced_input_action_event"
    assert payload["entry_event"] == ""
    assert payload["input_action_path"] == "/Game/Input/IA_Jump"
    assert body["operation"]["affected_targets"][0]["input_action_path"] == "/Game/Input/IA_Jump"
    result_fields = body["operation"]["expected_result_contract"]["operation_result_fields"]
    assert "input_action_path" in result_fields
    assert "created_nodes" in result_fields


def test_blueprint_node_template_rejects_unknown_template(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "add_blueprint_node_template",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "template_id": "delete_all_nodes",
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "blueprint_node_template_not_supported_in_v1"
    assert body["errors"][0]["details"]["allowed_template_ids"] == [
        "branch_print_string",
        "call_function",
        "enhanced_input_action_event",
        "get_variable",
        "print_string",
        "sequence_print_strings",
        "set_variable",
    ]


def test_blueprint_node_template_rejects_unknown_entry_event(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "add_blueprint_node_template",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "template_id": "print_string",
                "entry_event": "Tick",
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "blueprint_node_entry_event_not_supported_in_v1"
    assert body["errors"][0]["details"]["allowed_entry_events"] == ["BeginPlay"]


def test_blueprint_node_template_rejects_unknown_branch_path(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "add_blueprint_node_template",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "template_id": "branch_print_string",
                "branch_path": "maybe",
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "blueprint_branch_path_not_supported_in_v1"
    assert body["errors"][0]["details"]["allowed_branch_paths"] == ["false", "true"]


def test_connect_blueprint_nodes_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "connect_blueprint_nodes",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "graph_name": "EventGraph",
                "source_node_id": "6C7D8E9F-0000-1111-2222-333344445555",
                "source_pin_name": "then",
                "target_node_id": "8E9F0001-2222-3333-4444-555566667777",
                "target_pin_name": "execute",
                "compile_after_edit": True,
            },
            "reason": "Connect two explicit Blueprint pins from graph snapshot.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    payload = body["operation"]["operation_payload"]
    assert payload["graph_name"] == "EventGraph"
    assert payload["source_node_id"] == "6C7D8E9F-0000-1111-2222-333344445555"
    assert payload["source_pin_name"] == "then"
    assert payload["target_node_id"] == "8E9F0001-2222-3333-4444-555566667777"
    assert payload["target_pin_name"] == "execute"
    assert payload["compile_after_edit"] is True
    assert body["operation"]["tool_id"] == "editor_connect_blueprint_nodes"
    assert body["operation"]["affected_targets"][0]["source_pin_name"] == "then"
    result_fields = body["operation"]["expected_result_contract"]["operation_result_fields"]
    assert "linked_pins" in result_fields
    assert "compile_status" in result_fields


def test_connect_blueprint_nodes_rejects_unsafe_node_identifier(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "connect_blueprint_nodes",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "graph_name": "EventGraph",
                "source_node_id": "../bad",
                "source_pin_name": "then",
                "target_node_id": "TargetNode",
                "target_pin_name": "execute",
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "source_node_id_invalid"


def test_blueprint_node_template_result_summary_includes_graph_diagnostics(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "add_blueprint_node_template",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "template_id": "print_string",
                "graph_name": "EventGraph",
                "message": "Hello diagnostics",
                "entry_event": "BeginPlay",
                "compile_after_edit": True,
            },
        },
    )
    assert created.status_code == 200
    proposal_id = created.json()["item"]["proposal_id"]
    assert client.post(f"/api/v1/editor-operations/proposals/{proposal_id}/confirm").status_code == 200

    result = client.post(
        "/api/v1/editor-operations/results",
        json={
            "proposal_id": proposal_id,
            "operation_type": "add_blueprint_node_template",
            "execution_state": "completed",
            "success": True,
            "executed_by": "ue_plugin",
            "result": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "graph_name": "EventGraph",
                "template_id": "print_string",
                "created_nodes": [{"node_name": "K2Node_CallFunction_0"}],
                "linked_nodes": [{"source": "EventBeginPlay", "target": "K2Node_CallFunction_0"}],
                "linked_pins": [{"source_pin": "then", "target_pin": "execute"}],
                "compile_status": "succeeded",
                "dirty": True,
                "dirty_packages": ["/Game/Blueprints/BP_PlayerCharacter"],
                "applied_fields": {"template_id": "print_string"},
            },
        },
    )
    assert result.status_code == 200
    summary = result.json()["item"]["result_summary"]
    diagnostics = summary["operation_diagnostics"]
    assert diagnostics["schema_version"] == "blueprint_graph_operation_diagnostics_v1"
    assert diagnostics["category"] == "blueprint_graph"
    assert diagnostics["blueprint_path"] == "/Game/Blueprints/BP_PlayerCharacter"
    assert diagnostics["graph_name"] == "EventGraph"
    assert diagnostics["template_id"] == "print_string"
    assert diagnostics["created_node_count"] == 1
    assert diagnostics["linked_node_count"] == 1
    assert diagnostics["linked_pin_count"] == 1
    assert diagnostics["compile_requested"] is True
    assert diagnostics["compile_status"] == "succeeded"
    assert diagnostics["diagnostic_flags"] == []
    assert diagnostics["needs_user_attention"] is False
    assert summary["needs_user_attention"] is False

    history = client.get(
        "/api/v1/editor-operations/history",
        params={"operation_type": "add_blueprint_node_template"},
    )
    assert history.status_code == 200
    history_item = history.json()["items"][0]
    assert history_item["proposal_id"] == proposal_id
    history_diagnostics = history_item["result_summary"]["operation_diagnostics"]
    assert history_diagnostics["created_node_count"] == 1
    assert history_diagnostics["linked_pin_count"] == 1


def test_blueprint_node_template_result_summary_flags_missing_expected_links(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "add_blueprint_node_template",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "template_id": "print_string",
                "graph_name": "EventGraph",
                "message": "Unlinked diagnostics",
                "entry_event": "BeginPlay",
                "compile_after_edit": True,
            },
        },
    )
    assert created.status_code == 200
    proposal_id = created.json()["item"]["proposal_id"]
    assert client.post(f"/api/v1/editor-operations/proposals/{proposal_id}/confirm").status_code == 200

    result = client.post(
        "/api/v1/editor-operations/results",
        json={
            "proposal_id": proposal_id,
            "operation_type": "add_blueprint_node_template",
            "execution_state": "completed",
            "success": True,
            "executed_by": "ue_plugin",
            "result": {
                "created_nodes": [{"node_name": "K2Node_CallFunction_0"}],
                "linked_pins": [],
                "compile_status": "succeeded",
                "dirty": True,
                "dirty_packages": ["/Game/Blueprints/BP_PlayerCharacter"],
            },
        },
    )
    assert result.status_code == 200
    diagnostics = result.json()["item"]["result_summary"]["operation_diagnostics"]
    assert diagnostics["created_node_count"] == 1
    assert diagnostics["linked_pin_count"] == 0
    assert diagnostics["diagnostic_flags"] == ["expected_linked_pins_missing"]
    assert diagnostics["needs_user_attention"] is True
    assert result.json()["item"]["result_summary"]["needs_user_attention"] is True


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


def test_move_assets_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "move_assets",
            "payload": {
                "asset_paths": ["/Game/Props/SM_Chair_A", "/Game/Props/SM_Table_A"],
                "target_folder": "/Game/Environment/Props",
            },
            "reason": "Organize props into the environment folder.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "move_assets"
    assert body["operation"]["tool_id"] == "editor_move_assets"
    payload = body["operation"]["operation_payload"]
    assert payload["item_count"] == 2
    assert payload["moves"][0]["target_path"] == "/Game/Environment/Props/SM_Chair_A"
    assert payload["moves"][1]["target_path"] == "/Game/Environment/Props/SM_Table_A"
    assert body["item"]["confirmation"]["state"] == "pending"


def test_move_assets_rejects_same_folder(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "move_assets",
            "payload": {
                "asset_paths": ["/Game/Props/SM_Chair_A"],
                "target_folder": "/Game/Props",
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "move_asset_target_folder_matches_current"


def test_add_umg_widget_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "add_umg_widget",
            "payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "TitleText",
                "widget_class": "TextBlock",
                "parent_widget_name": "RootCanvas",
                "text": "Ready",
            },
            "reason": "Add a title label to HUD.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "add_umg_widget"
    assert body["operation"]["tool_id"] == "editor_add_umg_widget"
    payload = body["operation"]["operation_payload"]
    assert payload["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert payload["widget_class"] == "/Script/UMG.TextBlock"
    assert payload["parent_widget_name"] == "RootCanvas"
    assert payload["text"] == "Ready"
    assert body["item"]["confirmation"]["state"] == "pending"


def test_add_umg_widget_rejects_unsupported_class(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "add_umg_widget",
            "payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "InventoryList",
                "widget_class": "/Script/UMG.ListView",
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "widget_class_not_supported_in_v1"


def test_set_umg_widget_text_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "set_umg_widget_text",
            "payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "TitleText",
                "text": "Mission Ready",
            },
            "reason": "Update HUD title copy.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "set_umg_widget_text"
    assert body["operation"]["tool_id"] == "editor_set_umg_widget_text"
    payload = body["operation"]["operation_payload"]
    assert payload["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert payload["widget_name"] == "TitleText"
    assert payload["text"] == "Mission Ready"
    assert payload["save_policy"] == "mark_dirty_only"
    assert body["item"]["confirmation"]["state"] == "pending"


def test_set_umg_widget_text_rejects_empty_text(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "set_umg_widget_text",
            "payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "TitleText",
                "text": "",
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "widget_text_required"


def test_set_umg_widget_layout_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "set_umg_widget_layout",
            "payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "TitleText",
                "layout": {
                    "position": {"x": 20, "y": 30},
                    "size": {"x": 300, "y": 48},
                    "alignment": {"x": 0.5, "y": 0.0},
                    "anchors": {"minimum": {"x": 0, "y": 0}, "maximum": {"x": 0, "y": 0}},
                },
            },
            "reason": "Place HUD title in the top-left canvas area.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "set_umg_widget_layout"
    assert body["operation"]["tool_id"] == "editor_set_umg_widget_layout"
    payload = body["operation"]["operation_payload"]
    assert payload["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert payload["widget_name"] == "TitleText"
    assert payload["slot_type"] == "CanvasPanelSlot"
    assert payload["layout"]["position"] == {"x": 20.0, "y": 30.0}
    assert payload["layout"]["size"] == {"x": 300.0, "y": 48.0}
    assert payload["layout"]["alignment"] == {"x": 0.5, "y": 0.0}
    assert payload["layout"]["anchors"]["minimum"] == {"x": 0.0, "y": 0.0}
    assert body["item"]["confirmation"]["state"] == "pending"


def test_set_umg_widget_layout_rejects_empty_layout(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "set_umg_widget_layout",
            "payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "TitleText",
                "layout": {},
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "layout_requires_position_size_alignment_or_anchors"


def test_set_umg_widget_visibility_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "set_umg_widget_visibility",
            "payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "TitleText",
                "visibility": "collapsed",
            },
            "reason": "Hide the HUD title for this screen state.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "set_umg_widget_visibility"
    assert body["operation"]["tool_id"] == "editor_set_umg_widget_visibility"
    payload = body["operation"]["operation_payload"]
    assert payload["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert payload["widget_name"] == "TitleText"
    assert payload["visibility"] == "collapsed"
    assert payload["save_policy"] == "mark_dirty_only"
    assert body["item"]["confirmation"]["state"] == "pending"


def test_set_umg_widget_visibility_rejects_unknown_value(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "set_umg_widget_visibility",
            "payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "TitleText",
                "visibility": "transparent",
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "widget_visibility_not_supported_in_v1"


def test_place_actor_in_level_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "place_actor_in_level",
            "payload": {
                "actor_class": "/Script/Engine.PointLight",
                "actor_label": "KeyLight_A",
                "transform": {
                    "location": {"x": 120.0, "y": 50.0, "z": 300.0},
                    "rotation": {"pitch": -25.0, "yaw": 45.0, "roll": 0.0},
                    "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                },
            },
            "reason": "Place a key light for preview.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "place_actor_in_level"
    assert body["operation"]["tool_id"] == "editor_place_actor_in_level"
    payload = body["operation"]["operation_payload"]
    assert payload["actor_class"] == "/Script/Engine.PointLight"
    assert payload["actor_label"] == "KeyLight_A"
    assert payload["transform"]["location"]["z"] == 300.0
    assert payload["save_policy"] == "mark_dirty_only"
    assert body["item"]["confirmation"]["state"] == "pending"


def test_place_actor_rejects_invalid_scale(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "place_actor_in_level",
            "payload": {
                "actor_class": "/Script/Engine.Actor",
                "transform": {"scale": {"x": 0.0, "y": 1.0, "z": 1.0}},
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "scale_x_out_of_range"


def test_set_actor_transform_delta_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "set_actor_transform",
            "payload": {
                "actor_reference": "BP_TestActor_1",
                "transform_mode": "delta",
                "transform_delta": {"location": {"x": 0.0, "y": 200.0, "z": 0.0}},
            },
            "reason": "Move the placed actor to the right.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "set_actor_transform"
    assert body["operation"]["tool_id"] == "editor_set_actor_transform"
    payload = body["operation"]["operation_payload"]
    assert payload["actor_reference"] == "BP_TestActor_1"
    assert payload["transform_mode"] == "delta"
    assert payload["transform_delta"]["location"] == {"x": 0.0, "y": 200.0, "z": 0.0}
    assert payload["save_policy"] == "mark_dirty_only"
    assert body["item"]["confirmation"]["state"] == "pending"


def test_set_actor_transform_rejects_missing_transform(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "set_actor_transform",
            "payload": {
                "actor_reference": "BP_TestActor_1",
                "transform_mode": "absolute",
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "transform_requires_location_rotation_or_scale"


def test_set_material_instance_scalar_parameter_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "set_material_instance_parameter",
            "payload": {
                "material_instance_path": "/Game/Materials/MI_Player",
                "parameter_name": "Roughness",
                "parameter_type": "scalar",
                "value": 0.35,
            },
            "reason": "Tune the preview material.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "set_material_instance_parameter"
    assert body["operation"]["tool_id"] == "editor_set_material_instance_parameter"
    payload = body["operation"]["operation_payload"]
    assert payload["material_instance_path"] == "/Game/Materials/MI_Player"
    assert payload["parameter_name"] == "Roughness"
    assert payload["parameter_type"] == "scalar"
    assert payload["value"] == 0.35
    assert body["item"]["confirmation"]["state"] == "pending"


def test_set_material_instance_vector_parameter_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "set_material_instance_parameter",
            "payload": {
                "material_instance_path": "/Game/Materials/MI_Player",
                "parameter_name": "Tint Color",
                "parameter_type": "vector",
                "value": {"r": 0.1, "g": 0.2, "b": 0.3, "a": 1.0},
            },
        },
    )
    assert response.status_code == 200
    payload = response.json()["operation"]["operation_payload"]
    assert payload["parameter_type"] == "vector"
    assert payload["value"] == {"r": 0.1, "g": 0.2, "b": 0.3, "a": 1.0}


def test_set_material_instance_texture_parameter_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "set_material_instance_texture_parameter",
            "payload": {
                "material_instance_path": "/Game/Materials/MI_Player",
                "parameter_name": "BaseTexture",
                "texture_path": "/Game/Textures/T_Player_D",
            },
            "reason": "Assign the preview diffuse texture.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "set_material_instance_texture_parameter"
    assert body["operation"]["tool_id"] == "editor_set_material_instance_texture_parameter"
    payload = body["operation"]["operation_payload"]
    assert payload["material_instance_path"] == "/Game/Materials/MI_Player"
    assert payload["parameter_name"] == "BaseTexture"
    assert payload["texture_path"] == "/Game/Textures/T_Player_D"
    assert payload["save_policy"] == "mark_dirty_only"
    assert body["item"]["confirmation"]["state"] == "pending"


def test_set_material_instance_rejects_unknown_parameter_type(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "set_material_instance_parameter",
            "payload": {
                "material_instance_path": "/Game/Materials/MI_Player",
                "parameter_name": "Tint",
                "parameter_type": "texture",
                "value": "/Game/Textures/T_Test",
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "material_parameter_type_not_supported_in_v1"


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


def test_agent_chat_can_place_selected_blueprint_in_level(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_place_blueprint_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "把 BP_TestActor 放到当前关卡，位置 0 0 100",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
                "selected_assets": ["/Game/Blueprints/BP_TestActor"],
            },
            "payload": {"user_query": "把 BP_TestActor 放到当前关卡，位置 0 0 100"},
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
    proposal = body["action_proposals"][0]
    assert proposal["dry_run_preview"]["operation_type"] == "place_actor_in_level"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["actor_class"] == "/Game/Blueprints/BP_TestActor.BP_TestActor_C"
    assert payload["transform"]["location"] == {"x": 0.0, "y": 0.0, "z": 100.0}


def test_agent_chat_builds_print_string_template_for_beginplay_text(client: TestClient) -> None:
    query = "给 BP_TestActor 的 EventBeginPlay 添加一个 Print String 节点"
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_blueprint_print_beginplay_session",
                "messages": [{"role": "user", "content": query, "language": "auto"}],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
                "selected_assets": ["/Game/Blueprints/BP_TestActor"],
            },
            "payload": {"user_query": query},
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
    proposal = body["action_proposals"][0]
    assert proposal["dry_run_preview"]["operation_type"] == "add_blueprint_node_template"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["blueprint_path"] == "/Game/Blueprints/BP_TestActor"
    assert payload["template_id"] == "print_string"
    assert payload["graph_name"] == "EventGraph"
    assert payload["entry_event"] == "BeginPlay"


def test_agent_chat_detects_construction_script_graph_for_blueprint_template(
    client: TestClient,
) -> None:
    query = "Add Print String node to BP_TestActor ConstructionScript"
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_blueprint_print_construction_session",
                "messages": [{"role": "user", "content": query, "language": "auto"}],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
                "selected_assets": ["/Game/Blueprints/BP_TestActor"],
            },
            "payload": {"user_query": query},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "en-US",
                "return_debug_projection": True,
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["task"]["status"] == "waiting_confirmation"
    payload = body["action_proposals"][0]["dry_run_preview"]["operation_payload"]
    assert payload["template_id"] == "print_string"
    assert payload["graph_name"] == "ConstructionScript"
    assert payload["entry_event"] == ""


def test_agent_chat_can_compile_selected_blueprint(client: TestClient) -> None:
    query = "编译这个蓝图"
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_compile_selected_blueprint_session",
                "messages": [{"role": "user", "content": query, "language": "auto"}],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
                "selected_assets": ["/Game/Blueprints/BP_TestActor"],
            },
            "payload": {"user_query": query},
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
    proposal = body["action_proposals"][0]
    assert proposal["dry_run_preview"]["operation_type"] == "compile_blueprint"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["blueprint_path"] == "/Game/Blueprints/BP_TestActor"
    assert payload["compile_mode"] == "default"


def test_agent_chat_resolves_blueprint_compile_from_project_inventory(
    client: TestClient,
) -> None:
    snapshot = client.post(
        "/api/v1/project-inventory/snapshot",
        json={
            "project_id": "DemoProject",
            "project_name": "DemoProject",
            "assets": [
                {
                    "asset_path": "/Game/Blueprints/BP_EnemySpawner.BP_EnemySpawner",
                    "asset_name": "BP_EnemySpawner",
                    "asset_type": "Blueprint",
                    "settings": {"parent_class": "AActor"},
                }
            ],
        },
    )
    query = "Compile BP_EnemySpawner blueprint"
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_compile_inventory_blueprint_session",
                "messages": [{"role": "user", "content": query, "language": "auto"}],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
                "selected_assets": [],
            },
            "payload": {"user_query": query},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "en-US",
                "return_debug_projection": True,
            },
        },
    )

    assert snapshot.status_code == 200
    assert response.status_code == 200
    body = response.json()
    assert body["task"]["status"] == "waiting_confirmation"
    proposal = body["action_proposals"][0]
    assert proposal["dry_run_preview"]["operation_type"] == "compile_blueprint"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["blueprint_path"] == "/Game/Blueprints/BP_EnemySpawner"


def test_agent_chat_can_create_blueprint_overlap_event_stub(client: TestClient) -> None:
    query = "给 BP_TestActor 添加 ActorBeginOverlap 事件节点"
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_blueprint_overlap_event_stub_session",
                "messages": [{"role": "user", "content": query, "language": "auto"}],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
                "selected_assets": ["/Game/Blueprints/BP_TestActor"],
            },
            "payload": {"user_query": query},
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
    proposal = body["action_proposals"][0]
    assert proposal["dry_run_preview"]["operation_type"] == "create_blueprint_event_stub"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["blueprint_path"] == "/Game/Blueprints/BP_TestActor"
    assert payload["event_name"] == "ActorBeginOverlap"
    assert payload["graph_name"] == "EventGraph"


def test_agent_chat_resolves_blueprint_tick_event_stub_from_inventory(
    client: TestClient,
) -> None:
    snapshot = client.post(
        "/api/v1/project-inventory/snapshot",
        json={
            "project_id": "DemoProject",
            "project_name": "DemoProject",
            "assets": [
                {
                    "asset_path": "/Game/Blueprints/BP_EnemySpawner.BP_EnemySpawner",
                    "asset_name": "BP_EnemySpawner",
                    "asset_type": "Blueprint",
                }
            ],
        },
    )
    query = "Add Tick event to BP_EnemySpawner blueprint"
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_blueprint_tick_event_stub_session",
                "messages": [{"role": "user", "content": query, "language": "auto"}],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
                "selected_assets": [],
            },
            "payload": {"user_query": query},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "en-US",
                "return_debug_projection": True,
            },
        },
    )

    assert snapshot.status_code == 200
    assert response.status_code == 200
    body = response.json()
    assert body["task"]["status"] == "waiting_confirmation"
    proposal = body["action_proposals"][0]
    assert proposal["dry_run_preview"]["operation_type"] == "create_blueprint_event_stub"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["blueprint_path"] == "/Game/Blueprints/BP_EnemySpawner"
    assert payload["event_name"] == "Tick"


def test_agent_chat_resolves_blueprint_from_project_inventory_for_level_placement(
    client: TestClient,
) -> None:
    snapshot = client.post(
        "/api/v1/project-inventory/snapshot",
        json={
            "project_id": "DemoProject",
            "project_name": "DemoProject",
            "assets": [
                {
                    "asset_path": "/Game/Blueprints/BP_EnemySpawner.BP_EnemySpawner",
                    "asset_name": "BP_EnemySpawner",
                    "asset_type": "Blueprint",
                    "settings": {"parent_class": "AActor"},
                }
            ],
        },
    )
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_place_inventory_blueprint_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Place BP_EnemySpawner in the current level at location 10 20 30",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
                "selected_assets": [],
            },
            "payload": {
                "user_query": "Place BP_EnemySpawner in the current level at location 10 20 30"
            },
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "en-US",
                "return_debug_projection": True,
            },
        },
    )

    assert snapshot.status_code == 200
    assert response.status_code == 200
    body = response.json()
    assert body["task"]["status"] == "waiting_confirmation"
    payload = body["action_proposals"][0]["dry_run_preview"]["operation_payload"]
    assert payload["actor_class"] == "/Game/Blueprints/BP_EnemySpawner.BP_EnemySpawner_C"
    assert payload["transform"]["location"] == {"x": 10.0, "y": 20.0, "z": 30.0}
    assert body["debug_view"]["active_context"]["inventory"]["query_candidate_count"] == 1


def test_agent_chat_reuses_recent_placed_actor_for_transform(client: TestClient) -> None:
    session_id = "chat_actor_transform_active_context_session"
    first = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": session_id,
                "messages": [
                    {
                        "role": "user",
                        "content": "Place BP_TestActor in the current level at location 0 0 100",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
                "selected_assets": ["/Game/Blueprints/BP_TestActor"],
            },
            "payload": {"user_query": "Place BP_TestActor in the current level at location 0 0 100"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "en-US",
                "return_debug_projection": True,
            },
        },
    )
    assert first.status_code == 200
    proposal_id = first.json()["action_proposals"][0]["proposal_id"]
    confirmed = client.post(f"/api/v1/editor-operations/proposals/{proposal_id}/confirm")
    assert confirmed.status_code == 200
    result = client.post(
        "/api/v1/editor-operations/results",
        json={
            "proposal_id": proposal_id,
            "operation_type": "place_actor_in_level",
            "execution_state": "completed",
            "success": True,
            "executed_by": "ue_plugin",
            "transaction_id": f"ue_transaction_{proposal_id}",
            "undo_hint": "Use editor undo.",
            "result": {
                "actor_class": "/Game/Blueprints/BP_TestActor.BP_TestActor_C",
                "actor_label": "BP_TestActor_1",
                "actor_name": "BP_TestActor_C_1",
            },
        },
    )
    assert result.status_code == 200

    followup = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": session_id,
                "messages": [
                    {
                        "role": "user",
                        "content": "Move that actor right 200",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
            },
            "payload": {"user_query": "Move that actor right 200"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "en-US",
                "return_debug_projection": True,
            },
        },
    )
    assert followup.status_code == 200
    body = followup.json()
    assert body["task"]["status"] == "waiting_confirmation"
    payload = body["action_proposals"][0]["dry_run_preview"]["operation_payload"]
    assert payload["actor_reference"] == "BP_TestActor_1"
    assert payload["transform_mode"] == "delta"
    assert payload["transform_delta"]["location"] == {"x": 0.0, "y": 200.0, "z": 0.0}
    last_operation = body["debug_view"]["active_context"]["editor_operation"]["last_successful"]
    assert last_operation["target"]["actor_reference"] == "BP_TestActor_1"


def test_agent_chat_resolves_umg_text_from_project_inventory(client: TestClient) -> None:
    snapshot = client.post(
        "/api/v1/project-inventory/snapshot",
        json={
            "project_id": "DemoProject",
            "project_name": "DemoProject",
            "assets": [
                {
                    "asset_path": "/Game/UI/WBP_MainHUD.WBP_MainHUD",
                    "asset_name": "WBP_MainHUD",
                    "asset_type": "WidgetBlueprint",
                }
            ],
        },
    )
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_umg_text_inventory_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Set WBP_MainHUD TitleText text to 'Mission Ready'",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
                "selected_assets": [],
            },
            "payload": {"user_query": "Set WBP_MainHUD TitleText text to 'Mission Ready'"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "en-US",
                "return_debug_projection": True,
            },
        },
    )

    assert snapshot.status_code == 200
    assert response.status_code == 200
    body = response.json()
    assert body["task"]["status"] == "waiting_confirmation"
    proposal = body["action_proposals"][0]
    assert proposal["dry_run_preview"]["operation_type"] == "set_umg_widget_text"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert payload["widget_name"] == "TitleText"
    assert payload["text"] == "Mission Ready"


def test_agent_chat_resolves_umg_layout_from_project_inventory(client: TestClient) -> None:
    snapshot = client.post(
        "/api/v1/project-inventory/snapshot",
        json={
            "project_id": "DemoProject",
            "project_name": "DemoProject",
            "assets": [
                {
                    "asset_path": "/Game/UI/WBP_MainHUD.WBP_MainHUD",
                    "asset_name": "WBP_MainHUD",
                    "asset_type": "WidgetBlueprint",
                }
            ],
        },
    )
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_umg_layout_inventory_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Set WBP_MainHUD TitleText position to 20 30 size to 300 48",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
                "selected_assets": [],
            },
            "payload": {"user_query": "Set WBP_MainHUD TitleText position to 20 30 size to 300 48"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "en-US",
                "return_debug_projection": True,
            },
        },
    )

    assert snapshot.status_code == 200
    assert response.status_code == 200
    body = response.json()
    assert body["task"]["status"] == "waiting_confirmation"
    proposal = body["action_proposals"][0]
    assert proposal["dry_run_preview"]["operation_type"] == "set_umg_widget_layout"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert payload["widget_name"] == "TitleText"
    assert payload["layout"]["position"] == {"x": 20.0, "y": 30.0}
    assert payload["layout"]["size"] == {"x": 300.0, "y": 48.0}


def test_agent_chat_resolves_umg_visibility_from_project_inventory(client: TestClient) -> None:
    snapshot = client.post(
        "/api/v1/project-inventory/snapshot",
        json={
            "project_id": "DemoProject",
            "project_name": "DemoProject",
            "assets": [
                {
                    "asset_path": "/Game/UI/WBP_MainHUD.WBP_MainHUD",
                    "asset_name": "WBP_MainHUD",
                    "asset_type": "WidgetBlueprint",
                }
            ],
        },
    )
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_umg_visibility_inventory_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Hide WBP_MainHUD TitleText widget",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
                "selected_assets": [],
            },
            "payload": {"user_query": "Hide WBP_MainHUD TitleText widget"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "en-US",
                "return_debug_projection": True,
            },
        },
    )

    assert snapshot.status_code == 200
    assert response.status_code == 200
    body = response.json()
    assert body["task"]["status"] == "waiting_confirmation"
    proposal = body["action_proposals"][0]
    assert proposal["dry_run_preview"]["operation_type"] == "set_umg_widget_visibility"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert payload["widget_name"] == "TitleText"
    assert payload["visibility"] == "collapsed"


def test_agent_chat_can_set_selected_material_instance_parameter(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_material_parameter_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "把 MI_Player 的 Roughness 调到 0.35",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
                "selected_assets": ["/Game/Materials/MI_Player"],
            },
            "payload": {"user_query": "把 MI_Player 的 Roughness 调到 0.35"},
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
    proposal = body["action_proposals"][0]
    assert proposal["dry_run_preview"]["operation_type"] == "set_material_instance_parameter"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["material_instance_path"] == "/Game/Materials/MI_Player"
    assert payload["parameter_name"] == "Roughness"
    assert payload["parameter_type"] == "scalar"
    assert payload["value"] == 0.35


def test_agent_chat_resolves_material_from_project_inventory(client: TestClient) -> None:
    snapshot = client.post(
        "/api/v1/project-inventory/snapshot",
        json={
            "project_id": "DemoProject",
            "project_name": "DemoProject",
            "assets": [
                {
                    "asset_path": "/Game/Materials/MI_Player.MI_Player",
                    "asset_name": "MI_Player",
                    "asset_type": "MaterialInstanceConstant",
                }
            ],
        },
    )
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_material_inventory_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Set MI_Player material Roughness to 0.25",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
                "selected_assets": [],
            },
            "payload": {"user_query": "Set MI_Player material Roughness to 0.25"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "en-US",
                "return_debug_projection": True,
            },
        },
    )

    assert snapshot.status_code == 200
    assert response.status_code == 200
    body = response.json()
    assert body["task"]["status"] == "waiting_confirmation"
    payload = body["action_proposals"][0]["dry_run_preview"]["operation_payload"]
    assert payload["material_instance_path"] == "/Game/Materials/MI_Player"
    assert payload["parameter_name"] == "Roughness"
    assert payload["value"] == 0.25
    assert body["debug_view"]["active_context"]["inventory"]["query_candidate_count"] == 1


def test_agent_chat_resolves_material_texture_from_project_inventory(client: TestClient) -> None:
    snapshot = client.post(
        "/api/v1/project-inventory/snapshot",
        json={
            "project_id": "DemoProject",
            "project_name": "DemoProject",
            "assets": [
                {
                    "asset_path": "/Game/Materials/MI_Player.MI_Player",
                    "asset_name": "MI_Player",
                    "asset_type": "MaterialInstanceConstant",
                },
                {
                    "asset_path": "/Game/Textures/T_Player_D.T_Player_D",
                    "asset_name": "T_Player_D",
                    "asset_type": "Texture2D",
                },
            ],
        },
    )
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_material_texture_inventory_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Set MI_Player material BaseTexture to T_Player_D texture",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
                "selected_assets": [],
            },
            "payload": {"user_query": "Set MI_Player material BaseTexture to T_Player_D texture"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "en-US",
                "return_debug_projection": True,
            },
        },
    )

    assert snapshot.status_code == 200
    assert response.status_code == 200
    body = response.json()
    assert body["task"]["status"] == "waiting_confirmation"
    proposal = body["action_proposals"][0]
    assert proposal["dry_run_preview"]["operation_type"] == "set_material_instance_texture_parameter"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["material_instance_path"] == "/Game/Materials/MI_Player"
    assert payload["parameter_name"] == "BaseTexture"
    assert payload["texture_path"] == "/Game/Textures/T_Player_D"


def test_agent_chat_reuses_recent_material_operation_context(client: TestClient) -> None:
    session_id = "chat_material_active_context_session"
    first = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": session_id,
                "messages": [
                    {
                        "role": "user",
                        "content": "Set selected material MI_Player Roughness to 0.35",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
                "selected_assets": ["/Game/Materials/MI_Player"],
            },
            "payload": {"user_query": "Set selected material MI_Player Roughness to 0.35"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "en-US",
                "return_debug_projection": True,
            },
        },
    )
    assert first.status_code == 200
    first_body = first.json()
    proposal = first_body["action_proposals"][0]
    proposal_id = proposal["proposal_id"]

    confirmed = client.post(f"/api/v1/editor-operations/proposals/{proposal_id}/confirm")
    assert confirmed.status_code == 200
    result = client.post(
        "/api/v1/editor-operations/results",
        json={
            "proposal_id": proposal_id,
            "operation_type": "set_material_instance_parameter",
            "execution_state": "completed",
            "success": True,
            "executed_by": "ue_plugin",
            "transaction_id": f"ue_transaction_{proposal_id}",
            "undo_hint": "Use editor undo.",
            "result": {
                "material_instance_path": "/Game/Materials/MI_Player",
                "parameter_name": "Roughness",
                "parameter_type": "scalar",
                "value": 0.35,
            },
        },
    )
    assert result.status_code == 200

    followup = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": session_id,
                "messages": [
                    {
                        "role": "user",
                        "content": "Set that material Roughness to 0.55",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
                "selected_assets": [],
            },
            "payload": {"user_query": "Set that material Roughness to 0.55"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "en-US",
                "return_debug_projection": True,
            },
        },
    )
    assert followup.status_code == 200
    followup_body = followup.json()
    assert followup_body["task"]["status"] == "waiting_confirmation"
    payload = followup_body["action_proposals"][0]["dry_run_preview"]["operation_payload"]
    assert payload["material_instance_path"] == "/Game/Materials/MI_Player"
    assert payload["parameter_name"] == "Roughness"
    assert payload["value"] == 0.55
    active_context = followup_body["debug_view"]["active_context"]
    last_operation = active_context["editor_operation"]["last_successful"]
    assert last_operation["target"]["material_instance_path"] == "/Game/Materials/MI_Player"
