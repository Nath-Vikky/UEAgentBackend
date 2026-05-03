from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.settings import get_settings
from app.db.session import get_engine, get_session_factory
from app.main import create_app


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    runtime_root = Path(".test-runtime") / f"integration-{uuid.uuid4().hex}"
    storage_dir = runtime_root / "storage"
    shutil.rmtree(runtime_root, ignore_errors=True)
    storage_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("STORAGE_DIR", str(storage_dir.resolve()))
    monkeypatch.setenv("UPLOAD_DIR", str((storage_dir / "uploads").resolve()))
    monkeypatch.setenv("ARTIFACT_DIR", str((storage_dir / "artifacts").resolve()))
    monkeypatch.setenv("KB_DIR", str((storage_dir / "kb").resolve()))
    monkeypatch.setenv("KB_SOURCE_PATHS", "./knowledge")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    shutil.rmtree(runtime_root, ignore_errors=True)


def test_system_bootstrap_and_runtime_profiles(client: TestClient) -> None:
    bootstrap = client.get("/api/v1/system/bootstrap")
    profiles = client.get("/api/v1/system/runtime-profiles")
    kb_status = client.get("/api/v1/knowledge-base/status")

    assert bootstrap.status_code == 200
    assert bootstrap.json()["service_status"] == "ok"
    assert "capabilities" in bootstrap.json()
    assert "supported_languages" in bootstrap.json()

    assert profiles.status_code == 200
    assert profiles.json()["profiles"]
    assert profiles.json()["default_profile_id"] == "default"

    assert kb_status.status_code == 200
    assert "summary" in kb_status.json()
    assert "local_search_readiness" in kb_status.json()["summary"]


def test_system_health_exposes_startup_checks(client: TestClient) -> None:
    response = client.get("/api/v1/system/health")
    body = response.json()

    assert response.status_code == 200
    assert body["startup_checks"]["checks"]
    assert body["startup_checks"]["counts"]["warning"] >= 1
    assert any(item["check_id"] == "llm_api_key" for item in body["startup_checks"]["checks"])
    assert any(
        item["check_id"] == "tool_registry_contracts" and item["status"] == "ok"
        for item in body["startup_checks"]["checks"]
    )
    assert body["startup_checks"]["blocking"] is False


def test_system_capabilities_expose_core_and_deferred_scope(client: TestClient) -> None:
    response = client.get("/api/v1/system/capabilities")
    body = response.json()

    assert response.status_code == 200
    assert body["capabilities"]["supported_task_types"] == [
        "agent_chat",
        "project_qa",
        "code_review",
        "code_generate",
        "logs_analyze",
        "assets_inspect",
    ]
    assert body["capabilities"]["skill_architecture"]["mode"] == "fixed_built_in_skills"
    assert body["capabilities"]["skill_architecture"]["protocol_version"] == "skill_protocol_v1"
    assert body["capabilities"]["skill_architecture"]["protocol_components"] == [
        "collector",
        "rules",
        "retrieval",
        "llm_analyzer",
        "projector",
    ]
    assert body["capabilities"]["skill_architecture"]["runtime_lifecycle_field"] == "debug_view.skill.lifecycle"
    assert body["capabilities"]["skill_architecture"]["runtime_dynamic_skills"] is False
    assert body["capabilities"]["skill_architecture"]["public_skill_count"] == 5
    assert len(body["capabilities"]["skill_catalog"]) == 5
    assert body["capabilities"]["tool_registry"]["mode"] == "declarative_static_registry"
    assert body["capabilities"]["tool_registry"]["protocol_version"] == "tool_protocol_v2"
    assert "mcp_stdio" in body["capabilities"]["tool_registry"]["protocol"]["transports"]
    assert any(
        item["tool_id"] == "query_project_inventory"
        and "当前项目" in item["trigger_keywords"]
        and item["side_effect_level"] == "read_only"
        and item["category"] == "sensing"
        and item["allowed_in_free_chat"] is True
        for item in body["capabilities"]["tool_registry"]["tools"]
    )
    assert any(
        item["skill_id"] == "CodeReviewSkill"
        and item["architecture"]["collector"] == "ue_project_code_file_scanner_and_reader"
        and item["architecture"]["llm_analyzer"] == "optional_live_llm_or_deterministic_fallback"
        and item["protocol"]["runtime_lifecycle_field"] == "debug_view.skill.lifecycle"
        for item in body["capabilities"]["skill_catalog"]
    )
    assert "config_generate" in body["capabilities"]["deferred_task_types"]
    assert any(
        item["task_type"] == "code_review" and item["frontend_ui"] == "file_picker"
        for item in body["capabilities"]["feature_catalog"]
    )


def test_project_inventory_snapshot_and_query(client: TestClient) -> None:
    snapshot = client.post(
        "/api/v1/project-inventory/snapshot",
        json={
            "project_id": "RushBa",
            "project_name": "RushBa",
            "source": "ue_plugin",
            "plugin_version": "0.1-test",
            "snapshot_time": "2026-04-23T10:00:00Z",
            "scan_diagnostics": {"asset_count_from_editor": 2, "code_file_count_from_scanner": 1},
            "assets": [
                {
                    "asset_path": "/Game/Environment/SM_Rock.SM_Rock",
                    "asset_name": "SM_Rock",
                    "asset_type": "StaticMesh",
                    "package_path": "/Game/Environment",
                    "dependencies": ["/Game/Materials/M_Rock"],
                    "referencers": ["/Game/Maps/L_Test"],
                    "settings": {
                        "nanite_enabled": True,
                        "lod_count": 3,
                        "collision_complexity": "UseComplexAsSimple",
                    },
                    "properties": {"material_slots": ["M_Rock"], "triangle_count": 12000},
                },
                {
                    "asset_path": "/Game/Blueprints/BP_PlayerCharacter.BP_PlayerCharacter",
                    "asset_name": "BP_PlayerCharacter",
                    "asset_type": "Blueprint",
                    "package_path": "/Game/Blueprints",
                    "settings": {"parent_class": "ACharacter", "tick_enabled": True},
                    "properties": {"components": ["Capsule", "SkeletalMesh", "Camera"]},
                },
            ],
            "code_files": [
                {
                    "file_path": "Source/RushBa/Player/RBPlayerCharacter.cpp",
                    "module_name": "RushBa",
                    "file_type": "cpp",
                    "classes": ["ARBPlayerCharacter"],
                    "size_bytes": 4096,
                    "last_modified": "2026-04-23T09:59:00Z",
                }
            ],
        },
    )
    summary = client.get("/api/v1/project-inventory/summary", params={"project_id": "RushBa"})
    static_meshes = client.get(
        "/api/v1/project-inventory/assets",
        params={"project_id": "RushBa", "asset_type": "StaticMesh"},
    )
    nanite_query = client.post(
        "/api/v1/project-inventory/query",
        json={"project_id": "RushBa", "query": "有哪些开启 Nanite 的静态网格体？"},
    )
    code_files = client.get(
        "/api/v1/project-inventory/code-files",
        params={"project_id": "RushBa", "module_name": "RushBa"},
    )
    asset_id = static_meshes.json()["items"][0]["asset_id"]
    asset_detail = client.get(f"/api/v1/project-inventory/assets/{asset_id}", params={"project_id": "RushBa"})
    asset_name_query = client.post(
        "/api/v1/project-inventory/query",
        json={
            "project_id": "RushBa",
            "query": "\u8bf7\u67e5\u770bBP_PlayerCharacter\u7684\u5c5e\u6027\u662f\u4ec0\u4e48",
        },
    )
    code_name_query = client.post(
        "/api/v1/project-inventory/query",
        json={
            "project_id": "RushBa",
            "query": "\u67e5\u770bRBPlayerCharacter.cpp\u7684\u4ee3\u7801\u6587\u4ef6\u4fe1\u606f",
        },
    )

    assert snapshot.status_code == 200
    assert snapshot.json()["snapshot"]["status"] == "saved"
    assert snapshot.json()["snapshot"]["asset_count"] == 2
    assert snapshot.json()["snapshot"]["summary"]["asset_count"] == 2
    assert snapshot.json()["snapshot"]["summary"]["code_file_count"] == 1
    assert snapshot.json()["snapshot"]["scan_diagnostics"]["asset_count_from_editor"] == 2
    assert summary.status_code == 200
    assert summary.json()["summary"]["asset_type_counts"]["StaticMesh"] == 1
    assert summary.json()["summary"]["scan_diagnostics"]["code_file_count_from_scanner"] == 1
    assert static_meshes.status_code == 200
    assert static_meshes.json()["items"][0]["settings"]["nanite_enabled"] is True
    assert nanite_query.status_code == 200
    assert nanite_query.json()["items"][0]["asset_name"] == "SM_Rock"
    assert code_files.status_code == 200
    assert code_files.json()["items"][0]["classes"] == ["ARBPlayerCharacter"]
    assert code_files.json()["items"][0]["last_modified"] == "2026-04-23T09:59:00Z"
    assert asset_detail.status_code == 200
    assert asset_detail.json()["item"]["asset_path"] == "/Game/Environment/SM_Rock.SM_Rock"
    assert asset_name_query.status_code == 200
    assert asset_name_query.json()["items"][0]["asset_name"] == "BP_PlayerCharacter"
    assert code_name_query.status_code == 200
    assert code_name_query.json()["items"][0]["file_path"] == "Source/RushBa/Player/RBPlayerCharacter.cpp"


def test_agent_chat_project_qa_can_answer_from_project_inventory(client: TestClient) -> None:
    snapshot = client.post(
        "/api/v1/project-inventory/snapshot",
        json={
            "project_id": "RushBa",
            "project_name": "RushBa",
            "assets": [
                {
                    "asset_path": "/Game/Environment/SM_Rock.SM_Rock",
                    "asset_name": "SM_Rock",
                    "asset_type": "StaticMesh",
                    "settings": {"nanite_enabled": True, "lod_count": 3},
                }
            ],
        },
    )
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "inventory_chat_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "这个工程里有哪些开启 Nanite 的静态网格体？",
                        "language": "auto",
                    }
                ],
            },
            "context": {"project_name": "RushBa", "active_panel": "AgentChat"},
            "payload": {"user_query": "这个工程里有哪些开启 Nanite 的静态网格体？"},
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
    body = response.json()

    assert snapshot.status_code == 200
    assert response.status_code == 200
    assert body["intent"]["route_type"] == "project_qa"
    assert body["data"]["inventory"]["items"]
    assert body["data"]["inventory"]["items"][0]["asset_name"] == "SM_Rock"
    assert "SM_Rock" in body["assistant_message"]
    assert body["debug_view"]["inventory"]["summary"]["asset_match_count"] == 1


def test_agent_chat_project_asset_listing_selects_inventory_tool(client: TestClient) -> None:
    snapshot = client.post(
        "/api/v1/project-inventory/snapshot",
        json={
            "project_id": "RushBa",
            "project_name": "RushBa",
            "assets": [
                {
                    "asset_path": "/Game/Blueprints/BP_PlayerCharacter.BP_PlayerCharacter",
                    "asset_name": "BP_PlayerCharacter",
                    "asset_type": "Blueprint",
                    "settings": {"parent_class": "ACharacter"},
                },
                {
                    "asset_path": "/Game/Blueprints/BP_EnemySpawner.BP_EnemySpawner",
                    "asset_name": "BP_EnemySpawner",
                    "asset_type": "Blueprint",
                    "settings": {"parent_class": "AActor"},
                },
            ],
        },
    )
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "inventory_blueprint_chat_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "当前项目有哪些蓝图资产？",
                        "language": "auto",
                    }
                ],
            },
            "context": {"project_name": "RushBa", "active_panel": "AgentChat"},
            "payload": {"user_query": "当前项目有哪些蓝图资产？"},
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
    body = response.json()

    assert snapshot.status_code == 200
    assert response.status_code == 200
    assert body["intent"]["route_type"] == "project_qa"
    assert body["debug_view"]["route"]["selected_tool_id"] == "query_project_inventory"
    assert "inspect_asset_metadata" not in body["debug_view"]["route"]["candidate_tool_ids"]
    assert body["data"]["tool_plan"]["selected_tool_id"] == "query_project_inventory"
    assert body["data"]["react_loop"]["mode"] == "react_lite"
    assert body["data"]["react_loop"]["stop_reason"] == "agent_decided_done"
    assert any(
        item.get("tool_id") == "query_project_inventory"
        for item in body["debug_view"]["react_loop"]["steps"]
    )
    assert body["data"]["inventory"]["summary"]["inferred_asset_type"] == "Blueprint"
    assert len(body["data"]["inventory"]["items"]) == 2
    assert body["debug_view"]["tools"][0]["tool_id"] == "retrieve_project_knowledge"
    assert body["debug_view"]["tools"][0]["status"] == "skipped"
    assert body["debug_view"]["tools"][1]["tool_id"] == "query_project_inventory"
    assert body["debug_view"]["tools"][1]["status"] == "completed"
    assert "BP_PlayerCharacter" in body["assistant_message"]
    assert "BP_EnemySpawner" in body["assistant_message"]


