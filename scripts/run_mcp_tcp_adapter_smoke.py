from __future__ import annotations

import argparse
import json
import socketserver
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.settings import Settings
from app.services.mcp_tool_adapter import MCPToolAdapter


Validator = Callable[[dict[str, Any]], tuple[bool, str]]


UE_AGENT_TOOL_FIXTURE_TOOLS = [
    {
        "name": "ue_agent_tools_list",
        "description": "Return UE editor tool metadata.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_editor_context",
        "description": "Read lightweight live Unreal Editor context.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_selected_actors",
        "description": "Read currently selected Level Actors.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_level_actors",
        "description": "Read current level Actors with optional filters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "class_contains": {"type": "string"},
                "tag": {"type": "string"},
                "folder_path": {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "get_selected_assets",
        "description": "Read currently selected Content Browser assets.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_static_mesh_details",
        "description": "Read Static Mesh details by path, query, or current selection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "static_mesh_path": {"type": "string"},
                "asset_path": {"type": "string"},
                "query": {"type": "string"},
            },
        },
    },
    {
        "name": "get_blueprint_graph",
        "description": "Read Blueprint graph metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {"blueprint_path": {"type": "string"}},
            "required": ["blueprint_path"],
        },
    },
    {
        "name": "get_widget_tree",
        "description": "Read Widget Blueprint tree metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {"widget_blueprint_path": {"type": "string"}},
            "required": ["widget_blueprint_path"],
        },
    },
    {
        "name": "get_widget_details",
        "description": "Read one Widget Blueprint widget's live detail metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "widget_blueprint_path": {"type": "string"},
                "widget_name": {"type": "string"},
                "target_widget": {"type": "string"},
                "query": {"type": "string"},
            },
            "required": ["widget_blueprint_path", "widget_name"],
        },
    },
    {
        "name": "get_material_instance_parameters",
        "description": "Read Material Instance parameters.",
        "inputSchema": {
            "type": "object",
            "properties": {"material_instance_path": {"type": "string"}},
        },
    },
    {
        "name": "rename_asset",
        "description": "Confirmed-write fixture tool; UEAgentTool rejects raw TCP execution.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset_path": {"type": "string"},
                "new_name": {"type": "string"},
            },
            "required": ["asset_path", "new_name"],
        },
    },
]


