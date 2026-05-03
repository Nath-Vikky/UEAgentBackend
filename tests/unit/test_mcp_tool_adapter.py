from __future__ import annotations

from app.core.settings import Settings
from app.services.mcp_tool_adapter import MCPToolAdapter, build_mcp_adapter_status, build_mcp_capability


def test_mcp_adapter_is_disabled_by_default() -> None:
    settings = Settings()

    status = build_mcp_adapter_status(settings)
    capability = build_mcp_capability(settings)

    assert status["status"] == "disabled"
    assert status["enabled"] is False
    assert capability["tool_layer_only"] is True
    assert capability["frontend_protocol"] == "http"


def test_mcp_adapter_warns_when_enabled_without_command() -> None:
    settings = Settings(mcp_tool_adapter_enabled=True, mcp_stdio_command="")

    status = build_mcp_adapter_status(settings)

    assert status["status"] == "misconfigured"
    assert status["reason"] == "mcp_stdio_command_missing"


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

