from __future__ import annotations

from typing import Any

from app.services.mcp_tool_mapping import (
    detect_live_tool_side_effect_level,
    is_write_side_effect_level,
    live_tool_trust_state,
    resolve_local_tool_id_from_live_tool,
)


def build_live_provider_matches(
    *,
    live_tools: list[dict[str, Any]],
    manifest_tools: list[dict[str, Any]],
) -> dict[str, Any]:
    local_tool_ids = {_tool_id(item) for item in manifest_tools if _tool_id(item)}
    local_tool_side_effects = {
        _tool_id(item): str(_tool_annotations(item).get("side_effect_level") or "read_only")
        for item in manifest_tools
        if _tool_id(item)
    }
    local_tool_name_to_tool_id = {
        _tool_name(item): _tool_id(item)
        for item in manifest_tools
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
        normalized = normalize_live_tool(
            item,
            mapped_local_tool_id=mapped_tool_id,
            mapped_side_effect_level=local_tool_side_effects.get(mapped_tool_id, ""),
        )
        live_by_name[_tool_name(item)] = normalized
        if mapped_tool_id and mapped_tool_id not in live_by_local_tool_id:
            live_by_local_tool_id[mapped_tool_id] = normalized

    external_tools = [
        build_external_tool(item)
        for name, item in sorted(live_by_name.items())
        if name and not item.get("mapped_local_tool_id")
    ]
    live_mapped_tools = [item for item in live_by_local_tool_id.values()]
    live_mapped_write_tools = [
        item for item in live_mapped_tools if is_write_side_effect_level(item.get("mapped_side_effect_level"))
    ]
    external_write_tools = [
        item for item in external_tools if is_write_side_effect_level(item.get("detected_side_effect_level"))
    ]
    return {
        "live_by_name": live_by_name,
        "live_by_local_tool_id": live_by_local_tool_id,
        "external_tools": external_tools,
        "live_mapped_tools": live_mapped_tools,
        "live_mapped_write_tools": live_mapped_write_tools,
        "external_write_tools": external_write_tools,
    }


def build_provider_tool(
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
    preferred_provider = preferred_provider_for_tool(
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


def preferred_provider_for_tool(*, live_available: bool, boundary: dict[str, Any]) -> str:
    if live_available and boundary.get("direct_mcp_call_allowed"):
        return "frontend_mcp_live"
    if boundary.get("local_tool_registry_call_allowed"):
        return "local_tool_registry"
    if boundary.get("mode") == "confirmed_write_proposal":
        return "http_proposal_bridge"
    return "service_owned"


def build_external_tool(tool: dict[str, Any]) -> dict[str, Any]:
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


def normalize_live_tool(
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
