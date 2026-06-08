from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.core.settings import Settings
from app.schemas.requests import UnifiedTaskRequest
from app.services.llm_service import ChatRuntimeConfig
from app.services.task_handlers.base import TaskExecutionContext
from app.services.task_handlers import read_only_tool_summaries


class _FakeMCPToolExecutor:
    def __init__(self, settings: Settings):
        self.settings = settings

    def call_readonly_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        if tool_name == "get_blueprint_graph":
            return {
                "ok": True,
                "status": "completed",
                "reason": "mcp_tool_call_completed",
                "tool_name": tool_name,
                "transport": "mcp_tcp",
                "result": {
                    "structuredContent": {
                        "blueprint_path": arguments["blueprint_path"],
                        "graphs": [
                            {
                                "graph_name": "EventGraph",
                                "graph_type": "Ubergraph",
                                "node_count": 2,
                                "link_count": 1,
                                "nodes": [
                                    {"node_id": "EventBeginPlay", "title": "Event BeginPlay"},
                                    {"node_id": "PrintString_1", "title": "Print String"},
                                ],
                            }
                        ],
                    },
                    "content": [{"type": "text", "text": "graph"}],
                    "isError": False,
                },
                "errors": [],
            }
        if tool_name == "get_widget_tree":
            return {
                "ok": True,
                "status": "completed",
                "reason": "mcp_tool_call_completed",
                "tool_name": tool_name,
                "transport": "mcp_tcp",
                "result": {
                    "structuredContent": {
                        "widget_blueprint_path": arguments["widget_blueprint_path"],
                        "root": "RootCanvas",
                        "widgets": [
                            {
                                "widget_name": "TitleText",
                                "widget_class": "/Script/UMG.TextBlock",
                                "parent_widget": "RootCanvas",
                                "visibility": "Visible",
                                "text_block": {"text": "Mission Ready", "font_size": 24},
                                "slot": {
                                    "slot_type": "CanvasPanelSlot",
                                    "position": {"x": 64, "y": 32},
                                    "size": {"x": 320, "y": 64},
                                    "z_order": 2,
                                },
                            }
                        ],
                    },
                    "content": [{"type": "text", "text": "widget"}],
                    "isError": False,
                },
                "errors": [],
            }
        if tool_name == "get_material_instance_parameters":
            material_path = (arguments or {}).get("material_instance_path") or "/Game/Materials/MI_Player.MI_Player"
            return {
                "ok": True,
                "status": "completed",
                "reason": "mcp_tool_call_completed",
                "tool_name": tool_name,
                "transport": "mcp_tcp",
                "result": {
                    "structuredContent": {
                        "material_instance_schema_version": "ue_agent_tool_tcp_fixture_v1",
                        "material_instance_path": material_path,
                        "material_instance_name": "MI_Player",
                        "parent_material": "/Game/Materials/M_Player.M_Player",
                        "parameters": [
                            {
                                "name": "Roughness",
                                "parameter_name": "Roughness",
                                "parameter_type": "scalar",
                                "value": 0.35,
                            }
                        ],
                        "scalar_parameters": [
                            {
                                "name": "Roughness",
                                "parameter_name": "Roughness",
                                "parameter_type": "scalar",
                                "value": 0.35,
                            }
                        ],
                        "vector_parameters": [],
                        "texture_parameters": [],
                        "static_switch_parameters": [],
                    },
                    "content": [{"type": "text", "text": "material"}],
                    "isError": False,
                },
                "errors": [],
            }
        if tool_name == "get_selected_assets":
            return {
                "ok": True,
                "status": "completed",
                "reason": "mcp_tool_call_completed",
                "tool_name": tool_name,
                "transport": "mcp_tcp",
                "result": {
                    "structuredContent": {
                        "asset_selection_schema_version": "ue_agent_tool_selected_assets_fixture_v1",
                        "selected_asset_count": 3,
                        "assets": [
                            {
                                "asset_name": "BP_PlayerCharacter",
                                "asset_path": "/Game/Blueprints/BP_PlayerCharacter.BP_PlayerCharacter",
                                "asset_type": "Blueprint",
                                "package_path": "/Game/Blueprints",
                            },
                            {
                                "asset_name": "SM_Rock",
                                "asset_path": "/Game/Environment/SM_Rock.SM_Rock",
                                "asset_type": "StaticMesh",
                                "package_path": "/Game/Environment",
                                "static_mesh": {
                                    "nanite_enabled": True,
                                    "lod_count": 3,
                                    "lightmap_resolution": 128,
                                    "collision_complexity": "simple_and_complex",
                                    "material_slot_count": 2,
                                    "material_slots": [
                                        {
                                            "slot_name": "Rock_Base",
                                            "material_path": "/Game/Materials/M_Rock.M_Rock",
                                        },
                                        {
                                            "slot_name": "Rock_Detail",
                                            "material_path": "/Game/Materials/M_Rock_Detail.M_Rock_Detail",
                                        },
                                    ],
                                },
                            },
                        ],
                    },
                    "content": [{"type": "text", "text": "selected assets"}],
                    "isError": False,
                },
                "errors": [],
            }
        if tool_name == "get_static_mesh_details":
            return {
                "ok": True,
                "status": "completed",
                "reason": "mcp_tool_call_completed",
                "tool_name": tool_name,
                "transport": "mcp_tcp",
                "result": {
                    "structuredContent": {
                        "static_mesh_schema_version": "ue_agent_static_mesh_details_v1",
                        "static_mesh_name": "SM_Rock",
                        "static_mesh_path": "/Game/Environment/SM_Rock.SM_Rock",
                        "resolved_from": "query_or_path",
                        "static_mesh": {
                            "nanite_enabled": True,
                            "lod_count": 3,
                            "lightmap_resolution": 128,
                            "collision_complexity": "simple_and_complex",
                            "material_slot_count": 2,
                            "material_slots": [
                                {"slot_name": "Rock_Base", "material_path": "/Game/Materials/M_Rock.M_Rock"},
                                {"slot_name": "Rock_Detail", "material_path": "/Game/Materials/M_Rock_Detail.M_Rock_Detail"},
                            ],
                        },
                    },
                    "content": [{"type": "text", "text": "static mesh"}],
                    "isError": False,
                },
                "errors": [],
            }
        if tool_name == "get_level_actors":
            return {
                "ok": True,
                "status": "completed",
                "reason": "mcp_tool_call_completed",
                "tool_name": tool_name,
                "transport": "mcp_tcp",
                "result": {
                    "structuredContent": {
                        "level_actor_schema_version": "ue_agent_level_actors_v1",
                        "world_name": "DemoWorld",
                        "map_name": "DemoMap",
                        "total_actor_count": 3,
                        "matched_actor_count": 2,
                        "filters": arguments or {},
                        "actors": [
                            {
                                "actor_label": "BP_PlayerCharacter_1",
                                "actor_name": "BP_PlayerCharacter_C_1",
                                "actor_class": "/Game/Blueprints/BP_PlayerCharacter.BP_PlayerCharacter_C",
                                "folder_path": "Gameplay/Player",
                                "tags": ["Player"],
                                "component_count": 3,
                            }
                        ],
                    },
                    "content": [{"type": "text", "text": "level actors"}],
                    "isError": False,
                },
                "errors": [],
            }
        return {
            "ok": False,
            "status": "blocked",
            "reason": "tool_not_in_mcp_allowed_tools",
            "tool_name": tool_name,
            "transport": "mcp_tcp",
            "result": {},
            "errors": [],
        }


