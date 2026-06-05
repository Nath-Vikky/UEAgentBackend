from __future__ import annotations

from collections import Counter
from typing import Any

from app.services.editor_operations.catalog import OPERATION_GROUPS, OPERATION_SPECS, READ_ONLY_INSPECTION_SPECS
from app.services.tool_registry_readonly_call_service import LOCAL_READONLY_CALL_PATH
from app.tools.registry import ToolSpec, iter_tool_specs

TOOL_MANIFEST_PROTOCOL_VERSION = "tool_manifest_v1"
MCP_COMPATIBLE_SCHEMA_VERSION = "mcp_tools_list_compatible_v1"

TOOL_MANIFEST_PROFILES: dict[str, dict[str, Any]] = {
    "full": {
        "title": "Full Tool Registry",
        "description": "Expose all enabled Tool Registry entries after optional filters.",
        "tool_ids": (),
    },
    "readonly_sensing": {
        "title": "Read-only Editor Sensing",
        "description": "Compact read-only tool surface for current project/editor facts.",
        "tool_ids": (
            "editor_inspect_assets",
            "editor_inspect_asset_detail",
            "editor_inspect_level_actors",
            "editor_inspect_level_actor_detail",
            "editor_inspect_material_instance_parameters",
            "editor_inspect_material_instance_detail",
            "mcp_get_blueprint_graph",
            "mcp_get_widget_tree",
        ),
    },
    "blueprint_demo": {
        "title": "Blueprint Graph Demo",
        "description": "Blueprint graph sensing, node insertion, pin connection, and compile proposal tools.",
        "tool_ids": (
            "mcp_get_blueprint_graph",
            "editor_create_blueprint_asset",
            "editor_add_blueprint_variable",
            "editor_add_blueprint_component",
            "editor_create_blueprint_event_stub",
            "editor_add_blueprint_node_template",
            "editor_connect_blueprint_nodes",
            "editor_compile_blueprint",
        ),
    },
    "umg_demo": {
        "title": "UMG Widget Demo",
        "description": "UMG sensing and common Widget Blueprint edit proposal tools.",
        "tool_ids": (
            "mcp_get_widget_tree",
            "editor_add_umg_widget",
            "editor_set_umg_widget_text",
            "editor_set_umg_widget_layout",
            "editor_set_umg_widget_visibility",
            "editor_set_umg_widget_appearance",
            "editor_set_umg_widget_brush",
            "editor_set_umg_slot_layout_v2",
            "editor_reparent_umg_widget",
            "editor_duplicate_umg_widget",
            "editor_delete_umg_widget",
        ),
    },
    "material_demo": {
        "title": "Material Instance Demo",
        "description": "Material Instance inspection and safe parameter proposal tools.",
        "tool_ids": (
            "editor_inspect_material_instance_parameters",
            "editor_inspect_material_instance_detail",
            "editor_set_material_instance_parameter",
            "editor_set_material_instance_texture_parameter",
            "editor_set_material_instance_static_switch",
        ),
    },
    "level_demo": {
        "title": "Level Actor Demo",
        "description": "Level Actor inspection, placement, transform, metadata, and arrangement proposal tools.",
        "tool_ids": (
            "editor_inspect_level_actors",
            "editor_inspect_level_actor_detail",
            "editor_place_actor_in_level",
            "editor_set_actor_transform",
            "editor_set_actor_metadata",
            "editor_arrange_actors_pattern",
        ),
    },
    "asset_maintenance": {
        "title": "Asset Maintenance Demo",
        "description": "Asset inventory, rename/move/duplicate, Static Mesh settings, and redirector maintenance tools.",
        "tool_ids": (
            "editor_inspect_assets",
            "editor_inspect_asset_detail",
            "editor_rename_asset",
            "editor_batch_rename_assets",
            "editor_move_assets",
            "editor_duplicate_asset",
            "editor_fixup_redirectors",
            "editor_apply_static_mesh_settings",
        ),
    },
}


def _empty_schema() -> dict[str, Any]:
    return {"type": "object", "properties": {}}


def _mcp_tool_name(spec: ToolSpec) -> str:
    if spec.transport.startswith("mcp") and spec.mcp_tool_name:
        return spec.mcp_tool_name
    return spec.tool_id