def test_agent_chat_project_asset_listing_handles_prefix_and_missing_snapshot(client: TestClient) -> None:
    query = "\u6211\u5f53\u524d\u9879\u76ee\u7684\u84dd\u56fe\u8d44\u4ea7\u6709\u54ea\u4e9b\uff0c\u4f60\u5217\u4e00\u4e0b"
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "inventory_missing_snapshot_chat_session",
                "messages": [{"role": "user", "content": query, "language": "auto"}],
            },
            "context": {"project_name": "MissingSnapshotProject", "active_panel": "AgentChat"},
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
    body = response.json()

    assert response.status_code == 200
    assert body["intent"]["route_type"] == "project_qa"
    assert body["debug_view"]["route"]["selected_tool_id"] == "query_project_inventory"
    assert body["data"]["inventory"]["items"] == []
    assert body["data"]["inventory"]["summary"]["empty_reason"] == "no_project_inventory_snapshot"
    assert body["data"]["tool_plan"]["use_inventory"] is True
    assert body["assistant_message"].strip()
    assert "Project Inventory" in body["assistant_message"]


def test_agent_chat_project_asset_listing_supports_compact_chinese_query(client: TestClient) -> None:
    snapshot = client.post(
        "/api/v1/project-inventory/snapshot",
        json={
            "project_id": "CompactQueryProject",
            "project_name": "CompactQueryProject",
            "assets": [
                {
                    "asset_path": "/Game/Blueprints/BP_PlayerCharacter.BP_PlayerCharacter",
                    "asset_name": "BP_PlayerCharacter",
                    "asset_type": "Blueprint",
                    "settings": {"parent_class": "ACharacter"},
                },
                {
                    "asset_path": "/Game/Blueprints/BP_EnemySpawner.BP_EnemySpawner",
                    "asset_name": "BP_EnemySpawner",
                    "asset_type": "Blueprint",
                    "settings": {"parent_class": "AActor"},
                },
            ],
        },
    )
    query = "\u5f53\u524d\u9879\u76ee\u84dd\u56fe\u8d44\u4ea7\u6709\u54ea\u4e9b"
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "inventory_compact_query_chat_session",
                "messages": [{"role": "user", "content": query, "language": "auto"}],
            },
            "context": {"project_name": "CompactQueryProject", "active_panel": "AgentChat"},
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
    body = response.json()

    assert snapshot.status_code == 200
    assert response.status_code == 200
    assert body["debug_view"]["route"]["selected_tool_id"] == "query_project_inventory"
    assert body["data"]["inventory"]["summary"]["inferred_asset_type"] == "Blueprint"
    assert len(body["data"]["inventory"]["items"]) == 2
    assert "BP_PlayerCharacter" in body["assistant_message"]
    assert "BP_EnemySpawner" in body["assistant_message"]


def test_agent_chat_project_qa_can_read_current_project_file(client: TestClient) -> None:
    project_root = Path(".test-runtime") / f"react-file-read-{uuid.uuid4().hex}"
    source_file = project_root / "Source" / "Demo" / "PlayerCharacter.cpp"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text(
        "void APlayerCharacter::BeginPlay()\n{\n    Super::BeginPlay();\n    SetupEnhancedInput();\n}\n",
        encoding="utf-8",
    )
    try:
        query = "请解释当前文件里做了什么"
        response = client.post(
            "/api/v1/chat/runs",
            json={
                "task_type": "agent_chat",
                "session": {
                    "session_id": "react_file_read_chat_session",
                    "messages": [{"role": "user", "content": query, "language": "auto"}],
                },
                "context": {
                    "project_name": "ReadFileProject",
                    "project_root": str(project_root.resolve()),
                    "active_panel": "AgentChat",
                    "current_file": "Source/Demo/PlayerCharacter.cpp",
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
        body = response.json()

        assert response.status_code == 200
        assert body["intent"]["route_type"] == "project_qa"
        assert body["data"]["project_file"]["status"] == "completed"
        assert "SetupEnhancedInput" in body["data"]["project_file"]["text_excerpt"]
        assert body["data"]["tool_contracts"]["input_contracts"]
        assert all(item["ok"] for item in body["data"]["tool_contracts"]["input_contracts"])
        assert all(item["ok"] for item in body["debug_view"]["tool_contracts"]["result_contracts"])
        assert body["data"]["self_reflection"]["status"] in {"passed", "degraded"}
        assert body["debug_view"]["self_reflection"]["grounding_level"] == "project_grounded"
        assert any(item["tool_id"] == "read_project_file" for item in body["debug_view"]["tools"])
        assert any(
            item.get("tool_id") == "read_project_file"
            for item in body["debug_view"]["react_loop"]["steps"]
        )
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_agent_chat_recalls_project_long_term_memory_across_sessions(client: TestClient) -> None:
    project_name = f"MemoryProject_{uuid.uuid4().hex[:8]}"
    first = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": f"memory_source_{uuid.uuid4().hex}",
                "messages": [
                    {
                        "role": "user",
                        "content": "请记住：我们的项目 UE 版本是 5.4，所有蓝图命名要加 BP_ 前缀。",
                        "language": "auto",
                    }
                ],
            },
            "context": {"project_name": project_name, "active_panel": "AgentChat"},
            "payload": {"user_query": "请记住：我们的项目 UE 版本是 5.4，所有蓝图命名要加 BP_ 前缀。"},
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
    second = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": f"memory_reader_{uuid.uuid4().hex}",
                "messages": [
                    {
                        "role": "user",
                        "content": "创建新蓝图应该注意什么？",
                        "language": "auto",
                    }
                ],
            },
            "context": {"project_name": project_name, "active_panel": "AgentChat"},
            "payload": {"user_query": "创建新蓝图应该注意什么？"},
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
    body = second.json()

    assert first.status_code == 200
    assert second.status_code == 200
    memory = body["data"]["context_bundle"]["long_term_memory"]
    assert memory["status"] == "available"
    assert any("BP_" in item["text"] and "5.4" in item["text"] for item in memory["items"])
    assert body["debug_view"]["memory_summary"]["long_term_memory"]["count"] >= 1


def test_create_task_and_fetch_dual_views(client: TestClient) -> None:
    created = client.post(
        "/api/v1/tasks/project-qa",
        json={
            "task_type": "project_qa",
            "session": {
                "session_id": "integration_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "帮我审视当前项目配置流程",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "CodeAssistant",
                "current_file": "Config/DefaultGame.ini",
                "current_module": "CoreGame",
            },
            "payload": {"user_query": "帮我审视当前项目配置流程"},
            "ui_state": {"active_view": "debug", "selected_panel": "ProjectQA"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )
    created_body = created.json()
    task_id = created_body["task"]["task_id"]
    task_detail = client.get(f"/api/v1/tasks/{task_id}")
    user_view = client.get(f"/api/v1/tasks/{task_id}/user-view")
    debug_view = client.get(f"/api/v1/tasks/{task_id}/debug-view")
    trace_view = client.get(f"/api/v1/tasks/{task_id}/trace")
    recent = client.get("/api/v1/tasks/recent")

    assert created.status_code == 200
    assert task_detail.status_code == 200
    assert user_view.status_code == 200
    assert debug_view.status_code == 200
    assert trace_view.status_code == 200
    assert recent.status_code == 200

    assert user_view.json()["text"] == task_detail.json()["user_view"]["text"]
    assert debug_view.json()["route"]["route_type"] == task_detail.json()["intent"]["route_type"]
    assert trace_view.json()["trace_summary"]["trace_id"] == task_detail.json()["task"]["trace_id"]
    assert recent.json()["items"]


def test_kb_refresh_builds_documents_and_chunks(client: TestClient) -> None:
    refreshed = client.post(
        "/api/v1/knowledge-base/refresh",
        json={"source_paths": ["../backend.md"], "force_rebuild": True},
    )
    refreshed_body = refreshed.json()
    job_id = refreshed_body["job"]["job_id"]
    job = client.get(f"/api/v1/knowledge-base/import-jobs/{job_id}")
    status = client.get("/api/v1/knowledge-base/status")

    assert refreshed.status_code == 200
    assert job.status_code == 200
    assert status.status_code == 200
    assert job.json()["job"]["status"] == "completed"
    summary = status.json()["summary"]
    readiness = summary["rag_readiness"]
    assert summary["documents"] >= 1
    assert summary["chunks"] >= 1
    assert summary["effective_mode"] == "lexical_only"
    assert readiness["status"] == "degraded"
    assert readiness["lexical_ready"] is True
    assert readiness["usable_for_project_qa"] is True
    assert readiness["vector_store_ready"] is False
    assert readiness["indexed_documents"] >= 1
    assert readiness["indexed_chunks"] >= 1
    assert readiness["domain_counts"]["project_docs"] >= 1
    assert "run_rag_eval.py" in readiness["eval_command"]
    assert summary["ingestion_pipeline"] == [
        "loader",
        "parser",
        "cleaner",
        "chunker",
        "lexical_index",
        "embedding",
        "vector_store",
        "retrieval",
    ]
    assert "cpp" in summary["format_groups"]["code"]


def test_kb_import_text_accepts_content_metadata_and_tags(client: TestClient) -> None:
    imported = client.post(
        "/api/v1/knowledge-base/import",
        json={
            "source_type": "text",
            "title": "Actor Tick Example",
            "content": "AMyActor::AMyActor() { PrimaryActorTick.bCanEverTick = false; }",
            "domain": "code_reference",
            "metadata": {"module": "RushBa", "language": "cpp"},
            "tags": ["example", "actor"],
        },
    )
    documents = client.get("/api/v1/knowledge-base/documents")
    matching = [
        item for item in documents.json()["items"] if item["title"] == "Actor Tick Example"
    ]

    assert imported.status_code == 200
    assert imported.json()["job"]["status"] == "completed"
    assert matching
    assert matching[0]["domain"] == "code_reference"
    assert matching[0]["doc_type"] == "code"
    assert matching[0]["module"] == "RushBa"
    assert matching[0]["tags"] == ["example", "actor"]
    assert matching[0]["metadata"]["language"] == "cpp"


def test_session_create_restore_history_tasks_and_clear(client: TestClient) -> None:
    created = client.post(
        "/api/v1/sessions",
        json={
            "session_id": "restorable_session",
            "project_name": "DemoProject",
            "preferred_output_language": "en-US",
            "profile_id": "default",
            "metadata": {"created_from": "frontend_restore_test"},
        },
    )
    chat = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "restorable_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Explain command-query separation in one paragraph.",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "AgentChat",
                "current_file": "Source/MyModule/MyActor.cpp",
            },
            "payload": {"user_query": "Explain command-query separation in one paragraph."},
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
    summary = client.get("/api/v1/sessions/restorable_session")
    history = client.get("/api/v1/sessions/restorable_session/history")
    tasks = client.get("/api/v1/sessions/restorable_session/tasks")
    cleared = client.post("/api/v1/sessions/restorable_session/clear")
    history_after = client.get("/api/v1/sessions/restorable_session/history")
    tasks_after = client.get("/api/v1/sessions/restorable_session/tasks")

    assert created.status_code == 200
    assert created.json()["item"]["session_id"] == "restorable_session"
    assert chat.status_code == 200
    assert summary.status_code == 200
    assert summary.json()["item"]["message_count"] >= 1
    assert summary.json()["item"]["task_count"] >= 1
    assert history.status_code == 200
    assert history.json()["items"]
    assert history.json()["items"][-1]["role"] == "assistant"
    assert tasks.status_code == 200
    assert tasks.json()["items"]
    assert tasks.json()["items"][0]["task"]["task_id"] == chat.json()["task"]["task_id"]
    assert cleared.status_code == 200
    assert cleared.json()["item"]["message_count"] == 0
    assert cleared.json()["item"]["task_count"] == 0
    assert history_after.status_code == 200
    assert history_after.json()["items"] == []
    assert tasks_after.status_code == 200
    assert tasks_after.json()["items"] == []


def test_session_history_restore_keeps_user_assistant_order_across_turns(client: TestClient) -> None:
    first_chat = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "restored_order_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "What is dependency inversion in one sentence?",
                        "language": "auto",
                    }
                ],
            },
            "context": {"project_name": "DemoProject", "active_panel": "AgentChat"},
            "payload": {"user_query": "What is dependency inversion in one sentence?"},
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
    first_history = client.get("/api/v1/sessions/restored_order_session/history")
    restored_messages = [
        {
            "role": item["role"],
            "content": item["content"],
            "language": item["language"],
        }
        for item in first_history.json()["items"]
    ]
    second_chat = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "restored_order_session",
                "messages": [
                    *restored_messages,
                    {
                        "role": "user",
                        "content": "And when should I care about it?",
                        "language": "auto",
                    },
                ],
            },
            "context": {"project_name": "DemoProject", "active_panel": "AgentChat"},
            "payload": {"user_query": "And when should I care about it?"},
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
    final_history = client.get("/api/v1/sessions/restored_order_session/history")
    items = final_history.json()["items"]

    assert first_chat.status_code == 200
    assert first_history.status_code == 200
    assert len(restored_messages) == 2
    assert restored_messages[0]["role"] == "user"
    assert restored_messages[1]["role"] == "assistant"
    assert second_chat.status_code == 200
    assert final_history.status_code == 200
    assert [item["role"] for item in items] == ["user", "assistant", "user", "assistant"]
    assert items[0]["content"] == "What is dependency inversion in one sentence?"
    assert items[2]["content"] == "And when should I care about it?"
    assert items[-1]["content"] == second_chat.json()["assistant_message"]