class _UEAgentToolTcpHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        for raw_line in self.rfile:
            request = json.loads(raw_line.decode("utf-8"))
            request_id = request.get("id")
            method = str(request.get("method") or "")
            if request_id is None:
                continue

            if method == "initialize":
                response = self._response(
                    request_id,
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "UEAgentTool.EditorToolServer", "version": "0.1.0"},
                        "ue_agent": {
                            "transport": "tcp_jsonrpc_line",
                            "status": "listening:127.0.0.1:fixture",
                            "http_proposal_flow_required_for_writes": True,
                        },
                    },
                )
            elif method == "tools/list":
                response = self._response(request_id, {"tools": UE_AGENT_TOOL_FIXTURE_TOOLS})
            elif method == "tools/call":
                params = request.get("params") if isinstance(request.get("params"), dict) else {}
                response = self._response(request_id, self._tool_result(str(params.get("name") or "")))
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": "Method not found"},
                }

            self.wfile.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n")
            self.wfile.flush()

    @staticmethod
    def _response(request_id: int, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _tool_result(tool_name: str) -> dict[str, Any]:
        if tool_name == "ue_agent_tools_list":
            return {
                "content": [{"type": "text", "text": json.dumps({"tools": UE_AGENT_TOOL_FIXTURE_TOOLS})}],
                "structuredContent": {"tools": UE_AGENT_TOOL_FIXTURE_TOOLS},
            }
        if tool_name == "get_editor_context":
            structured = {
                "context_schema_version": "ue_agent_tool_editor_context_fixture_v1",
                "server_status": "listening:127.0.0.1:fixture",
                "tool_summary": {
                    "tool_count": 4,
                    "read_only_tool_count": 3,
                    "confirmed_write_tool_count": 1,
                },
                "editor_world": {
                    "editor_available": True,
                    "world_name": "FixtureEditorWorld",
                    "selected_actor_count": 2,
                },
            }
            return {
                "content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False)}],
                "structuredContent": structured,
                "isError": False,
            }
        if tool_name == "get_selected_actors":
            structured = {
                "selection_schema_version": "ue_agent_tool_selected_actors_fixture_v1",
                "selected_actor_count": 2,
                "actors": [
                    {
                        "actor_label": "BP_EnemySpawner_1",
                        "actor_name": "BP_EnemySpawner_C_1",
                        "actor_class": "/Game/Blueprints/BP_EnemySpawner.BP_EnemySpawner_C",
                        "actor_path": "PersistentLevel.BP_EnemySpawner_C_1",
                        "component_count": 2,
                        "components": [
                            {"component_name": "DefaultSceneRoot", "component_class": "SceneComponent"},
                            {"component_name": "SpawnPoint", "component_class": "ArrowComponent"},
                        ],
                    },
                    {
                        "actor_label": "BP_PatrolPoint_1",
                        "actor_name": "BP_PatrolPoint_C_1",
                        "actor_class": "/Game/Blueprints/BP_PatrolPoint.BP_PatrolPoint_C",
                        "actor_path": "PersistentLevel.BP_PatrolPoint_C_1",
                        "component_count": 1,
                        "components": [{"component_name": "DefaultSceneRoot", "component_class": "SceneComponent"}],
                    },
                ],
            }
            return {
                "content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False)}],
                "structuredContent": structured,
                "isError": False,
            }
        if tool_name == "get_level_actors":
            structured = {
                "level_actor_schema_version": "ue_agent_level_actors_v1",
                "transport": "tcp_jsonrpc_line",
                "server_status": "running",
                "world_name": "DemoWorld",
                "map_name": "DemoMap",
                "total_actor_count": 3,
                "matched_actor_count": 2,
                "max_actors_returned": 20,
                "filters": {"class_contains": "Character", "tag": "Player", "limit": 20},
                "actors": [
                    {
                        "actor_label": "BP_PlayerCharacter_1",
                        "actor_name": "BP_PlayerCharacter_C_1",
                        "actor_class": "/Game/Blueprints/BP_PlayerCharacter.BP_PlayerCharacter_C",
                        "actor_path": "PersistentLevel.BP_PlayerCharacter_C_1",
                        "folder_path": "Gameplay/Player",
                        "tags": ["Player"],
                        "component_count": 3,
                    },
                    {
                        "actor_label": "BP_NPCCharacter_1",
                        "actor_name": "BP_NPCCharacter_C_1",
                        "actor_class": "/Game/Blueprints/BP_NPCCharacter.BP_NPCCharacter_C",
                        "actor_path": "PersistentLevel.BP_NPCCharacter_C_1",
                        "folder_path": "Gameplay/NPC",
                        "tags": ["Player"],
                        "component_count": 2,
                    },
                ],
            }
            return {
                "content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False)}],
                "structuredContent": structured,
                "isError": False,
            }
        if tool_name == "get_selected_assets":
            structured = {
                "asset_selection_schema_version": "ue_agent_tool_selected_assets_fixture_v1",
                "selected_asset_count": 3,
                "assets": [
                    {
                        "asset_name": "BP_PlayerCharacter",
                        "asset_path": "/Game/Blueprints/BP_PlayerCharacter.BP_PlayerCharacter",
                        "asset_type": "Blueprint",
                        "package_name": "/Game/Blueprints/BP_PlayerCharacter",
                        "package_path": "/Game/Blueprints",
                    },
                    {
                        "asset_name": "MI_Player",
                        "asset_path": "/Game/Materials/MI_Player.MI_Player",
                        "asset_type": "MaterialInstanceConstant",
                        "package_name": "/Game/Materials/MI_Player",
                        "package_path": "/Game/Materials",
                    },
                    {
                        "asset_name": "SM_Rock",
                        "asset_path": "/Game/Environment/SM_Rock.SM_Rock",
                        "asset_type": "StaticMesh",
                        "package_name": "/Game/Environment/SM_Rock",
                        "package_path": "/Game/Environment",
                        "static_mesh": {
                            "nanite_enabled": True,
                            "lod_count": 3,
                            "lightmap_resolution": 128,
                            "collision_complexity": "simple_and_complex",
                            "material_slot_count": 2,
                            "material_slots": [
                                {"slot_name": "Rock_Base", "material_path": "/Game/Materials/M_Rock.M_Rock"},
                                {
                                    "slot_name": "Rock_Detail",
                                    "material_path": "/Game/Materials/M_Rock_Detail.M_Rock_Detail",
                                },
                            ],
                        },
                    },
                ],
            }
            return {
                "content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False)}],
                "structuredContent": structured,
                "isError": False,
            }
        if tool_name == "get_static_mesh_details":
            structured = {
                "static_mesh_schema_version": "ue_agent_static_mesh_details_v1",
                "transport": "tcp_jsonrpc_line",
                "server_status": "running",
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
            }
            return {
                "content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False)}],
                "structuredContent": structured,
                "isError": False,
            }
        if tool_name == "get_blueprint_graph":
            structured = {
                "graph_schema_version": "ue_agent_tool_tcp_fixture_v1",
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "graphs": [
                    {
                        "graph_name": "EventGraph",
                        "graph_type": "Ubergraph",
                        "nodes": [
                            {"node_id": "EventBeginPlay", "title": "Event BeginPlay"},
                            {"node_id": "PrintString_1", "title": "Print String"},
                        ],
                    }
                ],
            }
            return {
                "content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False)}],
                "structuredContent": structured,
                "isError": False,
            }
        if tool_name == "get_widget_tree":
            structured = {
                "widget_tree_schema_version": "ue_agent_tool_tcp_fixture_v1",
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "root": "RootCanvas",
                "widgets": [
                    {"name": "RootCanvas", "class": "CanvasPanel"},
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
                    },
                ],
            }
            return {
                "content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False)}],
                "structuredContent": structured,
                "isError": False,
            }
        if tool_name == "get_widget_details":
            structured = {
                "widget_detail_schema_version": "ue_agent_widget_details_v1",
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_blueprint_name": "WBP_MainHUD",
                "requested_widget_name": "TitleText",
                "widget_name": "TitleText",
                "root_widget": "RootCanvas",
                "widget": {
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
                },
                "child_count": 0,
                "children": [],
            }
            return {
                "content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False)}],
                "structuredContent": structured,
                "isError": False,
            }
        if tool_name == "get_material_instance_parameters":
            structured = {
                "material_instance_schema_version": "ue_agent_tool_tcp_fixture_v1",
                "material_instance_path": "/Game/Materials/MI_Player.MI_Player",
                "material_instance_name": "MI_Player",
                "parent_material": "/Game/Materials/M_Player.M_Player",
                "parameters": [
                    {"name": "Roughness", "parameter_name": "Roughness", "parameter_type": "scalar", "value": 0.35},
                    {
                        "name": "BaseColor",
                        "parameter_name": "BaseColor",
                        "parameter_type": "vector",
                        "value": {"r": 0.9, "g": 0.7, "b": 0.45, "a": 1.0},
                    },
                    {
                        "name": "BaseTexture",
                        "parameter_name": "BaseTexture",
                        "parameter_type": "texture",
                        "texture_path": "/Game/Textures/T_Player_D.T_Player_D",
                        "value": "/Game/Textures/T_Player_D.T_Player_D",
                    },
                    {
                        "name": "UseDetailNormal",
                        "parameter_name": "UseDetailNormal",
                        "parameter_type": "static_switch",
                        "value": True,
                    },
                ],
                "scalar_parameters": [
                    {"name": "Roughness", "parameter_name": "Roughness", "parameter_type": "scalar", "value": 0.35}
                ],
                "vector_parameters": [
                    {
                        "name": "BaseColor",
                        "parameter_name": "BaseColor",
                        "parameter_type": "vector",
                        "value": {"r": 0.9, "g": 0.7, "b": 0.45, "a": 1.0},
                    }
                ],
                "texture_parameters": [
                    {
                        "name": "BaseTexture",
                        "parameter_name": "BaseTexture",
                        "parameter_type": "texture",
                        "texture_path": "/Game/Textures/T_Player_D.T_Player_D",
                        "value": "/Game/Textures/T_Player_D.T_Player_D",
                    }
                ],
                "static_switch_parameters": [
                    {
                        "name": "UseDetailNormal",
                        "parameter_name": "UseDetailNormal",
                        "parameter_type": "static_switch",
                        "value": True,
                    }
                ],
                "parameter_count": 4,
            }
            return {
                "content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False)}],
                "structuredContent": structured,
                "isError": False,
            }
        return {
            "isError": True,
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Tool '{tool_name}' requires the existing HTTP Proposal confirmation flow "
                        "and cannot be executed through raw MCP/TCP."
                    ),
                }
            ],
        }