TOOL_ID_TO_EDITOR_OPERATION = {str(spec["tool_id"]): operation_type for operation_type, spec in OPERATION_SPECS.items()}
TOOL_ID_TO_READONLY_OPERATION = {
    str(spec["tool_id"]): operation_type for operation_type, spec in READ_ONLY_INSPECTION_SPECS.items()
}
TOOL_ID_TO_READONLY_GROUP = {str(spec["tool_id"]): str(spec["group"]) for spec in READ_ONLY_INSPECTION_SPECS.values()}


def _operation_group(operation_type: str) -> str:
    for group_id, group in OPERATION_GROUPS.items():
        if operation_type in set(group["operation_types"]):
            return group_id
    return "misc"


def _derived_manifest_metadata(spec: ToolSpec) -> dict[str, Any]:
    editor_operation = TOOL_ID_TO_EDITOR_OPERATION.get(spec.tool_id, "")
    readonly_operation = TOOL_ID_TO_READONLY_OPERATION.get(spec.tool_id, "")
    operation_type = editor_operation or readonly_operation
    if operation_type:
        return {
            "operation_family": _operation_group(operation_type)
            if editor_operation
            else TOOL_ID_TO_READONLY_GROUP.get(spec.tool_id, "sensing"),
            "frontend_executor_id": operation_type,
            "operation_type": operation_type,
            "bridge_kind": "editor_operation_proposal" if editor_operation else "inventory_readonly",
        }
    if spec.tool_id == "mcp_get_blueprint_graph":
        return {
            "operation_family": "blueprint",
            "frontend_executor_id": _mcp_tool_name(spec),
            "operation_type": "inspect_blueprint_graph",
            "bridge_kind": "mcp_readonly_or_inventory_fallback",
        }
    if spec.tool_id == "mcp_get_widget_tree":
        return {
            "operation_family": "umg",
            "frontend_executor_id": _mcp_tool_name(spec),
            "operation_type": "inspect_widget_tree",
            "bridge_kind": "mcp_readonly_or_inventory_fallback",
        }
    return {
        "operation_family": spec.category,
        "frontend_executor_id": spec.executor or _mcp_tool_name(spec),
        "operation_type": "",
        "bridge_kind": "tool_registry",
    }


def _execution_boundary(spec: ToolSpec) -> dict[str, Any]:
    if spec.side_effect_level == "read_only":
        return {
            "mode": "readonly_tool",
            "direct_mcp_call_allowed": spec.transport.startswith("mcp"),
            "local_tool_registry_call_allowed": True,
            "local_tool_registry_call_path": LOCAL_READONLY_CALL_PATH,
            "http_frontend_confirmation_required": False,
            "write_path": "not_applicable",
        }
    if spec.side_effect_level == "plan_only":
        return {
            "mode": "plan_only",
            "direct_mcp_call_allowed": False,
            "local_tool_registry_call_allowed": False,
            "http_frontend_confirmation_required": False,
            "write_path": "draft_or_plan_only",
        }
    if spec.effective_requires_confirmation:
        return {
            "mode": "confirmed_write_proposal",
            "direct_mcp_call_allowed": False,
            "local_tool_registry_call_allowed": False,
            "http_frontend_confirmation_required": True,
            "write_path": "POST /api/v1/editor-operations/proposals",
        }
    return {
        "mode": "controlled_tool",
        "direct_mcp_call_allowed": False,
        "local_tool_registry_call_allowed": False,
        "http_frontend_confirmation_required": False,
        "write_path": "service_owned",
    }


def _manifest_tool(spec: ToolSpec) -> dict[str, Any]:
    boundary = _execution_boundary(spec)
    derived = _derived_manifest_metadata(spec)
    return {
        "name": _mcp_tool_name(spec),
        "description": spec.description,
        "inputSchema": spec.input_schema or _empty_schema(),
        "annotations": {
            "tool_id": spec.tool_id,
            "title": spec.title,
            "task_type": spec.task_type,
            "category": spec.category,
            "transport": spec.transport,
            "side_effect_level": spec.side_effect_level,
            "requires_confirmation": spec.effective_requires_confirmation,
            "route_preference": spec.route_preference,
            "owned_by_skill": spec.owned_by_skill,
            "permission_gate": spec.permission_gate,
            "allowed_in_free_chat": spec.allowed_in_free_chat,
            "enabled": spec.enabled,
            "tier": spec.tier,
            "context_cost": spec.context_cost,
            "operation_family": derived["operation_family"],
            "frontend_executor_id": derived["frontend_executor_id"],
            "operation_type": derived["operation_type"],
            "bridge_kind": derived["bridge_kind"],
            "trigger_keywords": list(spec.trigger_keywords),
            "required_payload_fields": list(spec.required_payload_fields),
            "optional_payload_fields": list(spec.optional_payload_fields),
            "timeout_ms": spec.timeout_ms,
            "execution_boundary": boundary,
        },
    }


