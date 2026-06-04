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
        description="Run deterministic editor workflow/follow-up materialization smoke checks."
    )
    parser.add_argument(
        "--output",
        default="storage/artifacts/smoke/editor-workflow-materialization-smoke-latest.json",
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
    runtime_root = Path(".smoke-runtime") / f"workflow-materialization-{uuid.uuid4().hex}"
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


def _run_workflow_step_materialization(client: TestClient) -> dict[str, Any]:
    plan_response = client.post(
        "/api/v1/editor-operations/workflows/plan",
        json={
            "goal": "Add Ready Print String and compile",
            "workflow_type": "blueprint_print_then_compile",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "message": "Ready",
            },
        },
    )
    plan_body = plan_response.json()
    plan = dict(plan_body.get("workflow_plan") or {})
    step = list(plan.get("steps") or [{}])[0]
    proposal_response = client.post(
        "/api/v1/editor-operations/workflows/steps/proposal",
        json={
            "workflow_plan_id": plan.get("plan_id"),
            "step": step,
            "requested_by": "workflow_materialization_smoke",
        },
    )
    body = proposal_response.json()
    checks = [
        _check("plan_status_code", 200, plan_response.status_code),
        _check("proposal_status_code", 200, proposal_response.status_code),
        _check("workflow_step_schema", "editor_workflow_step_materialization_v1", body.get("workflow_step", {}).get("schema_version")),
        _check("operation_type", "add_blueprint_node_template", body.get("proposal", {}).get("operation", {}).get("operation_type")),
        _check("confirmation_state", "pending", body.get("proposal", {}).get("item", {}).get("confirmation", {}).get("state")),
        _check("auto_execute", False, body.get("workflow_step", {}).get("auto_execute")),
    ]
    return {
        "case_id": "workflow_step_to_proposal",
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
    }


def _run_delay_workflow_step_materialization(client: TestClient) -> dict[str, Any]:
    plan_response = client.post(
        "/api/v1/editor-operations/workflows/plan",
        json={
            "goal": "Add a Print String after 2 seconds and compile",
            "workflow_type": "blueprint_print_then_compile",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "message": "Ready after delay",
                "delay_seconds": 2,
            },
        },
    )
    plan_body = plan_response.json()
    plan = dict(plan_body.get("workflow_plan") or {})
    step = list(plan.get("steps") or [{}])[0]
    proposal_response = client.post(
        "/api/v1/editor-operations/workflows/steps/proposal",
        json={
            "workflow_plan_id": plan.get("plan_id"),
            "step": step,
            "requested_by": "workflow_materialization_smoke",
        },
    )
    body = proposal_response.json()
    operation_payload = body.get("proposal", {}).get("operation", {}).get("operation_payload", {})
    step_payload = step.get("payload", {})
    checks = [
        _check("plan_status_code", 200, plan_response.status_code),
        _check("proposal_status_code", 200, proposal_response.status_code),
        _check("step_template_id", "delay_print_string", step_payload.get("template_id")),
        _check("step_delay_seconds", 2.0, step_payload.get("delay_seconds")),
        _check("operation_type", "add_blueprint_node_template", body.get("proposal", {}).get("operation", {}).get("operation_type")),
        _check("proposal_template_id", "delay_print_string", operation_payload.get("template_id")),
        _check("proposal_delay_seconds", 2.0, operation_payload.get("delay_seconds")),
        _check("confirmation_state", "pending", body.get("proposal", {}).get("item", {}).get("confirmation", {}).get("state")),
        _check("auto_execute", False, body.get("workflow_step", {}).get("auto_execute")),
    ]
    return {
        "case_id": "delay_workflow_step_to_proposal",
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
    }


