from __future__ import annotations

from app.core.settings import Settings
from app.services.tool_provider_service import build_tool_provider_view


def test_tool_provider_view_exposes_static_provider_priority_without_live_discovery() -> None:
    view = build_tool_provider_view(Settings(_env_file=None), include_live_discovery=False)

    assert view["schema_version"] == "tool_provider_view_v1"
    assert view["mode"] == "frontend_mcp_preferred_when_available"
    assert view["live_discovery"]["attempted"] is False
    assert view["safety_policy"]["confirmed_write_tools_require_proposal"] is True
    assert view["safety_policy"]["unknown_external_tools_auto_execute"] is False
    provider_ids = [item["provider_id"] for item in view["provider_priority"]]
    assert provider_ids == ["frontend_mcp_live", "local_tool_registry", "http_proposal_bridge"]

    tools = {item["tool_id"]: item for item in view["tools"]}
    assert tools["mcp_get_editor_context"]["live_provider_status"] == "not_attempted"
    assert tools["mcp_get_editor_context"]["preferred_provider"] == "local_tool_registry"
    assert tools["editor_arrange_actors_pattern"]["preferred_provider"] == "http_proposal_bridge"
    assert tools["editor_arrange_actors_pattern"]["providers"][2]["direct_call_allowed"] is False
