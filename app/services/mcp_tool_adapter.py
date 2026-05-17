from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from app.core.settings import Settings
from app.services.mcp_client import MCPClientError, MCPStdioClient, MCPTcpClient, MCPTimeoutError

MCP_ADAPTER_PROTOCOL_VERSION = "mcp_tool_adapter_v1"
MCP_SUPPORTED_TRANSPORTS = ["mcp_stdio", "mcp_tcp", "mcp_http"]


def _command_exists(command: str) -> bool:
    text = str(command or "").strip()
    if not text:
        return False
    if any(separator in text for separator in ("\\", "/")):
        return Path(text).expanduser().exists()
    return shutil.which(text) is not None


def _transport_name(settings: Settings) -> str:
    configured = str(settings.mcp_transport or "stdio").strip().lower()
    if configured in {"tcp", "mcp_tcp"}:
        return "mcp_tcp"
    return "mcp_stdio"


def build_mcp_adapter_status(settings: Settings) -> dict[str, Any]:
    enabled = bool(settings.mcp_tool_adapter_enabled)
    transport = _transport_name(settings)
    command = settings.mcp_stdio_command.strip()
    command_available = _command_exists(command) if transport == "mcp_stdio" else False
    if not enabled:
        status = "disabled"
        reason = "mcp_tool_adapter_disabled"
    elif transport == "mcp_stdio" and not command:
        status = "misconfigured"
        reason = "mcp_stdio_command_missing"
    elif transport == "mcp_stdio" and not command_available:
        status = "warning"
        reason = "mcp_stdio_command_not_found_in_current_environment"
    elif transport == "mcp_tcp" and not settings.mcp_tcp_host.strip():
        status = "misconfigured"
        reason = "mcp_tcp_host_missing"
    elif transport == "mcp_tcp" and settings.mcp_tcp_port <= 0:
        status = "misconfigured"
        reason = "mcp_tcp_port_invalid"
    elif not settings.mcp_allowed_tools:
        status = "misconfigured"
        reason = "mcp_allowed_tools_missing"
    elif transport == "mcp_tcp":
        status = "ready"
        reason = "mcp_tcp_endpoint_configured"
    else:
        status = "ready"
        reason = "mcp_stdio_command_configured"

    return {
        "protocol_version": MCP_ADAPTER_PROTOCOL_VERSION,
        "enabled": enabled,
        "status": status,
        "reason": reason,
        "transport": transport,
        "supported_transports": MCP_SUPPORTED_TRANSPORTS,
        "stdio": {
            "command": command,
            "args": list(settings.mcp_stdio_args),
            "command_available": command_available,
            "timeout_ms": settings.mcp_stdio_timeout_ms,
            "auto_discover_on_startup": settings.mcp_auto_discover_on_startup,
        },
        "tcp": {
            "host": settings.mcp_tcp_host.strip(),
            "port": settings.mcp_tcp_port,
            "timeout_ms": settings.mcp_tcp_timeout_ms,
        },
        "allowed_tools": list(settings.mcp_allowed_tools),
        "discovery": {
            "status": "not_attempted",
            "reason": "discovery_is_explicit_by_default",
            "auto_discover_on_startup": settings.mcp_auto_discover_on_startup,
        },
        "safety_policy": {
            "default_side_effect_level": "read_only",
            "free_chat_auto_execute": False,
            "write_tools_require_proposal": True,
            "http_remains_primary_frontend_protocol": True,
        },
    }


def build_mcp_capability(settings: Settings) -> dict[str, Any]:
    status = build_mcp_adapter_status(settings)
    return {
        "mode": "optional_tool_transport",
        "protocol_version": MCP_ADAPTER_PROTOCOL_VERSION,
        "status": status["status"],
        "enabled": status["enabled"],
        "reason": status["reason"],
        "transports": MCP_SUPPORTED_TRANSPORTS,
        "default_enabled": False,
        "runtime_dependency": "none_when_disabled",
        "frontend_protocol": "http",
        "tool_layer_only": True,
        "configured_allowed_tools": status["allowed_tools"],
        "configured_transport": status["transport"],
        "discovery": status["discovery"],
        "debug_endpoints": {
            "list_tools": "/api/v1/mcp/tools",
            "call_tool": "/api/v1/mcp/tools/{tool_name}/call",
        },
        "safety_policy": status["safety_policy"],
    }