class _TcpFixture:
    def __enter__(self) -> _TcpFixture:
        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _UEAgentToolTcpHandler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run deterministic UEAgentTool MCP TCP adapter smoke checks."
    )
    parser.add_argument(
        "--output",
        default="storage/artifacts/smoke/mcp-tcp-adapter-smoke-latest.json",
        help="JSON report output path. Use '-' to print to stdout without writing a file.",
    )
    return parser.parse_args()


def _emit_report(report: dict[str, Any], output: str) -> None:
    report_json = json.dumps(report, ensure_ascii=False, indent=2)
    if output == "-":
        print(report_json)
        return
    output_path = Path(output)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report_json, encoding="utf-8")
    except OSError as exc:
        print(f"WARNING: could not write smoke report to {output_path}: {exc}")
    print(report_json)


def _settings(port: int, allowed_tools: list[str]) -> Settings:
    return Settings(
        mcp_tool_adapter_enabled=True,
        mcp_transport="tcp",
        mcp_tcp_host="127.0.0.1",
        mcp_tcp_port=port,
        mcp_tcp_timeout_ms=1000,
        mcp_allowed_tools=allowed_tools,
    )


@contextmanager
def _fixture_adapter(allowed_tools: list[str]) -> Iterator[MCPToolAdapter]:
    with _TcpFixture() as fixture:
        yield MCPToolAdapter(_settings(fixture.port, allowed_tools))


