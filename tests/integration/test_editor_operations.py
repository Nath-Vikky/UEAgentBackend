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


def _seed_named_blueprint_inventory(
    client: TestClient,
    *,
    project_id: str = "DemoProject",
    asset_path: str = "/Game/Blueprints/BP_ProjectSpecificName.BP_ProjectSpecificName",
    asset_name: str = "BP_ProjectSpecificName",
) -> None:
    response = client.post(
        "/api/v1/project-inventory/snapshot",
        json={
            "project_id": project_id,
            "project_name": project_id,
            "assets": [
                {
                    "asset_path": asset_path,
                    "asset_name": asset_name,
                    "asset_type": "Blueprint",
                    "settings": {"parent_class": "AActor"},
                }
            ],
        },
    )
    assert response.status_code == 200


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
        "duplicate_asset",
        "fixup_redirectors",
        "add_umg_widget",
        "set_umg_widget_text",
        "set_umg_widget_layout",
        "set_umg_widget_visibility",
        "set_umg_widget_appearance",
        "set_umg_widget_brush",
        "set_umg_slot_layout_v2",
        "reparent_umg_widget",
        "duplicate_umg_widget",
        "delete_umg_widget",
        "place_actor_in_level",
        "set_actor_transform",
        "set_actor_metadata",
        "arrange_actors_pattern",
        "set_material_instance_parameter",
        "set_material_instance_texture_parameter",
        "set_material_instance_static_switch",
    }.issubset(operation_types)
    operation_items = {
        item["operation_type"]: item
        for item in body["capabilities"]["items"]
    }
    assert body["capabilities"]["summary"]["operation_count"] >= 18
    assert body["capabilities"]["summary"]["implemented_frontend_count"] >= 18
    assert body["capabilities"]["summary"]["read_only_operation_count"] >= 4
    assert body["capabilities"]["summary"]["roadmap_operation_count"] >= 0
    assert body["capabilities"]["summary"]["risk_flag_counts"]["MEDIUM"] >= 1
    assert body["capabilities"]["summary"]["group_counts"]["blueprint"] >= 7
    assert body["capabilities"]["summary"]["group_counts"]["level"] >= 4
    group_ids = {item["group_id"] for item in body["capabilities"]["groups"]}
    assert {"asset", "blueprint", "umg", "level", "material"}.issubset(group_ids)
    roadmap_items = {
        item["operation_type"]: item
        for item in body["capabilities"]["roadmap_items"]
    }
    read_only_items = {
        item["operation_type"]: item
        for item in body["capabilities"]["read_only_items"]
    }
    assert "set_umg_widget_appearance" not in roadmap_items
    assert "set_umg_slot_layout_v2" not in roadmap_items
    assert "set_actor_metadata" not in roadmap_items
    assert "arrange_actors_pattern" not in roadmap_items
    assert read_only_items["inspect_level_actors"]["side_effect_level"] == "read_only"
    assert read_only_items["inspect_level_actors"]["requires_confirmation"] is False
    assert read_only_items["inspect_level_actors"]["proposal_enabled"] is False
    assert read_only_items["inspect_assets"]["endpoint"].endswith("/inspect/assets")
    assert read_only_items["inspect_asset_detail"]["endpoint"].endswith("/inspect/asset-detail")
    assert read_only_items["inspect_material_instance_parameters"]["endpoint"].endswith(
        "/inspect/material-instance-parameters"
    )
    assert operation_items["add_blueprint_variable"]["frontend_status"] == "implemented_v1"
    assert operation_items["add_blueprint_variable"]["group"] == "blueprint"
    assert operation_items["add_blueprint_variable"]["risk_flags"] == "MEDIUM"
    assert operation_items["add_blueprint_variable"]["requires_confirmation"] is True
    assert operation_items["add_blueprint_variable"]["auto_save"] is False
    assert "blueprint_path" in operation_items["add_blueprint_variable"]["result_contract_fields"]
    assert operation_items["add_blueprint_component"]["frontend_status"] == "implemented_v1"
    assert operation_items["create_blueprint_event_stub"]["frontend_status"] == "implemented_v1"
    assert operation_items["add_blueprint_node_template"]["frontend_status"] == "implemented_v1"
    assert operation_items["compile_blueprint"]["frontend_status"] == "implemented_v1"
    assert operation_items["batch_rename_assets"]["frontend_status"] == "implemented_v1"
    assert operation_items["move_assets"]["frontend_status"] == "implemented_v1"
    assert operation_items["duplicate_asset"]["frontend_status"] == "implemented_v1"
    assert operation_items["fixup_redirectors"]["frontend_status"] == "implemented_v1"
    assert operation_items["add_umg_widget"]["frontend_status"] == "implemented_v1"
    assert operation_items["set_umg_widget_text"]["frontend_status"] == "implemented_v1"
    assert operation_items["set_umg_widget_layout"]["frontend_status"] == "implemented_v1"
    assert operation_items["set_umg_widget_visibility"]["frontend_status"] == "implemented_v1"
    assert operation_items["set_umg_widget_appearance"]["frontend_status"] == "implemented_v1"
    assert operation_items["set_umg_widget_brush"]["frontend_status"] == "implemented_v1"
    assert operation_items["set_umg_slot_layout_v2"]["frontend_status"] == "implemented_v1"
    assert operation_items["reparent_umg_widget"]["frontend_status"] == "implemented_v1"
    assert operation_items["duplicate_umg_widget"]["frontend_status"] == "implemented_v1"
    assert operation_items["delete_umg_widget"]["frontend_status"] == "implemented_v1"
    assert operation_items["place_actor_in_level"]["frontend_status"] == "implemented_v1"
    assert operation_items["set_actor_transform"]["frontend_status"] == "implemented_v1"
    assert operation_items["set_actor_metadata"]["frontend_status"] == "implemented_v1"
    assert operation_items["arrange_actors_pattern"]["frontend_status"] == "implemented_v1"
    assert operation_items["set_material_instance_parameter"]["frontend_status"] == "implemented_v1"
    assert operation_items["set_material_instance_texture_parameter"]["frontend_status"] == "implemented_v1"
    assert operation_items["set_material_instance_static_switch"]["frontend_status"] == "implemented_v1"
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
    assert "editor_duplicate_asset" in tool_ids
    assert "editor_fixup_redirectors" in tool_ids
    assert "mcp_get_blueprint_graph" in tool_ids
    assert "mcp_get_widget_tree" in tool_ids
    assert "editor_add_umg_widget" in tool_ids
    assert "editor_set_umg_widget_text" in tool_ids
    assert "editor_set_umg_widget_layout" in tool_ids
    assert "editor_set_umg_widget_visibility" in tool_ids
    assert "editor_set_umg_widget_appearance" in tool_ids
    assert "editor_set_umg_widget_brush" in tool_ids
    assert "editor_set_umg_slot_layout_v2" in tool_ids
    assert "editor_reparent_umg_widget" in tool_ids
    assert "editor_duplicate_umg_widget" in tool_ids
    assert "editor_delete_umg_widget" in tool_ids
    assert "editor_place_actor_in_level" in tool_ids
    assert "editor_set_actor_transform" in tool_ids
    assert "editor_set_actor_metadata" in tool_ids
    assert "editor_arrange_actors_pattern" in tool_ids
    assert "editor_set_material_instance_parameter" in tool_ids
    assert "editor_set_material_instance_texture_parameter" in tool_ids
    assert "editor_set_material_instance_static_switch" in tool_ids
    assert "editor_inspect_assets" in tool_ids
    assert "editor_inspect_asset_detail" in tool_ids
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


