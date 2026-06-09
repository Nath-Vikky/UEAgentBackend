from __future__ import annotations

from typing import Any

from app.core.settings import Settings
from app.services.mcp_provider_matching import (
    build_live_provider_matches,
    build_provider_tool,
    normalize_live_tool,
)
from app.services.mcp_tool_adapter import MCPToolAdapter, build_mcp_adapter_status
from app.services.tool_manifest_service import build_tool_manifest

TOOL_PROVIDER_VIEW_VERSION = "tool_provider_view_v1"


def build_tool_provider_view(
    settings: Settings,
    *,
    include_live_discovery: bool = False,
) -> dict[str, Any]:
    """Merge static Tool Registry data with optional live frontend MCP discovery."""

    manifest = build_tool_manifest(include_disabled=False)
    adapter_status = build_mcp_adapter_status(settings)
    live_discovery = _live_discovery(settings, include_live_discovery=include_live_discovery)
    live_tools = live_discovery.get("tools") if isinstance(live_discovery.get("tools"), list) else []
    matches = build_live_provider_matches(live_tools=live_tools, manifest_tools=manifest["tools"])
    live_by_name = matches["live_by_name"]
    live_by_local_tool_id = matches["live_by_local_tool_id"]
    local_tools = [
        build_provider_tool(
            item,
            live_by_local_tool_id=live_by_local_tool_id,
            include_live_discovery=include_live_discovery,
        )
        for item in manifest["tools"]
    ]
    external_tools = matches["external_tools"]
    preferred_counts: dict[str, int] = {}
    for item in local_tools:
        provider = str(item.get("preferred_provider") or "unknown")
        preferred_counts[provider] = preferred_counts.get(provider, 0) + 1
    live_mapped_tools = matches["live_mapped_tools"]
    live_mapped_write_tools = matches["live_mapped_write_tools"]
    external_write_tools = matches["external_write_tools"]

    return {
        "schema_version": TOOL_PROVIDER_VIEW_VERSION,
        "mode": "frontend_mcp_preferred_when_available",
        "summary": {
            "local_tool_count": len(local_tools),
            "live_discovered_tool_count": len(live_by_name),
            "live_mapped_tool_count": len(live_mapped_tools),
            "live_mapped_confirmed_write_tool_count": len(live_mapped_write_tools),
            "matched_live_tool_count": sum(1 for item in local_tools if item.get("live_provider_status") == "available"),
            "external_unmapped_tool_count": len(external_tools),
            "external_unmapped_write_tool_count": len(external_write_tools),
            "preferred_provider_counts": dict(sorted(preferred_counts.items())),
        },
        "provider_priority": [
            {
                "provider_id": "frontend_mcp_live",
                "description": "Live UEAgentTool or user-provided frontend MCP tools discovered through tools/list.",
                "priority": 10,
                "scope": "read_only_or_confirmed_write_discovery",
                "availability": "requires MCP_TOOL_ADAPTER_ENABLED=true and an allowed live tool.",
            },
            {
                "provider_id": "local_tool_registry",
                "description": "Backend local read-only or plan-only Tool Registry executor.",
                "priority": 20,
                "scope": "read_only_or_plan_only",
                "availability": "always available for implemented local tools.",
            },
            {
                "provider_id": "http_proposal_bridge",
                "description": "Default confirmed-write path. The UE plugin executes only after user confirmation.",
                "priority": 30,
                "scope": "confirmed_write",
                "availability": "always used for write tools.",
            },
        ],
        "adapter": adapter_status,
        "live_discovery": live_discovery,
        "safety_policy": {
            "http_remains_primary_frontend_protocol": True,
            "frontend_mcp_preferred_for_read_only_when_discovered": True,
            "frontend_mcp_confirmed_write_can_be_mapped_to_proposal": True,
            "unknown_external_tools_auto_execute": False,
            "confirmed_write_tools_require_proposal": True,
            "raw_mcp_write_tools_are_not_trusted": True,
        },
        "mcp_write_bridge": {
            "status": "proposal_mapping_only",
            "mapped_confirmed_write_tool_count": len(live_mapped_write_tools),
            "external_unmapped_write_tool_count": len(external_write_tools),
            "direct_mcp_write_allowed": False,
            "proposal_prepare_route": "POST /api/v1/mcp/tool-registry/proposals/prepare",
            "proposal_create_route": "POST /api/v1/mcp/tool-registry/proposals",
        },
        "routes": {
            "provider_view": "GET /api/v1/mcp/tool-providers",
            "external_mcp_discovery": "GET /api/v1/mcp/tools",
            "external_mcp_readonly_call": "POST /api/v1/mcp/tools/{tool_name}/call",
            "local_readonly_tool_call": "POST /api/v1/mcp/tool-registry/tools/{tool}/call",
            "local_plan_tool_call": "POST /api/v1/mcp/tool-registry/plans/{tool}/call",
            "confirmed_write_proposal": "POST /api/v1/editor-operations/proposals",
        },
        "tools": local_tools,
        "external_unmapped_tools": external_tools,
    }


def _live_discovery(settings: Settings, *, include_live_discovery: bool) -> dict[str, Any]:
    adapter_status = build_mcp_adapter_status(settings)
    if not include_live_discovery:
        return {
            "attempted": False,
            "ok": False,
            "status": "not_attempted",
            "reason": "include_live_discovery_false",
            "tools": [],
            "tool_count": 0,
        }
    result = MCPToolAdapter(settings).discover_tools()
    return {
        "attempted": True,
        "ok": bool(result.get("ok")),
        "status": result.get("status") or adapter_status["status"],
        "reason": result.get("reason") or adapter_status["reason"],
        "tools": [normalize_live_tool(item) for item in result.get("tools", []) if isinstance(item, dict)],
        "tool_count": int(result.get("tool_count") or len(result.get("tools") or [])),
        "allowed_tools": list(result.get("allowed_tools") or adapter_status.get("allowed_tools") or []),
        "debug": result.get("debug") or {},
    }
