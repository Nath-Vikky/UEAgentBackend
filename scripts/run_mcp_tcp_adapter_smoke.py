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
        "name": "get_selected_assets",
        "description": "Read currently selected Content Browser assets.",
        "inputSchema": {"type": "object", "properties": {}},
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
                    },
                    {
                        "actor_label": "BP_PatrolPoint_1",
                        "actor_name": "BP_PatrolPoint_C_1",
                        "actor_class": "/Game/Blueprints/BP_PatrolPoint.BP_PatrolPoint_C",
                        "actor_path": "PersistentLevel.BP_PatrolPoint_C_1",
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
                "selected_asset_count": 2,
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
                ],
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
                    {"name": "TitleText", "class": "TextBlock", "parent": "RootCanvas"},
                ],
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
            "get_selected_assets",
            "get_blueprint_graph",
            "get_widget_tree",
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
    )
    return ok, "TCP call returns selected actor structuredContent"


def _selected_assets_call_ok(payload: dict[str, Any]) -> tuple[bool, str]:
    structured = payload.get("result", {}).get("structuredContent", {})
    ok = (
        payload.get("ok") is True
        and structured.get("asset_selection_schema_version") == "ue_agent_tool_selected_assets_fixture_v1"
        and structured.get("selected_asset_count") == 2
    )
    return ok, "TCP call returns selected asset structuredContent"


def _widget_call_ok(payload: dict[str, Any]) -> tuple[bool, str]:
    structured = payload.get("result", {}).get("structuredContent", {})
    ok = payload.get("ok") is True and structured.get("root") == "RootCanvas"
    return ok, "TCP call returns Widget tree structuredContent"


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
        ["get_editor_context", "get_selected_actors", "get_selected_assets", "get_blueprint_graph", "get_widget_tree"]
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
                "call_get_selected_assets",
                adapter.call_readonly_tool("get_selected_assets", {}),
                _selected_assets_call_ok,
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
