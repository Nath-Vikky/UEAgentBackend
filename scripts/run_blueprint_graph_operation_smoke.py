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
            "case_id": "event_stub_actor_begin_overlap",
            "request": _proposal_payload(
                "create_blueprint_event_stub",
                {
                    "blueprint_path": blueprint_path,
                    "event_name": "ActorBeginOverlap",
                    "graph_name": "EventGraph",
                },
            ),
            "expected_status": 200,
            "expected_tool_id": "editor_create_blueprint_event_stub",
            "expected_payload": {
                "blueprint_path": blueprint_path,
                "event_name": "ActorBeginOverlap",
                "graph_name": "EventGraph",
            },
            "expected_result_fields": ["event_name", "dirty_packages"],
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
            "case_id": "template_delay_print_string",
            "request": _proposal_payload(
                "add_blueprint_node_template",
                {
                    "blueprint_path": blueprint_path,
                    "template_id": "delay_print_string",
                    "graph_name": "EventGraph",
                    "message": "Delayed smoke",
                    "delay_seconds": 1.25,
                },
            ),
            "expected_status": 200,
            "expected_tool_id": "editor_add_blueprint_node_template",
            "expected_payload": {
                "template_id": "delay_print_string",
                "entry_event": "BeginPlay",
                "delay_seconds": 1.25,
            },
            "expected_result_fields": ["delay_seconds", "linked_pins"],
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


def _find_user_view_block(body: dict[str, Any], block_type: str) -> dict[str, Any] | None:
    user_view = body.get("user_view") if isinstance(body, dict) else None
    blocks = user_view.get("blocks") if isinstance(user_view, dict) else None
    if not isinstance(blocks, list):
        return None
    return next(
        (
            block
            for block in blocks
            if isinstance(block, dict) and block.get("block_type") == block_type
        ),
        None,
    )


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


