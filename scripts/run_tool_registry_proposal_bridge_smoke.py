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
        description="Run deterministic Tool Registry confirmed-write Proposal bridge smoke checks."
    )
    parser.add_argument(
        "--output",
        default="storage/artifacts/smoke/tool-registry-proposal-bridge-smoke-latest.json",
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
    runtime_root = Path(".smoke-runtime") / f"tool-registry-proposal-{uuid.uuid4().hex}"
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


def _post_proposal(client: TestClient, *, tool_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        "/api/v1/mcp/tool-registry/proposals",
        json={
            "tool_id": tool_id,
            "arguments": arguments,
            "reason": f"Smoke-test Tool Registry Proposal bridge for {tool_id}.",
            "requested_by": "tool_registry_proposal_bridge_smoke",
            "context": {"demo_source": "mcp_compatible_tool_registry_smoke"},
        },
    )
    body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    return {"status_code": response.status_code, "body": body}


def _post_prepare(client: TestClient, *, tool_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        "/api/v1/mcp/tool-registry/proposals/prepare",
        json={
            "tool_id": tool_id,
            "arguments": arguments,
            "requested_by": "tool_registry_proposal_bridge_smoke",
        },
    )
    body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    return {"status_code": response.status_code, "body": body}


def _manifest_boundary_ok(body: dict[str, Any]) -> tuple[bool, str]:
    manifest = body.get("manifest") or {}
    routes = manifest.get("routes") or {}
    safety = manifest.get("safety_policy") or {}
    tools = {
        item.get("annotations", {}).get("tool_id"): item.get("annotations", {})
        for item in list(manifest.get("tools") or [])
        if isinstance(item, dict)
    }
    ok = (
        routes.get("confirmed_write_proposal_prepare") == "POST /api/v1/mcp/tool-registry/proposals/prepare"
        and routes.get("confirmed_write_proposal_create") == "POST /api/v1/mcp/tool-registry/proposals"
        and safety.get("confirmed_write_direct_mcp_call_allowed") is False
        and tools.get("editor_add_blueprint_node_template", {}).get("execution_boundary", {}).get("mode")
        == "confirmed_write_proposal"
    )
    return ok, "manifest exposes confirmed-write proposal bridge and direct-write block"


def _profile_manifest_ok(body: dict[str, Any]) -> tuple[bool, str]:
    manifest = body.get("manifest") or {}
    tools = {
        item.get("annotations", {}).get("tool_id"): item.get("annotations", {})
        for item in list(manifest.get("tools") or [])
        if isinstance(item, dict)
    }
    ok = (
        manifest.get("filters", {}).get("profile") == "umg_demo"
        and manifest.get("profiles", {}).get("selected", {}).get("profile_id") == "umg_demo"
        and bool(manifest.get("profiles", {}).get("selected", {}).get("suggested_prompts"))
        and bool(manifest.get("profiles", {}).get("selected", {}).get("sample_tool_calls"))
        and "mcp_get_widget_tree" in tools
        and "editor_add_umg_widget" in tools
        and "editor_set_umg_widget_text" in tools
        and "editor_set_material_instance_parameter" not in tools
    )
    return ok, "profile manifest exposes a compact UMG demo tool set"


def _proposal_ok(expected_operation_type: str, expected_tool_id: str) -> Validator:
    def _validate(body: dict[str, Any]) -> tuple[bool, str]:
        proposal = body.get("proposal") or {}
        operation = body.get("proposal", {}).get("operation") or body.get("operation") or {}
        item = proposal.get("item") or body.get("item") or {}
        bridge = body.get("bridge") or {}
        ok = (
            body.get("success") is True
            and bridge.get("status") == "prepared"
            and bridge.get("auto_execute") is False
            and bridge.get("direct_editor_write_allowed") is False
            and operation.get("operation_type") == expected_operation_type
            and operation.get("tool_id") == expected_tool_id
            and item.get("confirmation", {}).get("state") == "pending"
        )
        return ok, f"{expected_tool_id} creates pending {expected_operation_type} Proposal"

    return _validate


def _readonly_prepare_blocked(body: dict[str, Any]) -> tuple[bool, str]:
    bridge = body.get("bridge") or {}
    errors = list(body.get("errors") or [])
    ok = (
        body.get("success") is False
        and bridge.get("status") == "blocked"
        and bridge.get("block_reason") == "tool_is_not_confirmed_write"
        and errors
        and errors[0].get("code") == "tool_is_not_confirmed_write"
    )
    return ok, "read-only tool cannot be converted to confirmed-write Proposal"


def _case_specs() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "manifest_confirmed_write_proposal_boundary",
            "kind": "manifest",
            "validator": _manifest_boundary_ok,
        },
        {
            "case_id": "manifest_umg_demo_profile",
            "kind": "manifest_profile",
            "profile": "umg_demo",
            "validator": _profile_manifest_ok,
        },
        {
            "case_id": "create_blueprint_add_step_alias_proposal",
            "tool_id": "editor_blueprint_add_step",
            "arguments": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "step_name": "PrintString",
                "graph_name": "EventGraph",
                "entry_event": "BeginPlay",
                "text": "Hello from UEAgent",
                "compile_after_edit": True,
            },
            "validator": _proposal_ok("add_blueprint_node_template", "editor_add_blueprint_node_template"),
        },
        {
            "case_id": "create_umg_text_widget_proposal",
            "tool_id": "editor_add_umg_widget",
            "arguments": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "TitleText",
                "widget_class": "TextBlock",
                "parent_widget_name": "RootCanvas",
                "text": "Mission Ready",
            },
            "validator": _proposal_ok("add_umg_widget", "editor_add_umg_widget"),
        },
        {
            "case_id": "create_material_scalar_proposal",
            "tool_id": "editor_set_material_instance_parameter",
            "arguments": {
                "material_instance_path": "/Game/Materials/MI_Player",
                "parameter_name": "Roughness",
                "parameter_type": "scalar",
                "value": 0.35,
            },
            "validator": _proposal_ok("set_material_instance_parameter", "editor_set_material_instance_parameter"),
        },
        {
            "case_id": "create_level_actor_place_proposal",
            "tool_id": "editor_place_actor_in_level",
            "arguments": {
                "actor_class": "/Script/Engine.PointLight",
                "actor_label": "KeyLight_A",
                "transform": {
                    "location": {"x": 120.0, "y": 50.0, "z": 300.0},
                    "rotation": {"pitch": -25.0, "yaw": 45.0, "roll": 0.0},
                    "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                },
            },
            "validator": _proposal_ok("place_actor_in_level", "editor_place_actor_in_level"),
        },
        {
            "case_id": "block_readonly_tool_from_proposal_bridge",
            "kind": "prepare",
            "tool_id": "mcp_get_blueprint_graph",
            "arguments": {"blueprint_path": "/Game/Blueprints/BP_PlayerCharacter"},
            "validator": _readonly_prepare_blocked,
        },
    ]