def _run_connect_workflow_step_materialization(client: TestClient) -> dict[str, Any]:
    plan_response = client.post(
        "/api/v1/editor-operations/workflows/plan",
        json={
            "goal": "Connect BeginPlay to Print String and compile",
            "workflow_type": "blueprint_connect_then_compile",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "graph_name": "EventGraph",
                "source_node_id": "EventBeginPlay",
                "source_pin_name": "then",
                "target_node_id": "PrintStringNode",
                "target_pin_name": "execute",
            },
        },
    )
    plan_body = plan_response.json()
    plan = dict(plan_body.get("workflow_plan") or {})
    step = list(plan.get("steps") or [{}])[0]
    proposal_response = client.post(
        "/api/v1/editor-operations/workflows/steps/proposal",
        json={
            "workflow_plan_id": plan.get("plan_id"),
            "step": step,
            "requested_by": "workflow_materialization_smoke",
        },
    )
    body = proposal_response.json()
    operation_payload = body.get("proposal", {}).get("operation", {}).get("operation_payload", {})
    checks = [
        _check("plan_status_code", 200, plan_response.status_code),
        _check("proposal_status_code", 200, proposal_response.status_code),
        _check("workflow_type", "blueprint_connect_then_compile", plan.get("workflow_type")),
        _check("step_count", 2, plan.get("step_count")),
        _check("operation_type", "connect_blueprint_nodes", body.get("proposal", {}).get("operation", {}).get("operation_type")),
        _check("proposal_source_node_id", "EventBeginPlay", operation_payload.get("source_node_id")),
        _check("proposal_source_pin_name", "then", operation_payload.get("source_pin_name")),
        _check("proposal_target_node_id", "PrintStringNode", operation_payload.get("target_node_id")),
        _check("proposal_target_pin_name", "execute", operation_payload.get("target_pin_name")),
        _check("confirmation_state", "pending", body.get("proposal", {}).get("item", {}).get("confirmation", {}).get("state")),
        _check("auto_execute", False, body.get("workflow_step", {}).get("auto_execute")),
    ]
    return {
        "case_id": "blueprint_connect_workflow_step_to_proposal",
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
    }


def _run_enhanced_input_workflow_step_materialization(client: TestClient) -> dict[str, Any]:
    plan_response = client.post(
        "/api/v1/editor-operations/workflows/plan",
        json={
            "goal": "Add Enhanced Input IA_Jump to Print String and compile",
            "workflow_type": "blueprint_enhanced_input_print_then_compile",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "input_action_path": "/Game/Input/IA_Jump",
            },
        },
    )
    plan_body = plan_response.json()
    plan = dict(plan_body.get("workflow_plan") or {})
    step = list(plan.get("steps") or [{}])[0]
    proposal_response = client.post(
        "/api/v1/editor-operations/workflows/steps/proposal",
        json={
            "workflow_plan_id": plan.get("plan_id"),
            "step": step,
            "requested_by": "workflow_materialization_smoke",
        },
    )
    body = proposal_response.json()
    operation_payload = body.get("proposal", {}).get("operation", {}).get("operation_payload", {})
    checks = [
        _check("plan_status_code", 200, plan_response.status_code),
        _check("proposal_status_code", 200, proposal_response.status_code),
        _check("workflow_type", "blueprint_enhanced_input_print_then_compile", plan.get("workflow_type")),
        _check("step_count", 2, plan.get("step_count")),
        _check("operation_type", "add_blueprint_node_template", body.get("proposal", {}).get("operation", {}).get("operation_type")),
        _check("proposal_template_id", "enhanced_input_print_string", operation_payload.get("template_id")),
        _check("proposal_input_action_path", "/Game/Input/IA_Jump", operation_payload.get("input_action_path")),
        _check("proposal_compile_after_edit", False, operation_payload.get("compile_after_edit")),
        _check("confirmation_state", "pending", body.get("proposal", {}).get("item", {}).get("confirmation", {}).get("state")),
        _check("auto_execute", False, body.get("workflow_step", {}).get("auto_execute")),
    ]
    return {
        "case_id": "enhanced_input_workflow_step_to_proposal",
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
    }


def _run_workflow_step_rejection(client: TestClient) -> dict[str, Any]:
    plan_response = client.post(
        "/api/v1/editor-operations/workflows/plan",
        json={
            "goal": "Create HUD title text",
            "workflow_type": "umg_text_widget",
            "payload": {"widget_name": "TitleText"},
        },
    )
    plan = dict(plan_response.json().get("workflow_plan") or {})
    step = list(plan.get("steps") or [{}])[0]
    response = client.post(
        "/api/v1/editor-operations/workflows/steps/proposal",
        json={"workflow_plan_id": plan.get("plan_id"), "step": step},
    )
    body = response.json()
    checks = [
        _check("status_code", 400, response.status_code),
        _check("error_code", "workflow_step_not_ready_for_proposal", body.get("errors", [{}])[0].get("code")),
    ]
    return {
        "case_id": "workflow_step_rejects_missing_inputs",
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
    }