def _status_ready(payload: dict[str, Any]) -> tuple[bool, str]:
    return payload.get("status") == "ready" and payload.get("transport") == "mcp_tcp", "adapter is ready for TCP"


def _discover_readonly_ok(payload: dict[str, Any]) -> tuple[bool, str]:
    names = [item.get("name") for item in list(payload.get("tools") or [])]
    return (
        names == [
            "get_editor_context",
            "get_selected_actors",
            "get_level_actors",
            "get_selected_assets",
            "get_static_mesh_details",
            "get_blueprint_graph",
            "get_widget_tree",
            "get_widget_details",
            "get_material_instance_parameters",
        ],
        "discovery filters to read-only allow-list",
    )


def _editor_context_call_ok(payload: dict[str, Any]) -> tuple[bool, str]:
    structured = payload.get("result", {}).get("structuredContent", {})
    ok = (
        payload.get("ok") is True
        and structured.get("context_schema_version") == "ue_agent_tool_editor_context_fixture_v1"
        and structured.get("editor_world", {}).get("selected_actor_count") == 2
    )
    return ok, "TCP call returns editor context structuredContent"


def _blueprint_call_ok(payload: dict[str, Any]) -> tuple[bool, str]:
    structured = payload.get("result", {}).get("structuredContent", {})
    graphs = list(structured.get("graphs") or [])
    ok = payload.get("ok") is True and bool(graphs) and graphs[0].get("graph_name") == "EventGraph"
    return ok, "TCP call returns Blueprint graph structuredContent"


def _selected_actors_call_ok(payload: dict[str, Any]) -> tuple[bool, str]:
    structured = payload.get("result", {}).get("structuredContent", {})
    ok = (
        payload.get("ok") is True
        and structured.get("selection_schema_version") == "ue_agent_tool_selected_actors_fixture_v1"
        and structured.get("selected_actor_count") == 2
        and structured.get("actors", [{}])[0].get("component_count") == 2
    )
    return ok, "TCP call returns selected actor structuredContent"


def _level_actors_call_ok(payload: dict[str, Any]) -> tuple[bool, str]:
    structured = payload.get("result", {}).get("structuredContent", {})
    actors = [item for item in list(structured.get("actors") or []) if isinstance(item, dict)]
    ok = (
        payload.get("ok") is True
        and structured.get("level_actor_schema_version") == "ue_agent_level_actors_v1"
        and structured.get("matched_actor_count") == 2
        and actors
        and actors[0].get("actor_label") == "BP_PlayerCharacter_1"
    )
    return ok, "TCP call returns current level Actor query structuredContent"


