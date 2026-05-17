from __future__ import annotations

import json
import socketserver
from concurrent.futures import ThreadPoolExecutor
import sys
import threading
from pathlib import Path

from app.core.settings import Settings
from app.services.mcp_tool_adapter import MCPToolAdapter, build_mcp_adapter_status, build_mcp_capability


FIXTURE_SERVER = Path(__file__).resolve().parents[1] / "fixtures" / "weather_mcp_server.py"
CRASHING_SERVER = Path(__file__).resolve().parents[1] / "fixtures" / "crashing_mcp_server.py"
STDERR_SPAM_SERVER = Path(__file__).resolve().parents[1] / "fixtures" / "stderr_spam_mcp_server.py"
TIMEOUT_SERVER = Path(__file__).resolve().parents[1] / "fixtures" / "timeout_mcp_server.py"


class _JsonRpcTcpHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        for raw_line in self.rfile:
            request = json.loads(raw_line.decode("utf-8"))
            request_id = request.get("id")
            method = request.get("method")
            if request_id is None:
                continue
            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "ue-editor-fixture"},
                    },
                }
            elif method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": [
                            {
                                "name": "ue_agent_tools_list",
                                "description": "Return UE editor tool metadata.",
                                "inputSchema": {"type": "object", "properties": {}},
                            }
                        ]
                    },
                }
            elif method == "tools/call":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"content": [{"type": "text", "text": "tool catalog"}]},
                }
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": "Method not found"},
                }
            self.wfile.write(json.dumps(response).encode("utf-8") + b"\n")
            self.wfile.flush()


class _TcpFixture:
    def __enter__(self) -> _TcpFixture:
        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _JsonRpcTcpHandler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])


def test_mcp_adapter_is_disabled_by_default() -> None:
    settings = Settings()

    status = build_mcp_adapter_status(settings)
    capability = build_mcp_capability(settings)

    assert status["status"] == "disabled"
    assert status["enabled"] is False
    assert capability["tool_layer_only"] is True
    assert capability["frontend_protocol"] == "http"


def test_mcp_capability_preserves_http_and_proposal_boundaries() -> None:
    settings = Settings(
        mcp_tool_adapter_enabled=True,
        mcp_stdio_command=sys.executable,
        mcp_allowed_tools=["get_widget_tree"],
    )

    capability = build_mcp_capability(settings)

    assert capability["mode"] == "optional_tool_transport"
    assert capability["frontend_protocol"] == "http"
    assert capability["tool_layer_only"] is True
    assert capability["default_enabled"] is False
    assert capability["safety_policy"]["free_chat_auto_execute"] is False
    assert capability["safety_policy"]["write_tools_require_proposal"] is True
    assert capability["configured_allowed_tools"] == ["get_widget_tree"]


def test_mcp_adapter_warns_when_enabled_without_command() -> None:
    settings = Settings(mcp_tool_adapter_enabled=True, mcp_stdio_command="")

    status = build_mcp_adapter_status(settings)

    assert status["status"] == "misconfigured"
    assert status["reason"] == "mcp_stdio_command_missing"


def test_mcp_adapter_requires_explicit_allowed_tools_when_enabled() -> None:
    settings = Settings(
        mcp_tool_adapter_enabled=True,
        mcp_stdio_command=sys.executable,
        mcp_allowed_tools=[],
    )

    status = build_mcp_adapter_status(settings)

    assert status["status"] == "misconfigured"
    assert status["reason"] == "mcp_allowed_tools_missing"


def test_mcp_adapter_validates_allow_list() -> None:
    settings = Settings(
        mcp_tool_adapter_enabled=True,
        mcp_stdio_command="python",
        mcp_allowed_tools=["get_widget_tree"],
    )
    adapter = MCPToolAdapter(settings)

    allowed = adapter.validate_readonly_tool_request("get_widget_tree")
    blocked = adapter.validate_readonly_tool_request("delete_widget")

    assert allowed["ok"] is True or allowed["status"] == "warning"
    if allowed["ok"]:
        assert allowed["tool_name"] == "get_widget_tree"
    assert blocked["ok"] is False
    assert blocked["reason"] in {
        "tool_not_in_mcp_allowed_tools",
        "mcp_stdio_command_not_found_in_current_environment",
    }


def test_mcp_adapter_discovers_allowed_fixture_tools() -> None:
    settings = Settings(
        mcp_tool_adapter_enabled=True,
        mcp_stdio_command=sys.executable,
        mcp_stdio_args=[str(FIXTURE_SERVER)],
        mcp_allowed_tools=["get_weather"],
        mcp_stdio_timeout_ms=5000,
    )

    result = MCPToolAdapter(settings).discover_tools()

    assert result["ok"] is True
    assert result["tool_count"] == 1
    assert result["tools"][0]["name"] == "get_weather"
    assert result["debug"]["initialize"]["server_info"]["name"] == "weather-fixture"


