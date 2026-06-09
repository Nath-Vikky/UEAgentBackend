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
    runtime_root = Path(".test-runtime") / f"contract-{uuid.uuid4().hex}"
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


def test_chat_run_contract_contains_phase1_top_level_fields(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": "contract_session",
                "messages": [
                    {
                        "role": "user",
                        "content": "请帮我看一下这个工程模块结构是否合理",
                        "language": "auto",
                    }
                ],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "AgentChat",
                "current_file": "Source/MyModule/MyActor.cpp",
            },
            "payload": {
                "user_query": "请帮我看一下这个工程模块结构是否合理",
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
    for key in [
        "success",
        "task",
        "intent",
        "locale",
        "user_view",
        "debug_view",
        "presentation",
        "assistant_message",
        "data",
        "usage",
        "trace_summary",
        "retrieval_trace",
        "planner_diagnostics",
        "step_results",
        "action_proposals",
        "errors",
    ]:
        assert key in body

    assert body["presentation"]["user_text"] == body["user_view"]["text"]
    assert body["presentation"]["user_title"] == body["user_view"]["title"]
    assert "route_type" in body["debug_view"]["route"]
    assert "raw_request" in body["debug_view"]
    assert body["intent"]["route_type"] in {"project_qa", "direct_answer", "single_tool", "workflow"}


def test_chat_run_uses_active_target_memory_for_followup_asset_reference(client: TestClient) -> None:
    session_id = "contract_active_target_memory_session"
    first = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": session_id,
                "messages": [{"role": "user", "content": "Analyze this asset."}],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "AgentChat",
                "selected_assets": ["/Game/Props/SM_Rock.SM_Rock"],
            },
            "payload": {"user_query": "Analyze this asset."},
            "runtime_options": {"debug": True, "return_debug_projection": True},
        },
    )
    assert first.status_code == 200

    followup = client.post(
        "/api/v1/chat/runs",
        json={
            "task_type": "agent_chat",
            "session": {
                "session_id": session_id,
                "messages": [{"role": "user", "content": "Analyze this asset again."}],
            },
            "context": {
                "project_name": "DemoProject",
                "active_panel": "AgentChat",
            },
            "payload": {"user_query": "Analyze this asset again."},
            "runtime_options": {"debug": True, "return_debug_projection": True},
        },
    )
    body = followup.json()

    assert followup.status_code == 200
    assert body["debug_view"]["route"]["selected_tool_id"] == "mcp_get_asset_details"
    assert body["debug_view"]["context_route_refinement"]["status"] == "applied"
    assert body["debug_view"]["context_resolution"]["target_id"] == "/Game/Props/SM_Rock.SM_Rock"
    assert body["debug_view"]["tool_plan_v1"]["requires_proposal"] is False
