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
        description="Run deterministic Agent Chat to editor-operation proposal smoke checks."
    )
    parser.add_argument(
        "--output",
        default="storage/artifacts/smoke/editor-operation-chat-bridge-smoke-latest.json",
        help="JSON report output path.",
    )
    return parser.parse_args()


@contextmanager
def _isolated_runtime() -> Iterator[None]:
    runtime_root = Path(".smoke-runtime") / f"editor-chat-bridge-{uuid.uuid4().hex}"
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


def _seed_inventory(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/v1/project-inventory/snapshot",
        json={
            "project_id": "DemoProject",
            "project_name": "DemoProject",
            "assets": [
                {
                    "asset_path": "/Game/Blueprints/BP_TestActor.BP_TestActor",
                    "asset_name": "BP_TestActor",
                    "asset_type": "Blueprint",
                    "settings": {"parent_class": "AActor"},
                },
                {
                    "asset_path": "/Game/Blueprints/BP_EnemySpawner.BP_EnemySpawner",
                    "asset_name": "BP_EnemySpawner",
                    "asset_type": "Blueprint",
                    "settings": {"parent_class": "AActor"},
                },
                {
                    "asset_path": "/Game/UI/WBP_MainHUD.WBP_MainHUD",
                    "asset_name": "WBP_MainHUD",
                    "asset_type": "WidgetBlueprint",
                },
                {
                    "asset_path": "/Game/Materials/MI_Player.MI_Player",
                    "asset_name": "MI_Player",
                    "asset_type": "MaterialInstanceConstant",
                },
                {
                    "asset_path": "/Game/Textures/T_Player_D.T_Player_D",
                    "asset_name": "T_Player_D",
                    "asset_type": "Texture2D",
                },
            ],
            "level_actors": [
                {
                    "actor_label": "BP_EnemySpawner_1",
                    "actor_name": "BP_EnemySpawner_C_1",
                    "actor_class": "BP_EnemySpawner_C",
                    "level_name": "TestMap",
                    "folder_path": "Gameplay",
                    "tags": ["Spawner"],
                }
            ],
        },
    )
    return {
        "ok": response.status_code == 200,
        "status_code": response.status_code,
        "body": response.json() if response.headers.get("content-type", "").startswith("application/json") else {},
    }


def _chat_request(
    *,
    case_id: str,
    query: str,
    selected_assets: list[str] | None = None,
    language: str = "en-US",
) -> dict[str, Any]:
    return {
        "task_type": "agent_chat",
        "session": {
            "session_id": f"editor_chat_bridge_{case_id}_{uuid.uuid4().hex[:8]}",
            "messages": [{"role": "user", "content": query, "language": "auto"}],
        },
        "context": {
            "project_name": "DemoProject",
            "project_root": "D:/DemoProject",
            "active_panel": "AgentChat",
            "selected_assets": selected_assets or [],
        },
        "payload": {"user_query": query},
        "runtime_options": {
            "profile_id": "default",
            "stream": False,
            "debug": True,
            "preferred_output_language": language,
            "return_debug_projection": True,
        },
    }