class _FailingMCPToolExecutor:
    def __init__(self, settings: Settings):
        self.settings = settings

    def call_readonly_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "error",
            "reason": "mcp_tcp_connect_failed",
            "tool_name": tool_name,
            "transport": "mcp_tcp",
            "result": {},
            "errors": [{"reason": "mcp_tcp_connect_failed"}],
        }


class _FakeLocalReadOnlyCallService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def call(self, tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "completed",
            "reason": "local_readonly_tool_completed",
            "tool_id": tool,
            "tool_name": "get_widget_tree",
            "transport": "local_tool_registry",
            "source": "project_inventory",
            "result": {
                "structuredContent": {
                    "widget_blueprint_path": arguments["widget_blueprint_path"],
                    "widget_tree": {
                        "root": "RootCanvas",
                        "widgets": [{"name": "TitleText", "class": "TextBlock", "parent": "RootCanvas"}],
                    },
                    "empty_reason": "",
                },
                "content": [{"type": "text", "text": "widget inventory"}],
            },
            "errors": [],
        }


class _FakeLocalMaterialReadOnlyCallService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def call(self, tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        material_path = (arguments or {}).get("material_instance_path") or "/Game/Materials/MI_Player.MI_Player"
        return {
            "ok": True,
            "status": "completed",
            "reason": "local_readonly_tool_completed",
            "tool_id": tool,
            "tool_name": "get_material_instance_parameters",
            "transport": "local_tool_registry",
            "source": "project_inventory",
            "result": {
                "inspection": {"empty_reason": "", "match_count": 1},
                "items": [
                    {
                        "material_instance_path": material_path,
                        "material_instance_name": "MI_Player",
                        "parent_material": "/Game/Materials/M_Player.M_Player",
                        "parameters": [
                            {
                                "name": "Roughness",
                                "parameter_name": "Roughness",
                                "parameter_type": "scalar",
                                "value": 0.35,
                            }
                        ],
                        "scalar_parameters": [
                            {
                                "name": "Roughness",
                                "parameter_name": "Roughness",
                                "parameter_type": "scalar",
                                "value": 0.35,
                            }
                        ],
                    }
                ],
            },
            "errors": [],
        }


class _FakeLocalLevelActorsReadOnlyCallService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def call(self, tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "completed",
            "reason": "local_readonly_tool_completed",
            "tool_id": tool,
            "tool_name": "get_level_actors",
            "transport": "local_tool_registry",
            "source": "project_inventory",
            "result": {
                "items": [
                    {
                        "actor_label": "BP_PlayerCharacter_1",
                        "actor_name": "BP_PlayerCharacter_C_1",
                        "actor_class": "/Game/Blueprints/BP_PlayerCharacter.BP_PlayerCharacter_C",
                        "folder_path": "Gameplay/Player",
                        "tags": ["Player"],
                        "component_count": 3,
                    }
                ],
                "summary": {"has_snapshot": True},
                "inspection": {"empty_reason": "", "match_count": 1},
            },
            "errors": [],
        }


class _FakeLocalStaticMeshReadOnlyCallService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def call(self, tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "completed",
            "reason": "local_readonly_tool_completed",
            "tool_id": tool,
            "tool_name": "get_static_mesh_details",
            "transport": "local_tool_registry",
            "source": "project_inventory",
            "result": {
                "item": {
                    "asset_name": "SM_Rock",
                    "asset_path": "/Game/Environment/SM_Rock.SM_Rock",
                    "asset_type": "StaticMesh",
                    "settings": {
                        "nanite_enabled": True,
                        "lod_count": 3,
                        "lightmap_resolution": 128,
                        "collision_complexity": "UseComplexAsSimple",
                    },
                    "properties": {"material_slots": ["M_Rock", "M_Rock_Detail"]},
                },
                "summary": {"has_snapshot": True},
                "inspection": {"empty_reason": "", "match_count": 1},
            },
            "errors": [],
        }


def _context(*, selected_tool_id: str, request: UnifiedTaskRequest) -> TaskExecutionContext:
    return TaskExecutionContext(
        request=request,
        routing={
            "intent": {"reason": "test route"},
            "route": {"selected_tool_id": selected_tool_id, "candidate_tool_ids": [selected_tool_id]},
        },
        task_id="task_test",
        run_id="run_test",
        trace_id="trace_test",
        actual_task_type="agent_chat",
        output_language="en",
        chat_config=ChatRuntimeConfig(
            profile_id="default",
            profile_name="Default",
            model="test",
            temperature=0.0,
            max_tokens=128,
            timeout_ms=1000,
        ),
        context_bundle={
            "project_inventory_context": {
                "current_blueprint": {
                    "asset_name": "BP_PlayerCharacter",
                    "asset_path": "/Game/Blueprints/BP_PlayerCharacter",
                },
                "current_blueprint_graph": {"graph_name": "EventGraph"},
                "selected_assets": [
                    {
                        "asset_name": "WBP_MainHUD",
                        "asset_type": "WidgetBlueprint",
                        "asset_path": "/Game/UI/WBP_MainHUD",
                    },
                    {
                        "asset_name": "MI_Player",
                        "asset_type": "MaterialInstanceConstant",
                        "asset_path": "/Game/Materials/MI_Player.MI_Player",
                    },
                    {
                        "asset_name": "SM_Rock",
                        "asset_type": "StaticMesh",
                        "asset_path": "/Game/Environment/SM_Rock.SM_Rock",
                        "static_mesh": {
                            "nanite_enabled": True,
                            "lod_count": 3,
                            "collision_complexity": "simple_and_complex",
                            "material_slot_count": 2,
                            "material_slots": [
                                {"slot_name": "Rock_Base", "material_path": "/Game/Materials/M_Rock.M_Rock"},
                                {"slot_name": "Rock_Detail", "material_path": "/Game/Materials/M_Rock_Detail.M_Rock_Detail"},
                            ],
                        },
                    }
                ],
                "material_instances": [
                    {
                        "material_instance_name": "MI_Player",
                        "material_instance_path": "/Game/Materials/MI_Player.MI_Player",
                    }
                ],
            }
        },
        dependencies=SimpleNamespace(settings=Settings()),
    )


def test_live_mcp_readonly_result_uses_tcp_blueprint_graph(monkeypatch) -> None:
    monkeypatch.setattr(read_only_tool_summaries, "MCPToolExecutor", _FakeMCPToolExecutor)
    request = UnifiedTaskRequest(
        session={"session_id": "s1", "messages": [{"role": "user", "content": "read current graph"}]},
        context={"editor_state": {"current_blueprint_path": "/Game/Blueprints/BP_PlayerCharacter"}},
        payload={},
    )
    base_debug: dict[str, Any] = {}

    result = read_only_tool_summaries.live_mcp_readonly_result(
        context=_context(selected_tool_id="mcp_get_blueprint_graph", request=request),
        base_debug=base_debug,
        output_language="en",
        selected_tool_id="mcp_get_blueprint_graph",
    )

    assert result is not None
    assert result["retrieval_trace"]["mode"] == "mcp_tcp_readonly"
    assert result["data"]["mcp_tool"]["transport"] == "mcp_tcp"
    assert "EventGraph" in result["assistant_message"]
    assert "Print String" in result["assistant_message"]
    assert base_debug["mcp_live_attempt"]["tool_name"] == "get_blueprint_graph"


def test_live_mcp_readonly_result_uses_selected_widget_path(monkeypatch) -> None:
    monkeypatch.setattr(read_only_tool_summaries, "MCPToolExecutor", _FakeMCPToolExecutor)
    request = UnifiedTaskRequest(
        session={"session_id": "s1", "messages": [{"role": "user", "content": "read widget tree"}]},
        context={"selected_assets": ["/Game/UI/WBP_MainHUD"]},
        payload={},
    )
    base_debug: dict[str, Any] = {}

    result = read_only_tool_summaries.live_mcp_readonly_result(
        context=_context(selected_tool_id="mcp_get_widget_tree", request=request),
        base_debug=base_debug,
        output_language="en",
        selected_tool_id="mcp_get_widget_tree",
    )

    assert result is not None
    assert result["data"]["mcp_tool"]["arguments"]["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert "RootCanvas" in result["assistant_message"]
    assert "TitleText" in result["assistant_message"]
    assert "Mission Ready" in result["assistant_message"]
    assert "slot=CanvasPanelSlot" in result["assistant_message"]


def test_live_mcp_readonly_result_reads_material_instance_parameters(monkeypatch) -> None:
    monkeypatch.setattr(read_only_tool_summaries, "MCPToolExecutor", _FakeMCPToolExecutor)
    request = UnifiedTaskRequest(
        session={"session_id": "s1", "messages": [{"role": "user", "content": "show selected material parameters"}]},
        context={"selected_assets": ["/Game/Materials/MI_Player.MI_Player"]},
        payload={},
    )
    base_debug: dict[str, Any] = {}

    result = read_only_tool_summaries.live_mcp_readonly_result(
        context=_context(selected_tool_id="mcp_get_material_instance_parameters", request=request),
        base_debug=base_debug,
        output_language="en",
        selected_tool_id="mcp_get_material_instance_parameters",
    )

    assert result is not None
    assert result["data"]["mcp_tool"]["arguments"]["material_instance_path"] == "/Game/Materials/MI_Player.MI_Player"
    assert "MI_Player" in result["assistant_message"]
    assert "Roughness" in result["assistant_message"]
    assert base_debug["mcp_live_attempt"]["tool_name"] == "get_material_instance_parameters"


def test_live_mcp_readonly_result_summarizes_static_mesh_selected_asset(monkeypatch) -> None:
    monkeypatch.setattr(read_only_tool_summaries, "MCPToolExecutor", _FakeMCPToolExecutor)
    request = UnifiedTaskRequest(
        session={"session_id": "s1", "messages": [{"role": "user", "content": "list selected assets"}]},
        context={},
        payload={},
    )
    base_debug: dict[str, Any] = {}

    result = read_only_tool_summaries.live_mcp_readonly_result(
        context=_context(selected_tool_id="mcp_get_selected_assets", request=request),
        base_debug=base_debug,
        output_language="en",
        selected_tool_id="mcp_get_selected_assets",
    )

    assert result is not None
    assert result["retrieval_trace"]["mode"] == "mcp_tcp_readonly"
    assert "SM_Rock" in result["assistant_message"]
    assert "lods=3" in result["assistant_message"]
    assert "nanite=True" in result["assistant_message"]
    assert "collision=simple_and_complex" in result["assistant_message"]
    assert "Rock_Base" in result["assistant_message"]


def test_live_mcp_readonly_result_reads_static_mesh_details(monkeypatch) -> None:
    monkeypatch.setattr(read_only_tool_summaries, "MCPToolExecutor", _FakeMCPToolExecutor)
    request = UnifiedTaskRequest(
        session={"session_id": "s1", "messages": [{"role": "user", "content": "SM_Rock Nanite LOD collision"}]},
        context={},
        payload={},
    )
    base_debug: dict[str, Any] = {}

    result = read_only_tool_summaries.live_mcp_readonly_result(
        context=_context(selected_tool_id="mcp_get_static_mesh_details", request=request),
        base_debug=base_debug,
        output_language="en",
        selected_tool_id="mcp_get_static_mesh_details",
    )

    assert result is not None
    assert result["data"]["mcp_tool"]["arguments"]["query"] == "SM_Rock"
    assert "SM_Rock" in result["assistant_message"]
    assert "lods=3" in result["assistant_message"]
    assert "nanite=True" in result["assistant_message"]
    assert "Rock_Base" in result["assistant_message"]


def test_live_mcp_readonly_result_reads_level_actors(monkeypatch) -> None:
    monkeypatch.setattr(read_only_tool_summaries, "MCPToolExecutor", _FakeMCPToolExecutor)
    request = UnifiedTaskRequest(
        session={"session_id": "s1", "messages": [{"role": "user", "content": "list current level actors"}]},
        context={},
        payload={"class_contains": "Character", "tag": "Player", "limit": 20},
    )
    base_debug: dict[str, Any] = {}

    result = read_only_tool_summaries.live_mcp_readonly_result(
        context=_context(selected_tool_id="mcp_get_level_actors", request=request),
        base_debug=base_debug,
        output_language="en",
        selected_tool_id="mcp_get_level_actors",
    )

    assert result is not None
    assert result["data"]["mcp_tool"]["arguments"]["class_contains"] == "Character"
    assert "BP_PlayerCharacter_1" in result["assistant_message"]
    assert "matched_actor_count=2" in result["assistant_message"]
    assert "tags=Player" in result["assistant_message"]


def test_live_mcp_readonly_result_returns_none_when_tcp_fails(monkeypatch) -> None:
    monkeypatch.setattr(read_only_tool_summaries, "MCPToolExecutor", _FailingMCPToolExecutor)
    request = UnifiedTaskRequest(
        session={"session_id": "s1", "messages": [{"role": "user", "content": "read current graph"}]},
        context={"editor_state": {"current_blueprint_path": "/Game/Blueprints/BP_PlayerCharacter"}},
        payload={},
    )
    base_debug: dict[str, Any] = {}

    result = read_only_tool_summaries.live_mcp_readonly_result(
        context=_context(selected_tool_id="mcp_get_blueprint_graph", request=request),
        base_debug=base_debug,
        output_language="en",
        selected_tool_id="mcp_get_blueprint_graph",
    )

    assert result is None
    assert base_debug["mcp_live_attempt"]["reason"] == "mcp_tcp_connect_failed"


def test_local_tool_registry_readonly_result_reads_widget_tree(monkeypatch) -> None:
    monkeypatch.setattr(read_only_tool_summaries, "ToolRegistryReadOnlyCallService", _FakeLocalReadOnlyCallService)
    request = UnifiedTaskRequest(
        session={"session_id": "s1", "messages": [{"role": "user", "content": "inspect widget tree"}]},
        context={"selected_assets": ["/Game/UI/WBP_MainHUD"]},
        payload={},
    )
    base_debug: dict[str, Any] = {}

    result = read_only_tool_summaries.local_tool_registry_readonly_result(
        context=_context(selected_tool_id="mcp_get_widget_tree", request=request),
        base_debug=base_debug,
        output_language="en",
        selected_tool_id="mcp_get_widget_tree",
    )

    assert result is not None
    assert result["retrieval_trace"]["mode"] == "local_tool_registry_readonly"
    assert result["data"]["local_tool"]["transport"] == "local_tool_registry"
    assert "RootCanvas" in result["assistant_message"]
    assert "TitleText" in result["assistant_message"]


def test_local_tool_registry_readonly_result_reads_material_parameters(monkeypatch) -> None:
    monkeypatch.setattr(
        read_only_tool_summaries,
        "ToolRegistryReadOnlyCallService",
        _FakeLocalMaterialReadOnlyCallService,
    )
    request = UnifiedTaskRequest(
        session={"session_id": "s1", "messages": [{"role": "user", "content": "inspect material parameters"}]},
        context={"selected_assets": ["/Game/Materials/MI_Player.MI_Player"]},
        payload={},
    )
    base_debug: dict[str, Any] = {}

    result = read_only_tool_summaries.local_tool_registry_readonly_result(
        context=_context(selected_tool_id="mcp_get_material_instance_parameters", request=request),
        base_debug=base_debug,
        output_language="en",
        selected_tool_id="mcp_get_material_instance_parameters",
    )

    assert result is not None
    assert result["retrieval_trace"]["mode"] == "local_tool_registry_readonly"
    assert result["data"]["local_tool"]["transport"] == "local_tool_registry"
    assert "MI_Player" in result["assistant_message"]
    assert "Roughness" in result["assistant_message"]


def test_local_tool_registry_readonly_result_reads_level_actors(monkeypatch) -> None:
    monkeypatch.setattr(
        read_only_tool_summaries,
        "ToolRegistryReadOnlyCallService",
        _FakeLocalLevelActorsReadOnlyCallService,
    )
    request = UnifiedTaskRequest(
        session={"session_id": "s1", "messages": [{"role": "user", "content": "list current level actors"}]},
        context={},
        payload={},
    )
    base_debug: dict[str, Any] = {}

    result = read_only_tool_summaries.local_tool_registry_readonly_result(
        context=_context(selected_tool_id="mcp_get_level_actors", request=request),
        base_debug=base_debug,
        output_language="en",
        selected_tool_id="mcp_get_level_actors",
    )

    assert result is not None
    assert result["retrieval_trace"]["mode"] == "local_tool_registry_readonly"
    assert "BP_PlayerCharacter_1" in result["assistant_message"]
    assert "Gameplay/Player" in result["assistant_message"]


def test_local_tool_registry_readonly_result_reads_static_mesh_details(monkeypatch) -> None:
    monkeypatch.setattr(
        read_only_tool_summaries,
        "ToolRegistryReadOnlyCallService",
        _FakeLocalStaticMeshReadOnlyCallService,
    )
    request = UnifiedTaskRequest(
        session={"session_id": "s1", "messages": [{"role": "user", "content": "SM_Rock Nanite LOD collision"}]},
        context={},
        payload={},
    )
    base_debug: dict[str, Any] = {}

    result = read_only_tool_summaries.local_tool_registry_readonly_result(
        context=_context(selected_tool_id="mcp_get_static_mesh_details", request=request),
        base_debug=base_debug,
        output_language="en",
        selected_tool_id="mcp_get_static_mesh_details",
    )

    assert result is not None
    assert result["retrieval_trace"]["mode"] == "local_tool_registry_readonly"
    assert "SM_Rock" in result["assistant_message"]
    assert "UseComplexAsSimple" in result["assistant_message"]
    assert "M_Rock" in result["assistant_message"]


def test_local_tool_registry_readonly_result_reads_selected_assets_context() -> None:
    request = UnifiedTaskRequest(
        session={"session_id": "s1", "messages": [{"role": "user", "content": "list selected assets"}]},
        context={"selected_assets": ["/Game/Blueprints/BP_Player.BP_Player"]},
        payload={},
    )
    base_debug: dict[str, Any] = {}

    result = read_only_tool_summaries.local_tool_registry_readonly_result(
        context=_context(selected_tool_id="mcp_get_selected_assets", request=request),
        base_debug=base_debug,
        output_language="en",
        selected_tool_id="mcp_get_selected_assets",
    )

    assert result is not None
    assert result["retrieval_trace"]["mode"] == "request_context_selected_assets"
    assert result["data"]["selected_assets"][0]["asset_name"] == "WBP_MainHUD"
    assert "WBP_MainHUD" in result["assistant_message"]
    assert "BP_Player" in result["assistant_message"]
