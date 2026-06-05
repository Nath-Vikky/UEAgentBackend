from __future__ import annotations

import shutil
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.settings import get_settings
from app.db.session import get_engine, get_session_factory
from app.main import create_app


FIXTURE_SERVER = Path(__file__).resolve().parents[1] / "fixtures" / "weather_mcp_server.py"


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    runtime_root = Path(".test-runtime") / f"mcp-tools-{uuid.uuid4().hex}"
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
    monkeypatch.setenv("MCP_TOOL_ADAPTER_ENABLED", "true")
    monkeypatch.setenv("MCP_STDIO_COMMAND", sys.executable)
    monkeypatch.setenv("MCP_STDIO_ARGS", str(FIXTURE_SERVER))
    monkeypatch.setenv("MCP_ALLOWED_TOOLS", "get_weather")
    monkeypatch.setenv("MCP_STDIO_TIMEOUT_MS", "5000")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    shutil.rmtree(runtime_root, ignore_errors=True)


def test_mcp_tools_discovery_and_call_api(client: TestClient) -> None:
    tools_response = client.get("/api/v1/mcp/tools")

    assert tools_response.status_code == 200
    tools_body = tools_response.json()
    assert tools_body["success"] is True
    assert tools_body["tools"][0]["name"] == "get_weather"

    call_response = client.post(
        "/api/v1/mcp/tools/get_weather/call",
        json={"arguments": {"city": "Shanghai"}},
    )

    assert call_response.status_code == 200
    call_body = call_response.json()
    assert call_body["success"] is True
    assert call_body["result"]["content"][0]["text"] == "Shanghai: sunny, 24C"