def _cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "chat_print_string_beginplay",
            "request": _chat_request(
                case_id="chat_print_string_beginplay",
                query="给 BP_TestActor 的 EventBeginPlay 添加一个 Print String 节点",
                selected_assets=["/Game/Blueprints/BP_TestActor"],
                language="zh-CN",
            ),
            "expected_operation_type": "add_blueprint_node_template",
            "expected_payload": {
                "template_id": "print_string",
                "blueprint_path": "/Game/Blueprints/BP_TestActor",
                "entry_event": "BeginPlay",
            },
        },
        {
            "case_id": "chat_compile_inventory_blueprint",
            "request": _chat_request(
                case_id="chat_compile_inventory_blueprint",
                query="Compile BP_EnemySpawner blueprint",
            ),
            "expected_operation_type": "compile_blueprint",
            "expected_payload": {
                "blueprint_path": "/Game/Blueprints/BP_EnemySpawner",
            },
        },
        {
            "case_id": "chat_event_stub_tick",
            "request": _chat_request(
                case_id="chat_event_stub_tick",
                query="Add Tick event to BP_EnemySpawner blueprint",
            ),
            "expected_operation_type": "create_blueprint_event_stub",
            "expected_payload": {
                "blueprint_path": "/Game/Blueprints/BP_EnemySpawner",
                "event_name": "Tick",
            },
        },
        {
            "case_id": "chat_place_actor",
            "request": _chat_request(
                case_id="chat_place_actor",
                query="Place BP_EnemySpawner in the current level at location 10 20 30",
            ),
            "expected_operation_type": "place_actor_in_level",
            "expected_payload": {
                "actor_class": "/Game/Blueprints/BP_EnemySpawner.BP_EnemySpawner_C",
            },
        },
        {
            "case_id": "chat_umg_text",
            "request": _chat_request(
                case_id="chat_umg_text",
                query="Set WBP_MainHUD TitleText text to 'Mission Ready'",
            ),
            "expected_operation_type": "set_umg_widget_text",
            "expected_payload": {
                "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                "widget_name": "TitleText",
                "text": "Mission Ready",
            },
        },
        {
            "case_id": "chat_material_scalar",
            "request": _chat_request(
                case_id="chat_material_scalar",
                query="Set MI_Player material Roughness to 0.25",
            ),
            "expected_operation_type": "set_material_instance_parameter",
            "expected_payload": {
                "material_instance_path": "/Game/Materials/MI_Player",
                "parameter_name": "Roughness",
                "parameter_type": "scalar",
                "value": 0.25,
            },
        },
        {
            "case_id": "chat_material_static_switch",
            "request": _chat_request(
                case_id="chat_material_static_switch",
                query="Enable MI_Player material UseDetail static switch",
            ),
            "expected_operation_type": "set_material_instance_static_switch",
            "expected_payload": {
                "material_instance_path": "/Game/Materials/MI_Player",
                "parameter_name": "UseDetail",
                "value": True,
            },
        },
        {
            "case_id": "chat_actor_metadata",
            "request": _chat_request(
                case_id="chat_actor_metadata",
                query="Rename actor BP_EnemySpawner_1 label to EnemySpawn_A",
            ),
            "expected_operation_type": "set_actor_metadata",
            "expected_payload": {
                "actor_reference": "BP_EnemySpawner_1",
                "metadata.actor_label": "EnemySpawn_A",
            },
        },
    ]


def _nested_get(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _evaluate_case(client: TestClient, case: dict[str, Any]) -> dict[str, Any]:
    response = client.post("/api/v1/chat/runs", json=case["request"])
    try:
        body = response.json()
    except ValueError:
        body = {"raw_text": response.text}

    proposals = body.get("action_proposals") if isinstance(body, dict) else []
    proposal = proposals[0] if isinstance(proposals, list) and proposals else {}
    preview = proposal.get("dry_run_preview") if isinstance(proposal, dict) else {}
    payload = preview.get("operation_payload") if isinstance(preview, dict) else {}
    checks: list[dict[str, Any]] = [
        {
            "name": "status_code",
            "ok": response.status_code == 200,
            "expected": 200,
            "actual": response.status_code,
        },
        {
            "name": "task_status",
            "ok": _nested_get(body, "task.status") == "waiting_confirmation",
            "expected": "waiting_confirmation",
            "actual": _nested_get(body, "task.status") if isinstance(body, dict) else None,
        },
        {
            "name": "operation_type",
            "ok": preview.get("operation_type") == case["expected_operation_type"],
            "expected": case["expected_operation_type"],
            "actual": preview.get("operation_type"),
        },
    ]
    for key, expected_value in case.get("expected_payload", {}).items():
        actual_value = _nested_get(payload, key)
        checks.append(
            {
                "name": f"payload.{key}",
                "ok": actual_value == expected_value,
                "expected": expected_value,
                "actual": actual_value,
            }
        )
    return {
        "case_id": case["case_id"],
        "ok": all(item["ok"] for item in checks),
        "status_code": response.status_code,
        "operation_type": preview.get("operation_type"),
        "proposal_id": proposal.get("proposal_id") if isinstance(proposal, dict) else None,
        "checks": checks,
    }


def main() -> int:
    args = _parse_args()
    with _isolated_runtime():
        with TestClient(create_app()) as client:
            inventory_seed = _seed_inventory(client)
            results = [_evaluate_case(client, case) for case in _cases()]

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "deterministic_no_ue_no_llm",
        "overall_ok": inventory_seed["ok"] and all(item["ok"] for item in results),
        "summary": {
            "case_count": len(results),
            "passed": sum(1 for item in results if item["ok"]),
            "failed": sum(1 for item in results if not item["ok"]),
        },
        "inventory_seed": {key: value for key, value in inventory_seed.items() if key != "body"},
        "checks": results,
        "notes": [
            "This smoke test verifies Agent Chat routing into editor-operation proposals.",
            "It does not launch Unreal Editor, execute editor writes, compile Blueprints, or call an LLM.",
            "It complements run_blueprint_graph_operation_smoke.py, which tests the explicit Proposal API.",
        ],
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["overall_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
