from __future__ import annotations

import shutil
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.settings import get_settings
from app.db.session import get_engine, get_session_factory
from app.main import create_app


FIXTURE_SERVER = Path(__file__).resolve().parents[1] / "fixtures" / "weather_mcp_server.py"


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    runtime_root = Path(".test-runtime") / f"mcp-tools-{uuid.uuid4().hex}"
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
    monkeypatch.setenv("MCP_TOOL_ADAPTER_ENABLED", "true")
    monkeypatch.setenv("MCP_STDIO_COMMAND", sys.executable)
    monkeypatch.setenv("MCP_STDIO_ARGS", str(FIXTURE_SERVER))
    monkeypatch.setenv("MCP_ALLOWED_TOOLS", "get_weather")
    monkeypatch.setenv("MCP_STDIO_TIMEOUT_MS", "5000")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    shutil.rmtree(runtime_root, ignore_errors=True)


def test_mcp_tools_discovery_and_call_api(client: TestClient) -> None:
    tools_response = client.get("/api/v1/mcp/tools")

    assert tools_response.status_code == 200
    tools_body = tools_response.json()
    assert tools_body["success"] is True
    assert tools_body["tools"][0]["name"] == "get_weather"

    call_response = client.post(
        "/api/v1/mcp/tools/get_weather/call",
        json={"arguments": {"city": "Shanghai"}},
    )

    assert call_response.status_code == 200
    call_body = call_response.json()
    assert call_body["success"] is True
    assert call_body["result"]["content"][0]["text"] == "Shanghai: sunny, 24C"


def test_mcp_tools_api_blocks_unlisted_tool(client: TestClient) -> None:
    response = client.post(
        "/api/v1/mcp/tools/delete_weather_cache/call",
        json={"arguments": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["reason"] == "tool_not_in_mcp_allowed_tools"


def test_tool_registry_manifest_api_exposes_proposal_boundary(client: TestClient) -> None:
    response = client.get("/api/v1/mcp/tool-registry/manifest?side_effect_level=confirmed_write")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    manifest = body["manifest"]
    assert manifest["schema_version"] == "mcp_tools_list_compatible_v1"
    assert manifest["safety_policy"]["confirmed_write_direct_mcp_call_allowed"] is False
    tools = {
        item["annotations"]["tool_id"]: item
        for item in manifest["tools"]
    }
    assert "editor_arrange_actors_pattern" in tools
    boundary = tools["editor_arrange_actors_pattern"]["annotations"]["execution_boundary"]
    assert boundary["mode"] == "confirmed_write_proposal"
    assert boundary["direct_mcp_call_allowed"] is False
    assert boundary["write_path"] == "POST /api/v1/editor-operations/proposals"


def test_tool_registry_proposal_prepare_api_maps_confirmed_write_tool(client: TestClient) -> None:
    response = client.post(
        "/api/v1/mcp/tool-registry/proposals/prepare",
        json={
            "tool_id": "editor_arrange_actors_pattern",
            "arguments": {
                "actor_references": ["BP_EnemySpawner_1", "BP_PatrolPoint_1", "BP_PatrolPoint_2"],
                "pattern": {"type": "grid", "spacing": 250, "columns": 2},
            },
            "reason": "Arrange patrol actors.",
            "requested_by": "integration_test",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    bridge = body["bridge"]
    assert bridge["status"] == "prepared"
    assert bridge["operation_type"] == "arrange_actors_pattern"
    assert bridge["auto_execute"] is False
    assert bridge["proposal_request_hint"]["path"] == "/api/v1/editor-operations/proposals"
    assert bridge["proposal_request"]["payload"]["pattern"]["type"] == "grid"


def test_tool_registry_proposal_api_creates_pending_editor_proposal(client: TestClient) -> None:
    response = client.post(
        "/api/v1/mcp/tool-registry/proposals",
        json={
            "tool_id": "editor_arrange_actors_pattern",
            "arguments": {
                "actor_references": ["BP_EnemySpawner_1", "BP_PatrolPoint_1", "BP_PatrolPoint_2"],
                "pattern": {"type": "grid", "spacing": 250, "columns": 2},
            },
            "requested_by": "integration_test",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["bridge"]["status"] == "prepared"
    proposal = body["proposal"]
    assert proposal["item"]["confirmation"]["state"] == "pending"
    assert proposal["operation"]["operation_type"] == "arrange_actors_pattern"
    assert proposal["operation"]["tool_id"] == "editor_arrange_actors_pattern"


def test_tool_registry_proposal_prepare_api_blocks_readonly_tool(client: TestClient) -> None:
    response = client.post(
        "/api/v1/mcp/tool-registry/proposals/prepare",
        json={
            "tool_id": "mcp_get_blueprint_graph",
            "arguments": {"blueprint_path": "/Game/BP_Test"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["bridge"]["status"] == "blocked"
    assert body["errors"][0]["code"] == "tool_is_not_confirmed_write"
