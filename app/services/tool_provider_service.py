from __future__ import annotations

from typing import Any

from app.core.settings import Settings
from app.services.mcp_tool_mapping import (
    detect_live_tool_side_effect_level,
    is_write_side_effect_level,
    live_tool_trust_state,
    resolve_local_tool_id_from_live_tool,
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
    local_tool_ids = {_tool_id(item) for item in manifest["tools"] if _tool_id(item)}
    local_tool_side_effects = {
        _tool_id(item): str(_tool_annotations(item).get("side_effect_level") or "read_only")
        for item in manifest["tools"]
        if _tool_id(item)
    }
    local_tool_name_to_tool_id = {
        _tool_name(item): _tool_id(item)
        for item in manifest["tools"]
        if _tool_name(item) and _tool_id(item)
    }
    live_by_name: dict[str, dict[str, Any]] = {}
    live_by_local_tool_id: dict[str, dict[str, Any]] = {}
    for item in live_tools:
        if not _tool_name(item):
            continue
        mapped_tool_id = resolve_local_tool_id_from_live_tool(
            item,
            local_tool_ids=local_tool_ids,
            local_tool_name_to_tool_id=local_tool_name_to_tool_id,
        )
        normalized = _normalize_live_tool(
            item,
            mapped_local_tool_id=mapped_tool_id,
            mapped_side_effect_level=local_tool_side_effects.get(mapped_tool_id, ""),
        )
        live_by_name[_tool_name(item)] = normalized
        if mapped_tool_id and mapped_tool_id not in live_by_local_tool_id:
            live_by_local_tool_id[mapped_tool_id] = normalized
    local_tools = [
        _provider_tool(
            item,
            live_by_local_tool_id=live_by_local_tool_id,
            include_live_discovery=include_live_discovery,
        )
        for item in manifest["tools"]
    ]
    external_tools = [
        _external_tool(item)
        for name, item in sorted(live_by_name.items())
        if name and not item.get("mapped_local_tool_id")
    ]
    preferred_counts: dict[str, int] = {}
    for item in local_tools:
        provider = str(item.get("preferred_provider") or "unknown")
        preferred_counts[provider] = preferred_counts.get(provider, 0) + 1
    live_mapped_tools = [item for item in live_by_local_tool_id.values()]
    live_mapped_write_tools = [
        item for item in live_mapped_tools if is_write_side_effect_level(item.get("mapped_side_effect_level"))
    ]
    external_write_tools = [
        item for item in external_tools if is_write_side_effect_level(item.get("detected_side_effect_level"))
    ]

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
        "tools": [_normalize_live_tool(item) for item in result.get("tools", []) if isinstance(item, dict)],
        "tool_count": int(result.get("tool_count") or len(result.get("tools") or [])),
        "allowed_tools": list(result.get("allowed_tools") or adapter_status.get("allowed_tools") or []),
        "debug": result.get("debug") or {},
    }


def _provider_tool(
    tool: dict[str, Any],
    *,
    live_by_local_tool_id: dict[str, dict[str, Any]],
    include_live_discovery: bool,
) -> dict[str, Any]:
    annotations = tool.get("annotations") if isinstance(tool.get("annotations"), dict) else {}
    boundary = annotations.get("execution_boundary") if isinstance(annotations.get("execution_boundary"), dict) else {}
    name = str(tool.get("name") or "")
    tool_id = str(annotations.get("tool_id") or name)
    live_tool = live_by_local_tool_id.get(tool_id)
    live_available = live_tool is not None
    live_status = "available" if live_available else ("not_discovered" if include_live_discovery else "not_attempted")
    local_status = "available" if boundary.get("local_tool_registry_call_allowed") else "not_supported"
    proposal_status = "available" if boundary.get("mode") == "confirmed_write_proposal" else "not_applicable"
    preferred_provider = _preferred_provider(
        live_available=live_available,
        boundary=boundary,
    )
    return {
        "tool_id": tool_id,
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
                "tool_name": str((live_tool or {}).get("name") or name),
                "direct_call_allowed": bool(live_available and boundary.get("direct_mcp_call_allowed")),
                "proposal_bridge_allowed": bool(live_available and boundary.get("mode") == "confirmed_write_proposal"),
                "trust_state": str((live_tool or {}).get("trust_state") or "not_discovered"),
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
    detected_side_effect_level = detect_live_tool_side_effect_level(tool)
    return {
        "name": str(tool.get("name") or ""),
        "description": str(tool.get("description") or ""),
        "inputSchema": tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {"type": "object"},
        "annotations": tool.get("annotations") if isinstance(tool.get("annotations"), dict) else {},
        "detected_side_effect_level": detected_side_effect_level,
        "trust_state": live_tool_trust_state(tool),
        "allowed_for_agent_free_chat": False,
        "direct_call_allowed": False,
        "proposal_bridge_allowed": False,
        "integration_hint": "Map this tool into app/tools/registry.py before using it in Agent workflows.",
    }


def _normalize_live_tool(
    tool: dict[str, Any],
    *,
    mapped_local_tool_id: str = "",
    mapped_side_effect_level: str = "",
) -> dict[str, Any]:
    return {
        "name": str(tool.get("name") or ""),
        "description": str(tool.get("description") or ""),
        "inputSchema": tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {"type": "object"},
        "annotations": tool.get("annotations") if isinstance(tool.get("annotations"), dict) else {},
        "detected_side_effect_level": detect_live_tool_side_effect_level(
            tool,
            fallback=mapped_side_effect_level,
        ),
        "mapped_local_tool_id": mapped_local_tool_id,
        "mapped_side_effect_level": mapped_side_effect_level,
        "trust_state": live_tool_trust_state(
            tool,
            mapped_local_tool_id=mapped_local_tool_id,
            mapped_side_effect_level=mapped_side_effect_level,
        ),
    }


def _tool_name(tool: dict[str, Any]) -> str:
    return str(tool.get("name") or "").strip()


def _tool_annotations(tool: dict[str, Any]) -> dict[str, Any]:
    annotations = tool.get("annotations") if isinstance(tool.get("annotations"), dict) else {}
    return annotations


def _tool_id(tool: dict[str, Any]) -> str:
    return str(_tool_annotations(tool).get("tool_id") or tool.get("name") or "").strip()
