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