def test_session_memory_summary_compacts_long_chat_context(client: TestClient) -> None:
    session_id = "memory_summary_session"

    def post_chat(message: str):
        return client.post(
            "/api/v1/chat/runs",
            json={
                "task_type": "agent_chat",
                "session": {
                    "session_id": session_id,
                    "messages": [{"role": "user", "content": message, "language": "auto"}],
                },
                "context": {"active_panel": "AgentChat"},
                "payload": {"user_query": message},
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

    for index in range(10):
        response = post_chat(f"Tell me one short cooking tip number {index}.")
        assert response.status_code == 200

    session = client.get(f"/api/v1/sessions/{session_id}")
    memory = session.json()["item"]["memory_summary"]

    assert session.status_code == 200
    assert memory["status"] == "available"
    assert memory["version"] == "memory_summary_v1"
    assert memory["message_count"] >= 20
    assert memory["summarized_message_count"] >= 14

    follow_up = post_chat("Use our earlier discussion and summarize what we have covered.")
    body = follow_up.json()
    context_summary = body["debug_view"]["context_bundle"]["session_summary"]
    recent_text = "\n".join(item["content"] for item in body["debug_view"]["context_bundle"]["recent_messages"])

    assert follow_up.status_code == 200
    assert context_summary["status"] == "available"
    assert context_summary["version"] == "memory_summary_v1"
    assert context_summary["summarized_message_count"] >= 14
    assert len(body["debug_view"]["context_bundle"]["recent_messages"]) <= 8
    assert "cooking tip number 9" in recent_text
    assert "cooking tip number 0" not in recent_text
    assert body["debug_view"]["memory_summary"]["updated_session_memory"]["status"] == "available"


def test_tool_tasks_do_not_pollute_agent_chat_session_history(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks/code-review",
        json={
            "task_type": "code_review",
            "session": {
                "session_id": "tool_task_history_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Review this Unreal snippet.",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "CodeReview",
                "current_file": "Source/Demo/MyActor.cpp",
            },
            "payload": {
                "user_query": "Review this Unreal snippet.",
                "code": "void AMyActor::Tick(float DeltaTime) { Super::Tick(DeltaTime); }",
            },
            "ui_state": {"active_view": "user", "selected_panel": "CodeReview"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )
    history = client.get("/api/v1/sessions/tool_task_history_session/history")
    tasks = client.get("/api/v1/sessions/tool_task_history_session/tasks")

    assert response.status_code == 200
    assert history.status_code == 200
    assert history.json()["items"] == []
    assert tasks.status_code == 200
    assert tasks.json()["items"]

    follow_up = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "tool_task_history_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Summarize what tool task just ran.",
                        "language": "auto",
                    }
                ],
            },
            "context": {"active_panel": "AgentChat"},
            "payload": {"user_query": "Summarize what tool task just ran."},
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
    follow_up_history = client.get("/api/v1/sessions/tool_task_history_session/history")
    context_bundle = follow_up.json()["debug_view"]["context_bundle"]

    assert follow_up.status_code == 200
    assert context_bundle["tool_context"]
    assert context_bundle["tool_context"][0]["task_type"] == "code_review"
    assert [item["role"] for item in follow_up_history.json()["items"]] == ["user", "assistant"]


def test_project_qa_returns_confidence_and_citations(client: TestClient) -> None:
    client.post(
        "/api/v1/knowledge-base/refresh",
        json={"source_paths": ["../backend.md"], "force_rebuild": True},
    )
    response = client.post(
        "/api/v1/tasks/project-qa",
        json={
            "task_type": "project_qa",
            "session": {
                "session_id": "qa_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "\u8bf7\u7ed3\u5408\u540e\u7aef\u6587\u6863\u8bf4\u660e user_view \u548c debug_view \u7684\u804c\u8d23",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "AgentChat",
                "current_file": "backend.md",
                "kb_domains_hint": ["project_docs"],
            },
            "payload": {
                "user_query": "\u8bf7\u7ed3\u5408\u540e\u7aef\u6587\u6863\u8bf4\u660e user_view \u548c debug_view \u7684\u804c\u8d23",
                "domain_filters": ["project_docs"],
            },
            "ui_state": {"active_view": "user", "selected_panel": "ProjectQA"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert body["intent"]["route_type"] == "project_qa"
    assert body["data"]["confidence"] > 0
    assert body["data"]["citations"]
    assert body["user_view"]["citations_preview"]
    assert body["retrieval_trace"]["retrieved_docs"]
    assert body["debug_view"]["context_bundle"]["version"] == "context_bundle_v1"
    assert body["data"]["context_bundle"]["input_summary"]["route_type"] == "project_qa"
    decision_trace = body["debug_view"]["agent_decision_trace"]
    assert decision_trace["version"] == "agent_decision_trace_v1"
    assert decision_trace["summary"]["route_type"] == "project_qa"
    assert decision_trace["decisions"]["retrieval_decision"]["details"]["retrieved_count"] == len(
        body["retrieval_trace"]["retrieved_docs"]
    )


def test_agent_chat_knowledge_catalog_lists_sources_without_code_bodies(client: TestClient) -> None:
    client.post(
        "/api/v1/knowledge-base/reindex",
        json={"source_paths": ["./knowledge"]},
    )
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "knowledge_catalog_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "知识库有哪些内容",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "AgentChat",
            },
            "payload": {"user_query": "知识库有哪些内容"},
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
    body = response.json()
    answer = body["assistant_message"]

    assert response.status_code == 200
    assert body["intent"]["route_type"] == "project_qa"
    assert body["data"]["answer_mode"] == "knowledge_catalog"
    assert body["data"]["catalog"]["document_count"] > 0
    assert "当前知识库已索引" in answer
    assert "knowledge/engine-notes" in answer
    assert "#include" not in answer
    assert "UCLASS(" not in answer
    assert body["data"]["answer_generation"]["mode"] == "knowledge_catalog"
    assert body["data"]["answer_generation"]["provider"] == "openai_compatible"


def test_project_qa_chinese_actor_lifecycle_hits_engine_note(client: TestClient) -> None:
    client.post(
        "/api/v1/knowledge-base/reindex",
        json={"source_paths": ["./knowledge"]},
    )
    response = client.post(
        "/api/v1/tasks/project-qa",
        json={
            "task_type": "project_qa",
            "session": {
                "session_id": "actor_lifecycle_zh_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "actor的生命周期是什么",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "AgentChat",
            },
            "payload": {"user_query": "actor的生命周期是什么"},
            "ui_state": {"active_view": "user", "selected_panel": "ProjectQA"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert body["intent"]["route_type"] == "project_qa"
    assert body["data"]["retrieved_docs"]
    assert any(
        "ue-actor-lifecycle" in item["source_path"]
        for item in body["data"]["retrieved_docs"]
    )
    assert body["data"]["citations"]
    assert body["debug_view"]["retrieval"]["mode"] in {
        "lexical_only",
        "local_hybrid_fallback",
        "hybrid_vector",
        "semantic_vector",
    }


def test_project_qa_explicit_english_preference_keeps_english_locale(client: TestClient) -> None:
    client.post(
        "/api/v1/knowledge-base/refresh",
        json={"source_paths": ["../backend.md"], "force_rebuild": True},
    )
    response = client.post(
        "/api/v1/tasks/project-qa",
        json={
            "task_type": "project_qa",
            "session": {
                "session_id": "qa_session_en",
                "messages": [
                    {
                        "role": "user",
                        "content": "Which locale fields are required by the backend language policy?",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "AgentChat",
                "current_file": "backend.md",
                "kb_domains_hint": ["project_docs"],
            },
            "payload": {
                "user_query": "Which locale fields are required by the backend language policy?",
                "domain_filters": ["project_docs"],
            },
            "ui_state": {"active_view": "user", "selected_panel": "ProjectQA"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "en-US",
                "return_debug_projection": True,
            },
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert body["intent"]["route_type"] == "project_qa"
    assert body["locale"]["final_output_language"] == "en-US"
    assert body["data"]["citations"]


def test_direct_chat_skips_kb_retrieval(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Explain what topological sorting means in simple terms.",
                        "language": "auto",
                    }
                ],
            },
            "context": {"active_panel": "AgentChat"},
            "payload": {"user_query": "Explain what topological sorting means in simple terms."},
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
    body = response.json()

    assert response.status_code == 200
    assert body["intent"]["route_type"] == "direct_answer"
    assert body["retrieval_trace"]["mode"] == "not_used"
    assert body["debug_view"]["skill"]["protocol_version"] == "skill_protocol_v1"
    assert body["debug_view"]["skill"]["skill_id"] == "ProjectQASkill"
    assert body["debug_view"]["skill"]["retrieval_active"] is False
    assert body["debug_view"]["skill"]["lifecycle"]["collector"]["status"] == "completed"
    assert body["debug_view"]["skill"]["lifecycle"]["rules"]["status"] == "completed"
    assert body["debug_view"]["skill"]["lifecycle"]["retrieval"]["status"] == "skipped"
    assert body["debug_view"]["skill"]["lifecycle"]["llm"]["status"] == "skipped"
    assert body["debug_view"]["skill"]["lifecycle"]["llm"]["reason"] == "degraded_fallback"
    assert body["debug_view"]["skill"]["lifecycle"]["projector"]["status"] == "completed"
    assert body["data"]["skill"]["collector"] == "chat_messages_and_editor_context"
    assert body["trace_summary"]["skill_id"] == "ProjectQASkill"
    assert body["debug_view"]["context_bundle"]["version"] == "context_bundle_v1"
    assert body["debug_view"]["context_bundle"]["input_summary"]["route_type"] == "direct_answer"
    assert body["debug_view"]["context_bundle"]["recent_messages"]
    assert "context_budget" in body["debug_view"]["memory_summary"]
    assert body["data"]["context_bundle"]["version"] == "context_bundle_v1"
    decision_trace = body["debug_view"]["agent_decision_trace"]
    assert decision_trace["version"] == "agent_decision_trace_v1"
    assert decision_trace["summary"]["route_type"] == "direct_answer"
    assert decision_trace["decisions"]["intent_decision"]["decision"] == "direct_answer"
    assert decision_trace["decisions"]["context_decision"]["details"]["context_bundle_version"] == "context_bundle_v1"
    assert decision_trace["decisions"]["retrieval_decision"]["decision"] == "not_used"


def test_direct_chat_with_project_context_still_skips_kb_when_query_is_generic(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_session_with_context",
                "messages": [
                    {
                        "role": "user",
                        "content": "Explain event sourcing in simple terms.",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "AgentChat",
                "current_file": "Source/MyModule/MyActor.cpp",
                "current_module": "MyModule",
            },
            "payload": {"user_query": "Explain event sourcing in simple terms."},
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
    body = response.json()

    assert response.status_code == 200
    assert body["intent"]["route_type"] == "direct_answer"
    assert body["retrieval_trace"]["mode"] == "not_used"
    assert body["debug_view"]["route"]["project_signal_strength"] == "weak"


def test_agent_chat_with_explicit_project_reference_routes_to_project_qa(client: TestClient) -> None:
    client.post(
        "/api/v1/knowledge-base/refresh",
        json={"source_paths": ["../backend.md"], "force_rebuild": True},
    )
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_session_project_qa",
                "messages": [
                    {
                        "role": "user",
                        "content": "Explain how this file and the backend docs define the dual-view contract.",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "AgentChat",
                "current_file": "backend.md",
                "current_module": "Backend",
                "kb_domains_hint": ["project_docs"],
            },
            "payload": {
                "user_query": "Explain how this file and the backend docs define the dual-view contract.",
                "domain_filters": ["project_docs"],
            },
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
    body = response.json()

    assert response.status_code == 200
    assert body["intent"]["route_type"] == "project_qa"
    assert body["retrieval_trace"]["retrieved_docs"]
    assert body["debug_view"]["route"]["decision_source"] == "heuristic_strong_project_signal"
    assert body["debug_view"]["skill"]["skill_id"] == "ProjectQASkill"
    assert body["debug_view"]["skill"]["retrieval_active"] is True


def test_ambiguous_agent_chat_can_be_promoted_to_project_qa_by_llm_judge(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client.post(
        "/api/v1/knowledge-base/refresh",
        json={"source_paths": ["../backend.md"], "force_rebuild": True},
    )

    def _fake_route_judge(self, *, messages, config):  # type: ignore[no-untyped-def]
        assert messages
        assert config.profile_id == "default"
        return {
            "ok": True,
            "route_type": "project_qa",
            "confidence": 0.91,
            "reason": "The user is asking about repository-specific architecture.",
            "error": "",
            "provider": "openai_compatible",
            "model": config.model,
            "profile_id": config.profile_id,
            "usage": {
                "input_tokens": 12,
                "output_tokens": 7,
                "estimated_cost_usd": 0.0,
                "latency_ms": 9,
            },
        }

    monkeypatch.setattr("app.services.llm_service.LLMService.classify_agent_chat", _fake_route_judge)

    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_session_llm_router",
                "messages": [
                    {
                        "role": "user",
                        "content": "How is this organized?",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "AgentChat",
                "current_file": "backend.md",
                "current_module": "Backend",
            },
            "payload": {"user_query": "How is this organized?"},
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
    body = response.json()

    assert response.status_code == 200
    assert body["intent"]["route_type"] == "project_qa"
    assert body["debug_view"]["route"]["decision_source"] == "llm_route_judge"
    assert body["debug_view"]["route"]["llm_route_decision"]["route_type"] == "project_qa"


def test_agent_chat_llm_route_parse_failure_does_not_500(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_complete(self, *, messages, config):  # type: ignore[no-untyped-def]
        return {
            "ok": True,
            "reason": "completed",
            "error": "",
            "provider": "openai_compatible",
            "model": config.model,
            "profile_id": config.profile_id,
            "text": "not json",
            "usage": {
                "input_tokens": 4,
                "output_tokens": 2,
                "estimated_cost_usd": 0.0,
                "latency_ms": 3,
            },
        }

    monkeypatch.setattr("app.services.llm_service.LLMService.complete", _fake_complete)

    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_session_llm_router_invalid_json",
                "messages": [
                    {
                        "role": "user",
                        "content": "How is this organized?",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "AgentChat",
                "current_file": "Source/Demo/DemoActor.cpp",
                "current_module": "Demo",
            },
            "payload": {"user_query": "How is this organized?"},
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
    body = response.json()

    assert response.status_code == 200
    assert body["debug_view"]["route"]["llm_route_decision"]["status"] == "skipped"
    assert body["debug_view"]["route"]["llm_route_decision"]["reason"] == "route_parse_failed"


def test_agent_chat_missing_llm_route_decision_does_not_500(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_route_judge(self, *, messages, config):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr("app.services.llm_service.LLMService.classify_agent_chat", _fake_route_judge)

    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_session_llm_router_none",
                "messages": [
                    {
                        "role": "user",
                        "content": "How is this organized?",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "AgentChat",
                "current_file": "Source/Demo/DemoActor.cpp",
                "current_module": "Demo",
            },
            "payload": {"user_query": "How is this organized?"},
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
    body = response.json()

    assert response.status_code == 200
    assert body["debug_view"]["route"]["llm_route_decision"]["status"] == "skipped"
    assert body["debug_view"]["route"]["llm_route_decision"]["reason"] == "llm_route_decision_missing"


def test_direct_chat_uses_live_llm_when_available(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_complete(self, *, messages, config):  # type: ignore[no-untyped-def]
        assert messages
        assert config.model
        return {
            "ok": True,
            "reason": "completed",
            "error": "",
            "provider": "openai_compatible",
            "model": config.model,
            "profile_id": config.profile_id,
            "text": "Topological sorting orders nodes so every dependency appears before the node that needs it.",
            "usage": {
                "input_tokens": 24,
                "output_tokens": 19,
                "estimated_cost_usd": 0.0,
                "latency_ms": 18,
            },
        }

    monkeypatch.setattr("app.services.llm_service.LLMService.complete", _fake_complete)

    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "chat_session_live",
                "messages": [
                    {
                        "role": "user",
                        "content": "Explain topological sorting in one sentence.",
                        "language": "auto",
                    }
                ],
            },
            "context": {"active_panel": "AgentChat"},
            "payload": {"user_query": "Explain topological sorting in one sentence."},
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
    body = response.json()

    assert response.status_code == 200
    assert body["assistant_message"].startswith("Topological sorting orders nodes")
    assert body["data"]["answer_generation"]["mode"] == "live_llm"
    assert body["debug_view"]["tools"][0]["tool_id"] == "llm_direct_answer"
    assert body["usage"]["input_tokens"] == 24
    assert body["usage"]["output_tokens"] == 19


def test_code_review_workflow_persists_artifacts_and_events(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks/code-review",
        json={
            "task_type": "code_review",
            "session": {
                "session_id": "code_review_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Review this Unreal diff for lifetime and loading issues.",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "CodeReview",
                "current_file": "Source/MyModule/MyActor.cpp",
                "current_module": "MyModule",
            },
            "payload": {
                "user_query": "Review this Unreal diff for lifetime and loading issues.",
                "diff_text": "@@\n+ UObject* RawAsset = nullptr;\n+ virtual void Tick(float DeltaTime) override;\n+ auto Asset = LoadObject<UObject>(nullptr, TEXT(\"/Game/Hero/Hero01\"));\n",
            },
            "ui_state": {"active_view": "user", "selected_panel": "CodeReview"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )
    body = response.json()
    task_id = body["task"]["task_id"]
    run_id = body["task"]["run_id"]
    artifacts = client.get(f"/api/v1/tasks/{task_id}/artifacts")
    stream = client.get(f"/api/v1/chat/runs/{run_id}/events/stream")

    assert response.status_code == 200
    assert body["intent"]["route_type"] == "workflow"
    assert body["data"]["issue_list"]
    assert body["debug_view"]["tools"]
    assert artifacts.status_code == 200
    assert artifacts.json()["items"]
    assert stream.status_code == 200
    assert "event: run_started" in stream.text
    assert "event: step_completed" in stream.text


def test_chat_run_stream_endpoint_keeps_non_streaming_fallback(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/runs/stream",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": f"stream_session_{uuid.uuid4().hex}",
                "messages": [
                    {
                        "role": "user",
                        "content": "你好，简单介绍一下这个助手。",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "AgentChat",
            },
            "payload": {"user_query": "你好，简单介绍一下这个助手。"},
            "ui_state": {"active_view": "user", "selected_panel": "AgentChat"},
            "runtime_options": {
                "profile_id": "default",
                "stream": True,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: stream_opened" in response.text
    assert "event: run_started" in response.text
    assert "event: final" in response.text
    assert '"fallback_endpoint": "/api/v1/chat/runs"' in response.text


def test_chat_run_stream_endpoint_emits_assistant_delta(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_complete(self, *, messages, config, stream_sink=None):  # type: ignore[no-untyped-def]
        if stream_sink:
            stream_sink("Hello")
            stream_sink(" world")
        return {
            "ok": True,
            "reason": "completed",
            "error": "",
            "provider": "openai_compatible",
            "model": config.model,
            "profile_id": config.profile_id,
            "text": "Hello world",
            "usage": {
                "input_tokens": 1,
                "output_tokens": 2,
                "estimated_cost_usd": 0.0,
                "latency_ms": 1,
            },
        }

    monkeypatch.setattr("app.services.llm_service.LLMService.complete", _fake_complete)

    response = client.post(
        "/api/v1/chat/runs/stream",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": f"stream_delta_session_{uuid.uuid4().hex}",
                "messages": [
                    {
                        "role": "user",
                        "content": "Say hello.",
                        "language": "auto",
                    }
                ],
            },
            "context": {"active_panel": "AgentChat"},
            "payload": {"user_query": "Say hello."},
            "ui_state": {"active_view": "user", "selected_panel": "AgentChat"},
            "runtime_options": {
                "profile_id": "default",
                "stream": True,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )

    assert response.status_code == 200
    assert "event: assistant_delta" in response.text
    assert '"text": "Hello"' in response.text
    assert '"text": " world"' in response.text
    assert '"assistant_message": "Hello world"' in response.text


def test_code_review_file_listing_and_selected_file_review(client: TestClient) -> None:
    project_root = Path(".test-workspace") / f"code review {uuid.uuid4().hex}"
    code_dir = project_root / "Source" / "MyModule"
    plugin_code_dir = project_root / "Plugins" / "My Plugin" / "Source" / "MyPluginRuntime" / "Public"
    shutil.rmtree(project_root, ignore_errors=True)
    code_dir.mkdir(parents=True, exist_ok=True)
    plugin_code_dir.mkdir(parents=True, exist_ok=True)
    try:
        file_path = code_dir / "MyActor.cpp"
        file_path.write_text(
            '#include "MyActor.h"\n'
            "void AMyActor::Tick(float DeltaTime)\n"
            "{\n"
            '    auto Asset = LoadObject<UObject>(nullptr, TEXT("/Game/Hero/Hero01"));\n'
            "}\n",
            encoding="utf-8",
        )
        plugin_file_path = plugin_code_dir / "MyTool.hpp"
        plugin_file_path.write_text("class FMyTool {};\n", encoding="utf-8")

        files = client.post(
            "/api/v1/tasks/code-review/files",
            json={
                "project_root": str(project_root.resolve()),
                "source_roots": ["Source"],
                "query": "MyActor",
                "limit": 50,
            },
        )
        files_body = files.json()

        assert files.status_code == 200
        assert files_body["returned_count"] == 1
        assert files_body["items"][0]["relative_path"] == "Source/MyModule/MyActor.cpp"
        assert files_body["items"][0]["file_path"] == "Source/MyModule/MyActor.cpp"
        assert files_body["items"][0]["label"] == "MyActor.cpp"
        assert files_body["items"][0]["module_name"] == "MyModule"
        assert files_body["items"][0]["file_type"] == "cpp"

        plugin_files = client.post(
            "/api/v1/tasks/code-review/files",
            json={
                "project_root": str(project_root.resolve()).replace("\\", "/") + "/",
                "source_roots": ["Source", "Plugins"],
                "query": "mypluginruntime",
                "limit": 200,
            },
        )
        plugin_body = plugin_files.json()

        assert plugin_files.status_code == 200
        assert plugin_body["returned_count"] == 1
        assert plugin_body["items"][0]["file_path"] == "Plugins/My Plugin/Source/MyPluginRuntime/Public/MyTool.hpp"
        assert plugin_body["items"][0]["module_name"] == "MyPluginRuntime"
        assert plugin_body["scan_diagnostics"]["existing_source_roots"] == ["Source", "Plugins"]

        review = client.post(
            "/api/v1/tasks/code-review",
            json={
                "task_type": "code_review",
                "session": {
                    "session_id": "code_review_selected_file_session",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Review the selected file.",
                            "language": "auto",
                        }
                    ],
                },
                "context": {
                    "project_name": "DemoProject",
                    "active_panel": "CodeReview",
                    "current_file": "Source/MyModule/MyActor.cpp",
                    "current_module": "MyModule",
                },
                "payload": {
                    "user_query": "Review the selected file.",
                    "project_root": str(project_root.resolve()),
                    "source_roots": ["Source"],
                    "file_path": "Source/MyModule/MyActor.cpp",
                    "focus": "General",
                },
                "ui_state": {"active_view": "user", "selected_panel": "CodeReview"},
                "runtime_options": {
                    "profile_id": "default",
                    "stream": False,
                    "debug": True,
                    "preferred_output_language": "auto",
                    "return_debug_projection": True,
                },
            },
        )
        body = review.json()

        assert review.status_code == 200
        assert body["task"]["status"] == "completed"
        assert body["debug_view"]["skill"]["protocol_version"] == "skill_protocol_v1"
        assert body["debug_view"]["skill"]["skill_id"] == "CodeReviewSkill"
        assert body["debug_view"]["skill"]["collector"] == "ue_project_code_file_scanner_and_reader"
        assert body["debug_view"]["skill"]["lifecycle"]["retrieval"]["status"] == "completed"
        assert body["debug_view"]["skill"]["lifecycle"]["llm"]["status"] == "skipped"
        assert body["debug_view"]["skill"]["lifecycle"]["llm"]["reason"] == "missing_openai_api_key"
        assert body["debug_view"]["local_search"]["mode"] == "local_grep"
        assert body["debug_view"]["local_search"]["summary"]["domain_filters"] == [
            "team_rules",
            "engine_notes",
            "project_docs",
            "examples",
        ]
        assert body["data"]["review_scope"]["source_kind"] == "file_path"
        assert body["data"]["review_scope"]["file_path"] == "Source/MyModule/MyActor.cpp"
        assert body["data"]["review_scope"]["resolved_absolute_path"]
        assert body["data"]["review_scope"]["read_status"] == "ok"
        assert body["data"]["review_scope"]["content_length"] > 0
        assert body["data"]["review_scope"]["applied_focus"] == "General"
        assert "hardcoded_asset_path" in body["data"]["rule_hits"]
        assert [block["block_type"] for block in body["user_view"]["blocks"][:6]] == [
            "summary",
            "llm_analysis",
            "issues",
            "recommendations",
            "references",
            "next_steps",
        ]
        block_types = [block["block_type"] for block in body["user_view"]["blocks"]]
        assert "agent_workflow" in block_types
        assert "fix_draft" in block_types
        assert "validation_plan" in block_types
        assert body["data"]["llm_analysis"]["status"] == "skipped"
        assert body["data"]["llm_analysis"]["reason_code"] == "missing_openai_api_key"
        assert "api key" in body["data"]["llm_analysis"]["reason"].lower()
        assert body["data"]["localized_review"]["issues"]
        assert body["data"]["llm_review"]["reason"] == "missing_openai_api_key"
        assert body["data"]["agent_workflow"]["version"] == "review_fix_validation_workflow_v1"
        assert body["data"]["fix_draft"]["write_policy"]["written_to_disk"] is False
        assert any(item["rule_id"] == "hardcoded_asset_path" for item in body["data"]["fix_draft"]["items"])
        assert any(item["category"] == "asset_reference" for item in body["data"]["validation_plan"]["items"])
        assert any(step["step_id"] == "draft_fix_plan" for step in body["step_results"])
        assert any(tool["tool_id"] == "build_validation_plan" for tool in body["debug_view"]["tools"])
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_code_review_live_llm_uses_compact_timeout_config(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = Path(".test-workspace") / f"code-review-llm-{uuid.uuid4().hex}"
    code_dir = project_root / "Source" / "MyModule"
    shutil.rmtree(project_root, ignore_errors=True)
    code_dir.mkdir(parents=True, exist_ok=True)
    try:
        file_path = code_dir / "MyActor.cpp"
        file_path.write_text(
            '#include "MyActor.h"\n'
            "void AMyActor::Tick(float DeltaTime)\n"
            "{\n"
            '    auto Asset = LoadObject<UObject>(nullptr, TEXT("/Game/Hero/Hero01"));\n'
            "}\n",
            encoding="utf-8",
        )

        def _fake_complete_json_object(self, *, messages, config):  # type: ignore[no-untyped-def]
            assert messages
            assert config.timeout_ms >= 60000
            assert config.max_tokens <= 700
            return {
                "ok": True,
                "payload": {
                    "summary": "The file should avoid synchronous asset loads on hot paths.",
                    "issues": [
                        {
                            "severity": "medium",
                            "line": 4,
                            "title": "Synchronous load in Tick",
                            "reason": "Tick should stay lightweight.",
                            "impact": "May stall the game thread.",
                            "suggestion": "Switch to a soft reference or preload path.",
                        }
                    ],
                    "recommendations": [
                        {"suggestion": "Move loading out of Tick."},
                    ],
                    "next_steps": ["Validate the actor in PIE."],
                },
                "reason": "completed",
                "error": "",
                "provider": "openai_compatible",
                "model": config.model,
                "profile_id": config.profile_id,
                "usage": {
                    "input_tokens": 40,
                    "output_tokens": 24,
                    "estimated_cost_usd": 0.0,
                    "latency_ms": 11,
                },
            }

        monkeypatch.setattr(
            "app.services.llm_service.LLMService.complete_json_object",
            _fake_complete_json_object,
        )

        review = client.post(
            "/api/v1/tasks/code-review",
            json={
                "task_type": "code_review",
                "session": {
                    "session_id": "code_review_live_llm_session",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Review the selected file.",
                            "language": "auto",
                        }
                    ],
                },
                "context": {
                    "project_name": "DemoProject",
                    "active_panel": "CodeReview",
                    "current_file": "Source/MyModule/MyActor.cpp",
                    "current_module": "MyModule",
                },
                "payload": {
                    "user_query": "Review the selected file.",
                    "project_root": str(project_root.resolve()),
                    "source_roots": ["Source"],
                    "file_path": "Source/MyModule/MyActor.cpp",
                    "focus": "General",
                },
                "ui_state": {"active_view": "user", "selected_panel": "CodeReview"},
                "runtime_options": {
                    "profile_id": "default",
                    "stream": False,
                    "debug": True,
                    "preferred_output_language": "auto",
                    "return_debug_projection": True,
                },
            },
        )
        body = review.json()

        assert review.status_code == 200
        assert body["data"]["llm_analysis"]["status"] == "completed"
        assert body["data"]["llm_review"]["reason"] == "completed"
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_code_review_llm_text_fallback_is_rendered_as_analysis(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = Path(".test-workspace") / f"code-review-text-fallback-{uuid.uuid4().hex}"
    code_dir = project_root / "Source" / "MyModule"
    shutil.rmtree(project_root, ignore_errors=True)
    code_dir.mkdir(parents=True, exist_ok=True)
    try:
        file_path = code_dir / "MyActor.cpp"
        file_path.write_text(
            '#include "MyActor.h"\n'
            "void AMyActor::Tick(float DeltaTime)\n"
            "{\n"
            '    auto Asset = LoadObject<UObject>(nullptr, TEXT("/Game/Hero/Hero01"));\n'
            "}\n",
            encoding="utf-8",
        )

        def _fake_complete_json_object(self, *, messages, config):  # type: ignore[no-untyped-def]
            assert messages
            return {
                "ok": False,
                "payload": None,
                "reason": "json_parse_failed",
                "error": "json_object_not_found",
                "provider": "openai_compatible",
                "model": config.model,
                "profile_id": config.profile_id,
                "text": "LLM saw the selected C++ file and recommends moving synchronous asset loading out of Tick.",
                "usage": {
                    "input_tokens": 40,
                    "output_tokens": 24,
                    "estimated_cost_usd": 0.0,
                    "latency_ms": 11,
                },
            }

        monkeypatch.setattr(
            "app.services.llm_service.LLMService.complete_json_object",
            _fake_complete_json_object,
        )

        review = client.post(
            "/api/v1/tasks/code-review",
            json={
                "task_type": "code_review",
                "session": {
                    "session_id": "code_review_text_fallback_session",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Review the selected file.",
                            "language": "auto",
                        }
                    ],
                },
                "context": {
                    "project_name": "DemoProject",
                    "active_panel": "CodeReview",
                    "current_file": "Source/MyModule/MyActor.cpp",
                    "current_module": "MyModule",
                },
                "payload": {
                    "user_query": "Review the selected file.",
                    "project_root": str(project_root.resolve()),
                    "source_roots": ["Source"],
                    "file_path": "Source/MyModule/MyActor.cpp",
                    "focus": "General",
                },
                "ui_state": {"active_view": "user", "selected_panel": "CodeReview"},
                "runtime_options": {
                    "profile_id": "default",
                    "stream": False,
                    "debug": True,
                    "preferred_output_language": "auto",
                    "return_debug_projection": True,
                },
            },
        )
        body = review.json()

        assert review.status_code == 200
        assert body["data"]["review_scope"]["read_status"] == "ok"
        assert body["data"]["llm_analysis"]["status"] == "completed"
        assert body["data"]["llm_review"]["reason"] == "completed_text_fallback"
        assert body["data"]["llm_review"]["structured"] is False
        assert "selected C++ file" in body["data"]["llm_analysis"]["text"]
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_code_review_llm_json_like_text_fallback_is_sanitized_for_highlights(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = Path(".test-workspace") / f"code-review-json-fallback-{uuid.uuid4().hex}"
    code_dir = project_root / "Source" / "MyModule"
    shutil.rmtree(project_root, ignore_errors=True)
    code_dir.mkdir(parents=True, exist_ok=True)
    try:
        file_path = code_dir / "MyActor.cpp"
        file_path.write_text(
            '#include "MyActor.h"\n'
            "void AMyActor::Tick(float DeltaTime)\n"
            "{\n"
            '    auto Asset = LoadObject<UObject>(nullptr, TEXT("/Game/Hero/Hero01"));\n'
            "}\n",
            encoding="utf-8",
        )

        def _fake_complete_json_object(self, *, messages, config):  # type: ignore[no-untyped-def]
            assert messages
            return {
                "ok": False,
                "payload": None,
                "reason": "json_parse_failed",
                "error": "json_object_not_found",
                "provider": "openai_compatible",
                "model": config.model,
                "profile_id": config.profile_id,
                "text": (
                    "```json\n"
                    '{"summary":{"overview":"The code still loads assets inside Tick."},'
                    '"issues":[{"title":{"text":"Synchronous load in Tick"},'
                    '"reason":{"message":"Tick runs every frame."},'
                    '"suggestion":{"text":"Move the load to initialization or async loading."}}],'
                    '"recommendations":[{"suggestion":"Use soft references for the asset path."}]}\n'
                    "```"
                ),
                "usage": {
                    "input_tokens": 40,
                    "output_tokens": 24,
                    "estimated_cost_usd": 0.0,
                    "latency_ms": 11,
                },
            }

        monkeypatch.setattr(
            "app.services.llm_service.LLMService.complete_json_object",
            _fake_complete_json_object,
        )

        review = client.post(
            "/api/v1/tasks/code-review",
            json={
                "task_type": "code_review",
                "session": {
                    "session_id": "code_review_json_fallback_session",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Review the selected file.",
                            "language": "auto",
                        }
                    ],
                },
                "context": {
                    "project_name": "DemoProject",
                    "active_panel": "CodeReview",
                    "current_file": "Source/MyModule/MyActor.cpp",
                    "current_module": "MyModule",
                },
                "payload": {
                    "user_query": "Review the selected file.",
                    "project_root": str(project_root.resolve()),
                    "source_roots": ["Source"],
                    "file_path": "Source/MyModule/MyActor.cpp",
                    "focus": "General",
                },
                "ui_state": {"active_view": "user", "selected_panel": "CodeReview"},
                "runtime_options": {
                    "profile_id": "default",
                    "stream": False,
                    "debug": True,
                    "preferred_output_language": "auto",
                    "return_debug_projection": True,
                },
            },
        )
        body = review.json()
        llm_block = next(
            block for block in body["user_view"]["blocks"] if block["block_type"] == "llm_analysis"
        )

        assert review.status_code == 200
        assert body["data"]["llm_analysis"]["status"] == "completed"
        assert body["data"]["llm_review"]["reason"] == "completed_text_fallback"
        assert body["data"]["llm_analysis"]["text"] == "The code still loads assets inside Tick."
        assert llm_block["text"] == "The code still loads assets inside Tick."
        assert not llm_block["text"].lstrip().startswith("{")
        assert "overview" not in llm_block["text"]
        assert body["data"]["llm_review"]["payload"]["issues"][0]["title"] == "Synchronous load in Tick"
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_code_review_malformed_json_like_text_extracts_llm_summary(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = Path(".test-workspace") / f"code-review-malformed-json-{uuid.uuid4().hex}"
    code_dir = project_root / "Source" / "MyModule"
    shutil.rmtree(project_root, ignore_errors=True)
    code_dir.mkdir(parents=True, exist_ok=True)
    try:
        file_path = code_dir / "MyActor.cpp"
        file_path.write_text(
            '#include "MyActor.h"\n'
            "void AMyActor::Tick(float DeltaTime)\n"
            "{\n"
            '    auto Asset = LoadObject<UObject>(nullptr, TEXT("/Game/Hero/Hero01"));\n'
            "}\n",
            encoding="utf-8",
        )

        def _fake_complete_json_object(self, *, messages, config):  # type: ignore[no-untyped-def]
            assert messages
            return {
                "ok": False,
                "payload": None,
                "reason": "json_parse_failed",
                "error": "invalid_unescaped_quote",
                "provider": "openai_compatible",
                "model": config.model,
                "profile_id": config.profile_id,
                "text": (
                    "{summary: \"The code synchronously loads an asset during Tick.\", "
                    "issues: [{title: \"LoadObject in Tick\", "
                    "reason: \"The copied snippet TEXT(\"/Game/Hero/Hero01\") makes the JSON invalid.\", "
                    "suggestion: \"Move loading to BeginPlay or an async path.\"}]}"
                ),
                "usage": {
                    "input_tokens": 40,
                    "output_tokens": 24,
                    "estimated_cost_usd": 0.0,
                    "latency_ms": 11,
                },
            }

        monkeypatch.setattr(
            "app.services.llm_service.LLMService.complete_json_object",
            _fake_complete_json_object,
        )

        review = client.post(
            "/api/v1/tasks/code-review",
            json={
                "task_type": "code_review",
                "session": {
                    "session_id": "code_review_malformed_json_fallback_session",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Review the selected file.",
                            "language": "auto",
                        }
                    ],
                },
                "context": {
                    "project_name": "DemoProject",
                    "active_panel": "CodeReview",
                    "current_file": "Source/MyModule/MyActor.cpp",
                    "current_module": "MyModule",
                },
                "payload": {
                    "user_query": "Review the selected file.",
                    "project_root": str(project_root.resolve()),
                    "source_roots": ["Source"],
                    "file_path": "Source/MyModule/MyActor.cpp",
                    "focus": "General",
                },
                "ui_state": {"active_view": "user", "selected_panel": "CodeReview"},
                "runtime_options": {
                    "profile_id": "default",
                    "stream": False,
                    "debug": True,
                    "preferred_output_language": "auto",
                    "return_debug_projection": True,
                },
            },
        )
        body = review.json()
        llm_block = next(
            block for block in body["user_view"]["blocks"] if block["block_type"] == "llm_analysis"
        )

        assert review.status_code == 200
        assert body["data"]["llm_analysis"]["status"] == "completed"
        assert body["data"]["llm_review"]["reason"] == "completed_text_fallback"
        assert body["data"]["llm_analysis"]["text"] == "The code synchronously loads an asset during Tick."
        assert llm_block["text"] == "The code synchronously loads an asset during Tick."
        assert "无法可靠解析" not in llm_block["text"]
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_code_review_without_selected_file_reports_frontend_payload_gap(client: TestClient) -> None:
    review = client.post(
        "/api/v1/tasks/code-review",
        json={
            "task_type": "code_review",
            "session": {
                "session_id": "code_review_missing_file_payload_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Review the selected file.",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "CodeReview",
                "current_file": "Source/MyModule/MyActor.cpp",
                "current_module": "MyModule",
            },
            "payload": {"user_query": "Review the selected file.", "focus": "General"},
            "ui_state": {"active_view": "user", "selected_panel": "CodeReview"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )
    body = review.json()

    assert review.status_code == 200
    assert body["data"]["review_scope"]["source_kind"] == "query_only"
    assert body["data"]["llm_analysis"]["status"] == "skipped"
    assert body["data"]["llm_analysis"]["reason_code"] == "missing_selected_code_content"
    assert body["data"]["llm_review"]["error"] == "missing_selected_code_content"


def test_logs_analyze_workflow_returns_structured_events(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks/logs-analyze",
        json={
            "task_type": "logs_analyze",
            "session": {
                "session_id": "logs_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Analyze this crash log.",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "LogAnalyzer",
                "current_file": "Saved/Logs/Demo.log",
            },
            "payload": {
                "user_query": "Analyze this crash log.",
                "log_source": "Saved/Logs/Demo.log",
                "log_text": "[2026.04.17-10.00.00] LogTemp: Error: Access violation\nCallstack: 0x0001 Demo!MyModule\nLogStreaming: Warning: Failed to load /Game/Maps/TestMap",
            },
            "ui_state": {"active_view": "user", "selected_panel": "LogAnalyzer"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "en-US",
                "return_debug_projection": True,
            },
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert body["intent"]["route_type"] == "workflow"
    assert body["data"]["findings"]
    assert body["data"]["structured_events"]
    assert body["data"]["parser_diagnostics"]["callstack_lines"]
    assert [block["title"] for block in body["user_view"]["blocks"]] == [
        "Log Summary",
        "LLM Analysis",
        "Issue Families",
        "Suggested Actions",
        "Captured Log Window",
        "Affected Modules / Resources",
        "Validation Plan",
    ]
    assert body["data"]["llm_analysis"]["status"] == "skipped"
    assert body["data"]["llm_analysis"]["reason_code"] == "missing_openai_api_key"
    assert body["data"]["retrieval_quality_gate"]["status"] in {"passed", "skipped"}
    assert body["data"]["validation_plan"]["items"]
    assert any(item["category"] == "asset_validation" for item in body["data"]["validation_plan"]["items"])
    assert any(step["step_id"] == "llm_log_analysis_synthesis" for step in body["step_results"])
    assert any(step["step_id"] == "build_validation_plan" for step in body["step_results"])
    assert body["debug_view"]["skill"]["skill_id"] == "LogsAnalyzeSkill"
    assert body["debug_view"]["skill"]["collector"] == "ue_log_input_payload"
    assert body["trace_summary"]["skill_id"] == "LogsAnalyzeSkill"


def test_logs_analyze_can_read_selected_log_file(client: TestClient) -> None:
    test_root = Path(".test-runtime") / f"logs-fixture-{uuid.uuid4().hex}"
    log_file = test_root / "Saved" / "Logs" / "Demo.log"
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text(
            "\n".join(
                [
                    "[2026.04.17-10.00.00] LogTemp: Display: Starting PIE",
                    "[2026.04.17-10.00.01] LogTemp: Error: Access violation reading address",
                    "Callstack: 0x0001 Demo!UMySubsystem::Tick",
                    "LogStreaming: Warning: Failed to load /Game/Props/MissingMesh",
                ]
            ),
            encoding="utf-8",
        )

        response = client.post(
            "/api/v1/tasks/logs-analyze",
            json={
                "task_type": "logs_analyze",
                "session": {
                    "session_id": "logs_file_session",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Analyze this selected log file.",
                            "language": "auto",
                        }
                    ],
                },
                "context": {
                    "project_name": "DemoProject",
                    "active_panel": "LogAnalyzer",
                    "current_file": str(log_file),
                },
                "payload": {
                    "user_query": "Analyze this selected log file.",
                    "log_file_path": str(log_file),
                    "notes": "User selected the file from the Logs Analyze panel.",
                },
                "ui_state": {"active_view": "user", "selected_panel": "LogAnalyzer"},
                "runtime_options": {
                    "profile_id": "default",
                    "stream": False,
                    "debug": True,
                    "preferred_output_language": "en-US",
                    "return_debug_projection": True,
                },
            },
        )
        body = response.json()

        assert response.status_code == 200
        assert body["data"]["log_summary"]["line_count"] == 4
        assert body["data"]["input_context"]["input_mode"] == "file_tail"
        assert body["data"]["input_context"]["read_diagnostics"][0]["read_status"] == "completed"
        assert "access_violation" in body["data"]["issue_families"]
        assert "asset_load_failure" in body["data"]["issue_families"]
        assert body["data"]["llm_analysis"]["status"] == "skipped"
        assert body["data"]["llm_analysis"]["reason_code"] == "missing_openai_api_key"
        assert body["data"]["validation_plan"]["items"]
        assert body["debug_view"]["skill"]["collector"] == "ue_log_input_payload"
    finally:
        shutil.rmtree(test_root, ignore_errors=True)


def test_config_generate_workflow_returns_draft_and_proposal(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks/config-generate",
        json={
            "task_type": "config_generate",
            "session": {
                "session_id": "config_generate_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Generate a character spawn config.",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "ConfigGenerator",
                "current_file": "Config/Spawn.json",
            },
            "payload": {
                "user_query": "Generate a character spawn config.",
                "requirement_description": "Spawn the default hero with an enabled state.",
                "object_type": "HeroSpawnConfig",
                "schema": {
                    "type": "object",
                    "required": ["name", "enabled"],
                    "properties": {
                        "name": {"type": "string"},
                        "enabled": {"type": "boolean"},
                        "count": {"type": "integer", "minimum": 0},
                    },
                },
            },
            "ui_state": {"active_view": "user", "selected_panel": "ConfigGenerator"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )
    body = response.json()
    task_id = body["task"]["task_id"]
    artifacts = client.get(f"/api/v1/tasks/{task_id}/artifacts")

    assert response.status_code == 200
    assert body["intent"]["route_type"] == "workflow"
    assert body["data"]["draft_config"]["enabled"] is False
    assert body["action_proposals"]
    assert artifacts.status_code == 200
    assert artifacts.json()["items"]


def test_code_generate_returns_draft_and_artifact(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks/code-generate",
        json={
            "task_type": "code_generate",
            "session": {
                "session_id": "code_generate_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Generate a simple UE actor skeleton.",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "CodeGenerator",
                "current_module": "Gameplay",
            },
            "payload": {
                "user_query": "Generate a simple UE actor skeleton.",
                "requirement_description": "spawn helper actor",
                "target_type": "ue_cpp_class",
            },
            "ui_state": {"active_view": "user", "selected_panel": "CodeGenerator"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )
    body = response.json()
    task_id = body["task"]["task_id"]
    artifacts = client.get(f"/api/v1/tasks/{task_id}/artifacts")

    assert response.status_code == 200
    assert body["intent"]["route_type"] == "single_tool"
    assert body["data"]["code_draft"]
    assert body["data"]["file_structure_suggestions"]
    assert body["data"]["generated_items"]
    assert body["data"]["generation_mode"]
    assert body["data"]["reference_lookup"]["local_reference_count"] >= 1
    assert body["data"]["local_search"]["items"]
    assert body["debug_view"]["local_search"]["summary"]["result_count"] >= 1
    assert "engine_notes" in body["debug_view"]["local_search"]["summary"]["domain_filters"]
    assert [block["block_type"] for block in body["user_view"]["blocks"]] == [
        "summary",
        "generated_items",
        "validation_plan",
    ]
    assert body["data"]["validation_plan"]["items"]
    assert body["data"]["validation_plan"]["write_policy"]["written_to_disk"] is False
    assert any(item["category"] == "compile" for item in body["data"]["validation_plan"]["items"])
    assert body["debug_view"]["skill"]["skill_id"] == "CodeGenerateSkill"
    assert body["debug_view"]["skill"]["collector"] == "user_requirement_and_optional_editor_context"
    assert body["trace_summary"]["skill_id"] == "CodeGenerateSkill"
    assert body["action_proposals"]
    assert artifacts.status_code == 200
    assert artifacts.json()["items"]


def test_code_generate_write_proposal_writes_files_after_confirmation(client: TestClient) -> None:
    project_root = Path(".test-workspace") / f"code-write-{uuid.uuid4().hex}"
    shutil.rmtree(project_root, ignore_errors=True)
    project_root.mkdir(parents=True, exist_ok=True)
    try:
        response = client.post(
            "/api/v1/tasks/code-generate",
            json={
                "task_type": "code_generate",
                "session": {
                    "session_id": "code_generate_write_session",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Generate a simple UE actor and prepare a write proposal.",
                            "language": "auto",
                        }
                    ],
                },
                "context": {
                    "project_name": "DemoProject",
                    "project_root": str(project_root.resolve()),
                    "active_panel": "CodeGenerator",
                    "current_module": "Gameplay",
                },
                "payload": {
                    "user_query": "Generate a simple UE actor and prepare a write proposal.",
                    "requirement_description": "spawn helper actor",
                    "target_type": "ue_cpp_class",
                    "create_write_proposal": True,
                },
                "ui_state": {"active_view": "user", "selected_panel": "CodeGenerator"},
                "runtime_options": {
                    "profile_id": "default",
                    "stream": False,
                    "debug": True,
                    "preferred_output_language": "auto",
                    "return_debug_projection": True,
                },
            },
        )
        body = response.json()
        write_proposal = next(
            item for item in body["action_proposals"] if item["proposal_type"] == "write_code_files"
        )
        decision = client.post(
            f"/api/v1/proposals/{write_proposal['proposal_id']}/decision",
            json={"decision": "confirmed", "actor": "tester", "comment": "Write generated files."},
        )
        task_after = client.get(f"/api/v1/tasks/{body['task']['task_id']}")
        artifacts_after = client.get(f"/api/v1/tasks/{body['task']['task_id']}/artifacts")
        after_body = task_after.json()

        assert response.status_code == 200
        assert body["task"]["status"] == "waiting_confirmation"
        assert write_proposal["confirmation"]["state"] == "pending"
        assert write_proposal["dry_run_preview"]["write_plan"]["status"] == "ready"
        assert decision.status_code == 200
        assert task_after.status_code == 200
        assert after_body["data"]["approval_result"]["execution_state"] == "files_written"
        assert after_body["data"]["code_write_result"]["written_to_disk"] is True
        assert after_body["debug_view"]["side_effects"][0]["side_effect_level"] == "confirmed_write"
        assert artifacts_after.status_code == 200
        assert any(item["artifact_type"] == "code_write_report" for item in artifacts_after.json()["items"])
        for item in after_body["data"]["code_write_result"]["written_files"]:
            assert Path(item["target_path"]).exists()
            assert Path(item["target_path"]).read_text(encoding="utf-8")
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_code_generate_can_use_code_reference_documents(client: TestClient) -> None:
    project_root = Path(".test-workspace") / f"code-kb-{uuid.uuid4().hex}"
    source_dir = project_root / "Source" / "Combat"
    shutil.rmtree(project_root, ignore_errors=True)
    source_dir.mkdir(parents=True, exist_ok=True)
    try:
        reference_file = source_dir / "AbilityHelper.cpp"
        reference_file.write_text(
            '#include "AbilityHelper.h"\n'
            "void UAbilityHelper::ApplyAbility()\n"
            "{\n"
            "    // Reference helper\n"
            "}\n",
            encoding="utf-8",
        )

        refresh = client.post(
            "/api/v1/knowledge-base/refresh",
            json={"source_paths": [str(project_root.resolve())], "force_rebuild": True},
        )
        assert refresh.status_code == 200

        response = client.post(
            "/api/v1/tasks/code-generate",
            json={
                "task_type": "code_generate",
                "session": {
                    "session_id": "code_generate_reference_session",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Generate a helper actor based on our code style.",
                            "language": "auto",
                        }
                    ],
                },
                "context": {
                    "project_name": "DemoProject",
                    "active_panel": "CodeGenerator",
                    "current_module": "Combat",
                },
                "payload": {
                    "user_query": "Generate a helper actor based on our code style.",
                    "requirement_description": "ability helper actor",
                    "target_type": "ue_cpp_class",
                    "domain_filters": ["code_reference"],
                },
                "ui_state": {"active_view": "user", "selected_panel": "CodeGenerator"},
                "runtime_options": {
                    "profile_id": "default",
                    "stream": False,
                    "debug": True,
                    "preferred_output_language": "auto",
                    "return_debug_projection": True,
                },
            },
        )
        body = response.json()

        assert response.status_code == 200
        assert body["data"]["reference_lookup"]["reference_count"] >= 1
        assert "local_reference_count" in body["data"]["reference_lookup"]
        assert "reference_augmented" in body["data"]["generation_mode"]
        assert body["data"]["generated_items"]
        assert body["data"]["retrieved_references"]
        assert body["debug_view"]["skill"]["retrieval_active"] is True
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


def test_code_generate_returns_enhanced_input_character_for_chinese_request(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks/code-generate",
        json={
            "task_type": "code_generate",
            "session": {
                "session_id": "code_generate_enhanced_input_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "角色增强输入代码怎么写",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "RushBa",
                "active_panel": "CodeGenerator",
                "current_module": "RushBa",
            },
            "payload": {
                "user_query": "角色增强输入代码怎么写",
                "requirement_description": "角色增强输入代码怎么写",
                "target_type": "ue_cpp",
            },
            "ui_state": {"active_view": "user", "selected_panel": "CodeGenerator"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "zh-CN",
                "return_debug_projection": True,
            },
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert "Source/RushBa/Public/EnhancedInputCharacter.h" in body["data"]["code_draft"]
    assert "Source/RushBa/Private/EnhancedInputCharacter.cpp" in body["data"]["code_draft"]
    assert "UEnhancedInputComponent" in body["data"]["code_draft"]["Source/RushBa/Private/EnhancedInputCharacter.cpp"]
    assert "EnhancedInput" in "\n".join(body["data"]["patch_plan"])
    assert body["data"]["reference_lookup"]["local_reference_count"] >= 1
    assert any("enhanced-input" in item["source"] for item in body["data"]["retrieved_references"])


def test_config_validate_returns_report_and_artifact(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks/config-validate",
        json={
            "task_type": "config_validate",
            "session": {
                "session_id": "config_validate_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Validate this config payload.",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "ConfigValidator",
                "current_file": "Config/Spawn.json",
            },
            "payload": {
                "user_query": "Validate this config payload.",
                "schema": {
                    "type": "object",
                    "required": ["name", "enabled"],
                    "properties": {
                        "name": {"type": "string"},
                        "enabled": {"type": "boolean"},
                        "count": {"type": "integer", "minimum": 0},
                    },
                },
                "config_json": {
                    "name": "HeroSpawner",
                    "enabled": "yes",
                    "count": -1,
                    "extraField": True,
                },
            },
            "ui_state": {"active_view": "user", "selected_panel": "ConfigValidator"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )
    body = response.json()
    task_id = body["task"]["task_id"]
    artifacts = client.get(f"/api/v1/tasks/{task_id}/artifacts")

    assert response.status_code == 200
    assert body["intent"]["route_type"] == "single_tool"
    assert body["data"]["errors"]
    assert body["data"]["warnings"]
    assert body["data"]["validation_summary"]["is_valid"] is False
    assert artifacts.status_code == 200
    assert artifacts.json()["items"]


def test_perf_analyze_workflow_returns_suspicious_points(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks/perf-analyze",
        json={
            "task_type": "perf_analyze",
            "session": {
                "session_id": "perf_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Analyze this frame hitch report.",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "PerfAnalysis",
                "current_file": "Saved/Profiling/perf.txt",
            },
            "payload": {
                "user_query": "Analyze this frame hitch report.",
                "report_text": "FrameTime: 41.2 ms\nGameThread: 21.5 ms\nDrawCalls: 4200\nPeak Memory: 3072 MB",
                "insights_summary": "Streaming spikes and synchronous loading were observed during the hitch.",
            },
            "ui_state": {"active_view": "user", "selected_panel": "PerfAnalysis"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert body["intent"]["route_type"] == "workflow"
    assert body["data"]["suspicious_points"]
    assert body["data"]["metric_summary"]["peak_frame_time_ms"] >= 41.2


def test_assets_inspect_returns_violations(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks/assets-inspect",
        json={
            "task_type": "assets_inspect",
            "session": {
                "session_id": "asset_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Inspect these content assets.",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "AssetInspector",
                "selected_assets": ["/Game/temp hero/New Blueprint", "/Game/Other/heroAsset"],
            },
            "payload": {"user_query": "Inspect these content assets."},
            "ui_state": {"active_view": "user", "selected_panel": "AssetInspector"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert body["intent"]["route_type"] == "single_tool"
    assert body["data"]["violations"]
    assert body["data"]["rename_suggestions"]
    assert body["debug_view"]["skill"]["skill_id"] == "AssetsInspectSkill"
    assert body["debug_view"]["skill"]["collector"] == "selected_asset_metadata_payload"
    assert body["trace_summary"]["skill_id"] == "AssetsInspectSkill"
    assert [block["block_type"] for block in body["user_view"]["blocks"]][:4] == [
        "summary",
        "llm_analysis",
        "issues",
        "recommendations",
    ]
    assert body["data"]["llm_analysis"]["status"] == "skipped"
    assert body["data"]["llm_analysis"]["reason_code"] == "missing_openai_api_key"
    assert "api key" in body["data"]["llm_analysis"]["reason"].lower()
    assert body["data"]["validation_plan"]["items"]
    assert any(item["category"] == "asset_management" for item in body["data"]["validation_plan"]["items"])
    assert any(block["block_type"] == "validation_plan" for block in body["user_view"]["blocks"])


def test_assets_inspect_can_summarize_types_and_relationships(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks/assets-inspect",
        json={
            "task_type": "assets_inspect",
            "session": {
                "session_id": "asset_session_relationships",
                "messages": [
                    {
                        "role": "user",
                        "content": "Inspect the selected assets and summarize their relationships.",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "AssetInspector",
                "selected_assets": ["/Game/Demo/BP_Hero"],
            },
            "payload": {
                "user_query": "Inspect the selected assets and summarize their relationships.",
                "asset_items": [
                    {
                        "asset_path": "/Game/Demo/BP_Hero",
                        "asset_type": "Blueprint",
                        "package_path": "/Game/Demo",
                        "dependencies": ["/Game/Demo/SM_Hero", "/Game/Demo/M_Hero"],
                        "referencers": ["/Game/Demo/Maps/MainMap"],
                    }
                ],
            },
            "ui_state": {"active_view": "user", "selected_panel": "AssetInspector"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "en-US",
                "return_debug_projection": True,
            },
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["type_insights"][0]["asset_type"] == "Blueprint"
    assert body["data"]["relationship_summary"][0]["dependency_count"] == 2
    assert body["data"]["relationship_summary"][0]["referencer_count"] == 1
    assert "Asset Types" in [block["title"] for block in body["user_view"]["blocks"]]
    assert "Relationship Summary" in [block["title"] for block in body["user_view"]["blocks"]]


def test_assets_inspect_live_llm_uses_compact_timeout_config(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_complete_json_object(self, *, messages, config):  # type: ignore[no-untyped-def]
        assert messages
        assert config.timeout_ms >= 45000
        assert config.max_tokens <= 650
        return {
            "ok": True,
            "payload": {
                "analysis": "The selected asset is structurally clean, but you should verify downstream dependencies.",
                "key_points": ["Naming is acceptable.", "Check runtime dependencies."],
                "priority": "low",
                "recommendations": ["Confirm references inside the target map."],
            },
            "reason": "completed",
            "error": "",
            "provider": "openai_compatible",
            "model": config.model,
            "profile_id": config.profile_id,
            "usage": {
                "input_tokens": 32,
                "output_tokens": 18,
                "estimated_cost_usd": 0.0,
                "latency_ms": 8,
            },
        }

    monkeypatch.setattr(
        "app.services.llm_service.LLMService.complete_json_object",
        _fake_complete_json_object,
    )

    response = client.post(
        "/api/v1/tasks/assets-inspect",
        json={
            "task_type": "assets_inspect",
            "session": {
                "session_id": "asset_session_live_llm",
                "messages": [
                    {
                        "role": "user",
                        "content": "Inspect this blueprint asset.",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "AssetInspector",
                "selected_assets": ["/Game/Demo/BP_Hero"],
            },
            "payload": {
                "user_query": "Inspect this blueprint asset.",
                "asset_items": [
                    {
                        "asset_path": "/Game/Demo/BP_Hero",
                        "asset_name": "BP_Hero",
                        "asset_type": "Blueprint",
                        "package_path": "/Game/Demo",
                    }
                ],
            },
            "ui_state": {"active_view": "user", "selected_panel": "AssetInspector"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert body["data"]["llm_analysis"]["status"] == "completed"
    assert body["data"]["llm_analysis_raw"]["reason"] == "completed"


def test_assets_inspect_flags_default_world_asset_name(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks/assets-inspect",
        json={
            "task_type": "assets_inspect",
            "session": {
                "session_id": "asset_session_new_map",
                "messages": [
                    {
                        "role": "user",
                        "content": "检查这个地图资产命名。",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "RushBa",
                "active_panel": "AssetInspector",
                "selected_assets": ["/Game/NewMap.NewMap"],
            },
            "payload": {
                "user_query": "检查这个地图资产命名。",
                "asset_items": [
                    {
                        "asset_name": "NewMap",
                        "asset_path": "/Game/NewMap.NewMap",
                        "asset_type": "World",
                        "package_path": "/Game/NewMap",
                        "dependencies": [],
                        "referencers": [],
                    }
                ],
            },
            "ui_state": {"active_view": "user", "selected_panel": "AssetInspector"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "zh-CN",
                "return_debug_projection": True,
            },
        },
    )
    body = response.json()
    placeholder_issues = [
        item for item in body["data"]["violations"] if item["rule_id"] == "placeholder_asset_name"
    ]

    assert response.status_code == 200
    assert placeholder_issues
    assert placeholder_issues[0]["severity"] == "warning"
    assert "NewMap" in placeholder_issues[0]["reason"]
    assert "L_ProjectSpecificName" in placeholder_issues[0]["suggestion"]
    assert any(item["asset_name"] == "NewMap" for item in body["data"]["rename_suggestions"])
    assert any(block["block_type"] == "issues" for block in body["user_view"]["blocks"])
    issue_block = next(block for block in body["user_view"]["blocks"] if block["block_type"] == "issues")
    assert "默认" in issue_block["data"]["items"][0]["reason"]


def test_agent_chat_config_generate_waits_for_confirmation_and_records_decision(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "agent_config_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Generate config for a hero spawn entry.",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "ConfigGenerator",
                "current_file": "Config/Spawn.json",
            },
            "payload": {
                "user_query": "Generate config for a hero spawn entry.",
                "requirement_description": "Spawn the default hero with an enabled state.",
                "object_type": "HeroSpawnConfig",
                "schema": {
                    "type": "object",
                    "required": ["name", "enabled"],
                    "properties": {
                        "name": {"type": "string"},
                        "enabled": {"type": "boolean"},
                    },
                },
            },
            "ui_state": {"active_view": "user", "selected_panel": "ConfigGenerator"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )
    body = response.json()
    proposal_id = body["action_proposals"][0]["proposal_id"]
    task_id = body["task"]["task_id"]
    run_id = body["task"]["run_id"]
    pending = client.get("/api/v1/proposals/pending")
    detail = client.get(f"/api/v1/proposals/{proposal_id}")
    decision = client.post(
        f"/api/v1/proposals/{proposal_id}/decision",
        json={"decision": "confirmed", "actor": "tester", "comment": "Looks good."},
    )
    task_after = client.get(f"/api/v1/tasks/{task_id}")
    artifacts_after = client.get(f"/api/v1/tasks/{task_id}/artifacts")
    stream_after = client.get(f"/api/v1/chat/runs/{run_id}/events/stream")
    pending_after = client.get("/api/v1/proposals/pending")
    decision_id = decision.json()["item"]["decision_id"]
    decision_detail = client.get(f"/api/v1/proposals/decisions/{decision_id}")

    assert response.status_code == 200
    assert body["task"]["status"] == "waiting_confirmation"
    assert body["intent"]["route_type"] == "workflow"
    assert body["task"]["task_type"] == "config_generate"
    assert body["action_proposals"][0]["confirmation"]["state"] == "pending"
    assert pending.status_code == 200
    assert any(item["proposal_id"] == proposal_id for item in pending.json()["items"])
    assert detail.status_code == 200
    assert detail.json()["task"]["status"] == "waiting_confirmation"
    assert decision.status_code == 200
    assert decision.json()["item"]["decision"] == "confirmed"
    assert decision.json()["proposal"]["confirmation"]["state"] == "confirmed"
    assert task_after.status_code == 200
    assert task_after.json()["task"]["status"] == "completed"
    assert task_after.json()["task"]["finish_reason"] == "proposal_confirmed"
    assert task_after.json()["data"]["approval_result"]["decision"] == "confirmed"
    assert task_after.json()["data"]["approval_result"]["execution_state"] == "materialized"
    assert task_after.json()["user_view"]["status_hint"] == "approved"
    assert artifacts_after.status_code == 200
    assert any(item["artifact_type"] == "approved_config" for item in artifacts_after.json()["items"])
    assert stream_after.status_code == 200
    assert "event: proposal_followup_completed" in stream_after.text
    assert decision_detail.status_code == 200
    assert decision_detail.json()["item"]["decision"] == "confirmed"
    assert all(item["proposal_id"] != proposal_id for item in pending_after.json()["items"])


def test_cancel_waiting_confirmation_run_updates_status_and_stream(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks/config-generate",
        json={
            "task_type": "config_generate",
            "session": {
                "session_id": "cancel_config_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Generate a config draft that I may cancel.",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "ConfigGenerator",
                "current_file": "Config/Spawn.json",
            },
            "payload": {
                "user_query": "Generate a config draft that I may cancel.",
                "requirement_description": "Spawn hero config",
                "object_type": "HeroSpawnConfig",
                "schema": {
                    "type": "object",
                    "required": ["name", "enabled"],
                    "properties": {
                        "name": {"type": "string"},
                        "enabled": {"type": "boolean"},
                    },
                },
            },
            "ui_state": {"active_view": "user", "selected_panel": "ConfigGenerator"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )
    body = response.json()
    run_id = body["task"]["run_id"]
    task_id = body["task"]["task_id"]
    cancelled = client.post(f"/api/v1/chat/runs/{run_id}/cancel")
    trace = client.get(f"/api/v1/tasks/{task_id}/trace")
    stream = client.get(f"/api/v1/chat/runs/{run_id}/events/stream")

    assert response.status_code == 200
    assert body["task"]["status"] == "waiting_confirmation"
    assert cancelled.status_code == 200
    assert cancelled.json()["task"]["status"] == "cancelled"
    assert cancelled.json()["task"]["finish_reason"] == "cancelled_by_user"
    assert trace.status_code == 200
    assert any(event["event"] == "run_cancelled" for event in trace.json()["events"])
    assert stream.status_code == 200
    assert "event: run_cancelled" in stream.text


def test_metrics_endpoint_exposes_phase4_counters(client: TestClient) -> None:
    client.post(
        "/api/v1/tasks/config-generate",
        json={
            "task_type": "config_generate",
            "session": {
                "session_id": "metrics_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Generate a config for metrics.",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "ConfigGenerator",
            },
            "payload": {
                "user_query": "Generate a config for metrics.",
                "requirement_description": "Spawn hero config",
                "object_type": "HeroSpawnConfig",
                "schema": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {"name": {"type": "string"}},
                },
            },
            "ui_state": {"active_view": "user", "selected_panel": "ConfigGenerator"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )
    metrics = client.get("/metrics")

    assert metrics.status_code == 200
    assert "agent_tasks_total" in metrics.text
    assert "agent_proposals_pending_total" in metrics.text
    assert "agent_audit_logs_total" in metrics.text


def test_kb_document_management_and_retry_reindex(client: TestClient) -> None:
    refresh = client.post(
        "/api/v1/knowledge-base/refresh",
        json={"source_paths": ["../backend.md"], "force_rebuild": True},
    )
    refresh_body = refresh.json()
    job_id = refresh_body["job"]["job_id"]
    documents = client.get("/api/v1/knowledge-base/documents")
    first_doc_id = documents.json()["items"][0]["doc_id"]
    detail = client.get(f"/api/v1/knowledge-base/documents/{first_doc_id}")
    job_alias = client.get(f"/api/v1/knowledge-base/jobs/{job_id}")
    retry = client.post(f"/api/v1/knowledge-base/import-jobs/{job_id}/retry")
    retry_alias = client.post(f"/api/v1/knowledge-base/jobs/{job_id}/retry")
    reindex = client.post(
        "/api/v1/knowledge-base/reindex",
        json={"source_paths": ["../backend.md"], "force_rebuild": True},
    )
    deleted = client.delete(f"/api/v1/knowledge-base/documents/{first_doc_id}")

    assert refresh.status_code == 200
    assert documents.status_code == 200
    assert documents.json()["items"]
    assert detail.status_code == 200
    assert detail.json()["item"]["doc_id"] == first_doc_id
    assert job_alias.status_code == 200
    assert job_alias.json()["job"]["job_id"] == job_id
    assert retry.status_code == 200
    assert retry.json()["job"]["status"] == "completed"
    assert retry_alias.status_code == 200
    assert retry_alias.json()["job"]["status"] == "completed"
    assert reindex.status_code == 200
    assert reindex.json()["job"]["status"] == "completed"
    assert deleted.status_code == 200
    assert deleted.json()["item"]["doc_id"] == first_doc_id


def test_system_alerts_snapshot_returns_threshold_view(client: TestClient) -> None:
    client.post(
        "/api/v1/tasks/config-generate",
        json={
            "task_type": "config_generate",
            "session": {
                "session_id": "alerts_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "Generate config for alert inspection.",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "ConfigGenerator",
            },
            "payload": {
                "user_query": "Generate config for alert inspection.",
                "requirement_description": "Spawn hero config",
                "object_type": "HeroSpawnConfig",
                "schema": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {"name": {"type": "string"}},
                },
            },
            "ui_state": {"active_view": "user", "selected_panel": "ConfigGenerator"},
            "runtime_options": {
                "profile_id": "default",
                "stream": False,
                "debug": True,
                "preferred_output_language": "auto",
                "return_debug_projection": True,
            },
        },
    )
    alerts = client.get("/api/v1/system/alerts")

    assert alerts.status_code == 200
    assert "summary" in alerts.json()
    assert "items" in alerts.json()
    assert alerts.json()["items"]
    assert "pending_proposals" in alerts.json()["summary"]
