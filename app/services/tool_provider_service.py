from __future__ import annotations

from typing import Any

from app.core.settings import Settings
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
    live_by_name = {_tool_name(item): _normalize_live_tool(item) for item in live_tools if _tool_name(item)}
    local_tools = [_provider_tool(item, live_by_name=live_by_name, include_live_discovery=include_live_discovery) for item in manifest["tools"]]
    local_names = {str(item.get("name") or "") for item in manifest["tools"]}
    external_tools = [
        _external_tool(item)
        for name, item in sorted(live_by_name.items())
        if name and name not in local_names
    ]
    preferred_counts: dict[str, int] = {}
    for item in local_tools:
        provider = str(item.get("preferred_provider") or "unknown")
        preferred_counts[provider] = preferred_counts.get(provider, 0) + 1

    return {
        "schema_version": TOOL_PROVIDER_VIEW_VERSION,
        "mode": "frontend_mcp_preferred_when_available",
        "summary": {
            "local_tool_count": len(local_tools),
            "live_discovered_tool_count": len(live_by_name),
            "matched_live_tool_count": sum(1 for item in local_tools if item.get("live_provider_status") == "available"),
            "external_unmapped_tool_count": len(external_tools),
            "preferred_provider_counts": dict(sorted(preferred_counts.items())),
        },
        "provider_priority": [
            {
                "provider_id": "frontend_mcp_live",
                "description": "Live UEAgentTool or user-provided frontend MCP tools discovered through tools/list.",
                "priority": 10,
                "scope": "read_only_only",
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
            "unknown_external_tools_auto_execute": False,
            "confirmed_write_tools_require_proposal": True,
            "raw_mcp_write_tools_are_not_trusted": True,
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
        "tools": [_normalize_live_tool(item) for item in result.get("tools", []) if isinstance(item, dict)],
        "tool_count": int(result.get("tool_count") or len(result.get("tools") or [])),
        "allowed_tools": list(result.get("allowed_tools") or adapter_status.get("allowed_tools") or []),
        "debug": result.get("debug") or {},
    }


def _provider_tool(
    tool: dict[str, Any],
    *,
    live_by_name: dict[str, dict[str, Any]],
    include_live_discovery: bool,
) -> dict[str, Any]:
    annotations = tool.get("annotations") if isinstance(tool.get("annotations"), dict) else {}
    boundary = annotations.get("execution_boundary") if isinstance(annotations.get("execution_boundary"), dict) else {}
    name = str(tool.get("name") or "")
    live_tool = live_by_name.get(name)
    live_available = live_tool is not None
    live_status = "available" if live_available else ("not_discovered" if include_live_discovery else "not_attempted")
    local_status = "available" if boundary.get("local_tool_registry_call_allowed") else "not_supported"
    proposal_status = "available" if boundary.get("mode") == "confirmed_write_proposal" else "not_applicable"
    preferred_provider = _preferred_provider(
        live_available=live_available,
        boundary=boundary,
    )
    return {
        "tool_id": annotations.get("tool_id") or name,
        "name": name,
        "title": annotations.get("title") or name,
        "side_effect_level": annotations.get("side_effect_level") or "read_only",
        "operation_family": annotations.get("operation_family") or annotations.get("category") or "",
        "bridge_kind": annotations.get("bridge_kind") or "",
        "preferred_provider": preferred_provider,
        "live_provider_status": live_status,
        "providers": [
            {
                "provider_id": "frontend_mcp_live",
                "status": live_status,
                "tool_name": name,
                "direct_call_allowed": bool(live_available and boundary.get("direct_mcp_call_allowed")),
                "source": "tools/list" if live_available else "not_available",
                "metadata": live_tool or {},
            },
            {
                "provider_id": "local_tool_registry",
                "status": local_status,
                "call_path": boundary.get("local_tool_registry_call_path") or "",
                "direct_call_allowed": bool(boundary.get("local_tool_registry_call_allowed")),
            },
            {
                "provider_id": "http_proposal_bridge",
                "status": proposal_status,
                "call_path": boundary.get("write_path") or "",
                "direct_call_allowed": False,
            },
        ],
    }


def _preferred_provider(*, live_available: bool, boundary: dict[str, Any]) -> str:
    if live_available and boundary.get("direct_mcp_call_allowed"):
        return "frontend_mcp_live"
    if boundary.get("local_tool_registry_call_allowed"):
        return "local_tool_registry"
    if boundary.get("mode") == "confirmed_write_proposal":
        return "http_proposal_bridge"
    return "service_owned"


def _external_tool(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(tool.get("name") or ""),
        "description": str(tool.get("description") or ""),
        "inputSchema": tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {"type": "object"},
        "annotations": tool.get("annotations") if isinstance(tool.get("annotations"), dict) else {},
        "trust_state": "external_unmapped",
        "allowed_for_agent_free_chat": False,
        "integration_hint": "Map this tool into app/tools/registry.py before using it in Agent workflows.",
    }


def _normalize_live_tool(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(tool.get("name") or ""),
        "description": str(tool.get("description") or ""),
        "inputSchema": tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {"type": "object"},
        "annotations": tool.get("annotations") if isinstance(tool.get("annotations"), dict) else {},
    }


def _tool_name(tool: dict[str, Any]) -> str:
    return str(tool.get("name") or "").strip()
