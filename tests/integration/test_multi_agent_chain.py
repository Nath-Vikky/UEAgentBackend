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