def _selected_assets_call_ok(payload: dict[str, Any]) -> tuple[bool, str]:
    structured = payload.get("result", {}).get("structuredContent", {})
    assets = [item for item in list(structured.get("assets") or []) if isinstance(item, dict)]
    static_mesh = assets[2].get("static_mesh", {}) if len(assets) > 2 and isinstance(assets[2], dict) else {}
    ok = (
        payload.get("ok") is True
        and structured.get("asset_selection_schema_version") == "ue_agent_tool_selected_assets_fixture_v1"
        and structured.get("selected_asset_count") == 3
        and static_mesh.get("lod_count") == 3
        and static_mesh.get("material_slot_count") == 2
    )
    return ok, "TCP call returns selected asset and Static Mesh detail structuredContent"


def _static_mesh_details_call_ok(payload: dict[str, Any]) -> tuple[bool, str]:
    structured = payload.get("result", {}).get("structuredContent", {})
    static_mesh = structured.get("static_mesh") if isinstance(structured.get("static_mesh"), dict) else {}
    ok = (
        payload.get("ok") is True
        and structured.get("static_mesh_schema_version") == "ue_agent_static_mesh_details_v1"
        and structured.get("static_mesh_name") == "SM_Rock"
        and static_mesh.get("nanite_enabled") is True
        and static_mesh.get("lod_count") == 3
        and static_mesh.get("material_slot_count") == 2
    )
    return ok, "TCP call returns Static Mesh detail structuredContent"


def _widget_call_ok(payload: dict[str, Any]) -> tuple[bool, str]:
    structured = payload.get("result", {}).get("structuredContent", {})
    widgets = [item for item in list(structured.get("widgets") or []) if isinstance(item, dict)]
    title = next(
        (
            item
            for item in widgets
            if (item.get("widget_name") or item.get("name")) == "TitleText"
        ),
        {},
    )
    text_block = title.get("text_block") if isinstance(title.get("text_block"), dict) else {}
    slot = title.get("slot") if isinstance(title.get("slot"), dict) else {}
    ok = (
        payload.get("ok") is True
        and structured.get("root") == "RootCanvas"
        and text_block.get("text") == "Mission Ready"
        and slot.get("slot_type") == "CanvasPanelSlot"
    )
    return ok, "TCP call returns enriched Widget tree structuredContent"


def _widget_details_call_ok(payload: dict[str, Any]) -> tuple[bool, str]:
    structured = payload.get("result", {}).get("structuredContent", {})
    widget = structured.get("widget") if isinstance(structured.get("widget"), dict) else {}
    text_block = widget.get("text_block") if isinstance(widget.get("text_block"), dict) else {}
    slot = widget.get("slot") if isinstance(widget.get("slot"), dict) else {}
    ok = (
        payload.get("ok") is True
        and structured.get("widget_name") == "TitleText"
        and text_block.get("text") == "Mission Ready"
        and slot.get("slot_type") == "CanvasPanelSlot"
    )
    return ok, "TCP call returns focused Widget detail structuredContent"


def _material_parameters_call_ok(payload: dict[str, Any]) -> tuple[bool, str]:
    structured = payload.get("result", {}).get("structuredContent", {})
    parameters = list(structured.get("parameters") or [])
    ok = (
        payload.get("ok") is True
        and structured.get("material_instance_schema_version") == "ue_agent_tool_tcp_fixture_v1"
        and structured.get("material_instance_name") == "MI_Player"
        and len(parameters) == 4
    )
    return ok, "TCP call returns Material Instance parameter structuredContent"


def _write_blocked_by_allowlist(payload: dict[str, Any]) -> tuple[bool, str]:
    ok = payload.get("ok") is False and payload.get("reason") == "tool_not_in_mcp_allowed_tools"
    return ok, "confirmed-write tool is blocked before raw TCP call"


def _raw_write_rejected_by_server(payload: dict[str, Any]) -> tuple[bool, str]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    ok = payload.get("ok") is True and result.get("isError") is True
    return ok, "UEAgentTool-style server rejects raw write and points to Proposal flow"


def _run_case(case_id: str, payload: dict[str, Any], validator: Validator) -> dict[str, Any]:
    ok, reason = validator(payload)
    return {
        "case_id": case_id,
        "ok": ok,
        "reason": reason,
        "summary": {
            "status": payload.get("status"),
            "ok": payload.get("ok"),
            "reason": payload.get("reason"),
            "tool_count": payload.get("tool_count"),
            "transport": payload.get("transport") or payload.get("debug", {}).get("adapter", {}).get("transport"),
        },
    }


