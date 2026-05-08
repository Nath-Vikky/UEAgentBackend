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
    runtime_root = Path(".test-runtime") / f"multi-agent-{uuid.uuid4().hex}"
    storage_dir = runtime_root / "storage"
    shutil.rmtree(runtime_root, ignore_errors=True)
    storage_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("STORAGE_DIR", str(storage_dir.resolve()))
    monkeypatch.setenv("UPLOAD_DIR", str((storage_dir / "uploads").resolve()))
    monkeypatch.setenv("ARTIFACT_DIR", str((storage_dir / "artifacts").resolve()))
    monkeypatch.setenv("KB_DIR", str((storage_dir / "kb").resolve()))
    monkeypatch.setenv("KB_SOURCE_PATHS", "./knowledge")
    monkeypatch.setenv("EMBEDDING_ENABLED", "false")
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


def test_code_review_can_run_review_fix_validate_chain(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks/code-review",
        json={
            "session": {"session_id": "multi-agent-review", "messages": []},
            "payload": {
                "user_query": "review and fix this UE C++ code",
                "enable_multi_agent": True,
                "code": "UObject* RawAsset = nullptr;\nvoid Tick(float DeltaTime) {}\n",
            },
            "runtime_options": {"preferred_output_language": "en"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["task"]["task_type"] == "code_review"
    assert body["data"]["multi_agent"]["chain_id"] == "review_fix_validate"
    assert body["data"]["write_policy"]["written_to_disk"] is False
    assert body["debug_view"]["multi_agent"]["chain_id"] == "review_fix_validate"
    assert body["data"]["generated_items"]
    assert not body["action_proposals"]


def test_code_review_chain_skips_fix_generation_below_threshold(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks/code-review",
        json={
            "session": {"session_id": "multi-agent-review-skip", "messages": []},
            "payload": {
                "user_query": "review and fix this simple UE C++ code",
                "workflow_mode": "review_fix_validate",
                "code": "void Foo()\n{\n    int32 Count = 0;\n}\n",
            },
            "runtime_options": {"preferred_output_language": "en"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    gate = body["data"]["multi_agent"]["decision_gates"][0]
    assert gate["status"] == "skipped"
    assert body["data"]["generated_items"] == []
    assert body["data"]["write_policy"]["written_to_disk"] is False


def test_code_review_chain_degrades_when_fix_generation_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_generate(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("synthetic generate failure")

    monkeypatch.setattr(
        "app.agent.multi_agent.review_fix_validate.CodeGenerateSkillExecutor.execute",
        _raise_generate,
    )

    response = client.post(
        "/api/v1/tasks/code-review",
        json={
            "session": {"session_id": "multi-agent-generate-failure", "messages": []},
            "payload": {
                "user_query": "review and fix this UE C++ code",
                "enable_multi_agent": True,
                "code": (
                    "UObject* RawAsset = nullptr;\n"
                    "void Tick(float DeltaTime) { LoadObject<UObject>(nullptr, TEXT(\"/Game/Hero/Hero01\")); }\n"
                    "void RunWorker(){ AsyncTask(ENamedThreads::AnyBackgroundThreadNormalTask, [](){}); }\n"
                ),
            },
            "runtime_options": {"preferred_output_language": "en"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["task"]["status"] == "completed"
    assert body["data"]["multi_agent"]["status"] == "degraded"
    assert body["data"]["generated_items"] == []
    assert any("fix_draft_phase_failed" in item for item in body["data"]["warnings"])
    fix_phase = next(
        item for item in body["data"]["multi_agent"]["phases"] if item["node_id"] == "fix_draft"
    )
    assert fix_phase["status"] == "failed"
    assert fix_phase["data"]["reason"] == "fix_draft_phase_failed"


def test_code_review_chain_handles_query_only_without_selected_code(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks/code-review",
        json={
            "session": {
                "session_id": "multi-agent-query-only",
                "messages": [{"role": "user", "content": "Review my selected file."}],
            },
            "payload": {
                "user_query": "Review my selected file.",
                "workflow_mode": "review_fix_validate",
            },
            "runtime_options": {"preferred_output_language": "en"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["review_phase"]["review_scope"]["source_kind"] == "query_only"
    assert body["data"]["review_phase"]["llm_analysis"]["status"] == "skipped"
    assert body["data"]["review_phase"]["llm_analysis"]["reason_code"] == "missing_selected_code_content"
    assert body["data"]["generated_items"] == []
    assert body["data"]["multi_agent"]["status"] == "completed"


def test_code_review_chain_keeps_running_when_llm_review_times_out(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_timeout(self, *, messages, config):  # type: ignore[no-untyped-def]
        return {
            "ok": False,
            "payload": None,
            "reason": "request_failed",
            "error": "timeout",
            "provider": "openai_compatible",
            "model": config.model,
            "profile_id": config.profile_id,
            "usage": {"latency_ms": config.timeout_ms},
        }

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.llm_service.LLMService.complete_json_object",
        _fake_timeout,
    )

    response = client.post(
        "/api/v1/tasks/code-review",
        json={
            "session": {"session_id": "multi-agent-llm-timeout", "messages": []},
            "payload": {
                "user_query": "review this UE C++ code",
                "enable_multi_agent": True,
                "code": "UObject* RawAsset = nullptr;\nvoid Tick(float DeltaTime) {}\n",
            },
            "runtime_options": {"preferred_output_language": "en"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["review_phase"]["llm_analysis"]["status"] == "skipped"
    assert body["data"]["review_phase"]["llm_analysis"]["reason_code"] == "request_failed"
    assert body["data"]["multi_agent"]["chain_id"] == "review_fix_validate"
