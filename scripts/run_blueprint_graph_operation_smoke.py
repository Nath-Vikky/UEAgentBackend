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
        description="Run deterministic Blueprint graph operation proposal smoke checks."
    )
    parser.add_argument(
        "--output",
        default="storage/artifacts/smoke/blueprint-graph-operation-smoke-latest.json",
        help="JSON report output path.",
    )
    return parser.parse_args()


@contextmanager
def _isolated_runtime() -> Iterator[None]:
    runtime_root = Path(".smoke-runtime") / f"blueprint-ops-{uuid.uuid4().hex}"
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


def _proposal_payload(
    operation_type: str,
    payload: dict[str, Any],
    *,
    reason: str = "Blueprint graph operation smoke check.",
) -> dict[str, Any]:
    return {
        "operation_type": operation_type,
        "payload": payload,
        "reason": reason,
        "requested_by": "blueprint_graph_operation_smoke",
    }


def _cases() -> list[dict[str, Any]]:
    blueprint_path = "/Game/Blueprints/BP_PlayerCharacter"
    return [
        {
            "case_id": "template_print_string",
            "request": _proposal_payload(
                "add_blueprint_node_template",
                {
                    "blueprint_path": blueprint_path,
                    "template_id": "print_string",
                    "graph_name": "EventGraph",
                    "message": "Hello from smoke",
                    "duration": 1.0,
                    "entry_event": "BeginPlay",
                    "compile_after_edit": True,
                },
            ),
            "expected_status": 200,
            "expected_tool_id": "editor_add_blueprint_node_template",
            "expected_payload": {
                "template_id": "print_string",
                "entry_event": "BeginPlay",
                "compile_after_edit": True,
            },
            "expected_result_fields": ["created_nodes", "linked_pins"],
        },
        {
            "case_id": "template_branch_print_string",
            "request": _proposal_payload(
                "add_blueprint_node_template",
                {
                    "blueprint_path": blueprint_path,
                    "template_id": "branch_print_string",
                    "graph_name": "EventGraph",
                    "message": "Branch smoke",
                    "condition_default": False,
                    "branch_path": "false",
                },
            ),
            "expected_status": 200,
            "expected_tool_id": "editor_add_blueprint_node_template",
            "expected_payload": {
                "template_id": "branch_print_string",
                "condition_default": False,
                "branch_path": "false",
            },
            "expected_result_fields": ["branch_path", "condition_default", "linked_pins"],
        },
        {
            "case_id": "template_sequence_print_strings",
            "request": _proposal_payload(
                "add_blueprint_node_template",
                {
                    "blueprint_path": blueprint_path,
                    "template_id": "sequence_print_strings",
                    "graph_name": "EventGraph",
                    "messages": ["First", "Second"],
                },
            ),
            "expected_status": 200,
            "expected_tool_id": "editor_add_blueprint_node_template",
            "expected_payload": {
                "template_id": "sequence_print_strings",
                "sequence_output_count": 2,
                "messages": ["First", "Second"],
            },
            "expected_result_fields": ["sequence_output_count", "messages", "linked_pins"],
        },
        {
            "case_id": "template_get_variable",
            "request": _proposal_payload(
                "add_blueprint_node_template",
                {
                    "blueprint_path": blueprint_path,
                    "template_id": "get_variable",
                    "graph_name": "EventGraph",
                    "variable_name": "Health",
                },
            ),
            "expected_status": 200,
            "expected_tool_id": "editor_add_blueprint_node_template",
            "expected_payload": {
                "template_id": "get_variable",
                "variable_name": "Health",
                "variable_scope": "self",
            },
            "expected_result_fields": ["variable_name"],
        },
        {
            "case_id": "template_set_variable",
            "request": _proposal_payload(
                "add_blueprint_node_template",
                {
                    "blueprint_path": blueprint_path,
                    "template_id": "set_variable",
                    "graph_name": "EventGraph",
                    "variable_name": "Health",
                    "variable_value": "100.0",
                },
            ),
            "expected_status": 200,
            "expected_tool_id": "editor_add_blueprint_node_template",
            "expected_payload": {
                "template_id": "set_variable",
                "entry_event": "BeginPlay",
                "variable_name": "Health",
                "variable_value": "100.0",
            },
            "expected_result_fields": ["variable_name", "variable_value", "linked_pins"],
        },
        {
            "case_id": "template_call_function",
            "request": _proposal_payload(
                "add_blueprint_node_template",
                {
                    "blueprint_path": blueprint_path,
                    "template_id": "call_function",
                    "graph_name": "EventGraph",
                    "function_name": "RefreshHud",
                },
            ),
            "expected_status": 200,
            "expected_tool_id": "editor_add_blueprint_node_template",
            "expected_payload": {
                "template_id": "call_function",
                "entry_event": "BeginPlay",
                "function_name": "RefreshHud",
                "function_target": "self",
            },
            "expected_result_fields": ["function_name", "function_target", "linked_pins"],
        },
        {
            "case_id": "template_enhanced_input_action_event",
            "request": _proposal_payload(
                "add_blueprint_node_template",
                {
                    "blueprint_path": blueprint_path,
                    "template_id": "enhanced_input_action_event",
                    "graph_name": "EventGraph",
                    "input_action_path": "/Game/Input/IA_Jump",
                },
            ),
            "expected_status": 200,
            "expected_tool_id": "editor_add_blueprint_node_template",
            "expected_payload": {
                "template_id": "enhanced_input_action_event",
                "input_action_path": "/Game/Input/IA_Jump",
            },
            "expected_result_fields": ["input_action_path", "created_nodes"],
        },
        {
            "case_id": "connect_blueprint_nodes",
            "request": _proposal_payload(
                "connect_blueprint_nodes",
                {
                    "blueprint_path": blueprint_path,
                    "graph_name": "EventGraph",
                    "source_node_id": "6C7D8E9F-0000-1111-2222-333344445555",
                    "source_pin_name": "then",
                    "target_node_id": "8E9F0001-2222-3333-4444-555566667777",
                    "target_pin_name": "execute",
                    "compile_after_edit": True,
                },
            ),
            "expected_status": 200,
            "expected_tool_id": "editor_connect_blueprint_nodes",
            "expected_payload": {
                "source_pin_name": "then",
                "target_pin_name": "execute",
                "compile_after_edit": True,
            },
            "expected_result_fields": ["linked_pins", "compile_status"],
        },
        {
            "case_id": "compile_blueprint",
            "request": _proposal_payload(
                "compile_blueprint",
                {
                    "blueprint_path": blueprint_path,
                },
            ),
            "expected_status": 200,
            "expected_tool_id": "editor_compile_blueprint",
            "expected_payload": {
                "blueprint_path": blueprint_path,
                "compile_mode": "default",
            },
            "expected_result_fields": ["compile_status", "messages"],
        },
        {
            "case_id": "reject_unknown_template",
            "request": _proposal_payload(
                "add_blueprint_node_template",
                {
                    "blueprint_path": blueprint_path,
                    "template_id": "delete_all_nodes",
                },
            ),
            "expected_status": 400,
            "expected_error_code": "blueprint_node_template_not_supported_in_v1",
        },
        {
            "case_id": "reject_unsafe_pin_connect_node_id",
            "request": _proposal_payload(
                "connect_blueprint_nodes",
                {
                    "blueprint_path": blueprint_path,
                    "graph_name": "EventGraph",
                    "source_node_id": "../bad",
                    "source_pin_name": "then",
                    "target_node_id": "TargetNode",
                    "target_pin_name": "execute",
                },
            ),
            "expected_status": 400,
            "expected_error_code": "source_node_id_invalid",
        },
    ]


