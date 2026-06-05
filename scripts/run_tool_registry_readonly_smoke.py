from __future__ import annotations

import argparse
import json
import os
import shutil
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.core.settings import get_settings
from app.db.session import get_engine, get_session_factory
from app.main import create_app


Validator = Callable[[dict[str, Any]], tuple[bool, str]]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run deterministic local Tool Registry read-only call smoke checks."
    )
    parser.add_argument(
        "--output",
        default="storage/artifacts/smoke/tool-registry-readonly-smoke-latest.json",
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


@contextmanager
def _isolated_runtime() -> Iterator[None]:
    runtime_root = Path(".smoke-runtime") / f"tool-registry-readonly-{uuid.uuid4().hex}"
    storage_dir = runtime_root / "storage"
    shutil.rmtree(runtime_root, ignore_errors=True)
    storage_dir.mkdir(parents=True, exist_ok=True)
    overrides = {
        "DATABASE_URL": "sqlite+pysqlite:///:memory:",
        "STORAGE_DIR": str(storage_dir.resolve()),
        "UPLOAD_DIR": str((storage_dir / "uploads").resolve()),
        "ARTIFACT_DIR": str((storage_dir / "artifacts").resolve()),
        "KB_DIR": str((storage_dir / "kb").resolve()),
        "KB_SOURCE_PATHS": "./knowledge",
        "EMBEDDING_ENABLED": "false",
        "OPENAI_API_KEY": "",
        "MCP_TOOL_ADAPTER_ENABLED": "false",
    }
    previous = {key: os.environ.get(key) for key in overrides}
    for key, value in overrides.items():
        os.environ[key] = value
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()
        get_engine.cache_clear()
        get_session_factory.cache_clear()
        shutil.rmtree(runtime_root, ignore_errors=True)


def _seed_inventory(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/v1/project-inventory/snapshot",
        json={
            "project_id": "ReadonlyToolDemo",
            "project_name": "ReadonlyToolDemo",
            "assets": [
                {
                    "asset_path": "/Game/Blueprints/BP_PlayerCharacter.BP_PlayerCharacter",
                    "asset_name": "BP_PlayerCharacter",
                    "asset_type": "Blueprint",
                    "package_path": "/Game/Blueprints",
                    "blueprint": {
                        "parent_class": "ACharacter",
                        "components": ["CapsuleComponent", "CameraBoom", "FollowCamera"],
                        "variables": ["Health", "MoveSpeed"],
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
                                    {
                                        "node_id": "EventBeginPlay",
                                        "title": "Event BeginPlay",
                                        "node_class": "K2Node_Event",
                                        "pins": [
                                            {
                                                "pin_name": "then",
                                                "direction": "output",
                                                "linked_to": [
                                                    {"node_id": "PrintString_1", "pin_name": "execute"}
                                                ],
                                            }
                                        ],
                                    },
                                    {
                                        "node_id": "PrintString_1",
                                        "title": "Print String",
                                        "node_class": "K2Node_CallFunction",
                                        "pins": [
                                            {
                                                "pin_name": "execute",
                                                "direction": "input",
                                                "linked_to": [
                                                    {"node_id": "EventBeginPlay", "pin_name": "then"}
                                                ],
                                            },
                                            {"pin_name": "InString", "direction": "input", "default_value": "Hello"},
                                        ],
                                    },
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
                                {
                                    "name": "TitleText",
                                    "class": "TextBlock",
                                    "parent": "RootCanvas",
                                    "slot": {
                                        "type": "CanvasPanelSlot",
                                        "position": {"x": 20, "y": 30},
                                        "size": {"x": 300, "y": 48},
                                    },
                                    "properties": {"text": "Mission Ready", "visibility": "Visible"},
                                    "style": {"opacity": 0.85},
                                },
                            ],
                        }
                    },
                },
            ],
            "level_actors": [
                {
                    "actor_label": "BP_EnemySpawner_1",
                    "actor_name": "BP_EnemySpawner_C_1",
                    "actor_class": "BP_EnemySpawner_C",
                    "level_name": "DemoMap",
                    "folder_path": "Gameplay",
                    "transform": {"location": {"x": 100, "y": 0, "z": 20}},
                    "components": [{"component_name": "SceneRoot", "component_class": "SceneComponent"}],
                    "tags": ["Spawner"],
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
    body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    return {"ok": response.status_code == 200, "status_code": response.status_code, "body": body}


def _call_tool(client: TestClient, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/mcp/tool-registry/tools/{tool}/call",
        json={"arguments": arguments},
    )
    body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    return {"status_code": response.status_code, "body": body}


def _manifest_has_local_readonly_call(body: dict[str, Any]) -> tuple[bool, str]:
    manifest = body.get("manifest") or {}
    route_ok = manifest.get("routes", {}).get("local_readonly_tool_call") == (
        "POST /api/v1/mcp/tool-registry/tools/{tool}/call"
    )
    safety_ok = manifest.get("safety_policy", {}).get("read_only_local_tool_registry_call_allowed") is True
    tools = {
        item.get("annotations", {}).get("tool_id"): item.get("annotations", {})
        for item in list(manifest.get("tools") or [])
        if isinstance(item, dict)
    }
    metadata_ok = (
        tools.get("editor_arrange_actors_pattern", {}).get("frontend_executor_id") == "arrange_actors_pattern"
        and tools.get("editor_inspect_material_instance_detail", {}).get("operation_family") == "material"
    )
    return route_ok and safety_ok and metadata_ok, "manifest exposes local route, safety flag, and tool metadata"


def _blueprint_graph_ok(body: dict[str, Any]) -> tuple[bool, str]:
    content = body.get("call", {}).get("result", {}).get("structuredContent", {})
    graphs = list(content.get("graphs") or [])
    ok = (
        body.get("success") is True
        and content.get("graph_metrics", {}).get("graph_count") == 1
        and graphs
        and graphs[0].get("graph_name") == "EventGraph"
    )
    return ok, "blueprint graph call returns EventGraph inventory"


def _blueprint_node_detail_ok(body: dict[str, Any]) -> tuple[bool, str]:
    content = body.get("call", {}).get("result", {}).get("structuredContent", {})
    linked = list(content.get("linked_pins") or [])
    ok = (
        body.get("success") is True
        and content.get("graph_name") == "EventGraph"
        and content.get("node_id") == "PrintString_1"
        and content.get("node_class") == "K2Node_CallFunction"
        and bool(linked)
        and linked[0].get("target_node_id") == "EventBeginPlay"
    )
    return ok, "blueprint node detail call returns node class, pins, and links"


def _widget_tree_ok(body: dict[str, Any]) -> tuple[bool, str]:
    content = body.get("call", {}).get("result", {}).get("structuredContent", {})
    ok = body.get("success") is True and content.get("widget_count") == 2
    return ok, "widget tree call returns submitted Widget Blueprint hierarchy"


def _umg_widget_detail_ok(body: dict[str, Any]) -> tuple[bool, str]:
    content = body.get("call", {}).get("result", {}).get("structuredContent", {})
    ok = (
        body.get("success") is True
        and content.get("widget_name") == "TitleText"
        and content.get("widget_class") == "TextBlock"
        and content.get("parent_widget_name") == "RootCanvas"
        and (content.get("slot") or {}).get("type") == "CanvasPanelSlot"
        and (content.get("properties") or {}).get("text") == "Mission Ready"
    )
    return ok, "UMG widget detail call returns class, parent, slot, and properties"


def _actor_inventory_ok(body: dict[str, Any]) -> tuple[bool, str]:
    items = list(body.get("call", {}).get("result", {}).get("items") or [])
    ok = body.get("success") is True and bool(items) and items[0].get("actor_label") == "BP_EnemySpawner_1"
    return ok, "level actor call returns submitted actor"


def _material_detail_ok(body: dict[str, Any]) -> tuple[bool, str]:
    item = body.get("call", {}).get("result", {}).get("item") or {}
    scalars = list(item.get("scalar_parameters") or [])
    ok = body.get("success") is True and bool(scalars) and scalars[0].get("name") == "Roughness"
    return ok, "material detail call returns scalar parameter"


def _write_tool_blocked(body: dict[str, Any]) -> tuple[bool, str]:
    call = body.get("call") or {}
    ok = body.get("success") is False and call.get("reason") == "tool_is_not_read_only"
    return ok, "confirmed-write tool is blocked from local read-only call endpoint"


def _case_specs() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "manifest_local_readonly_boundary",
            "kind": "manifest",
            "validator": _manifest_has_local_readonly_call,
        },
        {
            "case_id": "call_blueprint_graph_inventory",
            "tool": "get_blueprint_graph",
            "arguments": {
                "project_id": "ReadonlyToolDemo",
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "graph_name": "EventGraph",
            },
            "validator": _blueprint_graph_ok,
        },
        {
            "case_id": "call_blueprint_node_detail_inventory",
            "tool": "editor_inspect_blueprint_node_detail",
            "arguments": {
                "project_id": "ReadonlyToolDemo",
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "graph_name": "EventGraph",
                "node_title": "Print String",
            },
            "validator": _blueprint_node_detail_ok,
        },
        {
            "case_id": "call_widget_tree_inventory",
            "tool": "get_widget_tree",
            "arguments": {
                "project_id": "ReadonlyToolDemo",
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
            },
            "validator": _widget_tree_ok,
        },
        {
            "case_id": "call_umg_widget_detail_inventory",
            "tool": "editor_inspect_umg_widget_detail",
            "arguments": {
                "project_id": "ReadonlyToolDemo",
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "TitleText",
            },
            "validator": _umg_widget_detail_ok,
        },
        {
            "case_id": "call_level_actor_inventory",
            "tool": "editor_inspect_level_actors",
            "arguments": {"project_id": "ReadonlyToolDemo", "query": "EnemySpawner"},
            "validator": _actor_inventory_ok,
        },
        {
            "case_id": "call_material_detail_inventory",
            "tool": "editor_inspect_material_instance_detail",
            "arguments": {"project_id": "ReadonlyToolDemo", "material_instance_path": "MI_Rock"},
            "validator": _material_detail_ok,
        },
        {
            "case_id": "block_confirmed_write_tool",
            "tool": "editor_set_actor_transform",
            "arguments": {"actor_reference": "BP_EnemySpawner_1"},
            "validator": _write_tool_blocked,
        },
    ]


def _run_case(client: TestClient, spec: dict[str, Any]) -> dict[str, Any]:
    if spec.get("kind") == "manifest":
        response = client.get("/api/v1/mcp/tool-registry/manifest")
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        payload = {"status_code": response.status_code, "body": body}
    else:
        payload = _call_tool(client, str(spec["tool"]), dict(spec.get("arguments") or {}))

    validator: Validator = spec["validator"]
    ok, reason = validator(payload["body"])
    return {
        "case_id": spec["case_id"],
        "ok": ok and payload["status_code"] == 200,
        "status_code": payload["status_code"],
        "reason": reason,
        "tool": spec.get("tool", ""),
        "summary": {
            "success": payload["body"].get("success"),
            "call_reason": payload["body"].get("call", {}).get("reason"),
            "manifest_tool_count": payload["body"].get("manifest", {}).get("summary", {}).get("tool_count"),
        },
    }


def main() -> int:
    args = _parse_args()
    with _isolated_runtime():
        with TestClient(create_app()) as client:
            seed = _seed_inventory(client)
            cases = [_run_case(client, spec) for spec in _case_specs()] if seed["ok"] else []

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "deterministic_no_ue_no_llm",
        "overall_ok": bool(seed["ok"]) and all(item["ok"] for item in cases),
        "summary": {
            "case_count": len(cases),
            "passed": sum(1 for item in cases if item["ok"]),
            "failed": sum(1 for item in cases if not item["ok"]),
        },
        "seed_inventory": seed,
        "cases": cases,
        "notes": [
            "This smoke validates the local Tool Registry read-only call endpoint.",
            "It does not enable an external MCP server, launch Unreal Editor, or call a live LLM.",
            "Confirmed-write tools must still become Proposals and are expected to be blocked here.",
        ],
    }
    _emit_report(report, args.output)
    return 0 if report["overall_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
