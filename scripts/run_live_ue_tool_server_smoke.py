from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.settings import Settings
from app.services.mcp_tool_adapter import MCPToolAdapter


DEFAULT_ALLOWED_TOOLS = (
    "ue_agent_tools_list,get_editor_context,get_selected_assets,get_asset_details,get_selected_actors,"
    "get_level_actors,get_level_actor_details,get_static_mesh_details,get_blueprint_graph,get_blueprint_node_details,"
    "get_widget_tree,get_widget_details,get_material_instance_parameters"
)


def _parse_csv(text: str) -> list[str]:
    return [item.strip() for item in str(text or "").split(",") if item.strip()]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an optional live smoke against the UEAgentTool TCP editor tool server."
    )
    parser.add_argument("--host", default="127.0.0.1", help="UEAgentTool TCP host.")
    parser.add_argument("--port", type=int, default=8765, help="UEAgentTool TCP port.")
    parser.add_argument(
        "--allowed-tools",
        default=DEFAULT_ALLOWED_TOOLS,
        help="Comma-separated MCP allow-list. Keep this read-only for live smoke.",
    )
    parser.add_argument(
        "--blueprint-path",
        default="",
        help="Optional Blueprint path to call get_blueprint_graph, e.g. /Game/Blueprints/BP_Player.",
    )
    parser.add_argument(
        "--actor-reference",
        default="",
        help="Optional Actor label/name/path to call get_level_actor_details, e.g. BP_PlayerCharacter_1.",
    )
    parser.add_argument(
        "--asset-query",
        default="",
        help="Optional asset path/name/query to call get_asset_details, e.g. BP_PlayerCharacter.",
    )
    parser.add_argument(
        "--blueprint-graph-name",
        default="",
        help="Optional Blueprint graph name for focused graph/node calls, e.g. EventGraph.",
    )
    parser.add_argument(
        "--blueprint-node-query",
        default="",
        help="Optional node title/id/name to call get_blueprint_node_details, e.g. Print String.",
    )
    parser.add_argument(
        "--widget-blueprint-path",
        default="",
        help="Optional Widget Blueprint path to call get_widget_tree, e.g. /Game/UI/WBP_MainHUD.",
    )
    parser.add_argument(
        "--widget-name",
        default="",
        help="Optional Widget name to call get_widget_details together with --widget-blueprint-path, e.g. TitleText.",
    )
    parser.add_argument(
        "--material-instance-path",
        default="",
        help="Optional Material Instance path to call get_material_instance_parameters, e.g. /Game/Materials/MI_Player.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=3000,
        help="TCP request timeout in milliseconds.",
    )
    parser.add_argument(
        "--output",
        default="storage/artifacts/smoke/live-ue-tool-server-smoke-latest.json",
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
        print(f"WARNING: could not write live smoke report to {output_path}: {exc}")
    print(report_json)


def _settings(args: argparse.Namespace) -> Settings:
    return Settings(
        mcp_tool_adapter_enabled=True,
        mcp_transport="tcp",
        mcp_tcp_host=str(args.host or "127.0.0.1"),
        mcp_tcp_port=int(args.port),
        mcp_tcp_timeout_ms=max(int(args.timeout_ms), 100),
        mcp_allowed_tools=_parse_csv(args.allowed_tools),
    )


def _case(case_id: str, payload: dict[str, Any], *, expect_tool_error: bool = False) -> dict[str, Any]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    is_tool_error = result.get("isError") is True
    ok = bool(payload.get("ok")) and (expect_tool_error or not is_tool_error)
    return {
        "case_id": case_id,
        "ok": ok,
        "summary": {
            "status": payload.get("status"),
            "reason": payload.get("reason"),
            "tool_name": payload.get("tool_name"),
            "transport": payload.get("transport") or payload.get("debug", {}).get("adapter", {}).get("transport"),
            "is_tool_error": is_tool_error,
            "tool_text": _first_content_text(result),
        },
    }


def _first_content_text(result: dict[str, Any]) -> str:
    content = result.get("content") if isinstance(result.get("content"), list) else []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            return str(item.get("text") or "")[:500]
    return ""


def _run_smoke(args: argparse.Namespace) -> list[dict[str, Any]]:
    adapter = MCPToolAdapter(_settings(args))
    cases = [_case("discover_tools", adapter.discover_tools())]
    allowed_tools = set(_parse_csv(args.allowed_tools))
    if "ue_agent_tools_list" in allowed_tools:
        cases.append(_case("call_ue_agent_tools_list", adapter.call_readonly_tool("ue_agent_tools_list", {})))
    if "get_editor_context" in allowed_tools:
        cases.append(_case("call_get_editor_context", adapter.call_readonly_tool("get_editor_context", {})))
    if "get_selected_assets" in allowed_tools:
        cases.append(_case("call_get_selected_assets", adapter.call_readonly_tool("get_selected_assets", {})))
    if args.asset_query and "get_asset_details" in allowed_tools:
        cases.append(
            _case(
                "call_get_asset_details",
                adapter.call_readonly_tool("get_asset_details", {"query": args.asset_query}),
            )
        )
    if "get_static_mesh_details" in allowed_tools:
        cases.append(
            _case(
                "call_get_static_mesh_details",
                adapter.call_readonly_tool("get_static_mesh_details", {}),
                expect_tool_error=True,
            )
        )
    if "get_selected_actors" in allowed_tools:
        cases.append(_case("call_get_selected_actors", adapter.call_readonly_tool("get_selected_actors", {})))
    if "get_level_actors" in allowed_tools:
        cases.append(_case("call_get_level_actors", adapter.call_readonly_tool("get_level_actors", {"limit": 40})))
    if args.actor_reference and "get_level_actor_details" in allowed_tools:
        cases.append(
            _case(
                "call_get_level_actor_details",
                adapter.call_readonly_tool(
                    "get_level_actor_details",
                    {"actor_reference": args.actor_reference},
                ),
            )
        )
    if args.blueprint_path:
        cases.append(
            _case(
                "call_get_blueprint_graph",
                adapter.call_readonly_tool("get_blueprint_graph", {"blueprint_path": args.blueprint_path}),
            )
        )
        if args.blueprint_node_query and "get_blueprint_node_details" in allowed_tools:
            node_args = {
                "blueprint_path": args.blueprint_path,
                "node_query": args.blueprint_node_query,
            }
            if args.blueprint_graph_name:
                node_args["graph_name"] = args.blueprint_graph_name
            cases.append(
                _case(
                    "call_get_blueprint_node_details",
                    adapter.call_readonly_tool("get_blueprint_node_details", node_args),
                )
            )
    if args.widget_blueprint_path:
        cases.append(
            _case(
                "call_get_widget_tree",
                adapter.call_readonly_tool(
                    "get_widget_tree",
                    {"widget_blueprint_path": args.widget_blueprint_path},
                ),
            )
        )
        if args.widget_name and "get_widget_details" in allowed_tools:
            cases.append(
                _case(
                    "call_get_widget_details",
                    adapter.call_readonly_tool(
                        "get_widget_details",
                        {"widget_blueprint_path": args.widget_blueprint_path, "widget_name": args.widget_name},
                    ),
                )
            )
    if "get_material_instance_parameters" in allowed_tools:
        material_args = {}
        if args.material_instance_path:
            material_args["material_instance_path"] = args.material_instance_path
        cases.append(
            _case(
                "call_get_material_instance_parameters",
                adapter.call_readonly_tool("get_material_instance_parameters", material_args),
            )
        )
    return cases


def main() -> int:
    args = _parse_args()
    cases = _run_smoke(args)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "optional_live_ueagenttool_tcp",
        "overall_ok": all(item["ok"] for item in cases),
        "summary": {
            "case_count": len(cases),
            "passed": sum(1 for item in cases if item["ok"]),
            "failed": sum(1 for item in cases if not item["ok"]),
        },
        "connection": {
            "host": args.host,
            "port": args.port,
            "timeout_ms": args.timeout_ms,
            "allowed_tools": _parse_csv(args.allowed_tools),
            "actor_reference": args.actor_reference,
            "blueprint_path": args.blueprint_path,
            "blueprint_graph_name": args.blueprint_graph_name,
            "blueprint_node_query": args.blueprint_node_query,
            "widget_blueprint_path": args.widget_blueprint_path,
            "material_instance_path": args.material_instance_path,
        },
        "cases": cases,
        "notes": [
            "This smoke requires the UEAgentTool editor tool TCP server to be running.",
            "It does not execute write tools; keep the allow-list read-only.",
            "Confirmed-write editor operations should still use HTTP Proposal Bridge.",
        ],
    }
    _emit_report(report, args.output)
    return 0 if report["overall_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
