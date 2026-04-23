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
    assert body["capabilities"]["skill_architecture"]["runtime_dynamic_skills"] is False
    assert body["capabilities"]["skill_architecture"]["public_skill_count"] == 5
    assert len(body["capabilities"]["skill_catalog"]) == 5
    assert any(
        item["skill_id"] == "CodeReviewSkill"
        and item["architecture"]["collector"] == "ue_project_code_file_scanner_and_reader"
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
    assert status.json()["summary"]["documents"] >= 1
    assert status.json()["summary"]["chunks"] >= 1
    assert status.json()["summary"]["ingestion_pipeline"] == [
        "loader",
        "parser",
        "cleaner",
        "chunker",
        "lexical_index",
        "embedding",
        "vector_store",
        "retrieval",
    ]
    assert "cpp" in status.json()["summary"]["format_groups"]["code"]


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
    assert history.json()["items"][-1]["role"] == "user"
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


def test_project_qa_english_query_keeps_english_locale(client: TestClient) -> None:
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
                "preferred_output_language": "auto",
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
    assert body["debug_view"]["skill"]["skill_id"] == "ProjectQASkill"
    assert body["debug_view"]["skill"]["retrieval_active"] is False
    assert body["data"]["skill"]["collector"] == "chat_messages_and_editor_context"
    assert body["trace_summary"]["skill_id"] == "ProjectQASkill"


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
        assert body["debug_view"]["skill"]["skill_id"] == "CodeReviewSkill"
        assert body["debug_view"]["skill"]["collector"] == "ue_project_code_file_scanner_and_reader"
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
        assert body["data"]["llm_analysis"]["status"] == "skipped"
        assert body["data"]["llm_analysis"]["reason_code"] == "missing_openai_api_key"
        assert "api key" in body["data"]["llm_analysis"]["reason"].lower()
        assert body["data"]["localized_review"]["issues"]
        assert body["data"]["llm_review"]["reason"] == "missing_openai_api_key"
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


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
                "preferred_output_language": "auto",
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
        "Issue Families",
        "Suggested Actions",
        "Captured Log Window",
        "Affected Modules / Resources",
    ]
    assert body["debug_view"]["skill"]["skill_id"] == "LogsAnalyzeSkill"
    assert body["debug_view"]["skill"]["collector"] == "ue_log_text_payload"
    assert body["trace_summary"]["skill_id"] == "LogsAnalyzeSkill"


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
    assert [block["block_type"] for block in body["user_view"]["blocks"]] == [
        "summary",
        "generated_items",
    ]
    assert body["debug_view"]["skill"]["skill_id"] == "CodeGenerateSkill"
    assert body["debug_view"]["skill"]["collector"] == "user_requirement_and_optional_editor_context"
    assert body["trace_summary"]["skill_id"] == "CodeGenerateSkill"
    assert body["action_proposals"]
    assert artifacts.status_code == 200
    assert artifacts.json()["items"]


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
        assert "reference_augmented" in body["data"]["generation_mode"]
        assert body["data"]["generated_items"]
        assert body["data"]["retrieved_references"]
        assert body["debug_view"]["skill"]["retrieval_active"] is True
    finally:
        shutil.rmtree(project_root, ignore_errors=True)


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
                "preferred_output_language": "auto",
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