def test_mcp_tools_api_blocks_unlisted_tool(client: TestClient) -> None:
    response = client.post(
        "/api/v1/mcp/tools/delete_weather_cache/call",
        json={"arguments": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["reason"] == "tool_not_in_mcp_allowed_tools"


def test_tool_registry_manifest_api_exposes_proposal_boundary(client: TestClient) -> None:
    response = client.get("/api/v1/mcp/tool-registry/manifest?side_effect_level=confirmed_write")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    manifest = body["manifest"]
    assert manifest["schema_version"] == "mcp_tools_list_compatible_v1"
    assert manifest["safety_policy"]["confirmed_write_direct_mcp_call_allowed"] is False
    tools = {
        item["annotations"]["tool_id"]: item
        for item in manifest["tools"]
    }
    assert "editor_arrange_actors_pattern" in tools
    boundary = tools["editor_arrange_actors_pattern"]["annotations"]["execution_boundary"]
    assert boundary["mode"] == "confirmed_write_proposal"
    assert boundary["direct_mcp_call_allowed"] is False
    assert boundary["write_path"] == "POST /api/v1/editor-operations/proposals"


def test_tool_registry_manifest_api_supports_demo_profiles(client: TestClient) -> None:
    response = client.get("/api/v1/mcp/tool-registry/manifest?profile=material_demo")

    assert response.status_code == 200
    body = response.json()
    manifest = body["manifest"]
    tool_ids = {item["annotations"]["tool_id"] for item in manifest["tools"]}
    assert manifest["filters"]["profile"] == "material_demo"
    assert manifest["profiles"]["selected"]["profile_id"] == "material_demo"
    assert manifest["profiles"]["selected"]["suggested_prompts"]
    assert manifest["profiles"]["selected"]["sample_tool_calls"][0]["tool_id"] == "editor_set_material_instance_parameter"
    assert "editor_inspect_material_instance_detail" in tool_ids
    assert "editor_set_material_instance_parameter" in tool_ids
    assert "editor_add_umg_widget" not in tool_ids


def test_tool_registry_proposal_prepare_api_maps_confirmed_write_tool(client: TestClient) -> None:
    response = client.post(
        "/api/v1/mcp/tool-registry/proposals/prepare",
        json={
            "tool_id": "editor_arrange_actors_pattern",
            "arguments": {
                "actor_references": ["BP_EnemySpawner_1", "BP_PatrolPoint_1", "BP_PatrolPoint_2"],
                "pattern": {"type": "grid", "spacing": 250, "columns": 2},
            },
            "reason": "Arrange patrol actors.",
            "requested_by": "integration_test",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    bridge = body["bridge"]
    assert bridge["status"] == "prepared"
    assert bridge["operation_type"] == "arrange_actors_pattern"
    assert bridge["auto_execute"] is False
    assert bridge["proposal_request_hint"]["path"] == "/api/v1/editor-operations/proposals"
    assert bridge["proposal_request"]["payload"]["pattern"]["type"] == "grid"


def test_tool_registry_proposal_api_creates_pending_editor_proposal(client: TestClient) -> None:
    response = client.post(
        "/api/v1/mcp/tool-registry/proposals",
        json={
            "tool_id": "editor_arrange_actors_pattern",
            "arguments": {
                "actor_references": ["BP_EnemySpawner_1", "BP_PatrolPoint_1", "BP_PatrolPoint_2"],
                "pattern": {"type": "grid", "spacing": 250, "columns": 2},
            },
            "requested_by": "integration_test",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["bridge"]["status"] == "prepared"
    proposal = body["proposal"]
    assert proposal["item"]["confirmation"]["state"] == "pending"
    assert proposal["operation"]["operation_type"] == "arrange_actors_pattern"
    assert proposal["operation"]["tool_id"] == "editor_arrange_actors_pattern"


def test_tool_registry_proposal_api_creates_blueprint_add_step_alias_proposal(client: TestClient) -> None:
    response = client.post(
        "/api/v1/mcp/tool-registry/proposals",
        json={
            "tool_id": "editor_blueprint_add_step",
            "arguments": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "step_name": "Print String",
                "graph_name": "EventGraph",
                "text": "Hello from MCP-style add_step",
                "entry_event": "BeginPlay",
            },
            "requested_by": "integration_test",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["bridge"]["tool_id"] == "editor_blueprint_add_step"
    proposal = body["proposal"]
    assert proposal["item"]["confirmation"]["state"] == "pending"
    assert proposal["operation"]["operation_type"] == "add_blueprint_node_template"
    assert proposal["operation"]["tool_id"] == "editor_add_blueprint_node_template"
    payload = proposal["operation"]["operation_payload"]
    assert payload["template_id"] == "print_string"
    assert payload["message"] == "Hello from MCP-style add_step"


def test_tool_registry_proposal_prepare_api_blocks_readonly_tool(client: TestClient) -> None:
    response = client.post(
        "/api/v1/mcp/tool-registry/proposals/prepare",
        json={
            "tool_id": "mcp_get_blueprint_graph",
            "arguments": {"blueprint_path": "/Game/BP_Test"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["bridge"]["status"] == "blocked"
    assert body["errors"][0]["code"] == "tool_is_not_confirmed_write"


def _save_demo_inventory_snapshot(client: TestClient) -> None:
    response = client.post(
        "/api/v1/project-inventory/snapshot",
        json={
            "project_id": "MCPDemoProject",
            "project_name": "MCPDemoProject",
            "assets": [
                {
                    "asset_path": "/Game/Blueprints/BP_PlayerCharacter.BP_PlayerCharacter",
                    "asset_name": "BP_PlayerCharacter",
                    "asset_type": "Blueprint",
                    "package_path": "/Game/Blueprints",
                    "blueprint": {
                        "parent_class": "ACharacter",
                        "components": ["CapsuleComponent", "FollowCamera"],
                        "variables": ["Health"],
                        "functions": ["SetupPlayerInputComponent"],
                        "graphs": ["EventGraph"],
                        "graph_summaries": [
                            {
                                "graph_name": "EventGraph",
                                "graph_type": "Ubergraph",
                                "node_count": 2,
                                "pin_count": 5,
                                "link_count": 1,
                                "nodes": [
                                    {"node_id": "EventBeginPlay", "title": "Event BeginPlay"},
                                    {"node_id": "PrintString_1", "title": "Print String"},
                                ],
                            }
                        ],
                    },
                },
                {
                    "asset_path": "/Game/UI/WBP_MainHUD.WBP_MainHUD",
                    "asset_name": "WBP_MainHUD",
                    "asset_type": "WidgetBlueprint",
                    "package_path": "/Game/UI",
                    "blueprint": {"parent_class": "UUserWidget"},
                    "properties": {
                        "widget_tree": {
                            "root": "RootCanvas",
                            "widgets": [
                                {"name": "RootCanvas", "class": "CanvasPanel"},
                                {"name": "TitleText", "class": "TextBlock", "parent": "RootCanvas"},
                            ],
                        }
                    },
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
    assert response.status_code == 200


def test_tool_registry_local_readonly_call_reads_blueprint_graph_inventory(client: TestClient) -> None:
    _save_demo_inventory_snapshot(client)

    response = client.post(
        "/api/v1/mcp/tool-registry/tools/get_blueprint_graph/call",
        json={
            "arguments": {
                "project_id": "MCPDemoProject",
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "graph_name": "EventGraph",
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    call = body["call"]
    assert call["transport"] == "local_tool_registry"
    assert call["tool_id"] == "mcp_get_blueprint_graph"
    structured = call["result"]["structuredContent"]
    assert structured["graph_schema_version"] == "inventory_blueprint_graph_snapshot_v2"
    assert structured["graph_metrics"]["graph_count"] == 1
    assert structured["graphs"][0]["graph_name"] == "EventGraph"
    assert structured["graphs"][0]["nodes"][0]["title"] == "Event BeginPlay"


def test_tool_registry_plan_call_sets_blueprint_edit_function_context(client: TestClient) -> None:
    _save_demo_inventory_snapshot(client)

    response = client.post(
        "/api/v1/mcp/tool-registry/plans/editor_blueprint_set_edit_function/call",
        json={
            "arguments": {
                "project_id": "MCPDemoProject",
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "graph_name": "EventGraph",
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    call = body["call"]
    assert call["side_effect_level"] == "plan_only"
    assert call["transport"] == "local_tool_registry"
    result = call["result"]
    assert result["plan"]["intent"] == "set_blueprint_edit_function"
    assert result["context_patch"]["blueprint_edit_context"]["graph_name"] == "EventGraph"
    assert result["context_patch"]["blueprint_edit_context"]["matched_inventory_graph"] is True
    assert result["next_tool_hints"][0]["tool_id"] == "editor_blueprint_add_step"


def test_tool_registry_plan_call_sets_blueprint_cursor_node_context(client: TestClient) -> None:
    _save_demo_inventory_snapshot(client)

    response = client.post(
        "/api/v1/mcp/tool-registry/plans/editor_blueprint_set_cursor_node/call",
        json={
            "arguments": {
                "project_id": "MCPDemoProject",
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "graph_name": "EventGraph",
                "node_title": "Event BeginPlay",
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    cursor = body["call"]["result"]["context_patch"]["blueprint_edit_context"]["cursor_node"]
    assert cursor["node_id"] == "EventBeginPlay"
    assert cursor["title"] == "Event BeginPlay"
    assert cursor["matched_inventory_node"] is True
    assert body["call"]["result"]["next_tool_hints"][0]["tool_id"] == "editor_connect_blueprint_nodes"


def test_tool_registry_plan_call_sets_umg_widget_blueprint_context(client: TestClient) -> None:
    _save_demo_inventory_snapshot(client)

    response = client.post(
        "/api/v1/mcp/tool-registry/plans/editor_umg_set_widget_blueprint_context/call",
        json={
            "arguments": {
                "project_id": "MCPDemoProject",
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    result = body["call"]["result"]
    context = result["context_patch"]["umg_edit_context"]
    assert result["plan"]["intent"] == "set_umg_widget_blueprint_context"
    assert context["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert context["root_widget_name"] == "RootCanvas"
    assert context["matched_inventory_widget_tree"] is True
    assert result["next_tool_hints"][0]["tool_id"] == "editor_add_umg_widget"


def test_tool_registry_plan_call_sets_umg_cursor_widget_context(client: TestClient) -> None:
    _save_demo_inventory_snapshot(client)

    response = client.post(
        "/api/v1/mcp/tool-registry/plans/editor_umg_set_cursor_widget/call",
        json={
            "arguments": {
                "project_id": "MCPDemoProject",
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "TitleText",
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    context = body["call"]["result"]["context_patch"]["umg_edit_context"]
    cursor = context["cursor_widget"]
    assert cursor["widget_name"] == "TitleText"
    assert cursor["widget_class"] == "TextBlock"
    assert cursor["parent_widget_name"] == "RootCanvas"
    assert cursor["matched_inventory_widget"] is True
    assert body["call"]["result"]["next_tool_hints"][0]["tool_id"] == "editor_set_umg_widget_text"


def test_tool_registry_local_readonly_call_reads_widget_actor_and_material_inventory(
    client: TestClient,
) -> None:
    _save_demo_inventory_snapshot(client)

    widget_response = client.post(
        "/api/v1/mcp/tool-registry/tools/get_widget_tree/call",
        json={
            "arguments": {
                "project_id": "MCPDemoProject",
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
            }
        },
    )
    actor_response = client.post(
        "/api/v1/mcp/tool-registry/tools/editor_inspect_level_actors/call",
        json={"arguments": {"project_id": "MCPDemoProject", "query": "EnemySpawner"}},
    )
    material_response = client.post(
        "/api/v1/mcp/tool-registry/tools/editor_inspect_material_instance_detail/call",
        json={"arguments": {"project_id": "MCPDemoProject", "material_instance_path": "MI_Rock"}},
    )

    assert widget_response.status_code == 200
    widget_body = widget_response.json()
    assert widget_body["success"] is True
    assert widget_body["call"]["result"]["structuredContent"]["widget_count"] == 2
    assert actor_response.status_code == 200
    assert actor_response.json()["call"]["result"]["items"][0]["actor_label"] == "BP_EnemySpawner_1"
    assert material_response.status_code == 200
    material_body = material_response.json()
    assert material_body["success"] is True
    assert material_body["call"]["result"]["item"]["scalar_parameters"][0]["name"] == "Roughness"


def test_tool_registry_local_readonly_call_blocks_write_tool(client: TestClient) -> None:
    response = client.post(
        "/api/v1/mcp/tool-registry/tools/editor_set_actor_transform/call",
        json={"arguments": {"actor_reference": "BP_EnemySpawner_1"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["call"]["reason"] == "tool_is_not_read_only"
    assert body["errors"][0]["code"] == "tool_is_not_read_only"


def test_tool_registry_plan_call_blocks_write_tool(client: TestClient) -> None:
    response = client.post(
        "/api/v1/mcp/tool-registry/plans/editor_blueprint_add_step/call",
        json={"arguments": {"blueprint_path": "/Game/BP_Test", "step_name": "Print String"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["call"]["reason"] == "tool_is_not_plan_only"
    assert body["errors"][0]["code"] == "tool_is_not_plan_only"
