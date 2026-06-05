from __future__ import annotations

import argparse
import json
import os
import shutil
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.core.settings import get_settings
from app.db.session import get_engine, get_session_factory
from app.main import create_app


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run deterministic Project Inventory -> Agent Chat grounding smoke checks."
    )
    parser.add_argument(
        "--output",
        default="storage/artifacts/smoke/project-inventory-chat-smoke-latest.json",
        help="JSON report output path. Use '-' to print to stdout without writing a file.",
    )
    return parser.parse_args()


def _emit_report(report: dict[str, Any], output: str) -> None:
    report_json = json.dumps(report, indent=2, ensure_ascii=False)
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
    runtime_root = Path(".smoke-runtime") / f"project-inventory-chat-{uuid.uuid4().hex}"
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


def _check(name: str, expected: Any, actual: Any) -> dict[str, Any]:
    return {"name": name, "ok": expected == actual, "expected": expected, "actual": actual}


def _contains(name: str, needle: str, haystack: str) -> dict[str, Any]:
    return {"name": name, "ok": needle in haystack, "expected": f"contains {needle}", "actual": haystack}


def _react_validation_details(body: dict[str, Any]) -> dict[str, Any]:
    react_trace = dict(body.get("debug_view", {}).get("react_trace") or {})
    for step in react_trace.get("steps") or []:
        if not isinstance(step, dict):
            continue
        if step.get("phase") == "validation":
            return dict(step.get("details") or {})
    return {}


def _seed_inventory(client: TestClient) -> Any:
    return client.post(
        "/api/v1/project-inventory/snapshot",
        json={
            "project_id": "GraphSmokeProject",
            "project_name": "GraphSmokeProject",
            "assets": [
                {
                    "asset_path": "/Game/Blueprints/BP_PlayerCharacter.BP_PlayerCharacter",
                    "asset_name": "BP_PlayerCharacter",
                    "asset_type": "Blueprint",
                    "blueprint": {
                        "parent_class": "ACharacter",
                        "graphs": ["EventGraph"],
                        "graph_summaries": [
                            {
                                "graph_name": "EventGraph",
                                "graph_type": "event",
                                "node_count": 2,
                                "pin_count": 5,
                                "link_count": 1,
                                "nodes": [
                                    {
                                        "node_id": "event-begin-play",
                                        "node_name": "K2Node_Event_0",
                                        "node_class": "K2Node_Event",
                                        "title": "Event BeginPlay",
                                    },
                                    {
                                        "node_id": "print-string",
                                        "node_name": "K2Node_CallFunction_0",
                                        "node_class": "K2Node_CallFunction",
                                        "title": "Print String",
                                    },
                                ],
                            }
                        ],
                    },
                }
            ],
        },
    )