def _result_fields(body: dict[str, Any]) -> list[str]:
    operation = body.get("operation") if isinstance(body, dict) else None
    contract = operation.get("expected_result_contract") if isinstance(operation, dict) else None
    fields = contract.get("operation_result_fields") if isinstance(contract, dict) else None
    return fields if isinstance(fields, list) else []


def _error_code(body: dict[str, Any]) -> str | None:
    errors = body.get("errors") if isinstance(body, dict) else None
    if not isinstance(errors, list) or not errors:
        return None
    first = errors[0]
    if not isinstance(first, dict):
        return None
    code = first.get("code")
    return str(code) if code else None


def _evaluate_case(client: TestClient, case: dict[str, Any]) -> dict[str, Any]:
    response = client.post("/api/v1/editor-operations/proposals", json=case["request"])
    try:
        body = response.json()
    except ValueError:
        body = {"raw_text": response.text}

    checks: list[dict[str, Any]] = [
        {
            "name": "status_code",
            "ok": response.status_code == case["expected_status"],
            "expected": case["expected_status"],
            "actual": response.status_code,
        }
    ]

    if response.status_code == 200:
        operation = body.get("operation") if isinstance(body, dict) else {}
        payload = operation.get("operation_payload") if isinstance(operation, dict) else {}
        checks.append(
            {
                "name": "tool_id",
                "ok": operation.get("tool_id") == case.get("expected_tool_id"),
                "expected": case.get("expected_tool_id"),
                "actual": operation.get("tool_id"),
            }
        )
        for key, expected_value in case.get("expected_payload", {}).items():
            checks.append(
                {
                    "name": f"payload.{key}",
                    "ok": payload.get(key) == expected_value,
                    "expected": expected_value,
                    "actual": payload.get(key),
                }
            )
        fields = _result_fields(body)
        for field_name in case.get("expected_result_fields", []):
            checks.append(
                {
                    "name": f"result_field.{field_name}",
                    "ok": field_name in fields,
                    "expected": "present",
                    "actual": "present" if field_name in fields else "missing",
                }
            )
    else:
        checks.append(
            {
                "name": "error_code",
                "ok": _error_code(body) == case.get("expected_error_code"),
                "expected": case.get("expected_error_code"),
                "actual": _error_code(body),
            }
        )

    return {
        "case_id": case["case_id"],
        "ok": all(item["ok"] for item in checks),
        "status_code": response.status_code,
        "checks": checks,
        "proposal_id": (body.get("item") or {}).get("proposal_id") if isinstance(body, dict) else None,
        "operation_type": (body.get("operation") or {}).get("operation_type")
        if isinstance(body, dict)
        else None,
        "tool_id": (body.get("operation") or {}).get("tool_id") if isinstance(body, dict) else None,
        "error_code": _error_code(body) if isinstance(body, dict) else None,
    }


def main() -> int:
    args = _parse_args()
    with _isolated_runtime():
        with TestClient(create_app()) as client:
            results = [_evaluate_case(client, case) for case in _cases()]

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "deterministic_no_ue_no_llm",
        "overall_ok": all(item["ok"] for item in results),
        "summary": {
            "case_count": len(results),
            "passed": sum(1 for item in results if item["ok"]),
            "failed": sum(1 for item in results if not item["ok"]),
        },
        "checks": results,
        "notes": [
            "This smoke test verifies backend Proposal contracts only.",
            "It does not launch Unreal Editor, execute editor writes, compile Blueprints, or call an LLM.",
            "Rejected cases are intentional guardrail checks.",
        ],
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["overall_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
