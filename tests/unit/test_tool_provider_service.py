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


def test_tool_provider_view_maps_live_mcp_confirmed_write_alias(monkeypatch) -> None:
    def fake_live_discovery(settings: Settings, *, include_live_discovery: bool) -> dict:
        del settings
        assert include_live_discovery is True
        return {
            "attempted": True,
            "ok": True,
            "status": "ready",
            "reason": "fixture",
            "tool_count": 1,
            "allowed_tools": ["add_step"],
            "tools": [
                {
                    "name": "add_step",
                    "description": "UMG-MCP style Blueprint step insertion.",
                    "inputSchema": {"type": "object", "properties": {}},
                    "annotations": {
                        "side_effect_level": "confirmed_write",
                        "requiresConfirmation": True,
                    },
                }
            ],
            "debug": {},
        }

    monkeypatch.setattr("app.services.tool_provider_service._live_discovery", fake_live_discovery)

    view = build_tool_provider_view(Settings(_env_file=None), include_live_discovery=True)

    assert view["summary"]["live_mapped_tool_count"] == 1
    assert view["summary"]["live_mapped_confirmed_write_tool_count"] == 1
    assert view["summary"]["external_unmapped_tool_count"] == 0
    assert view["mcp_write_bridge"]["status"] == "proposal_mapping_only"
    assert view["mcp_write_bridge"]["direct_mcp_write_allowed"] is False
    tools = {item["tool_id"]: item for item in view["tools"]}
    add_step = tools["editor_blueprint_add_step"]
    assert add_step["live_provider_status"] == "available"
    assert add_step["preferred_provider"] == "http_proposal_bridge"
    live_provider = add_step["providers"][0]
    assert live_provider["tool_name"] == "add_step"
    assert live_provider["direct_call_allowed"] is False
    assert live_provider["proposal_bridge_allowed"] is True
    assert live_provider["trust_state"] == "mapped_confirmed_write_proposal_only"


def test_tool_provider_view_blocks_external_unmapped_write_tool(monkeypatch) -> None:
    def fake_live_discovery(settings: Settings, *, include_live_discovery: bool) -> dict:
        del settings
        assert include_live_discovery is True
        return {
            "attempted": True,
            "ok": True,
            "status": "ready",
            "reason": "fixture",
            "tool_count": 1,
            "allowed_tools": ["delete_everything"],
            "tools": [
                {
                    "name": "delete_everything",
                    "description": "Unsafe unmapped write fixture.",
                    "inputSchema": {"type": "object", "properties": {}},
                    "annotations": {"side_effect_level": "destructive_write"},
                }
            ],
            "debug": {},
        }

    monkeypatch.setattr("app.services.tool_provider_service._live_discovery", fake_live_discovery)

    view = build_tool_provider_view(Settings(_env_file=None), include_live_discovery=True)

    assert view["summary"]["external_unmapped_tool_count"] == 1
    assert view["summary"]["external_unmapped_write_tool_count"] == 1
    external = view["external_unmapped_tools"][0]
    assert external["name"] == "delete_everything"
    assert external["trust_state"] == "external_unmapped_write_blocked"
    assert external["direct_call_allowed"] is False
    assert external["proposal_bridge_allowed"] is False