def test_mcp_adapter_calls_allowed_fixture_tool() -> None:
    settings = Settings(
        mcp_tool_adapter_enabled=True,
        mcp_stdio_command=sys.executable,
        mcp_stdio_args=[str(FIXTURE_SERVER)],
        mcp_allowed_tools=["get_weather"],
        mcp_stdio_timeout_ms=5000,
    )

    result = MCPToolAdapter(settings).call_readonly_tool("get_weather", {"city": "Shanghai"})

    assert result["ok"] is True
    assert result["result"]["content"][0]["text"] == "Shanghai: sunny, 24C"


def test_mcp_adapter_discovers_allowed_tcp_tools() -> None:
    with _TcpFixture() as fixture:
        settings = Settings(
            mcp_tool_adapter_enabled=True,
            mcp_transport="tcp",
            mcp_tcp_host="127.0.0.1",
            mcp_tcp_port=fixture.port,
            mcp_tcp_timeout_ms=1000,
            mcp_allowed_tools=["ue_agent_tools_list"],
        )

        result = MCPToolAdapter(settings).discover_tools()

    assert result["ok"] is True
    assert result["tool_count"] == 1
    assert result["tools"][0]["name"] == "ue_agent_tools_list"
    assert result["debug"]["adapter"]["transport"] == "mcp_tcp"


def test_mcp_adapter_calls_allowed_tcp_tool() -> None:
    with _TcpFixture() as fixture:
        settings = Settings(
            mcp_tool_adapter_enabled=True,
            mcp_transport="tcp",
            mcp_tcp_host="127.0.0.1",
            mcp_tcp_port=fixture.port,
            mcp_tcp_timeout_ms=1000,
            mcp_allowed_tools=["ue_agent_tools_list"],
        )

        result = MCPToolAdapter(settings).call_readonly_tool("ue_agent_tools_list", {})

    assert result["ok"] is True
    assert result["transport"] == "mcp_tcp"
    assert result["result"]["content"][0]["text"] == "tool catalog"


def test_mcp_adapter_blocks_unlisted_fixture_tool_before_process_call() -> None:
    settings = Settings(
        mcp_tool_adapter_enabled=True,
        mcp_stdio_command=sys.executable,
        mcp_stdio_args=[str(FIXTURE_SERVER)],
        mcp_allowed_tools=["get_weather"],
        mcp_stdio_timeout_ms=5000,
    )

    result = MCPToolAdapter(settings).call_readonly_tool("delete_weather_cache", {})

    assert result["ok"] is False
    assert result["reason"] == "tool_not_in_mcp_allowed_tools"


def test_mcp_adapter_returns_error_when_server_crashes_mid_call() -> None:
    settings = Settings(
        mcp_tool_adapter_enabled=True,
        mcp_stdio_command=sys.executable,
        mcp_stdio_args=[str(CRASHING_SERVER)],
        mcp_allowed_tools=["crash_tool"],
        mcp_stdio_timeout_ms=1000,
    )

    result = MCPToolAdapter(settings).call_readonly_tool("crash_tool", {})

    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["reason"] in {"mcp_stdio_timeout", "mcp_stdio_process_exited", "mcp_stdio_write_failed"}
    assert "fixture crash" in result["debug"]["error_details"].get("stderr", "")


def test_mcp_adapter_times_out_when_server_never_responds() -> None:
    settings = Settings(
        mcp_tool_adapter_enabled=True,
        mcp_stdio_command=sys.executable,
        mcp_stdio_args=[str(TIMEOUT_SERVER)],
        mcp_allowed_tools=["slow_tool"],
        mcp_stdio_timeout_ms=300,
    )

    result = MCPToolAdapter(settings).discover_tools()

    assert result["ok"] is False
    assert result["status"] == "error"
    assert result["reason"] == "mcp_stdio_timeout"


def test_mcp_adapter_handles_stderr_spam_without_blocking() -> None:
    settings = Settings(
        mcp_tool_adapter_enabled=True,
        mcp_stdio_command=sys.executable,
        mcp_stdio_args=[str(STDERR_SPAM_SERVER)],
        mcp_allowed_tools=["echo_tool"],
        mcp_stdio_timeout_ms=5000,
    )

    result = MCPToolAdapter(settings).call_readonly_tool("echo_tool", {"text": "hello"})

    assert result["ok"] is True
    assert result["result"]["content"][0]["text"] == "hello"


def test_mcp_adapter_concurrent_calls_use_isolated_stdio_processes() -> None:
    def _call(index: int) -> dict:
        settings = Settings(
            mcp_tool_adapter_enabled=True,
            mcp_stdio_command=sys.executable,
            mcp_stdio_args=[str(FIXTURE_SERVER)],
            mcp_allowed_tools=["get_weather"],
            mcp_stdio_timeout_ms=5000,
        )
        return MCPToolAdapter(settings).call_readonly_tool("get_weather", {"city": f"City{index}"})

    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(_call, range(3)))

    assert all(item["ok"] for item in results)
    assert [item["result"]["content"][0]["text"] for item in results] == [
        "City0: sunny, 24C",
        "City1: sunny, 24C",
        "City2: sunny, 24C",
    ]