def _run_case(client: TestClient, spec: dict[str, Any]) -> dict[str, Any]:
    if spec.get("kind") == "manifest":
        response = client.get("/api/v1/mcp/tool-registry/manifest?side_effect_level=confirmed_write")
        payload = {
            "status_code": response.status_code,
            "body": response.json() if response.headers.get("content-type", "").startswith("application/json") else {},
        }
    elif spec.get("kind") == "manifest_profile":
        response = client.get(f"/api/v1/mcp/tool-registry/manifest?profile={spec['profile']}")
        payload = {
            "status_code": response.status_code,
            "body": response.json() if response.headers.get("content-type", "").startswith("application/json") else {},
        }
    elif spec.get("kind") == "prepare":
        payload = _post_prepare(client, tool_id=str(spec["tool_id"]), arguments=dict(spec.get("arguments") or {}))
    else:
        payload = _post_proposal(client, tool_id=str(spec["tool_id"]), arguments=dict(spec.get("arguments") or {}))

    validator: Validator = spec["validator"]
    valid, reason = validator(payload["body"])
    body = payload["body"]
    operation = (body.get("proposal") or {}).get("operation") or {}
    return {
        "case_id": spec["case_id"],
        "ok": valid and payload["status_code"] == 200,
        "status_code": payload["status_code"],
        "reason": reason,
        "tool_id": spec.get("tool_id", ""),
        "summary": {
            "success": body.get("success"),
            "bridge_status": (body.get("bridge") or {}).get("status"),
            "operation_type": operation.get("operation_type"),
            "confirmation_state": ((body.get("proposal") or {}).get("item") or {}).get("confirmation", {}).get("state"),
            "error_code": (list(body.get("errors") or [{}])[0] or {}).get("code"),
        },
    }


def main() -> int:
    args = _parse_args()
    with _isolated_runtime():
        with TestClient(create_app()) as client:
            cases = [_run_case(client, spec) for spec in _case_specs()]

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "deterministic_no_ue_no_llm",
        "overall_ok": all(item["ok"] for item in cases),
        "summary": {
            "case_count": len(cases),
            "passed": sum(1 for item in cases if item["ok"]),
            "failed": sum(1 for item in cases if not item["ok"]),
        },
        "cases": cases,
        "notes": [
            "This smoke simulates MCP/Tool Registry clients requesting editor writes.",
            "It creates pending Proposals only; it does not launch Unreal Editor or execute editor writes.",
            "Read-only tools are intentionally blocked from the confirmed-write Proposal bridge.",
        ],
    }
    _emit_report(report, args.output)
    return 0 if report["overall_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