def _run_blueprint_graph_chat_grounding(client: TestClient, snapshot_response: Any) -> dict[str, Any]:
    graph_response = client.get(
        "/api/v1/project-inventory/blueprint-graphs",
        params={"project_id": "GraphSmokeProject", "blueprint_query": "BP_PlayerCharacter", "include_nodes": True},
    )
    query = "In the current project, what nodes are in BP_PlayerCharacter EventGraph?"
    chat_response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "project_inventory_chat_smoke_session",
                "messages": [{"role": "user", "content": query, "language": "auto"}],
            },
            "context": {"project_name": "GraphSmokeProject", "active_panel": "AgentChat"},
            "payload": {"user_query": query},
            "ui_state": {"active_view": "user", "selected_panel": "AgentChat"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )
    body = chat_response.json()
    graph_body = graph_response.json()
    assistant_message = str(body.get("assistant_message") or "")
    react_trace = dict(body.get("debug_view", {}).get("react_trace") or {})
    react_phases = [str(step.get("phase") or "") for step in react_trace.get("steps") or [] if isinstance(step, dict)]
    validation_details = _react_validation_details(body)
    checks = [
        _check("snapshot_status_code", 200, snapshot_response.status_code),
        _check("graph_status_code", 200, graph_response.status_code),
        _check("chat_status_code", 200, chat_response.status_code),
        _check("route_type", "project_qa", body.get("intent", {}).get("route_type")),
        _check("selected_tool_id", "query_project_inventory", body.get("debug_view", {}).get("route", {}).get("selected_tool_id")),
        _check("graph_endpoint_item_count", 1, len(graph_body.get("items") or [])),
        _check("graph_endpoint_node_count", 2, (graph_body.get("items") or [{}])[0].get("node_count")),
        _contains("assistant_mentions_event_graph", "EventGraph", assistant_message),
        _contains("assistant_mentions_begin_play", "Event BeginPlay", assistant_message),
        _contains("assistant_mentions_print_string", "Print String", assistant_message),
        _check("react_trace_version", "react_v2_trace_v1", react_trace.get("version")),
        _check("react_trace_display_safe", False, react_trace.get("boundary", {}).get("raw_chain_of_thought_exposed")),
        _check("react_trace_has_validation_phase", True, "validation" in react_phases),
        _check("react_trace_validation_passed", True, react_trace.get("summary", {}).get("validation_passed")),
        _check("react_trace_output_complete", True, validation_details.get("output_complete")),
    ]
    return {
        "case_id": "blueprint_graph_chat_grounding",
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
    }


def _run_mcp_blueprint_graph_fallback(client: TestClient) -> dict[str, Any]:
    query = "Show the current Blueprint graph"
    chat_response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "mcp_blueprint_graph_fallback_smoke_session",
                "messages": [{"role": "user", "content": query, "language": "auto"}],
            },
            "context": {
                "project_name": "GraphSmokeProject",
                "active_panel": "AgentChat",
                "editor_state": {
                    "current_blueprint_path": "/Game/Blueprints/BP_PlayerCharacter.BP_PlayerCharacter",
                    "current_graph_name": "EventGraph",
                },
            },
            "payload": {"user_query": query},
            "ui_state": {"active_view": "user", "selected_panel": "AgentChat"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )
    body = chat_response.json()
    assistant_message = str(body.get("assistant_message") or "")
    debug_view = dict(body.get("debug_view") or {})
    checks = [
        _check("chat_status_code", 200, chat_response.status_code),
        _check("route_type", "single_tool", body.get("intent", {}).get("route_type")),
        _check("selected_tool_id", "mcp_get_blueprint_graph", debug_view.get("route", {}).get("selected_tool_id")),
        _check("retrieval_mode", "project_inventory_focus", body.get("retrieval_trace", {}).get("mode")),
        _contains("assistant_mentions_event_graph", "EventGraph", assistant_message),
        _contains("assistant_mentions_print_string", "Print String", assistant_message),
    ]
    return {
        "case_id": "mcp_blueprint_graph_fallback_to_inventory",
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
    }


def main() -> int:
    args = _parse_args()
    with _isolated_runtime(), TestClient(create_app()) as client:
        snapshot_response = _seed_inventory(client)
        if snapshot_response.status_code == 200:
            cases = [
                _run_blueprint_graph_chat_grounding(client, snapshot_response),
                _run_mcp_blueprint_graph_fallback(client),
            ]
        else:
            cases = [
                {
                    "case_id": "seed_inventory",
                    "ok": False,
                    "checks": [_check("snapshot_status_code", 200, snapshot_response.status_code)],
                }
            ]
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "deterministic_no_ue_no_llm",
        "overall_ok": all(item["ok"] for item in cases),
        "summary": {
            "case_count": len(cases),
            "passed": sum(1 for item in cases if item["ok"]),
            "failed": sum(1 for item in cases if not item["ok"]),
        },
        "checks": cases,
        "notes": [
            "This smoke test verifies Project Inventory grounding in Agent Chat.",
            "It does not launch Unreal Editor, execute editor writes, compile Blueprints, or call an LLM.",
            "Current-project graph facts must come from the submitted Project Inventory snapshot.",
        ],
    }
    _emit_report(report, args.output)
    return 0 if report["overall_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