def _run_umg_hud_group_step_materialization(client: TestClient) -> dict[str, Any]:
    plan_response = client.post(
        "/api/v1/editor-operations/workflows/plan",
        json={
            "goal": "Plan a HUD group under RootCanvas with text 'HP 100'",
            "workflow_type": "umg_hud_group",
            "payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "parent_widget_name": "RootCanvas",
                "group_name": "StatusHUDGroup",
                "label_text": "HP 100",
            },
        },
    )
    plan_body = plan_response.json()
    plan = dict(plan_body.get("workflow_plan") or {})
    step = list(plan.get("steps") or [{}])[0]
    proposal_response = client.post(
        "/api/v1/editor-operations/workflows/steps/proposal",
        json={
            "workflow_plan_id": plan.get("plan_id"),
            "step": step,
            "requested_by": "workflow_materialization_smoke",
        },
    )
    body = proposal_response.json()
    operation_payload = body.get("proposal", {}).get("operation", {}).get("operation_payload", {})
    checks = [
        _check("plan_status_code", 200, plan_response.status_code),
        _check("proposal_status_code", 200, proposal_response.status_code),
        _check("workflow_type", "umg_hud_group", plan.get("workflow_type")),
        _check("step_count", 4, plan.get("step_count")),
        _check("operation_type", "add_umg_widget", body.get("proposal", {}).get("operation", {}).get("operation_type")),
        _check("proposal_widget_class", "/Script/UMG.HorizontalBox", operation_payload.get("widget_class")),
        _check("proposal_widget_name", "StatusHUDGroup", operation_payload.get("widget_name")),
        _check("proposal_parent_widget_name", "RootCanvas", operation_payload.get("parent_widget_name")),
        _check("confirmation_state", "pending", body.get("proposal", {}).get("item", {}).get("confirmation", {}).get("state")),
        _check("auto_execute", False, body.get("workflow_step", {}).get("auto_execute")),
    ]
    return {
        "case_id": "umg_hud_group_step_to_proposal",
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
    }


def _run_follow_up_materialization(client: TestClient) -> dict[str, Any]:
    created = client.post(
        "/api/v1/editor-operations/proposals",
        json={
            "operation_type": "add_blueprint_node_template",
            "payload": {
                "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                "template_id": "print_string",
                "graph_name": "EventGraph",
                "message": "Unlinked diagnostics",
                "entry_event": "BeginPlay",
                "compile_after_edit": True,
            },
        },
    )
    proposal_id = created.json()["item"]["proposal_id"] if created.status_code == 200 else ""
    confirm = client.post(f"/api/v1/editor-operations/proposals/{proposal_id}/confirm")
    result = client.post(
        "/api/v1/editor-operations/results",
        json={
            "proposal_id": proposal_id,
            "operation_type": "add_blueprint_node_template",
            "execution_state": "completed",
            "success": True,
            "executed_by": "ue_plugin",
            "result": {
                "created_nodes": [{"node_name": "K2Node_CallFunction_0"}],
                "linked_pins": [],
                "compile_status": "succeeded",
                "dirty": True,
                "dirty_packages": ["/Game/Blueprints/BP_PlayerCharacter"],
            },
        },
    )
    follow_ups = client.get(f"/api/v1/editor-operations/proposals/{proposal_id}/follow-ups")
    candidates = list(follow_ups.json().get("follow_up", {}).get("candidates") or [])
    candidate = candidates[0] if candidates else {}
    materialized = client.post(
        f"/api/v1/editor-operations/proposals/{proposal_id}/follow-ups/proposal",
        json={"candidate": candidate, "requested_by": "workflow_materialization_smoke"},
    )
    body = materialized.json()
    checks = [
        _check("create_status_code", 200, created.status_code),
        _check("confirm_status_code", 200, confirm.status_code),
        _check("result_status_code", 200, result.status_code),
        _check("follow_ups_status_code", 200, follow_ups.status_code),
        _check("materialized_status_code", 200, materialized.status_code),
        _check("follow_up_schema", "editor_operation_follow_up_materialization_v1", body.get("follow_up_step", {}).get("schema_version")),
        _check("operation_type", "connect_blueprint_nodes", body.get("proposal", {}).get("operation", {}).get("operation_type")),
        _check("confirmation_state", "pending", body.get("proposal", {}).get("item", {}).get("confirmation", {}).get("state")),
        _check("auto_execute", False, body.get("follow_up_step", {}).get("auto_execute")),
    ]
    return {
        "case_id": "follow_up_candidate_to_proposal",
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
    }


def main() -> int:
    args = _parse_args()
    with _isolated_runtime(), TestClient(create_app()) as client:
        cases = [
            _run_workflow_step_materialization(client),
            _run_delay_workflow_step_materialization(client),
            _run_connect_workflow_step_materialization(client),
            _run_enhanced_input_workflow_step_materialization(client),
            _run_workflow_step_rejection(client),
            _run_umg_hud_group_step_materialization(client),
            _run_follow_up_materialization(client),
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
            "This smoke test verifies backend materialization contracts only.",
            "It does not launch Unreal Editor, execute editor writes, compile Blueprints, or call an LLM.",
            "Materialized items are pending Proposals and still require user confirmation.",
        ],
    }
    _emit_report(report, args.output)
    return 0 if report["overall_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