def _run_smoke() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with _fixture_adapter(
        [
            "get_editor_context",
            "get_selected_actors",
            "get_level_actors",
            "get_selected_assets",
            "get_static_mesh_details",
            "get_blueprint_graph",
            "get_widget_tree",
            "get_widget_details",
            "get_material_instance_parameters",
        ]
    ) as adapter:
        cases.append(_run_case("adapter_status_ready", adapter.status(), _status_ready))
        cases.append(_run_case("discover_readonly_tools", adapter.discover_tools(), _discover_readonly_ok))
        cases.append(
            _run_case(
                "call_get_editor_context",
                adapter.call_readonly_tool("get_editor_context", {}),
                _editor_context_call_ok,
            )
        )
        cases.append(
            _run_case(
                "call_get_selected_actors",
                adapter.call_readonly_tool("get_selected_actors", {}),
                _selected_actors_call_ok,
            )
        )
        cases.append(
            _run_case(
                "call_get_level_actors",
                adapter.call_readonly_tool("get_level_actors", {"class_contains": "Character", "tag": "Player", "limit": 20}),
                _level_actors_call_ok,
            )
        )
        cases.append(
            _run_case(
                "call_get_selected_assets",
                adapter.call_readonly_tool("get_selected_assets", {}),
                _selected_assets_call_ok,
            )
        )
        cases.append(
            _run_case(
                "call_get_static_mesh_details",
                adapter.call_readonly_tool("get_static_mesh_details", {"query": "SM_Rock"}),
                _static_mesh_details_call_ok,
            )
        )
        cases.append(
            _run_case(
                "call_get_blueprint_graph",
                adapter.call_readonly_tool(
                    "get_blueprint_graph",
                    {"blueprint_path": "/Game/Blueprints/BP_PlayerCharacter"},
                ),
                _blueprint_call_ok,
            )
        )
        cases.append(
            _run_case(
                "call_get_widget_tree",
                adapter.call_readonly_tool(
                    "get_widget_tree",
                    {"widget_blueprint_path": "/Game/UI/WBP_MainHUD"},
                ),
                _widget_call_ok,
            )
        )
        cases.append(
            _run_case(
                "call_get_widget_details",
                adapter.call_readonly_tool(
                    "get_widget_details",
                    {"widget_blueprint_path": "/Game/UI/WBP_MainHUD", "widget_name": "TitleText"},
                ),
                _widget_details_call_ok,
            )
        )
        cases.append(
            _run_case(
                "call_get_material_instance_parameters",
                adapter.call_readonly_tool(
                    "get_material_instance_parameters",
                    {"material_instance_path": "/Game/Materials/MI_Player"},
                ),
                _material_parameters_call_ok,
            )
        )
        cases.append(
            _run_case(
                "block_raw_write_by_allowlist",
                adapter.call_readonly_tool("rename_asset", {"asset_path": "/Game/A", "new_name": "B"}),
                _write_blocked_by_allowlist,
            )
        )
    with _fixture_adapter(["rename_asset"]) as adapter:
        cases.append(
            _run_case(
                "raw_write_rejected_by_ue_tool_server",
                adapter.call_readonly_tool("rename_asset", {"asset_path": "/Game/A", "new_name": "B"}),
                _raw_write_rejected_by_server,
            )
        )
    return cases


def main() -> int:
    args = _parse_args()
    cases = _run_smoke()
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "deterministic_no_ue_no_llm_tcp_fixture",
        "overall_ok": all(item["ok"] for item in cases),
        "summary": {
            "case_count": len(cases),
            "passed": sum(1 for item in cases if item["ok"]),
            "failed": sum(1 for item in cases if not item["ok"]),
        },
        "cases": cases,
        "notes": [
            "This smoke emulates the UEAgentTool JSON-RPC line TCP tool server.",
            "It validates backend MCP TCP adapter compatibility for read-only editor sensing tools.",
            "It does not launch Unreal Editor, execute editor writes, or call a live LLM.",
            "Write tools should still use the HTTP Proposal confirmation flow.",
        ],
    }
    _emit_report(report, args.output)
    return 0 if report["overall_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