def test_editor_operation_read_only_inspections_use_project_inventory(client: TestClient) -> None:
    snapshot = client.post(
        "/api/v1/project-inventory/snapshot",
        json={
            "project_id": "ReadOnlyInspectionProject",
            "project_name": "ReadOnlyInspectionProject",
            "assets": [
                {
                    "asset_path": "/Game/Environment/SM_Rock.SM_Rock",
                    "asset_name": "SM_Rock",
                    "asset_type": "StaticMesh",
                    "package_path": "/Game/Environment",
                    "dependencies": ["/Game/Materials/M_Rock"],
                    "referencers": ["/Game/Maps/L_Test"],
                    "settings": {"nanite_enabled": True, "lod_count": 3},
                    "properties": {"material_slots": ["M_Rock"]},
                },
                {
                    "asset_path": "/Game/Blueprints/BP_PlayerCharacter.BP_PlayerCharacter",
                    "asset_name": "BP_PlayerCharacter",
                    "asset_type": "Blueprint",
                    "package_path": "/Game/Blueprints",
                    "blueprint": {"parent_class": "ACharacter"},
                },
            ],
            "level_actors": [
                {
                    "actor_label": "BP_EnemySpawner_1",
                    "actor_class": "BP_EnemySpawner_C",
                    "level_name": "L_Test",
                    "transform": {"location": {"x": 100, "y": 0, "z": 20}},
                    "components": [{"component_name": "SceneRoot", "component_class": "SceneComponent"}],
                }
            ],
            "material_instances": [
                {
                    "material_instance_path": "/Game/Materials/MI_Rock.MI_Rock",
                    "material_instance_name": "MI_Rock",
                    "parent_material": "/Game/Materials/M_Rock.M_Rock",
                    "scalar_parameters": [{"name": "Roughness", "value": 0.6}],
                    "static_switch_parameters": [{"name": "UseDetail", "value": True}],
                }
            ],
        },
    )
    actors = client.get(
        "/api/v1/editor-operations/inspect/level-actors",
        params={"project_id": "ReadOnlyInspectionProject", "query": "EnemySpawner"},
    )
    assets = client.get(
        "/api/v1/editor-operations/inspect/assets",
        params={"project_id": "ReadOnlyInspectionProject", "asset_type": "StaticMesh", "query": "Rock"},
    )
    asset_detail = client.get(
        "/api/v1/editor-operations/inspect/asset-detail",
        params={"project_id": "ReadOnlyInspectionProject", "asset_id": "SM_Rock"},
    )
    materials = client.get(
        "/api/v1/editor-operations/inspect/material-instance-parameters",
        params={"project_id": "ReadOnlyInspectionProject", "material_instance_path": "/Game/Materials/MI_Rock"},
    )

    assert snapshot.status_code == 200
    assert actors.status_code == 200
    assert actors.json()["inspection"]["operation_type"] == "inspect_level_actors"
    assert actors.json()["inspection"]["side_effect_level"] == "read_only"
    assert actors.json()["items"][0]["actor_label"] == "BP_EnemySpawner_1"
    assert assets.status_code == 200
    assert assets.json()["inspection"]["operation_type"] == "inspect_assets"
    assert assets.json()["inspection"]["side_effect_level"] == "read_only"
    assert assets.json()["items"][0]["asset_name"] == "SM_Rock"
    assert asset_detail.status_code == 200
    assert asset_detail.json()["inspection"]["operation_type"] == "inspect_asset_detail"
    assert asset_detail.json()["item"]["asset_name"] == "SM_Rock"
    assert asset_detail.json()["item"]["settings"]["nanite_enabled"] is True
    assert materials.status_code == 200
    assert materials.json()["inspection"]["operation_type"] == "inspect_material_instance_parameters"
    assert materials.json()["items"][0]["material_instance_name"] == "MI_Rock"
    assert materials.json()["items"][0]["scalar_parameters"][0]["name"] == "Roughness"


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
    assert result_body["follow_up"]["ready_candidate_count"] == 1
    follow_candidate = result_body["follow_up"]["candidates"][0]
    assert follow_candidate["operation_type"] == "fixup_redirectors"
    assert follow_candidate["payload"]["folder_path"] == "/Game/Maps"
    assert follow_candidate["auto_execute"] is False
    assert result_body["user_view"]["quick_actions"][0]["payload"]["candidate_id"].startswith("fixup_redirectors_")

    materialized = client.post(
        f"/api/v1/editor-operations/proposals/{proposal_id}/follow-ups/proposal",
        json={"candidate": follow_candidate, "requested_by": "integration_test"},
    )
    assert materialized.status_code == 200
    materialized_body = materialized.json()
    assert materialized_body["proposal"]["operation"]["operation_type"] == "fixup_redirectors"
    assert materialized_body["proposal"]["operation"]["operation_payload"]["folder_path"] == "/Game/Maps"
    assert materialized_body["proposal"]["item"]["confirmation"]["state"] == "pending"


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


def test_blueprint_node_template_overlap_print_string_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "add_blueprint_node_template",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "template_id": "print_string",
                "graph_name": "EventGraph",
                "message": "Overlap detected",
                "entry_event": "ActorBeginOverlap",
                "compile_after_edit": True,
            },
            "reason": "Add ActorBeginOverlap -> PrintString for a safe graph smoke test.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    payload = body["operation"]["operation_payload"]
    assert payload["template_id"] == "print_string"
    assert payload["message"] == "Overlap detected"
    assert payload["entry_event"] == "ActorBeginOverlap"
    assert body["operation"]["affected_targets"][0]["entry_event"] == "ActorBeginOverlap"
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


def test_blueprint_node_template_delay_print_string_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "add_blueprint_node_template",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "template_id": "delay_print_string",
                "graph_name": "EventGraph",
                "message": "Delayed print",
                "delay_seconds": 1.25,
                "compile_after_edit": True,
            },
            "reason": "Add BeginPlay -> Delay -> PrintString for a safe graph smoke test.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    payload = body["operation"]["operation_payload"]
    assert payload["template_id"] == "delay_print_string"
    assert payload["entry_event"] == "BeginPlay"
    assert payload["message"] == "Delayed print"
    assert payload["delay_seconds"] == 1.25
    assert body["operation"]["affected_targets"][0]["delay_seconds"] == 1.25
    result_fields = body["operation"]["expected_result_contract"]["operation_result_fields"]
    assert "delay_seconds" in result_fields
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


def test_blueprint_node_template_custom_event_print_string_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "add_blueprint_node_template",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "template_id": "custom_event_print_string",
                "graph_name": "EventGraph",
                "custom_event_name": "OnAgentTriggered",
                "message": "Custom event reached",
            },
            "reason": "Add Custom Event -> PrintString for a safe graph smoke test.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    payload = body["operation"]["operation_payload"]
    assert payload["template_id"] == "custom_event_print_string"
    assert payload["entry_event"] == ""
    assert payload["custom_event_name"] == "OnAgentTriggered"
    assert payload["message"] == "Custom event reached"
    assert body["operation"]["affected_targets"][0]["custom_event_name"] == "OnAgentTriggered"
    result_fields = body["operation"]["expected_result_contract"]["operation_result_fields"]
    assert "custom_event_name" in result_fields
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


def test_blueprint_node_template_enhanced_input_print_string_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "add_blueprint_node_template",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "template_id": "enhanced_input_print_string",
                "graph_name": "EventGraph",
                "input_action_path": "/Game/Input/IA_Jump",
                "message": "Jump triggered",
            },
            "reason": "Add Enhanced Input Action event and connect Triggered to PrintString.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    payload = body["operation"]["operation_payload"]
    assert payload["template_id"] == "enhanced_input_print_string"
    assert payload["entry_event"] == ""
    assert payload["input_action_path"] == "/Game/Input/IA_Jump"
    assert payload["message"] == "Jump triggered"
    result_fields = body["operation"]["expected_result_contract"]["operation_result_fields"]
    assert "input_action_path" in result_fields
    assert "linked_pins" in result_fields


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
        "custom_event_print_string",
        "delay_print_string",
        "enhanced_input_action_event",
        "enhanced_input_print_string",
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
    assert body["errors"][0]["details"]["allowed_entry_events"] == [
        "ActorBeginOverlap",
        "ActorEndOverlap",
        "BeginPlay",
    ]


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
    assert diagnostics["repair_advice"]["status"] == "not_needed"
    assert summary["repair_advice"]["status"] == "not_needed"
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
                "created_node_id": "11111111-2222-3333-4444-555566667777",
                "created_node_name": "K2Node_CallFunction_0",
                "entry_node_id": "AAAAAAAA-BBBB-CCCC-DDDD-EEEEFFFFFFFF",
                "entry_node_name": "EventBeginPlay",
                "created_nodes": [
                    {
                        "node_id": "11111111-2222-3333-4444-555566667777",
                        "node_name": "K2Node_CallFunction_0",
                        "node_class": "K2Node_CallFunction",
                        "role": "print_string",
                    }
                ],
                "linked_pins": [],
                "linked_pin_summaries": [],
                "compile_status": "succeeded",
                "dirty": True,
                "dirty_packages": ["/Game/Blueprints/BP_PlayerCharacter"],
            },
        },
    )
    assert result.status_code == 200
    result_body = result.json()
    diagnostics = result_body["item"]["result_summary"]["operation_diagnostics"]
    assert diagnostics["created_node_count"] == 1
    assert diagnostics["linked_pin_count"] == 0
    assert diagnostics["diagnostic_flags"] == ["expected_linked_pins_missing"]
    assert diagnostics["needs_user_attention"] is True
    assert diagnostics["repair_advice"]["status"] == "suggested"
    assert diagnostics["repair_advice"]["actions"][0]["action_id"] == "connect_expected_exec_pins"
    assert diagnostics["repair_advice"]["can_auto_retry"] is False
    assert result_body["item"]["result_summary"]["needs_user_attention"] is True
    assert result_body["item"]["result_summary"]["repair_advice"]["status"] == "suggested"
    assert result_body["user_view"]["status_hint"] == "needs_attention"
    graph_detail_block = next(
        block
        for block in result_body["user_view"]["blocks"]
        if block["block_type"] == "editor_operation_graph_details"
    )
    assert graph_detail_block["data"]["schema_version"] == "blueprint_graph_result_details_v1"
    assert graph_detail_block["data"]["created_node_id"] == "11111111-2222-3333-4444-555566667777"
    assert graph_detail_block["data"]["entry_node_id"] == "AAAAAAAA-BBBB-CCCC-DDDD-EEEEFFFFFFFF"
    assert "Primary created node: K2Node_CallFunction_0" in graph_detail_block["data"]["items"][4]
    assert result_body["user_view"]["quick_actions"]
    follow_up_action = result_body["user_view"]["quick_actions"][0]
    assert follow_up_action["payload"]["action_type"] == "create_editor_operation_follow_up_proposal"
    assert follow_up_action["payload"]["source_proposal_id"] == proposal_id
    assert follow_up_action["payload"]["safety"]["auto_execute"] is False
    assert follow_up_action["payload"]["safety"]["creates_pending_proposal_only"] is True
    assert result_body["follow_up"]["ready_candidate_count"] == 1
    assert result_body["task"]["task_type"] == "editor_operation_result"

    follow_ups = client.get(f"/api/v1/editor-operations/proposals/{proposal_id}/follow-ups")
    assert follow_ups.status_code == 200
    follow_up = follow_ups.json()["follow_up"]
    assert follow_up["schema_version"] == "editor_operation_follow_up_candidates_v1"
    assert follow_up["status"] == "suggested"
    assert follow_up["candidate_count"] == 1
    assert follow_up["ready_candidate_count"] == 1
    candidate = follow_up["candidates"][0]
    assert candidate["candidate_id"] == "connect_expected_exec_pins"
    assert candidate["operation_type"] == "connect_blueprint_nodes"
    assert candidate["proposal_ready"] is True
    assert candidate["auto_execute"] is False
    assert candidate["payload"]["source_node_id"] == "AAAAAAAA-BBBB-CCCC-DDDD-EEEEFFFFFFFF"
    assert candidate["payload"]["target_node_id"] == "11111111-2222-3333-4444-555566667777"
    assert candidate["create_request_hint"]["json"]["context"]["source_proposal_id"] == proposal_id

    materialized = client.post(
        f"/api/v1/editor-operations/proposals/{proposal_id}/follow-ups/proposal",
        json={"candidate": candidate, "requested_by": "integration_test"},
    )
    assert materialized.status_code == 200
    materialized_body = materialized.json()
    assert materialized_body["success"] is True
    assert materialized_body["follow_up_step"]["schema_version"] == "editor_operation_follow_up_materialization_v1"
    assert materialized_body["follow_up_step"]["source_proposal_id"] == proposal_id
    assert materialized_body["follow_up_step"]["candidate_id"] == "connect_expected_exec_pins"
    assert materialized_body["follow_up_step"]["operation_type"] == "connect_blueprint_nodes"
    assert materialized_body["follow_up_step"]["auto_execute"] is False
    assert materialized_body["proposal"]["item"]["confirmation"]["state"] == "pending"
    assert materialized_body["proposal"]["operation"]["operation_type"] == "connect_blueprint_nodes"
    assert (
        materialized_body["proposal"]["operation"]["context"]["follow_up_materialization"]["source_proposal_id"]
        == proposal_id
    )

    attention_history = client.get(
        "/api/v1/editor-operations/history",
        params={
            "operation_type": "add_blueprint_node_template",
            "needs_user_attention": "true",
        },
    )
    assert attention_history.status_code == 200
    attention_body = attention_history.json()
    assert attention_body["summary"]["needs_user_attention"] is True
    assert attention_body["items"][0]["proposal_id"] == proposal_id

    diagnostic_history = client.get(
        "/api/v1/editor-operations/history",
        params={
            "operation_type": "add_blueprint_node_template",
            "diagnostic_flag": "expected_linked_pins_missing",
        },
    )
    assert diagnostic_history.status_code == 200
    diagnostic_body = diagnostic_history.json()
    assert diagnostic_body["summary"]["diagnostic_flag"] == "expected_linked_pins_missing"
    assert diagnostic_body["items"][0]["proposal_id"] == proposal_id

    clean_history = client.get(
        "/api/v1/editor-operations/history",
        params={
            "operation_type": "add_blueprint_node_template",
            "needs_user_attention": "false",
        },
    )
    assert clean_history.status_code == 200
    assert clean_history.json()["items"] == []