def _evaluate_result_observability(client: TestClient) -> dict[str, Any]:
    blueprint_path = "/Game/Blueprints/BP_PlayerCharacter"
    created_node_id = "11111111-2222-3333-4444-555566667777"
    entry_node_id = "AAAAAAAA-BBBB-CCCC-DDDD-EEEEFFFFFFFF"
    created = client.post(
        "/api/v1/editor-operations/proposals",
        json=_proposal_payload(
            "add_blueprint_node_template",
            {
                "blueprint_path": blueprint_path,
                "template_id": "print_string",
                "graph_name": "EventGraph",
                "message": "Unlinked diagnostics",
                "entry_event": "BeginPlay",
                "compile_after_edit": True,
            },
            reason="Blueprint graph result observability smoke check.",
        ),
    )
    try:
        created_body = created.json()
    except ValueError:
        created_body = {"raw_text": created.text}

    proposal_id = (created_body.get("item") or {}).get("proposal_id") if isinstance(created_body, dict) else None
    checks: list[dict[str, Any]] = [
        {
            "name": "proposal.status_code",
            "ok": created.status_code == 200,
            "expected": 200,
            "actual": created.status_code,
        },
        {
            "name": "proposal.proposal_id",
            "ok": bool(proposal_id),
            "expected": "present",
            "actual": "present" if proposal_id else "missing",
        },
    ]
    result_body: dict[str, Any] = {}
    result_status_code: int | None = None
    if proposal_id:
        confirmed = client.post(f"/api/v1/editor-operations/proposals/{proposal_id}/confirm")
        checks.append(
            {
                "name": "confirm.status_code",
                "ok": confirmed.status_code == 200,
                "expected": 200,
                "actual": confirmed.status_code,
            }
        )
        result = client.post(
            "/api/v1/editor-operations/results",
            json={
                "proposal_id": proposal_id,
                "operation_type": "add_blueprint_node_template",
                "execution_state": "completed",
                "success": True,
                "executed_by": "ue_plugin",
                "result": {
                    "created_node_id": created_node_id,
                    "created_node_name": "K2Node_CallFunction_0",
                    "entry_node_id": entry_node_id,
                    "entry_node_name": "EventBeginPlay",
                    "created_nodes": [
                        {
                            "node_id": created_node_id,
                            "node_name": "K2Node_CallFunction_0",
                            "node_class": "K2Node_CallFunction",
                            "role": "print_string",
                        }
                    ],
                    "linked_pins": [],
                    "linked_pin_summaries": [],
                    "compile_status": "succeeded",
                    "dirty": True,
                    "dirty_packages": [blueprint_path],
                },
            },
        )
        result_status_code = result.status_code
        try:
            result_body = result.json()
        except ValueError:
            result_body = {"raw_text": result.text}
        checks.append(
            {
                "name": "result.status_code",
                "ok": result.status_code == 200,
                "expected": 200,
                "actual": result.status_code,
            }
        )

    result_summary = ((result_body.get("item") or {}).get("result_summary") or {}) if result_body else {}
    diagnostics = result_summary.get("operation_diagnostics") or {}
    graph_detail_block = _find_user_view_block(result_body, "editor_operation_graph_details")
    graph_detail_data = graph_detail_block.get("data") if isinstance(graph_detail_block, dict) else {}
    quick_actions = ((result_body.get("user_view") or {}).get("quick_actions") or []) if result_body else []
    first_quick_action = quick_actions[0] if quick_actions and isinstance(quick_actions[0], dict) else {}
    first_quick_action_payload = first_quick_action.get("payload") or {}
    follow_up = result_body.get("follow_up") or {}
    candidates = follow_up.get("candidates") or []
    first_candidate = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
    candidate_payload = first_candidate.get("payload") or {}

    checks.extend(
        [
            {
                "name": "diagnostics.created_node_count",
                "ok": diagnostics.get("created_node_count") == 1,
                "expected": 1,
                "actual": diagnostics.get("created_node_count"),
            },
            {
                "name": "diagnostics.linked_pin_count",
                "ok": diagnostics.get("linked_pin_count") == 0,
                "expected": 0,
                "actual": diagnostics.get("linked_pin_count"),
            },
            {
                "name": "diagnostics.expected_linked_pins_missing",
                "ok": "expected_linked_pins_missing" in (diagnostics.get("diagnostic_flags") or []),
                "expected": "present",
                "actual": diagnostics.get("diagnostic_flags"),
            },
            {
                "name": "graph_detail_block.present",
                "ok": graph_detail_block is not None,
                "expected": "present",
                "actual": "present" if graph_detail_block else "missing",
            },
            {
                "name": "graph_detail_block.schema_version",
                "ok": graph_detail_data.get("schema_version") == "blueprint_graph_result_details_v1",
                "expected": "blueprint_graph_result_details_v1",
                "actual": graph_detail_data.get("schema_version"),
            },
            {
                "name": "graph_detail_block.created_node_id",
                "ok": graph_detail_data.get("created_node_id") == created_node_id,
                "expected": created_node_id,
                "actual": graph_detail_data.get("created_node_id"),
            },
            {
                "name": "graph_detail_block.entry_node_id",
                "ok": graph_detail_data.get("entry_node_id") == entry_node_id,
                "expected": entry_node_id,
                "actual": graph_detail_data.get("entry_node_id"),
            },
            {
                "name": "quick_action.follow_up_proposal",
                "ok": first_quick_action_payload.get("action_type")
                == "create_editor_operation_follow_up_proposal",
                "expected": "create_editor_operation_follow_up_proposal",
                "actual": first_quick_action_payload.get("action_type"),
            },
            {
                "name": "follow_up.ready_candidate_count",
                "ok": follow_up.get("ready_candidate_count") == 1,
                "expected": 1,
                "actual": follow_up.get("ready_candidate_count"),
            },
            {
                "name": "follow_up.source_node_id",
                "ok": candidate_payload.get("source_node_id") == entry_node_id,
                "expected": entry_node_id,
                "actual": candidate_payload.get("source_node_id"),
            },
            {
                "name": "follow_up.target_node_id",
                "ok": candidate_payload.get("target_node_id") == created_node_id,
                "expected": created_node_id,
                "actual": candidate_payload.get("target_node_id"),
            },
        ]
    )
    return {
        "case_id": "result_observability_unlinked_print_string",
        "ok": all(item["ok"] for item in checks),
        "status_code": result_status_code,
        "checks": checks,
        "proposal_id": proposal_id,
        "operation_type": "add_blueprint_node_template",
        "tool_id": "editor_add_blueprint_node_template",
        "error_code": _error_code(result_body) if result_body else None,
    }


def main() -> int:
    args = _parse_args()
    with _isolated_runtime():
        with TestClient(create_app()) as client:
            results = [_evaluate_case(client, case) for case in _cases()]
            results.append(_evaluate_result_observability(client))

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
            "This smoke test verifies backend Proposal contracts and one result-time Blueprint graph diagnostics chain.",
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
