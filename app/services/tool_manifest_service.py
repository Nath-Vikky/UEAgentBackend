from __future__ import annotations

from collections import Counter
from typing import Any

from app.services.editor_operations.catalog import OPERATION_GROUPS, OPERATION_SPECS, READ_ONLY_INSPECTION_SPECS
from app.services.tool_registry_plan_call_service import LOCAL_PLAN_CALL_PATH
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
        "suggested_prompts": (
            "Show the current Blueprint graph.",
            "Inspect the Widget Tree for /Game/UI/WBP_MainHUD.",
            "Show selected Material Instance parameters.",
            "List current level Actors by class or tag.",
            "Show the type and path for /Game/Blueprints/BP_PlayerCharacter.",
            "Show Static Mesh Nanite, LOD, collision, and material slots.",
        ),
        "sample_tool_calls": (
            {"tool_id": "mcp_get_editor_context", "arguments": {}},
            {"tool_id": "mcp_get_selected_assets", "arguments": {}},
            {"tool_id": "mcp_get_asset_details", "arguments": {"query": "BP_PlayerCharacter"}},
            {"tool_id": "mcp_get_static_mesh_details", "arguments": {"query": "SM_Rock"}},
            {"tool_id": "mcp_get_selected_actors", "arguments": {}},
            {"tool_id": "mcp_get_level_actors", "arguments": {"class_contains": "Character", "limit": 20}},
            {"tool_id": "mcp_get_level_actor_details", "arguments": {"actor_reference": "BP_PlayerCharacter_1"}},
            {"tool_id": "mcp_get_blueprint_graph", "arguments": {"blueprint_path": "/Game/Blueprints/BP_PlayerCharacter"}},
            {
                "tool_id": "mcp_get_blueprint_node_details",
                "arguments": {"blueprint_path": "/Game/Blueprints/BP_PlayerCharacter", "node_query": "Print String"},
            },
            {"tool_id": "mcp_get_widget_tree", "arguments": {"widget_blueprint_path": "/Game/UI/WBP_MainHUD"}},
            {
                "tool_id": "mcp_get_umg_widget_details",
                "arguments": {"widget_blueprint_path": "/Game/UI/WBP_MainHUD", "widget_name": "TitleText"},
            },
            {"tool_id": "mcp_get_material_instance_parameters", "arguments": {"material_instance_path": "/Game/Materials/MI_Player"}},
        ),
        "tool_ids": (
            "mcp_get_editor_context",
            "mcp_get_selected_assets",
            "mcp_get_asset_details",
            "mcp_get_static_mesh_details",
            "mcp_get_selected_actors",
            "mcp_get_level_actors",
            "mcp_get_level_actor_details",
            "editor_inspect_assets",
            "editor_inspect_asset_detail",
            "editor_inspect_level_actors",
            "editor_inspect_level_actor_detail",
            "editor_inspect_material_instance_parameters",
            "editor_inspect_material_instance_detail",
            "mcp_get_blueprint_graph",
            "mcp_get_blueprint_node_details",
            "editor_inspect_blueprint_node_detail",
            "mcp_get_widget_tree",
            "mcp_get_umg_widget_details",
            "editor_inspect_umg_widget_detail",
            "mcp_get_material_instance_parameters",
        ),
    },
    "blueprint_demo": {
        "title": "Blueprint Graph Demo",
        "description": "Blueprint graph sensing, node insertion, pin connection, and compile proposal tools.",
        "suggested_prompts": (
            "Set BP_PlayerCharacter EventGraph as the edit function, add a Print String step, then compile.",
            "Add a Print String step to BP_PlayerCharacter BeginPlay, then compile.",
            "Connect the current Blueprint node to Print String, then compile.",
        ),
        "sample_tool_calls": (
            {
                "tool_id": "editor_blueprint_set_edit_function",
                "arguments": {
                    "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                    "graph_name": "EventGraph",
                },
            },
            {
                "tool_id": "editor_blueprint_add_step",
                "arguments": {
                    "blueprint_path": "/Game/Blueprints/BP_PlayerCharacter",
                    "step_name": "PrintString",
                    "graph_name": "EventGraph",
                    "text": "Hello from UEAgent",
                    "entry_event": "BeginPlay",
                },
            },
        ),
        "tool_ids": (
            "mcp_get_blueprint_graph",
            "mcp_get_blueprint_node_details",
            "editor_inspect_blueprint_node_detail",
            "editor_blueprint_set_edit_function",
            "editor_blueprint_set_cursor_node",
            "editor_create_blueprint_asset",
            "editor_add_blueprint_variable",
            "editor_add_blueprint_component",
            "editor_create_blueprint_event_stub",
            "editor_add_blueprint_node_template",
            "editor_blueprint_add_step",
            "editor_connect_blueprint_nodes",
            "editor_compile_blueprint",
        ),
    },
    "umg_demo": {
        "title": "UMG Widget Demo",
        "description": "UMG sensing and common Widget Blueprint edit proposal tools.",
        "suggested_prompts": (
            "Add a TextBlock named TitleText to WBP_MainHUD under RootCanvas.",
            "Set WBP_MainHUD TitleText text to Mission Ready.",
            "Move WBP_MainHUD IconImage under RootCanvas.",
        ),
        "sample_tool_calls": (
            {
                "tool_id": "editor_add_umg_widget",
                "arguments": {
                    "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
                    "widget_name": "TitleText",
                    "widget_class": "TextBlock",
                    "parent_widget_name": "RootCanvas",
                    "text": "Mission Ready",
                },
            },
        ),
        "tool_ids": (
            "mcp_get_widget_tree",
            "mcp_get_umg_widget_details",
            "editor_inspect_umg_widget_detail",
            "editor_umg_set_widget_blueprint_context",
            "editor_umg_set_cursor_widget",
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
        "suggested_prompts": (
            "Show MI_Player material parameters.",
            "Set MI_Player Roughness to 0.35.",
            "Set MI_Player BaseTexture to T_Player_D.",
        ),
        "sample_tool_calls": (
            {
                "tool_id": "editor_set_material_instance_parameter",
                "arguments": {
                    "material_instance_path": "/Game/Materials/MI_Player",
                    "parameter_name": "Roughness",
                    "parameter_type": "scalar",
                    "value": 0.35,
                },
            },
        ),
        "tool_ids": (
            "mcp_get_material_instance_parameters",
            "editor_inspect_material_instance_parameters",
            "editor_inspect_material_instance_detail",
            "editor_material_set_instance_context",
            "editor_material_set_parameter_context",
            "editor_set_material_instance_parameter",
            "editor_set_material_instance_texture_parameter",
            "editor_set_material_instance_static_switch",
        ),
    },
    "level_demo": {
        "title": "Level Actor Demo",
        "description": "Level Actor inspection, placement, transform, metadata, and arrangement proposal tools.",
        "suggested_prompts": (
            "Place a PointLight named KeyLight_A at 120 50 300.",
            "Move this actor right 200.",
            "Arrange selected patrol actors in a grid.",
        ),
        "sample_tool_calls": (
            {
                "tool_id": "editor_place_actor_in_level",
                "arguments": {
                    "actor_class": "/Script/Engine.PointLight",
                    "actor_label": "KeyLight_A",
                    "transform": {"location": {"x": 120.0, "y": 50.0, "z": 300.0}},
                },
            },
        ),
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
        "suggested_prompts": (
            "Show recent project assets.",
            "Duplicate BP_EnemySpawner to BP_EnemySpawner_Copy.",
            "Fix redirectors under /Game/Blueprints.",
        ),
        "sample_tool_calls": (
            {
                "tool_id": "editor_duplicate_asset",
                "arguments": {
                    "source_asset_path": "/Game/Blueprints/BP_EnemySpawner",
                    "new_name": "BP_EnemySpawner_Copy",
                    "target_folder": "/Game/Blueprints",
                },
            },
        ),
        "tool_ids": (
            "mcp_get_asset_details",
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

TOOL_MANIFEST_WORKFLOW_PREVIEWS: dict[str, dict[str, Any]] = {
    "readonly_sensing": {
        "workflow_id": "readonly_sensing_preview_v1",
        "title": "Observe current project facts",
        "summary": "Use read-only inventory/MCP-compatible tools to inspect assets, graphs, widgets, actors, and materials.",
        "observe_tools": (
            "mcp_get_editor_context",
            "mcp_get_selected_assets",
            "mcp_get_asset_details",
            "mcp_get_static_mesh_details",
            "mcp_get_selected_actors",
            "mcp_get_level_actors",
            "mcp_get_level_actor_details",
            "editor_inspect_assets",
            "mcp_get_blueprint_graph",
            "mcp_get_blueprint_node_details",
            "editor_inspect_blueprint_node_detail",
            "mcp_get_widget_tree",
            "mcp_get_umg_widget_details",
            "editor_inspect_umg_widget_detail",
            "editor_inspect_level_actors",
            "mcp_get_material_instance_parameters",
            "editor_inspect_material_instance_detail",
        ),
        "context_tools": (),
        "proposal_tools": (),
        "happy_path": (
            "Sync or submit Project Inventory.",
            "Call one read-only sensing tool.",
            "Use the structuredContent as grounding for chat or a later Proposal.",
        ),
        "confirmation_required": False,
    },
    "blueprint_demo": {
        "workflow_id": "blueprint_graph_edit_preview_v1",
        "title": "Observe Blueprint graph, select context, then propose graph edits",
        "summary": "Read the graph/node detail first, set graph/cursor context when useful, then create confirmed Blueprint Proposals.",
        "observe_tools": ("mcp_get_blueprint_graph", "mcp_get_blueprint_node_details", "editor_inspect_blueprint_node_detail"),
        "context_tools": ("editor_blueprint_set_edit_function", "editor_blueprint_set_cursor_node"),
        "proposal_tools": (
            "editor_blueprint_add_step",
            "editor_connect_blueprint_nodes",
            "editor_compile_blueprint",
        ),
        "happy_path": (
            "Inspect Blueprint graph.",
            "Optionally inspect the target node detail.",
            "Set edit function or cursor node context.",
            "Create a pending Proposal.",
            "Let the user confirm execution in UEAgentTool.",
        ),
        "confirmation_required": True,
    },
    "umg_demo": {
        "workflow_id": "umg_widget_edit_preview_v1",
        "title": "Observe Widget Tree, select Widget context, then propose UMG edits",
        "summary": "Read Widget Tree/detail first, set Widget Blueprint/current Widget context, then create confirmed UMG Proposals.",
        "observe_tools": ("mcp_get_widget_tree", "mcp_get_umg_widget_details", "editor_inspect_umg_widget_detail"),
        "context_tools": ("editor_umg_set_widget_blueprint_context", "editor_umg_set_cursor_widget"),
        "proposal_tools": (
            "editor_add_umg_widget",
            "editor_set_umg_widget_text",
            "editor_set_umg_widget_layout",
            "editor_set_umg_widget_appearance",
            "editor_reparent_umg_widget",
        ),
        "happy_path": (
            "Inspect Widget Tree.",
            "Inspect or select the target Widget.",
            "Create a pending UMG Proposal.",
            "Let the user confirm execution in UEAgentTool.",
        ),
        "confirmation_required": True,
    },
    "material_demo": {
        "workflow_id": "material_instance_edit_preview_v1",
        "title": "Observe Material parameters, select parameter context, then propose edits",
        "summary": "Read Material Instance parameters first, set instance/parameter context, then create confirmed parameter Proposals.",
        "observe_tools": (
            "mcp_get_material_instance_parameters",
            "editor_inspect_material_instance_parameters",
            "editor_inspect_material_instance_detail",
        ),
        "context_tools": ("editor_material_set_instance_context", "editor_material_set_parameter_context"),
        "proposal_tools": (
            "editor_set_material_instance_parameter",
            "editor_set_material_instance_texture_parameter",
            "editor_set_material_instance_static_switch",
        ),
        "happy_path": (
            "Inspect Material Instance parameters.",
            "Set Material Instance and parameter context.",
            "Create a pending Material Proposal.",
            "Let the user confirm execution in UEAgentTool.",
        ),
        "confirmation_required": True,
    },
    "level_demo": {
        "workflow_id": "level_actor_edit_preview_v1",
        "title": "Observe level actors, then propose placement or transform edits",
        "summary": "Read Level Actor facts before proposing actor placement, transform, metadata, or arrangement edits.",
        "observe_tools": (
            "mcp_get_selected_actors",
            "mcp_get_level_actors",
            "mcp_get_level_actor_details",
            "editor_inspect_level_actors",
            "editor_inspect_level_actor_detail",
        ),
        "context_tools": (),
        "proposal_tools": (
            "editor_place_actor_in_level",
            "editor_set_actor_transform",
            "editor_set_actor_metadata",
            "editor_arrange_actors_pattern",
        ),
        "happy_path": (
            "Inspect current level actors.",
            "Create a pending Level Actor Proposal.",
            "Let the user confirm execution in UEAgentTool.",
        ),
        "confirmation_required": True,
    },
    "asset_maintenance": {
        "workflow_id": "asset_maintenance_preview_v1",
        "title": "Inspect assets, then propose safe maintenance actions",
        "summary": "Read asset detail before proposing rename, move, duplicate, redirector fix, or Static Mesh setting edits.",
        "observe_tools": (
            "mcp_get_selected_assets",
            "mcp_get_asset_details",
            "mcp_get_static_mesh_details",
            "editor_inspect_assets",
            "editor_inspect_asset_detail",
        ),
        "context_tools": (),
        "proposal_tools": (
            "editor_rename_asset",
            "editor_batch_rename_assets",
            "editor_move_assets",
            "editor_duplicate_asset",
            "editor_fixup_redirectors",
            "editor_apply_static_mesh_settings",
        ),
        "happy_path": (
            "Inspect asset list or one asset detail.",
            "Create a pending asset maintenance Proposal.",
            "Let the user confirm execution in UEAgentTool.",
        ),
        "confirmation_required": True,
    },
}


def _empty_schema() -> dict[str, Any]:
    return {"type": "object", "properties": {}}


def _mcp_tool_name(spec: ToolSpec) -> str:
    if spec.transport.startswith("mcp") and spec.mcp_tool_name:
        return spec.mcp_tool_name
    return spec.tool_id


TOOL_ID_TO_EDITOR_OPERATION_ALIASES = {
    "editor_blueprint_add_step": "add_blueprint_node_template",
}
BLUEPRINT_PLAN_ONLY_TOOL_IDS = {
    "editor_blueprint_set_edit_function": "set_blueprint_edit_function_context",
    "editor_blueprint_set_cursor_node": "set_blueprint_cursor_node_context",
}
UMG_PLAN_ONLY_TOOL_IDS = {
    "editor_umg_set_widget_blueprint_context": "set_umg_widget_blueprint_context",
    "editor_umg_set_cursor_widget": "set_umg_cursor_widget_context",
}
MATERIAL_PLAN_ONLY_TOOL_IDS = {
    "editor_material_set_instance_context": "set_material_instance_context",
    "editor_material_set_parameter_context": "set_material_parameter_context",
}
TOOL_ID_TO_EDITOR_OPERATION = {str(spec["tool_id"]): operation_type for operation_type, spec in OPERATION_SPECS.items()}
TOOL_ID_TO_EDITOR_OPERATION.update(TOOL_ID_TO_EDITOR_OPERATION_ALIASES)
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
    if spec.tool_id == "mcp_get_editor_context":
        return {
            "operation_family": "editor",
            "frontend_executor_id": _mcp_tool_name(spec),
            "operation_type": "inspect_editor_context",
            "bridge_kind": "mcp_readonly_live_editor",
        }
    if spec.tool_id == "mcp_get_selected_actors":
        return {
            "operation_family": "level",
            "frontend_executor_id": _mcp_tool_name(spec),
            "operation_type": "inspect_selected_actors",
            "bridge_kind": "mcp_readonly_live_editor",
        }
    if spec.tool_id == "mcp_get_level_actors":
        return {
            "operation_family": "level",
            "frontend_executor_id": _mcp_tool_name(spec),
            "operation_type": "inspect_level_actors",
            "bridge_kind": "mcp_readonly_or_inventory_fallback",
        }
    if spec.tool_id == "mcp_get_level_actor_details":
        return {
            "operation_family": "level",
            "frontend_executor_id": _mcp_tool_name(spec),
            "operation_type": "inspect_level_actor_detail",
            "bridge_kind": "mcp_readonly_or_inventory_fallback",
        }
    if spec.tool_id == "mcp_get_selected_assets":
        return {
            "operation_family": "asset",
            "frontend_executor_id": _mcp_tool_name(spec),
            "operation_type": "inspect_selected_assets",
            "bridge_kind": "mcp_readonly_live_editor",
        }
    if spec.tool_id == "mcp_get_asset_details":
        return {
            "operation_family": "asset",
            "frontend_executor_id": _mcp_tool_name(spec),
            "operation_type": "inspect_asset_detail",
            "bridge_kind": "mcp_readonly_or_inventory_fallback",
        }
    if spec.tool_id == "mcp_get_static_mesh_details":
        return {
            "operation_family": "asset",
            "frontend_executor_id": _mcp_tool_name(spec),
            "operation_type": "inspect_static_mesh_details",
            "bridge_kind": "mcp_readonly_or_inventory_fallback",
        }
    if spec.tool_id == "mcp_get_blueprint_graph":
        return {
            "operation_family": "blueprint",
            "frontend_executor_id": _mcp_tool_name(spec),
            "operation_type": "inspect_blueprint_graph",
            "bridge_kind": "mcp_readonly_or_inventory_fallback",
        }
    if spec.tool_id == "mcp_get_blueprint_node_details":
        return {
            "operation_family": "blueprint",
            "frontend_executor_id": _mcp_tool_name(spec),
            "operation_type": "inspect_blueprint_node_detail",
            "bridge_kind": "mcp_readonly_or_inventory_fallback",
        }
    if spec.tool_id == "editor_inspect_blueprint_node_detail":
        return {
            "operation_family": "blueprint",
            "frontend_executor_id": "inspect_blueprint_node_detail",
            "operation_type": "inspect_blueprint_node_detail",
            "bridge_kind": "inventory_readonly",
        }
    if spec.tool_id == "mcp_get_widget_tree":
        return {
            "operation_family": "umg",
            "frontend_executor_id": _mcp_tool_name(spec),
            "operation_type": "inspect_widget_tree",
            "bridge_kind": "mcp_readonly_or_inventory_fallback",
        }
    if spec.tool_id == "mcp_get_umg_widget_details":
        return {
            "operation_family": "umg",
            "frontend_executor_id": _mcp_tool_name(spec),
            "operation_type": "inspect_umg_widget_detail",
            "bridge_kind": "mcp_readonly_or_inventory_fallback",
        }
    if spec.tool_id == "mcp_get_material_instance_parameters":
        return {
            "operation_family": "material",
            "frontend_executor_id": _mcp_tool_name(spec),
            "operation_type": "inspect_material_instance_parameters",
            "bridge_kind": "mcp_readonly_or_inventory_fallback",
        }
    if spec.tool_id == "editor_inspect_umg_widget_detail":
        return {
            "operation_family": "umg",
            "frontend_executor_id": "inspect_umg_widget_detail",
            "operation_type": "inspect_umg_widget_detail",
            "bridge_kind": "inventory_readonly",
        }
    if spec.tool_id in BLUEPRINT_PLAN_ONLY_TOOL_IDS:
        return {
            "operation_family": "blueprint",
            "frontend_executor_id": spec.tool_id,
            "operation_type": BLUEPRINT_PLAN_ONLY_TOOL_IDS[spec.tool_id],
            "bridge_kind": "plan_only_context",
        }
    if spec.tool_id in UMG_PLAN_ONLY_TOOL_IDS:
        return {
            "operation_family": "umg",
            "frontend_executor_id": spec.tool_id,
            "operation_type": UMG_PLAN_ONLY_TOOL_IDS[spec.tool_id],
            "bridge_kind": "plan_only_context",
        }
    if spec.tool_id in MATERIAL_PLAN_ONLY_TOOL_IDS:
        return {
            "operation_family": "material",
            "frontend_executor_id": spec.tool_id,
            "operation_type": MATERIAL_PLAN_ONLY_TOOL_IDS[spec.tool_id],
            "bridge_kind": "plan_only_context",
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
            "local_tool_registry_call_allowed": True,
            "local_tool_registry_call_path": LOCAL_PLAN_CALL_PATH,
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


def _profile_workflow_preview(profile_id: str) -> dict[str, Any]:
    raw = TOOL_MANIFEST_WORKFLOW_PREVIEWS.get(profile_id) or {}
    if not raw:
        return {}
    return {
        "workflow_id": str(raw.get("workflow_id") or ""),
        "title": str(raw.get("title") or ""),
        "summary": str(raw.get("summary") or ""),
        "observe_tools": list(raw.get("observe_tools") or ()),
        "context_tools": list(raw.get("context_tools") or ()),
        "proposal_tools": list(raw.get("proposal_tools") or ()),
        "happy_path": list(raw.get("happy_path") or ()),
        "confirmation_required": bool(raw.get("confirmation_required")),
    }


def _all_profile_workflow_previews() -> list[dict[str, Any]]:
    previews: list[dict[str, Any]] = []
    for profile_id in TOOL_MANIFEST_PROFILES:
        preview = _profile_workflow_preview(profile_id)
        if preview:
            preview["profile_id"] = profile_id
            previews.append(preview)
    return previews


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
                "suggested_prompts": list(profile_spec.get("suggested_prompts") or ()),
                "sample_tool_calls": list(profile_spec.get("sample_tool_calls") or ()),
                "workflow_preview": _profile_workflow_preview(profile_id),
                "tool_ids": list(profile_tool_ids),
            },
            "workflow_previews": _all_profile_workflow_previews(),
            "available": [
                {
                    "profile_id": item_id,
                    "title": str(item.get("title") or item_id),
                    "description": str(item.get("description") or ""),
                    "suggested_prompt_count": len(tuple(item.get("suggested_prompts") or ())),
                    "sample_tool_call_count": len(tuple(item.get("sample_tool_calls") or ())),
                    "has_workflow_preview": bool(TOOL_MANIFEST_WORKFLOW_PREVIEWS.get(item_id)),
                    "tool_count": len(tuple(item.get("tool_ids") or ())),
                }
                for item_id, item in TOOL_MANIFEST_PROFILES.items()
            ],
        },
        "routes": {
            "tool_provider_view": "GET /api/v1/mcp/tool-providers",
            "external_mcp_discovery": "GET /api/v1/mcp/tools",
            "external_mcp_readonly_call": "POST /api/v1/mcp/tools/{tool_name}/call",
            "local_manifest": "GET /api/v1/mcp/tool-registry/manifest",
            "local_readonly_tool_call": LOCAL_READONLY_CALL_PATH,
            "local_plan_tool_call": LOCAL_PLAN_CALL_PATH,
            "confirmed_write_proposal_prepare": "POST /api/v1/mcp/tool-registry/proposals/prepare",
            "confirmed_write_proposal_create": "POST /api/v1/mcp/tool-registry/proposals",
            "confirmed_write_proposal": "POST /api/v1/editor-operations/proposals",
        },
        "safety_policy": {
            "http_remains_primary_frontend_protocol": True,
            "mcp_manifest_is_descriptive": True,
            "read_only_local_tool_registry_call_allowed": True,
            "plan_only_local_tool_registry_call_allowed": True,
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