def test_editor_operation_diagnostics_summary_counts_attention_flags(client: TestClient) -> None:
    def _record_print_result(*, message: str, linked_pins: list[dict[str, str]]) -> str:
        created = client.post(
            "/api/v1/editor-operations/proposals",
            json={
                "operation_type": "add_blueprint_node_template",
                "payload": {
                    "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                    "template_id": "print_string",
                    "graph_name": "EventGraph",
                    "message": message,
                    "entry_event": "BeginPlay",
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
                    "linked_pins": linked_pins,
                    "compile_status": "succeeded",
                    "dirty": True,
                    "dirty_packages": ["/Game/Blueprints/BP_PlayerCharacter"],
                },
            },
        )
        assert result.status_code == 200
        return proposal_id

    _record_print_result(message="Linked", linked_pins=[{"source_pin": "then", "target_pin": "execute"}])
    attention_proposal_id = _record_print_result(message="Unlinked", linked_pins=[])

    response = client.get(
        "/api/v1/editor-operations/diagnostics",
        params={"operation_type": "add_blueprint_node_template"},
    )
    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["schema_version"] == "editor_operation_diagnostics_summary_v1"
    assert summary["operation_type"] == "add_blueprint_node_template"
    assert summary["inspected_count"] == 2
    assert summary["executed_count"] == 2
    assert summary["success_count"] == 2
    assert summary["failed_count"] == 0
    assert summary["needs_user_attention_count"] == 1
    assert summary["attention_rate"] == 0.5
    assert summary["operation_type_counts"]["add_blueprint_node_template"] == 2
    assert summary["diagnostic_flag_counts"]["expected_linked_pins_missing"] == 1
    assert summary["repair_status_counts"]["not_needed"] == 1
    assert summary["repair_status_counts"]["suggested"] == 1
    assert summary["repair_action_counts"]["connect_expected_exec_pins"] == 1
    assert summary["execution_state_counts"]["completed"] == 2
    assert summary["confirmation_state_counts"]["confirmed"] == 2
    attention_item = summary["recent_attention_items"][0]
    assert attention_item["proposal_id"] == attention_proposal_id
    assert attention_item["diagnostic_flags"] == ["expected_linked_pins_missing"]
    assert attention_item["repair_advice"]["actions"][0]["action_id"] == "connect_expected_exec_pins"


def test_blueprint_compile_failed_result_includes_repair_advice(client: TestClient) -> None:
    created = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "compile_blueprint",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
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
            "operation_type": "compile_blueprint",
            "execution_state": "failed",
            "success": False,
            "executed_by": "ue_plugin",
            "result": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "compile_status": "failed",
                "messages": ["Broken execution pin"],
            },
            "errors": [{"code": "compile_failed", "message": "Blueprint compile failed"}],
        },
    )
    assert result.status_code == 200
    summary = result.json()["item"]["result_summary"]
    diagnostics = summary["operation_diagnostics"]
    action_ids = [item["action_id"] for item in diagnostics["repair_advice"]["actions"]]
    assert diagnostics["diagnostic_flags"] == ["compile_failed"]
    assert diagnostics["needs_user_attention"] is True
    assert diagnostics["repair_advice"]["status"] == "suggested"
    assert diagnostics["repair_advice"]["severity"] == "error"
    assert "inspect_ue_execution_errors" in action_ids
    assert "open_blueprint_compile_results" in action_ids
    assert summary["repair_advice"]["safe_next_step"] == "manual_review"

    follow_ups = client.get(f"/api/v1/editor-operations/proposals/{proposal_id}/follow-ups")
    assert follow_ups.status_code == 200
    follow_up = follow_ups.json()["follow_up"]
    assert follow_up["status"] == "suggested"
    assert follow_up["ready_candidate_count"] == 1
    candidate = follow_up["candidates"][0]
    assert candidate["candidate_id"] == "retry_compile_blueprint"
    assert candidate["operation_type"] == "compile_blueprint"
    assert candidate["proposal_ready"] is True
    assert candidate["payload"]["blueprint_path"] == "/Game/Blueprints/BP_PlayerCharacter"
    assert candidate["create_request_hint"]["json"]["operation_type"] == "compile_blueprint"


def test_editor_operation_follow_ups_require_result_before_suggesting(client: TestClient) -> None:
    created = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "compile_blueprint",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
            },
        },
    )
    assert created.status_code == 200
    proposal_id = created.json()["item"]["proposal_id"]

    response = client.get(f"/api/v1/editor-operations/proposals/{proposal_id}/follow-ups")
    assert response.status_code == 200
    follow_up = response.json()["follow_up"]
    assert follow_up["status"] == "not_ready"
    assert follow_up["reason"] == "operation_result_missing"
    assert follow_up["candidates"] == []


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


def test_duplicate_asset_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "duplicate_asset",
            "payload": {
                "source_asset_path": "/Game/Blueprints/BP_EnemySpawner",
                "new_name": "BP_EnemySpawner_Copy",
                "target_folder": "/Game/Blueprints/Variants",
            },
            "reason": "Create a safe variant of this Blueprint.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "duplicate_asset"
    assert body["operation"]["tool_id"] == "editor_duplicate_asset"
    payload = body["operation"]["operation_payload"]
    assert payload["source_asset_path"] == "/Game/Blueprints/BP_EnemySpawner"
    assert payload["source_asset_name"] == "BP_EnemySpawner"
    assert payload["new_name"] == "BP_EnemySpawner_Copy"
    assert payload["target_folder"] == "/Game/Blueprints/Variants"
    assert payload["target_path"] == "/Game/Blueprints/Variants/BP_EnemySpawner_Copy"
    assert payload["save_policy"] == "mark_dirty_only"
    assert body["item"]["confirmation"]["state"] == "pending"


