from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from app.core.settings import Settings

MCP_ADAPTER_PROTOCOL_VERSION = "mcp_tool_adapter_v1"
MCP_SUPPORTED_TRANSPORTS = ["mcp_stdio", "mcp_http"]


def _command_exists(command: str) -> bool:
    text = str(command or "").strip()
    if not text:
        return False
    if any(separator in text for separator in ("\\", "/")):
        return Path(text).expanduser().exists()
    return shutil.which(text) is not None


def build_mcp_adapter_status(settings: Settings) -> dict[str, Any]:
    enabled = bool(settings.mcp_tool_adapter_enabled)
    command = settings.mcp_stdio_command.strip()
    command_available = _command_exists(command)
    if not enabled:
        status = "disabled"
        reason = "mcp_tool_adapter_disabled"
    elif not command:
        status = "misconfigured"
        reason = "mcp_stdio_command_missing"
    elif not command_available:
        status = "warning"
        reason = "mcp_stdio_command_not_found_in_current_environment"
    else:
        status = "ready"
        reason = "mcp_stdio_command_configured"

    return {
        "protocol_version": MCP_ADAPTER_PROTOCOL_VERSION,
        "enabled": enabled,
        "status": status,
        "reason": reason,
        "transport": "mcp_stdio",
        "supported_transports": MCP_SUPPORTED_TRANSPORTS,
        "stdio": {
            "command": command,
            "args": list(settings.mcp_stdio_args),
            "command_available": command_available,
            "timeout_ms": settings.mcp_stdio_timeout_ms,
        },
        "allowed_tools": list(settings.mcp_allowed_tools),
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