def build_tool_manifest(
    *,
    include_disabled: bool = True,
    category: str | None = None,
    side_effect_level: str | None = None,
    transport: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    specs = iter_tool_specs(include_disabled=include_disabled)
    profile_id = _normalize_profile_id(profile)
    profile_spec = TOOL_MANIFEST_PROFILES[profile_id]
    profile_tool_ids = tuple(profile_spec.get("tool_ids") or ())
    if profile_tool_ids:
        allowed_tool_ids = set(profile_tool_ids)
        specs = [spec for spec in specs if spec.tool_id in allowed_tool_ids]
    if category:
        specs = [spec for spec in specs if spec.category == category]
    if side_effect_level:
        specs = [spec for spec in specs if spec.side_effect_level == side_effect_level]
    if transport:
        specs = [spec for spec in specs if spec.transport == transport]

    tools = [_manifest_tool(spec) for spec in specs]
    transport_counts = Counter(spec.transport for spec in specs)
    side_effect_counts = Counter(spec.side_effect_level for spec in specs)
    category_counts = Counter(spec.category for spec in specs)
    proposal_count = sum(1 for spec in specs if spec.effective_requires_confirmation)

    return {
        "protocol_version": TOOL_MANIFEST_PROTOCOL_VERSION,
        "schema_version": MCP_COMPATIBLE_SCHEMA_VERSION,
        "source": "app.tools.registry.ToolSpec",
        "mode": "http_primary_mcp_compatible_manifest",
        "summary": {
            "tool_count": len(tools),
            "enabled_tool_count": sum(1 for spec in specs if spec.enabled),
            "proposal_tool_count": proposal_count,
            "read_only_tool_count": side_effect_counts.get("read_only", 0),
            "plan_only_tool_count": side_effect_counts.get("plan_only", 0),
            "transport_counts": dict(sorted(transport_counts.items())),
            "side_effect_counts": dict(sorted(side_effect_counts.items())),
            "category_counts": dict(sorted(category_counts.items())),
        },
        "filters": {
            "include_disabled": include_disabled,
            "category": category or "",
            "side_effect_level": side_effect_level or "",
            "transport": transport or "",
            "profile": profile_id,
            "profile_tool_count": len(profile_tool_ids),
        },
        "profiles": {
            "selected": {
                "profile_id": profile_id,
                "title": str(profile_spec.get("title") or profile_id),
                "description": str(profile_spec.get("description") or ""),
                "tool_ids": list(profile_tool_ids),
            },
            "available": [
                {
                    "profile_id": item_id,
                    "title": str(item.get("title") or item_id),
                    "description": str(item.get("description") or ""),
                    "tool_count": len(tuple(item.get("tool_ids") or ())),
                }
                for item_id, item in TOOL_MANIFEST_PROFILES.items()
            ],
        },
        "routes": {
            "external_mcp_discovery": "GET /api/v1/mcp/tools",
            "external_mcp_readonly_call": "POST /api/v1/mcp/tools/{tool_name}/call",
            "local_manifest": "GET /api/v1/mcp/tool-registry/manifest",
            "local_readonly_tool_call": LOCAL_READONLY_CALL_PATH,
            "confirmed_write_proposal_prepare": "POST /api/v1/mcp/tool-registry/proposals/prepare",
            "confirmed_write_proposal_create": "POST /api/v1/mcp/tool-registry/proposals",
            "confirmed_write_proposal": "POST /api/v1/editor-operations/proposals",
        },
        "safety_policy": {
            "http_remains_primary_frontend_protocol": True,
            "mcp_manifest_is_descriptive": True,
            "read_only_local_tool_registry_call_allowed": True,
            "confirmed_write_direct_mcp_call_allowed": False,
            "confirmed_write_requires_proposal_confirmation": True,
            "llm_output_never_executes_editor_write_directly": True,
        },
        "tools": tools,
    }


def _normalize_profile_id(profile: str | None) -> str:
    profile_id = str(profile or "full").strip().lower()
    if not profile_id:
        return "full"
    return profile_id if profile_id in TOOL_MANIFEST_PROFILES else "full"