def test_duplicate_asset_rejects_same_target(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "duplicate_asset",
            "payload": {
                "source_asset_path": "/Game/Blueprints/BP_EnemySpawner",
                "new_name": "BP_EnemySpawner",
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "duplicate_target_matches_source"


def test_fixup_redirectors_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "fixup_redirectors",
            "payload": {
                "folder_path": "/Game/Blueprints",
                "recursive": True,
                "max_redirectors": 25,
            },
            "reason": "Clean redirectors after asset moves.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "fixup_redirectors"
    assert body["operation"]["tool_id"] == "editor_fixup_redirectors"
    payload = body["operation"]["operation_payload"]
    assert payload["folder_path"] == "/Game/Blueprints"
    assert payload["recursive"] is True
    assert payload["max_redirectors"] == 25
    assert payload["save_policy"] == "editor_fixup_redirectors"
    assert body["operation"]["affected_targets"][0]["kind"] == "asset_folder"
    assert body["operation"]["expected_result_contract"]["operation_result_fields"] == [
        "folder_path",
        "recursive",
        "redirector_count",
        "fixed_redirectors",
        "dirty",
        "dirty_packages",
    ]
    assert body["item"]["confirmation"]["state"] == "pending"


def test_fixup_redirectors_rejects_game_root(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "fixup_redirectors",
            "payload": {"folder_path": "/Game"},
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "redirector_folder_too_broad"


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


def test_set_umg_widget_appearance_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "set_umg_widget_appearance",
            "payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "TitleText",
                "appearance": {
                    "render_opacity": 0.65,
                    "is_enabled": True,
                    "color_and_opacity": {"r": 0.1, "g": 0.8, "b": 0.3, "a": 1.0},
                    "font_size": 28,
                },
            },
            "reason": "Tune the HUD title appearance.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "set_umg_widget_appearance"
    assert body["operation"]["tool_id"] == "editor_set_umg_widget_appearance"
    payload = body["operation"]["operation_payload"]
    assert payload["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert payload["widget_name"] == "TitleText"
    assert payload["appearance"]["render_opacity"] == 0.65
    assert payload["appearance"]["is_enabled"] is True
    assert payload["appearance"]["color_and_opacity"]["g"] == 0.8
    assert payload["appearance"]["font_size"] == 28
    assert payload["save_policy"] == "mark_dirty_only"
    assert body["item"]["confirmation"]["state"] == "pending"


def test_set_umg_widget_appearance_rejects_empty_appearance(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "set_umg_widget_appearance",
            "payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "TitleText",
                "appearance": {},
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "appearance_requires_opacity_enabled_color_or_font_size"


def test_set_umg_widget_brush_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "set_umg_widget_brush",
            "payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "IconImage",
                "brush": {
                    "resource_type": "texture",
                    "resource_path": "/Game/Textures/T_Player_D",
                },
            },
            "reason": "Assign the HUD icon image.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "set_umg_widget_brush"
    assert body["operation"]["tool_id"] == "editor_set_umg_widget_brush"
    payload = body["operation"]["operation_payload"]
    assert payload["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert payload["widget_name"] == "IconImage"
    assert payload["brush"] == {"resource_type": "texture", "resource_path": "/Game/Textures/T_Player_D"}
    assert payload["save_policy"] == "mark_dirty_only"
    assert body["item"]["confirmation"]["state"] == "pending"


def test_set_umg_widget_brush_rejects_unknown_resource_type(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "set_umg_widget_brush",
            "payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "IconImage",
                "brush": {
                    "resource_type": "sound",
                    "resource_path": "/Game/Audio/S_UI_Click",
                },
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "brush_resource_type_not_supported"


def test_set_umg_slot_layout_v2_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "set_umg_slot_layout_v2",
            "payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "IconImage",
                "slot_type": "HorizontalBoxSlot",
                "layout": {
                    "padding": {"left": 8, "top": 4, "right": 8, "bottom": 4},
                    "horizontal_alignment": "center",
                    "vertical_alignment": "fill",
                    "size": {"rule": "fill", "value": 1},
                },
            },
            "reason": "Tune icon slot spacing in HUD.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "set_umg_slot_layout_v2"
    assert body["operation"]["tool_id"] == "editor_set_umg_slot_layout_v2"
    payload = body["operation"]["operation_payload"]
    assert payload["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert payload["widget_name"] == "IconImage"
    assert payload["slot_type"] == "HorizontalBoxSlot"
    assert payload["layout"]["padding"] == {"left": 8.0, "top": 4.0, "right": 8.0, "bottom": 4.0}
    assert payload["layout"]["horizontal_alignment"] == "center"
    assert payload["layout"]["vertical_alignment"] == "fill"
    assert payload["layout"]["size"] == {"rule": "fill", "value": 1.0}
    assert payload["save_policy"] == "mark_dirty_only"


def test_set_umg_slot_layout_v2_rejects_unknown_slot_type(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "set_umg_slot_layout_v2",
            "payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "IconImage",
                "slot_type": "GridSlot",
                "layout": {"padding": 8},
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "slot_type_not_supported"


def test_reparent_umg_widget_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "reparent_umg_widget",
            "payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "IconImage",
                "new_parent_name": "RootCanvas",
            },
            "reason": "Move the HUD icon under the root canvas.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "reparent_umg_widget"
    assert body["operation"]["tool_id"] == "editor_reparent_umg_widget"
    payload = body["operation"]["operation_payload"]
    assert payload["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert payload["widget_name"] == "IconImage"
    assert payload["new_parent_name"] == "RootCanvas"
    assert payload["save_policy"] == "mark_dirty_only"
    assert body["item"]["confirmation"]["state"] == "pending"
    assert body["operation"]["expected_result_contract"]["operation_result_fields"] == [
        "widget_blueprint_path",
        "widget_name",
        "old_parent_name",
        "new_parent_name",
        "dirty",
        "dirty_packages",
    ]


def test_reparent_umg_widget_rejects_same_parent_and_target(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "reparent_umg_widget",
            "payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "RootCanvas",
                "new_parent_name": "RootCanvas",
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "widget_parent_must_differ_from_target"


def test_duplicate_umg_widget_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "duplicate_umg_widget",
            "payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "IconImage",
                "new_widget_name": "IconImage_Copy",
            },
            "reason": "Create a second icon with the same style.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "duplicate_umg_widget"
    assert body["operation"]["tool_id"] == "editor_duplicate_umg_widget"
    payload = body["operation"]["operation_payload"]
    assert payload["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert payload["widget_name"] == "IconImage"
    assert payload["source_widget_name"] == "IconImage"
    assert payload["new_widget_name"] == "IconImage_Copy"
    assert body["operation"]["affected_targets"][0]["new_widget_name"] == "IconImage_Copy"
    assert body["operation"]["expected_result_contract"]["operation_result_fields"] == [
        "widget_blueprint_path",
        "source_widget_name",
        "new_widget_name",
        "parent_widget_name",
        "dirty",
        "dirty_packages",
    ]
    assert body["item"]["confirmation"]["state"] == "pending"


def test_duplicate_umg_widget_rejects_same_name(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "duplicate_umg_widget",
            "payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "IconImage",
                "new_widget_name": "IconImage",
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "new_widget_name_must_differ_from_source"


def test_delete_umg_widget_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "delete_umg_widget",
            "payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "IconImage_Copy",
            },
            "reason": "Remove the duplicate icon after reviewing the HUD.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "delete_umg_widget"
    assert body["operation"]["tool_id"] == "editor_delete_umg_widget"
    payload = body["operation"]["operation_payload"]
    assert payload["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert payload["widget_name"] == "IconImage_Copy"
    assert body["operation"]["affected_targets"][0]["action"] == "delete_umg_widget"
    assert body["operation"]["expected_result_contract"]["operation_result_fields"] == [
        "widget_blueprint_path",
        "widget_name",
        "old_parent_name",
        "removed_widgets",
        "dirty",
        "dirty_packages",
    ]
    assert body["item"]["confirmation"]["state"] == "pending"


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


def test_set_actor_metadata_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "set_actor_metadata",
            "payload": {
                "actor_reference": "BP_EnemySpawner_1",
                "metadata": {
                    "actor_label": "EnemySpawn_A",
                    "folder_path": "Gameplay/Spawners",
                    "tags": ["Spawner", "Enemy"],
                    "tag_mode": "append",
                },
            },
            "reason": "Organize the selected level actor.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "set_actor_metadata"
    assert body["operation"]["tool_id"] == "editor_set_actor_metadata"
    payload = body["operation"]["operation_payload"]
    assert payload["actor_reference"] == "BP_EnemySpawner_1"
    assert payload["metadata"]["actor_label"] == "EnemySpawn_A"
    assert payload["metadata"]["folder_path"] == "Gameplay/Spawners"
    assert payload["metadata"]["tags"] == ["Spawner", "Enemy"]
    assert payload["metadata"]["tag_mode"] == "append"
    assert payload["save_policy"] == "mark_dirty_only"
    assert body["item"]["confirmation"]["state"] == "pending"


def test_set_actor_metadata_rejects_empty_metadata(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "set_actor_metadata",
            "payload": {
                "actor_reference": "BP_EnemySpawner_1",
                "metadata": {},
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "metadata_requires_actor_label_folder_path_or_tags"


def test_arrange_actors_pattern_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "arrange_actors_pattern",
            "payload": {
                "actor_references": ["BP_EnemySpawner_1", "BP_PatrolPoint_1", "BP_PatrolPoint_2"],
                "pattern": {
                    "type": "grid",
                    "spacing": 250,
                    "columns": 2,
                    "origin": {"x": 100, "y": 200, "z": 0},
                },
            },
            "reason": "Arrange patrol actors into a small grid.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "arrange_actors_pattern"
    assert body["operation"]["tool_id"] == "editor_arrange_actors_pattern"
    payload = body["operation"]["operation_payload"]
    assert payload["actor_references"] == ["BP_EnemySpawner_1", "BP_PatrolPoint_1", "BP_PatrolPoint_2"]
    assert payload["pattern"]["type"] == "grid"
    assert payload["pattern"]["spacing"] == 250.0
    assert payload["pattern"]["columns"] == 2
    assert payload["pattern"]["origin"] == {"x": 100.0, "y": 200.0, "z": 0.0}
    assert payload["item_count"] == 3
    assert payload["save_policy"] == "mark_dirty_only"


def test_arrange_actors_pattern_rejects_single_actor(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "arrange_actors_pattern",
            "payload": {
                "actor_references": ["BP_EnemySpawner_1"],
                "pattern": {"type": "line", "spacing": 200},
            },
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "actor_references_require_at_least_two"


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


def test_set_material_instance_static_switch_proposal_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "set_material_instance_static_switch",
            "payload": {
                "material_instance_path": "/Game/Materials/MI_Player",
                "parameter_name": "UseDetail",
                "value": True,
            },
            "reason": "Enable the detail layer for this material instance.",
            "requested_by": "integration_test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation"]["operation_type"] == "set_material_instance_static_switch"
    assert body["operation"]["tool_id"] == "editor_set_material_instance_static_switch"
    payload = body["operation"]["operation_payload"]
    assert payload["material_instance_path"] == "/Game/Materials/MI_Player"
    assert payload["parameter_name"] == "UseDetail"
    assert payload["value"] is True
    assert payload["save_policy"] == "mark_dirty_only"
    assert "value" in body["operation"]["expected_result_contract"]["operation_result_fields"]


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


def test_agent_chat_can_duplicate_selected_asset(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_duplicate_selected_asset_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Duplicate selected asset as BP_EnemySpawner_Copy",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
                "selected_assets": ["/Game/Blueprints/BP_EnemySpawner"],
            },
            "payload": {"user_query": "Duplicate selected asset as BP_EnemySpawner_Copy"},
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
    proposal = body["action_proposals"][0]
    assert proposal["dry_run_preview"]["operation_type"] == "duplicate_asset"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["source_asset_path"] == "/Game/Blueprints/BP_EnemySpawner"
    assert payload["new_name"] == "BP_EnemySpawner_Copy"
    assert payload["target_path"] == "/Game/Blueprints/BP_EnemySpawner_Copy"


def test_agent_chat_can_move_inventory_asset_to_folder(client: TestClient) -> None:
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
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_move_asset_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Move BP_EnemySpawner asset to /Game/Environment/Blueprints",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
            },
            "payload": {"user_query": "Move BP_EnemySpawner asset to /Game/Environment/Blueprints"},
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
    assert proposal["dry_run_preview"]["operation_type"] == "move_assets"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["asset_paths"] == ["/Game/Blueprints/BP_EnemySpawner"]
    assert payload["target_folder"] == "/Game/Environment/Blueprints"
    assert payload["moves"][0]["target_path"] == "/Game/Environment/Blueprints/BP_EnemySpawner"


def test_agent_chat_can_fixup_redirectors_for_folder(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_fixup_redirectors_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Fix redirectors in /Game/Blueprints",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
            },
            "payload": {"user_query": "Fix redirectors in /Game/Blueprints"},
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
    proposal = body["action_proposals"][0]
    assert proposal["dry_run_preview"]["operation_type"] == "fixup_redirectors"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["folder_path"] == "/Game/Blueprints"
    assert payload["recursive"] is True
    assert payload["max_redirectors"] == 50


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


def test_agent_chat_can_prepare_actor_metadata_operation_from_inventory(client: TestClient) -> None:
    inventory = client.post(
        "/api/v1/project-inventory/snapshot",
        json={
            "project_id": "DemoProject",
            "project_name": "DemoProject",
            "level_actors": [
                {
                    "actor_label": "BP_EnemySpawner_1",
                    "actor_name": "BP_EnemySpawner_C_1",
                    "actor_class": "BP_EnemySpawner_C",
                    "level_name": "TestMap",
                    "folder_path": "Gameplay",
                    "tags": ["Spawner"],
                }
            ],
        },
    )
    assert inventory.status_code == 200

    query = "Rename actor BP_EnemySpawner_1 label to EnemySpawn_A"
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_actor_metadata_session",
                "messages": [{"role": "user", "content": query, "language": "auto"}],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
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
    proposal = body["action_proposals"][0]
    assert proposal["dry_run_preview"]["operation_type"] == "set_actor_metadata"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["actor_reference"] == "BP_EnemySpawner_1"
    assert payload["metadata"]["actor_label"] == "EnemySpawn_A"


def test_agent_chat_can_prepare_arrange_actors_pattern_from_inventory(client: TestClient) -> None:
    inventory = client.post(
        "/api/v1/project-inventory/snapshot",
        json={
            "project_id": "DemoProject",
            "project_name": "DemoProject",
            "level_actors": [
                {
                    "actor_label": "BP_EnemySpawner_1",
                    "actor_name": "BP_EnemySpawner_C_1",
                    "actor_class": "BP_EnemySpawner_C",
                    "level_name": "TestMap",
                },
                {
                    "actor_label": "BP_PatrolPoint_1",
                    "actor_name": "BP_PatrolPoint_C_1",
                    "actor_class": "BP_PatrolPoint_C",
                    "level_name": "TestMap",
                },
            ],
        },
    )
    assert inventory.status_code == 200

    query = "Arrange actors BP_EnemySpawner_1 and BP_PatrolPoint_1 in a line spacing 250"
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_arrange_actors_session",
                "messages": [{"role": "user", "content": query, "language": "auto"}],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
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
    proposal = body["action_proposals"][0]
    assert proposal["dry_run_preview"]["operation_type"] == "arrange_actors_pattern"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["actor_references"] == ["BP_EnemySpawner_1", "BP_PatrolPoint_1"]
    assert payload["pattern"]["type"] == "line"
    assert payload["pattern"]["spacing"] == 250.0


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


def test_agent_chat_defaults_eventgraph_print_string_to_beginplay(client: TestClient) -> None:
    query = "Add a Print String node to BP_TestActor EventGraph"
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_blueprint_print_eventgraph_default_beginplay_session",
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
    assert payload["blueprint_path"] == "/Game/Blueprints/BP_TestActor"
    assert payload["template_id"] == "print_string"
    assert payload["graph_name"] == "EventGraph"
    assert payload["entry_event"] == "BeginPlay"
    graph_policy = body["action_proposals"][0]["dry_run_preview"]["blueprint_graph_policy"]
    assert graph_policy["schema_version"] == "blueprint_graph_policy_v1"
    assert graph_policy["expected_behavior"]["connects_exec_pins"] is True
    assert graph_policy["warnings"] == []


def test_agent_chat_builds_overlap_print_string_template(client: TestClient) -> None:
    query = "Add a Print String node to BP_TestActor when ActorBeginOverlap happens"
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_blueprint_print_overlap_session",
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
    assert payload["blueprint_path"] == "/Game/Blueprints/BP_TestActor"
    assert payload["template_id"] == "print_string"
    assert payload["graph_name"] == "EventGraph"
    assert payload["entry_event"] == "ActorBeginOverlap"
    assert payload["message"] == "ActorBeginOverlap from UEAgent"


def test_agent_chat_keeps_unconnected_eventgraph_print_string_unlinked(client: TestClient) -> None:
    query = "Add an unconnected Print String node to BP_TestActor EventGraph"
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_blueprint_print_eventgraph_unconnected_session",
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
    assert payload["graph_name"] == "EventGraph"
    assert payload["entry_event"] == ""


def test_agent_chat_routes_chinese_print_string_action_to_editor_operation_from_inventory(
    client: TestClient,
) -> None:
    _seed_named_blueprint_inventory(client)
    query = "帮我给BP_ProjectSpecificName的Begin play加上print string"
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_chinese_bp_specific_name_print_session",
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
                "preferred_output_language": "zh-CN",
                "return_debug_projection": True,
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["task"]["status"] == "waiting_confirmation"
    assert body["planner_diagnostics"]["selected_tool_id"] == "editor_add_blueprint_node_template"
    proposal = body["action_proposals"][0]
    assert proposal["dry_run_preview"]["operation_type"] == "add_blueprint_node_template"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["blueprint_path"] == "/Game/Blueprints/BP_ProjectSpecificName"
    assert payload["template_id"] == "print_string"
    assert payload["entry_event"] == "BeginPlay"


def test_agent_chat_english_print_string_does_not_match_actor_metadata_when_bp_name_contains_name(
    client: TestClient,
) -> None:
    _seed_named_blueprint_inventory(client)
    query = "Add a Print String node to BP_ProjectSpecificName EventGraph"
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_english_bp_specific_name_print_session",
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

    assert response.status_code == 200
    body = response.json()
    assert body["task"]["status"] == "waiting_confirmation"
    proposal = body["action_proposals"][0]
    assert proposal["dry_run_preview"]["operation_type"] == "add_blueprint_node_template"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["blueprint_path"] == "/Game/Blueprints/BP_ProjectSpecificName"
    assert payload["template_id"] == "print_string"
    assert payload["graph_name"] == "EventGraph"
    assert payload["entry_event"] == "BeginPlay"


def test_agent_chat_unconnected_print_string_from_inventory_keeps_node_unlinked(
    client: TestClient,
) -> None:
    _seed_named_blueprint_inventory(client)
    query = "Add an unconnected Print String node to BP_ProjectSpecificName EventGraph"
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_inventory_unconnected_bp_specific_name_print_session",
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

    assert response.status_code == 200
    body = response.json()
    assert body["task"]["status"] == "waiting_confirmation"
    payload = body["action_proposals"][0]["dry_run_preview"]["operation_payload"]
    assert payload["blueprint_path"] == "/Game/Blueprints/BP_ProjectSpecificName"
    assert payload["template_id"] == "print_string"
    assert payload["entry_event"] == ""


def test_agent_chat_builds_delay_print_string_template(client: TestClient) -> None:
    query = "给 BP_TestActor 的 BeginPlay 延迟 2 秒后添加 Print String 节点"
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_blueprint_delay_print_session",
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
    payload = body["action_proposals"][0]["dry_run_preview"]["operation_payload"]
    assert payload["blueprint_path"] == "/Game/Blueprints/BP_TestActor"
    assert payload["template_id"] == "delay_print_string"
    assert payload["entry_event"] == "BeginPlay"
    assert payload["delay_seconds"] == 2.0


def test_agent_chat_builds_enhanced_input_print_string_template(client: TestClient) -> None:
    query = "Add Enhanced Input Action IA_Jump to BP_TestActor and connect Triggered to Print String"
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_blueprint_enhanced_input_print_session",
                "messages": [{"role": "user", "content": query, "language": "auto"}],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
                "selected_assets": ["/Game/Blueprints/BP_TestActor", "/Game/Input/IA_Jump"],
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
    assert payload["blueprint_path"] == "/Game/Blueprints/BP_TestActor"
    assert payload["template_id"] == "enhanced_input_print_string"
    assert payload["input_action_path"] == "/Game/Input/IA_Jump"
    assert payload["message"] == "IA_Jump triggered"


def test_agent_chat_builds_custom_event_print_string_template(client: TestClient) -> None:
    query = "Add custom event OnAgentTriggered to BP_TestActor and connect it to Print String"
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_blueprint_custom_event_print_session",
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
    assert payload["blueprint_path"] == "/Game/Blueprints/BP_TestActor"
    assert payload["template_id"] == "custom_event_print_string"
    assert payload["custom_event_name"] == "OnAgentTriggered"
    assert payload["message"] == "OnAgentTriggered from UEAgent"


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
    graph_policy = body["action_proposals"][0]["dry_run_preview"]["blueprint_graph_policy"]
    assert graph_policy["graph_name"] == "ConstructionScript"
    assert graph_policy["entry_event"] == ""
    assert graph_policy["expected_behavior"]["connects_exec_pins"] is False


def test_agent_chat_uses_active_graph_for_single_blueprint_template(
    client: TestClient,
) -> None:
    query = 'Add "Ready" Print String node to the current Blueprint'
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_blueprint_print_active_graph_session",
                "messages": [{"role": "user", "content": query, "language": "auto"}],
            },
            "context": {
                "project_name": "DemoProject",
                "project_root": "D:/DemoProject",
                "active_panel": "AgentChat",
                "selected_assets": ["/Game/Blueprints/BP_TestActor"],
                "editor_state": {
                    "current_blueprint_path": "/Game/Blueprints/BP_TestActor",
                    "current_graph_name": "ConstructionScript",
                },
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
    assert payload["blueprint_path"] == "/Game/Blueprints/BP_TestActor"
    assert payload["template_id"] == "print_string"
    assert payload["graph_name"] == "ConstructionScript"
    assert payload["entry_event"] == ""
    assert body["action_proposals"][0]["dry_run_preview"]["blueprint_graph_policy"]["warnings"] == []


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


def test_agent_chat_can_move_named_inventory_actor_without_actor_keyword(client: TestClient) -> None:
    snapshot = client.post(
        "/api/v1/project-inventory/snapshot",
        json={
            "project_id": "DemoProject",
            "project_name": "DemoProject",
            "level_actors": [
                {
                    "actor_label": "BP_EnemySpawner_1",
                    "actor_name": "BP_EnemySpawner_C_1",
                    "actor_class": "BP_EnemySpawner_C",
                    "level_name": "TestMap",
                }
            ],
        },
    )
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_named_actor_transform_inventory_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Move BP_EnemySpawner_1 right 200",
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
            "payload": {"user_query": "Move BP_EnemySpawner_1 right 200"},
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
    assert proposal["dry_run_preview"]["operation_type"] == "set_actor_transform"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["actor_reference"] == "BP_EnemySpawner_1"
    assert payload["transform_mode"] == "delta"
    assert payload["transform_delta"]["location"] == {"x": 0.0, "y": 200.0, "z": 0.0}


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


def test_agent_chat_resolves_add_umg_widget_from_project_inventory(client: TestClient) -> None:
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
                "session_id": "chat_add_umg_widget_inventory_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Add TextBlock TitleText to WBP_MainHUD under RootCanvas with text 'Mission Ready'",
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
                "user_query": "Add TextBlock TitleText to WBP_MainHUD under RootCanvas with text 'Mission Ready'"
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
    proposal = body["action_proposals"][0]
    assert proposal["dry_run_preview"]["operation_type"] == "add_umg_widget"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert payload["widget_name"] == "TitleText"
    assert payload["widget_class"] == "/Script/UMG.TextBlock"
    assert payload["parent_widget_name"] == "RootCanvas"
    assert payload["text"] == "Mission Ready"
    assert payload["is_variable"] is True


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


def test_agent_chat_resolves_umg_appearance_from_project_inventory(client: TestClient) -> None:
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
                "session_id": "chat_umg_appearance_inventory_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Set WBP_MainHUD TitleText opacity to 0.5",
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
            "payload": {"user_query": "Set WBP_MainHUD TitleText opacity to 0.5"},
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
    assert proposal["dry_run_preview"]["operation_type"] == "set_umg_widget_appearance"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert payload["widget_name"] == "TitleText"
    assert payload["appearance"]["render_opacity"] == 0.5


def test_agent_chat_resolves_umg_brush_from_project_inventory(client: TestClient) -> None:
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
                "session_id": "chat_umg_brush_inventory_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Set WBP_MainHUD IconImage brush texture to T_Player_D",
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
            "payload": {"user_query": "Set WBP_MainHUD IconImage brush texture to T_Player_D"},
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
    assert proposal["dry_run_preview"]["operation_type"] == "set_umg_widget_brush"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert payload["widget_name"] == "IconImage"
    assert payload["brush"] == {"resource_type": "texture", "resource_path": "/Game/Textures/T_Player_D"}


def test_agent_chat_resolves_umg_slot_layout_v2_from_project_inventory(client: TestClient) -> None:
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
                "session_id": "chat_umg_slot_layout_inventory_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Set WBP_MainHUD IconImage HorizontalBoxSlot padding to 8 4 8 4 and horizontal alignment to center",
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
                "user_query": "Set WBP_MainHUD IconImage HorizontalBoxSlot padding to 8 4 8 4 and horizontal alignment to center"
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
    proposal = body["action_proposals"][0]
    assert proposal["dry_run_preview"]["operation_type"] == "set_umg_slot_layout_v2"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert payload["widget_name"] == "IconImage"
    assert payload["slot_type"] == "HorizontalBoxSlot"
    assert payload["layout"]["padding"] == {"left": 8.0, "top": 4.0, "right": 8.0, "bottom": 4.0}
    assert payload["layout"]["horizontal_alignment"] == "center"


def test_agent_chat_resolves_umg_reparent_from_project_inventory(client: TestClient) -> None:
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
                "session_id": "chat_umg_reparent_inventory_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Move WBP_MainHUD IconImage widget under RootCanvas",
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
            "payload": {"user_query": "Move WBP_MainHUD IconImage widget under RootCanvas"},
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
    assert proposal["dry_run_preview"]["operation_type"] == "reparent_umg_widget"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert payload["widget_name"] == "IconImage"
    assert payload["new_parent_name"] == "RootCanvas"


def test_agent_chat_resolves_umg_duplicate_from_project_inventory(client: TestClient) -> None:
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
                "session_id": "chat_umg_duplicate_inventory_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Duplicate WBP_MainHUD IconImage widget as IconImage_Copy",
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
            "payload": {"user_query": "Duplicate WBP_MainHUD IconImage widget as IconImage_Copy"},
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
    assert proposal["dry_run_preview"]["operation_type"] == "duplicate_umg_widget"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert payload["widget_name"] == "IconImage"
    assert payload["new_widget_name"] == "IconImage_Copy"


def test_agent_chat_resolves_umg_delete_from_project_inventory(client: TestClient) -> None:
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
                "session_id": "chat_umg_delete_inventory_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Remove WBP_MainHUD IconImage widget",
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
            "payload": {"user_query": "Remove WBP_MainHUD IconImage widget"},
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
    assert proposal["dry_run_preview"]["operation_type"] == "delete_umg_widget"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert payload["widget_name"] == "IconImage"


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


def test_agent_chat_can_set_current_material_instance_parameter_from_active_context(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_current_material_parameter_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Set this material Roughness to 0.42",
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
                "user_query": "Set this material Roughness to 0.42",
                "selected_material_instances": [{"material_instance_path": "/Game/Materials/MI_Player"}],
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

    assert response.status_code == 200
    body = response.json()
    assert body["task"]["status"] == "waiting_confirmation"
    proposal = body["action_proposals"][0]
    assert proposal["dry_run_preview"]["operation_type"] == "set_material_instance_parameter"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["material_instance_path"] == "/Game/Materials/MI_Player"
    assert payload["parameter_name"] == "Roughness"
    assert payload["parameter_type"] == "scalar"
    assert payload["value"] == 0.42
    assert body["debug_view"]["active_context"]["material"]["current_material_instance_path"] == "/Game/Materials/MI_Player"


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


def test_agent_chat_resolves_material_vector_hex_from_project_inventory(client: TestClient) -> None:
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
                "session_id": "chat_material_vector_hex_inventory_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Set MI_Player material BaseColor to #FF8040",
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
            "payload": {"user_query": "Set MI_Player material BaseColor to #FF8040"},
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
    assert proposal["dry_run_preview"]["operation_type"] == "set_material_instance_parameter"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["material_instance_path"] == "/Game/Materials/MI_Player"
    assert payload["parameter_name"] == "BaseColor"
    assert payload["parameter_type"] == "vector"
    assert payload["value"]["r"] == 1.0
    assert payload["value"]["g"] == pytest.approx(128 / 255)
    assert payload["value"]["b"] == pytest.approx(64 / 255)
    assert payload["value"]["a"] == 1.0


def test_agent_chat_resolves_material_static_switch_from_project_inventory(client: TestClient) -> None:
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
                "session_id": "chat_material_static_switch_inventory_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Enable MI_Player material UseDetail static switch",
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
            "payload": {"user_query": "Enable MI_Player material UseDetail static switch"},
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
    assert proposal["dry_run_preview"]["operation_type"] == "set_material_instance_static_switch"
    payload = proposal["dry_run_preview"]["operation_payload"]
    assert payload["material_instance_path"] == "/Game/Materials/MI_Player"
    assert payload["parameter_name"] == "UseDetail"
    assert payload["value"] is True


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


def test_editor_workflow_plan_api_returns_proposal_steps(client: TestClient) -> None:
    response = client.post(
        "/api/v1/editor-operations/workflows/plan",
        json={
            "goal": "Create HUD status text and place it",
            "workflow_type": "umg_text_widget",
            "payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "StatusText",
                "text": "Ready",
                "layout": {"position": {"x": 32, "y": 48}},
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    plan = body["workflow_plan"]
    assert plan["schema_version"] == "editor_workflow_plan_v1"
    assert plan["status"] == "planned"
    assert plan["auto_execute"] is False
    assert plan["requires_user_confirmation_per_step"] is True
    assert [step["operation_type"] for step in plan["steps"]] == [
        "add_umg_widget",
        "set_umg_widget_text",
        "set_umg_widget_layout",
    ]
    assert all(
        step["create_request_hint"]["path"] == "/api/v1/editor-operations/proposals"
        for step in plan["steps"]
    )


def test_editor_workflow_step_can_materialize_pending_proposal(client: TestClient) -> None:
    plan_response = client.post(
        "/api/v1/editor-operations/workflows/plan",
        json={
            "goal": "Add Ready Print String and compile",
            "workflow_type": "blueprint_print_then_compile",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "message": "Ready",
            },
        },
    )
    assert plan_response.status_code == 200
    plan = plan_response.json()["workflow_plan"]

    response = client.post(
        "/api/v1/editor-operations/workflows/steps/proposal",
        json={
            "workflow_plan_id": plan["plan_id"],
            "step": plan["steps"][0],
            "requested_by": "integration_test",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["workflow_step"]["schema_version"] == "editor_workflow_step_materialization_v1"
    assert body["workflow_step"]["operation_type"] == "add_blueprint_node_template"
    assert body["workflow_step"]["auto_execute"] is False
    assert body["proposal"]["item"]["confirmation"]["state"] == "pending"
    assert body["proposal"]["operation"]["operation_type"] == "add_blueprint_node_template"
    assert (
        body["proposal"]["operation"]["context"]["workflow_materialization"]["workflow_plan_id"]
        == plan["plan_id"]
    )


def test_editor_workflow_step_rejects_unmet_dependencies(client: TestClient) -> None:
    plan_response = client.post(
        "/api/v1/editor-operations/workflows/plan",
        json={
            "goal": "Add Ready Print String and compile",
            "workflow_type": "blueprint_print_then_compile",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "message": "Ready",
            },
        },
    )
    assert plan_response.status_code == 200
    plan = plan_response.json()["workflow_plan"]

    response = client.post(
        "/api/v1/editor-operations/workflows/steps/proposal",
        json={
            "workflow_plan_id": plan["plan_id"],
            "step": plan["steps"][1],
            "requested_by": "integration_test",
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "workflow_step_dependencies_not_satisfied"
    assert body["errors"][0]["details"]["depends_on_step_ids"] == ["step_0_add_blueprint_node_template"]


def test_editor_workflow_step_allows_completed_dependencies(client: TestClient) -> None:
    plan_response = client.post(
        "/api/v1/editor-operations/workflows/plan",
        json={
            "goal": "Add Ready Print String and compile",
            "workflow_type": "blueprint_print_then_compile",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "message": "Ready",
            },
        },
    )
    assert plan_response.status_code == 200
    plan = plan_response.json()["workflow_plan"]

    response = client.post(
        "/api/v1/editor-operations/workflows/steps/proposal",
        json={
            "workflow_plan_id": plan["plan_id"],
            "step": plan["steps"][1],
            "requested_by": "integration_test",
            "context": {"completed_step_ids": ["step_0_add_blueprint_node_template"]},
        },
    )

    assert response.status_code == 200
    body = response.json()
    workflow_context = body["proposal"]["operation"]["context"]["workflow_materialization"]
    assert body["workflow_step"]["operation_type"] == "compile_blueprint"
    assert workflow_context["depends_on_step_ids"] == ["step_0_add_blueprint_node_template"]
    assert workflow_context["completed_step_ids"] == ["step_0_add_blueprint_node_template"]


def test_editor_workflow_state_projects_next_ready_step_from_results(client: TestClient) -> None:
    plan_response = client.post(
        "/api/v1/editor-operations/workflows/plan",
        json={
            "goal": "Add Ready Print String and compile",
            "workflow_type": "blueprint_print_then_compile",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "message": "Ready",
            },
        },
    )
    assert plan_response.status_code == 200
    plan = plan_response.json()["workflow_plan"]

    initial_state = client.post("/api/v1/editor-operations/workflows/state", json={"workflow_plan": plan})
    assert initial_state.status_code == 200
    initial = initial_state.json()["workflow_state"]
    assert initial["status"] == "ready_for_next_step"
    assert initial["next_ready_step_ids"] == ["step_0_add_blueprint_node_template"]
    assert initial["step_states"][1]["status"] == "waiting_dependency"

    materialized = client.post(
        "/api/v1/editor-operations/workflows/steps/proposal",
        json={
            "workflow_plan_id": plan["plan_id"],
            "step": plan["steps"][0],
            "requested_by": "integration_test",
        },
    )
    assert materialized.status_code == 200
    proposal_id = materialized.json()["proposal"]["item"]["proposal_id"]

    pending_state = client.post("/api/v1/editor-operations/workflows/state", json={"workflow_plan": plan})
    assert pending_state.status_code == 200
    pending = pending_state.json()["workflow_state"]
    assert pending["status"] == "waiting_for_execution"
    assert pending["step_states"][0]["status"] == "pending_confirmation"
    assert pending["next_ready_step_ids"] == []

    assert client.post(f"/api/v1/editor-operations/proposals/{proposal_id}/confirm").status_code == 200
    result = client.post(
        "/api/v1/editor-operations/results",
        json={
            "proposal_id": proposal_id,
            "operation_type": "add_blueprint_node_template",
            "execution_state": "completed",
            "success": True,
            "executed_by": "ue_plugin",
            "transaction_id": f"ue_transaction_{proposal_id}",
            "result": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "graph_name": "EventGraph",
                "created_nodes": [{"node_id": "PrintStringNode", "node_title": "Print String"}],
                "linked_pins": [{"source_pin": "then", "target_pin": "execute"}],
                "compile_status": "not_requested",
                "dirty": True,
            },
        },
    )
    assert result.status_code == 200

    completed_state = client.post("/api/v1/editor-operations/workflows/state", json={"workflow_plan": plan})
    assert completed_state.status_code == 200
    completed = completed_state.json()["workflow_state"]
    assert completed["status"] == "ready_for_next_step"
    assert completed["completed_step_ids"] == ["step_0_add_blueprint_node_template"]
    assert completed["next_ready_step_ids"] == ["step_1_compile_blueprint"]
    assert completed["next_step_proposal_requests"][0]["workflow_step_id"] == "step_1_compile_blueprint"
    assert completed["next_step_proposal_requests"][0]["endpoint"] == (
        "/api/v1/editor-operations/workflows/steps/proposal"
    )
    assert completed["next_step_proposal_requests"][0]["request"]["context"]["completed_step_ids"] == [
        "step_0_add_blueprint_node_template"
    ]
    assert completed["step_states"][0]["status"] == "completed"
    assert completed["step_states"][1]["status"] == "ready_for_proposal"

    compile_proposal = client.post(
        "/api/v1/editor-operations/workflows/steps/proposal",
        json=completed["next_step_proposal_requests"][0]["request"],
    )
    assert compile_proposal.status_code == 200
    assert compile_proposal.json()["workflow_step"]["operation_type"] == "compile_blueprint"


def test_editor_workflow_step_materialization_rejects_not_ready_step(client: TestClient) -> None:
    plan_response = client.post(
        "/api/v1/editor-operations/workflows/plan",
        json={
            "goal": "Create HUD title text",
            "workflow_type": "umg_text_widget",
            "payload": {"widget_name": "TitleText"},
        },
    )
    assert plan_response.status_code == 200
    plan = plan_response.json()["workflow_plan"]

    response = client.post(
        "/api/v1/editor-operations/workflows/steps/proposal",
        json={"workflow_plan_id": plan["plan_id"], "step": plan["steps"][0]},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["errors"][0]["code"] == "workflow_step_not_ready_for_proposal"


def test_editor_workflow_templates_api_lists_supported_plan_only_templates(client: TestClient) -> None:
    response = client.get("/api/v1/editor-operations/workflows/templates")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    templates = body["workflow_templates"]
    assert templates["schema_version"] == "editor_workflow_templates_v1"
    assert templates["auto_execute"] is False
    assert templates["safety_policy"]["planner_executes_editor_writes"] is False
    workflow_types = {item["workflow_type"] for item in templates["templates"]}
    assert "blueprint_print_then_compile" in workflow_types
    assert "blueprint_connect_then_compile" in workflow_types
    assert "umg_text_widget" in workflow_types
    assert "arrange_and_tag_actors" in workflow_types


def test_agent_chat_can_return_plan_only_editor_workflow(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_editor_workflow_plan",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Plan a workflow: add a Print String node to "
                            "/Game/Blueprints/BP_PlayerCharacter then compile it"
                        ),
                    }
                ],
            },
            "payload": {
                "user_query": (
                    "Plan a workflow: add a Print String node to "
                    "/Game/Blueprints/BP_PlayerCharacter then compile it"
                ),
                "message": "Ready",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["task"]["status"] == "completed"
    assert body["action_proposals"] == []
    plan = body["data"]["editor_workflow_plan"]
    assert plan["schema_version"] == "editor_workflow_plan_v1"
    assert plan["workflow_type"] == "blueprint_print_then_compile"
    assert plan["auto_execute"] is False
    assert [step["operation_type"] for step in plan["steps"]] == [
        "add_blueprint_node_template",
        "compile_blueprint",
    ]
    assert body["user_view"]["blocks"][0]["block_type"] == "editor_workflow_plan"
    assert body["user_view"]["quick_actions"]
    assert len(body["user_view"]["quick_actions"]) == 1
    first_action = body["user_view"]["quick_actions"][0]
    assert first_action["payload"]["action_type"] == "create_workflow_step_proposal"
    assert first_action["payload"]["endpoint"] == "/api/v1/editor-operations/workflows/steps/proposal"
    assert first_action["payload"]["safety"]["auto_execute"] is False
    assert first_action["payload"]["safety"]["creates_pending_proposal_only"] is True
    assert first_action["payload"]["request"]["workflow_plan_id"] == plan["plan_id"]
    assert first_action["payload"]["request"]["step"]["step_id"] == plan["steps"][0]["step_id"]
    assert body["debug_view"]["step_results"][0]["status"] == "ready"
    assert body["debug_view"]["step_results"][1]["status"] == "waiting_dependency"
    assert body["debug_view"]["workflow_trace"]["dependency_graph"]["ready_step_ids"] == [
        "step_0_add_blueprint_node_template"
    ]
    assert body["debug_view"]["workflow_trace"]["dependency_graph"]["waiting_step_ids"] == [
        "step_1_compile_blueprint"
    ]
    assert any(block["block_type"] == "workflow_ready_actions" for block in body["user_view"]["blocks"])


def test_agent_chat_workflow_uses_active_blueprint_focus_when_path_omitted(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_editor_workflow_active_focus",
                "messages": [
                    {
                        "role": "user",
                        "content": 'Plan a workflow: add "Ready" Print String then compile it',
                    }
                ],
            },
            "context": {
                "project_name": "RushBa",
                "active_panel": "AgentChat",
                "selected_assets": ["/Game/Blueprints/BP_FocusedActor.BP_FocusedActor"],
                "editor_state": {
                    "current_blueprint_path": "/Game/Blueprints/BP_FocusedActor.BP_FocusedActor",
                    "current_graph_name": "ConstructionScript",
                },
            },
            "payload": {
                "user_query": 'Plan a workflow: add "Ready" Print String then compile it',
            },
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    plan = body["data"]["editor_workflow_plan"]
    first, second = plan["steps"]
    assert plan["status"] == "planned"
    assert first["payload"]["blueprint_path"] == "/Game/Blueprints/BP_FocusedActor"
    assert first["payload"]["graph_name"] == "ConstructionScript"
    assert first["payload"]["entry_event"] == ""
    assert second["payload"]["blueprint_path"] == "/Game/Blueprints/BP_FocusedActor"
    assert body["debug_view"]["active_context"]["blueprint"]["current_graph_name"] == "ConstructionScript"


def test_agent_chat_workflow_can_connect_current_node_then_compile(client: TestClient) -> None:
    snapshot = client.post(
        "/api/v1/project-inventory/snapshot",
        json={
            "project_id": "WorkflowFocusProject",
            "project_name": "WorkflowFocusProject",
            "assets": [
                {
                    "asset_path": "/Game/Blueprints/BP_FocusedActor",
                    "asset_name": "BP_FocusedActor",
                    "asset_type": "Blueprint",
                    "blueprint": {
                        "parent_class": "AActor",
                        "graphs": ["EventGraph"],
                        "graph_summaries": [
                            {
                                "graph_name": "EventGraph",
                                "graph_type": "event",
                                "node_count": 2,
                                "pin_count": 4,
                                "link_count": 0,
                                "nodes": [
                                    {
                                        "node_id": "event-begin-play",
                                        "node_name": "K2Node_Event_0",
                                        "node_class": "K2Node_Event",
                                        "title": "Event BeginPlay",
                                        "pins": [
                                            {
                                                "pin_name": "then",
                                                "direction": "output",
                                                "category": "exec",
                                            }
                                        ],
                                    },
                                    {
                                        "node_id": "print-string",
                                        "node_name": "K2Node_CallFunction_0",
                                        "node_class": "K2Node_CallFunction",
                                        "title": "Print String",
                                        "pins": [
                                            {
                                                "pin_name": "execute",
                                                "direction": "input",
                                                "category": "exec",
                                            }
                                        ],
                                    },
                                ],
                            }
                        ],
                    },
                }
            ],
        },
    )
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_editor_workflow_connect_focus",
                "messages": [
                    {
                        "role": "user",
                        "content": "Plan a workflow: connect the current node to Print String then compile",
                    }
                ],
            },
            "context": {
                "project_name": "WorkflowFocusProject",
                "active_panel": "AgentChat",
                "editor_state": {
                    "current_blueprint_path": "/Game/Blueprints/BP_FocusedActor.BP_FocusedActor",
                    "current_graph_name": "EventGraph",
                    "selected_node_id": "event-begin-play",
                },
            },
            "payload": {
                "user_query": "Plan a workflow: connect the current node to Print String then compile",
                "target_node_name": "Print String",
            },
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )

    assert snapshot.status_code == 200
    assert response.status_code == 200
    body = response.json()
    plan = body["data"]["editor_workflow_plan"]
    first, second = plan["steps"]
    assert body["action_proposals"] == []
    assert plan["workflow_type"] == "blueprint_connect_then_compile"
    assert plan["status"] == "planned"
    assert first["operation_type"] == "connect_blueprint_nodes"
    assert first["payload"]["blueprint_path"] == "/Game/Blueprints/BP_FocusedActor"
    assert first["payload"]["graph_name"] == "EventGraph"
    assert first["payload"]["source_node_id"] == "event-begin-play"
    assert first["payload"]["source_pin_name"] == "then"
    assert first["payload"]["target_node_id"] == "print-string"
    assert first["payload"]["target_pin_name"] == "execute"
    assert second["operation_type"] == "compile_blueprint"
    assert second["depends_on_step_ids"] == ["step_0_connect_blueprint_nodes"]
    assert body["debug_view"]["active_context"]["blueprint"]["current_node_summary"]["node_id"] == "event-begin-play"


def test_agent_chat_workflow_can_plan_enhanced_input_then_compile(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_editor_workflow_enhanced_input",
                "messages": [
                    {
                        "role": "user",
                        "content": "Plan a workflow: add Enhanced Input IA_Jump to BP_Player then compile",
                    }
                ],
            },
            "context": {
                "project_name": "WorkflowInputProject",
                "active_panel": "AgentChat",
                "selected_assets": ["/Game/Blueprints/BP_Player", "/Game/Input/IA_Jump"],
            },
            "payload": {
                "user_query": "Plan a workflow: add Enhanced Input IA_Jump to BP_Player then compile",
                "input_action_path": "/Game/Input/IA_Jump",
            },
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    plan = body["data"]["editor_workflow_plan"]
    first, second = plan["steps"]
    assert body["action_proposals"] == []
    assert plan["workflow_type"] == "blueprint_enhanced_input_print_then_compile"
    assert plan["status"] == "planned"
    assert first["operation_type"] == "add_blueprint_node_template"
    assert first["payload"]["blueprint_path"] == "/Game/Blueprints/BP_Player"
    assert first["payload"]["template_id"] == "enhanced_input_print_string"
    assert first["payload"]["input_action_path"] == "/Game/Input/IA_Jump"
    assert first["payload"]["message"] == "IA_Jump triggered"
    assert second["operation_type"] == "compile_blueprint"
    assert second["depends_on_step_ids"] == ["step_0_add_blueprint_node_template"]