class MCPToolAdapter:
    """Small boundary object for future MCP calls.

    P3 intentionally keeps this adapter non-invasive: it exposes readiness and
    validates requested tool names, but does not take over the existing HTTP
    frontend/backend protocol or explicit Skill flows.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    def status(self) -> dict[str, Any]:
        return build_mcp_adapter_status(self.settings)

    def validate_readonly_tool_request(self, tool_name: str) -> dict[str, Any]:
        status = self.status()
        requested = str(tool_name or "").strip()
        allowed_tools = set(status["allowed_tools"])
        if status["status"] != "ready":
            return {
                "ok": False,
                "status": status["status"],
                "reason": status["reason"],
                "tool_name": requested,
            }
        if not requested:
            return {
                "ok": False,
                "status": "invalid_request",
                "reason": "missing_tool_name",
                "tool_name": requested,
            }
        if allowed_tools and requested not in allowed_tools:
            return {
                "ok": False,
                "status": "blocked",
                "reason": "tool_not_in_mcp_allowed_tools",
                "tool_name": requested,
                "allowed_tools": sorted(allowed_tools),
            }
        return {
            "ok": True,
            "status": "ready",
            "reason": "readonly_tool_request_allowed",
            "tool_name": requested,
            "transport": status["transport"],
        }

    def discover_tools(self) -> dict[str, Any]:
        status = self.status()
        if status["status"] != "ready":
            return {
                "ok": False,
                "status": status["status"],
                "reason": status["reason"],
                "tools": [],
                "allowed_tools": status["allowed_tools"],
                "debug": {"adapter": status},
            }
        try:
            with self._client() as client:
                initialize_result = client.initialize()
                tools_result = client.list_tools()
        except MCPTimeoutError as exc:
            return self._error_payload(exc, status=status, tools=[])
        except MCPClientError as exc:
            return self._error_payload(exc, status=status, tools=[])

        raw_tools = tools_result.get("tools") if isinstance(tools_result.get("tools"), list) else []
        tools = [item for item in raw_tools if isinstance(item, dict)]
        allowed_tools = set(status["allowed_tools"])
        if allowed_tools:
            tools = [item for item in tools if str(item.get("name") or "") in allowed_tools]
        return {
            "ok": True,
            "status": "ready",
            "reason": "mcp_tools_discovered",
            "tools": tools,
            "tool_count": len(tools),
            "allowed_tools": status["allowed_tools"],
            "debug": {
                "adapter": status,
                "initialize": {
                    "server_info": initialize_result.get("serverInfo") or {},
                    "protocol_version": initialize_result.get("protocolVersion"),
                    "capabilities": initialize_result.get("capabilities") or {},
                },
            },
        }

    def call_readonly_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        validation = self.validate_readonly_tool_request(tool_name)
        if not validation["ok"]:
            return validation
        try:
            with self._client() as client:
                initialize_result = client.initialize()
                result = client.call_tool(validation["tool_name"], arguments or {})
        except MCPTimeoutError as exc:
            return self._error_payload(exc, status=self.status(), tools=[], tool_name=tool_name)
        except MCPClientError as exc:
            return self._error_payload(exc, status=self.status(), tools=[], tool_name=tool_name)
        return {
            "ok": True,
            "status": "completed",
            "reason": "mcp_readonly_tool_completed",
            "tool_name": validation["tool_name"],
            "transport": validation["transport"],
            "result": result,
            "debug": {
                "adapter": self.status(),
                "initialize": {
                    "server_info": initialize_result.get("serverInfo") or {},
                    "protocol_version": initialize_result.get("protocolVersion"),
                },
            },
        }

    def _client(self) -> MCPStdioClient | MCPTcpClient:
        if _transport_name(self.settings) == "mcp_tcp":
            return MCPTcpClient(
                host=self.settings.mcp_tcp_host.strip(),
                port=self.settings.mcp_tcp_port,
                timeout_ms=self.settings.mcp_tcp_timeout_ms,
            )
        return MCPStdioClient(
            command=self.settings.mcp_stdio_command.strip(),
            args=list(self.settings.mcp_stdio_args),
            timeout_ms=self.settings.mcp_stdio_timeout_ms,
        )

    @staticmethod
    def _error_payload(
        exc: MCPClientError,
        *,
        status: dict[str, Any],
        tools: list[dict[str, Any]],
        tool_name: str | None = None,
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "error",
            "reason": exc.reason,
            "tool_name": tool_name,
            "tools": tools,
            "allowed_tools": status.get("allowed_tools") or [],
            "debug": {"adapter": status, "error_details": exc.details},
        }
