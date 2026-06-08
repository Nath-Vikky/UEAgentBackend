from __future__ import annotations

import re
from typing import Any

EDITOR_OPERATION_PROTOCOL_VERSION = "editor_operation_bridge_v1"
EDITOR_OPERATION_PROPOSAL_TYPE = "editor_operation"
EDITOR_OPERATION_FOLLOW_UP_MATERIALIZATION_VERSION = "editor_operation_follow_up_materialization_v1"

ASSET_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,63}$")
CLASS_NAME_RE = re.compile(r"^[A-Za-z_/][A-Za-z0-9_./:]*$")
PARAMETER_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_ ]{0,79}$")
SAFE_TEXT_RE = re.compile(r"^[A-Za-z0-9_./:-]+$")

STATIC_MESH_SETTING_KEYS = {
    "nanite_enabled",
    "collision_complexity",
    "lod_group",
    "generate_lightmap_uv",
    "lightmap_resolution",
}

STATIC_MESH_COLLISION_VALUES = {
    "project_default",
    "simple_and_complex",
    "use_simple_as_complex",
    "use_complex_as_simple",
}

BLUEPRINT_VARIABLE_TYPES = {
    "bool",
    "byte",
    "uint8",
    "int64",
    "int32",
    "float",
    "double",
    "FString",
    "FName",
    "FText",
    "FVector",
    "FRotator",
    "FTransform",
    "UObject",
    "AActor",
}

BLUEPRINT_VARIABLE_TYPE_ALIASES = {
    "bool": "bool",
    "byte": "byte",
    "uint8": "uint8",
    "int": "int32",
    "int32": "int32",
    "int64": "int64",
    "float": "float",
    "double": "double",
    "name": "FName",
    "fname": "FName",
    "string": "FString",
    "fstring": "FString",
    "text": "FText",
    "ftext": "FText",
    "vector": "FVector",
    "fvector": "FVector",
    "rotator": "FRotator",
    "frotator": "FRotator",
    "transform": "FTransform",
    "ftransform": "FTransform",
    "object": "UObject",
    "uobject": "UObject",
    "actor": "AActor",
    "aactor": "AActor",
}

BLUEPRINT_EVENT_NAMES = {
    "BeginPlay",
    "Tick",
    "ActorBeginOverlap",
    "ActorEndOverlap",
}

BLUEPRINT_NODE_TEMPLATE_IDS = {
    "branch_print_string",
    "call_function",
    "custom_event_print_string",
    "delay_print_string",
    "enhanced_input_action_event",
    "enhanced_input_print_string",
    "get_variable",
    "print_string",
    "sequence_print_strings",
    "set_variable",
}

BLUEPRINT_NODE_ENTRY_EVENTS = {
    "ActorBeginOverlap",
    "ActorEndOverlap",
    "BeginPlay",
}

BLUEPRINT_BRANCH_PATHS = {
    "false",
    "true",
}

UMG_WIDGET_CLASS_ALIASES = {
    "text": "/Script/UMG.TextBlock",
    "textblock": "/Script/UMG.TextBlock",
    "button": "/Script/UMG.Button",
    "image": "/Script/UMG.Image",
    "border": "/Script/UMG.Border",
    "canvas": "/Script/UMG.CanvasPanel",
    "canvaspanel": "/Script/UMG.CanvasPanel",
    "horizontalbox": "/Script/UMG.HorizontalBox",
    "verticalbox": "/Script/UMG.VerticalBox",
}

UMG_WIDGET_CLASS_ALLOWLIST = set(UMG_WIDGET_CLASS_ALIASES.values())

UMG_VISIBILITY_VALUES = {
    "visible",
    "collapsed",
    "hidden",
    "hit_test_invisible",
    "self_hit_test_invisible",
}

UMG_VISIBILITY_ALIASES = {
    "show": "visible",
    "shown": "visible",
    "visible": "visible",
    "hide": "collapsed",
    "hidden": "hidden",
    "invisible": "hidden",
    "collapse": "collapsed",
    "collapsed": "collapsed",
    "hit test invisible": "hit_test_invisible",
    "hittestinvisible": "hit_test_invisible",
    "hit_test_invisible": "hit_test_invisible",
    "self hit test invisible": "self_hit_test_invisible",
    "selfhittestinvisible": "self_hit_test_invisible",
    "self_hit_test_invisible": "self_hit_test_invisible",
}

MATERIAL_PARAMETER_TYPES = {"scalar", "vector"}

OPERATION_SPECS: dict[str, dict[str, Any]] = {
    "rename_selected_asset": {
        "tool_id": "editor_rename_asset",
        "title": "Rename Selected Asset",
        "risk_flags": "MEDIUM",
        "summary": "Rename one selected Unreal asset without moving it.",
        "required_fields": ["asset_path", "new_name"],
        "frontend_status": "implemented_v1",
    },
    "apply_static_mesh_basic_settings": {
        "tool_id": "editor_apply_static_mesh_settings",
        "title": "Apply Static Mesh Basic Settings",
        "risk_flags": "MEDIUM",
        "summary": "Apply a small whitelist of Static Mesh settings to one selected asset.",
        "required_fields": ["asset_path", "settings"],
        "frontend_status": "implemented_v1",
    },
    "create_blueprint_asset": {
        "tool_id": "editor_create_blueprint_asset",
        "title": "Create Blueprint Asset",
        "risk_flags": "MEDIUM",
        "summary": "Create one Blueprint asset under /Game after user confirmation.",
        "required_fields": ["parent_class", "target_folder", "asset_name"],
        "frontend_status": "implemented_v1",
    },
    "add_blueprint_variable": {
        "tool_id": "editor_add_blueprint_variable",
        "title": "Add Blueprint Variable",
        "risk_flags": "MEDIUM",
        "summary": "Add one variable to one Blueprint after user confirmation.",
        "required_fields": ["blueprint_path", "variable_name", "variable_type"],
        "frontend_status": "implemented_v1",
    },
    "add_blueprint_component": {
        "tool_id": "editor_add_blueprint_component",
        "title": "Add Blueprint Component",
        "risk_flags": "MEDIUM",
        "summary": "Add one component to one Blueprint after user confirmation.",
        "required_fields": ["blueprint_path", "component_name", "component_class"],
        "frontend_status": "implemented_v1",
    },
    "create_blueprint_event_stub": {
        "tool_id": "editor_create_blueprint_event_stub",
        "title": "Create Blueprint Event Stub",
        "risk_flags": "MEDIUM",
        "summary": "Create a small event stub in one Blueprint graph after user confirmation.",
        "required_fields": ["blueprint_path", "event_name"],
        "frontend_status": "implemented_v1",
    },
    "add_blueprint_node_template": {
        "tool_id": "editor_add_blueprint_node_template",
        "title": "Add Blueprint Node Template",
        "risk_flags": "MEDIUM",
        "summary": "Add one whitelisted Blueprint node template to a graph after user confirmation.",
        "required_fields": ["blueprint_path", "template_id"],
        "frontend_status": "implemented_v1",
    },
    "connect_blueprint_nodes": {
        "tool_id": "editor_connect_blueprint_nodes",
        "title": "Connect Blueprint Nodes",
        "risk_flags": "MEDIUM",
        "summary": "Connect two explicit Blueprint pins in one graph after user confirmation.",
        "required_fields": [
            "blueprint_path",
            "graph_name",
            "source_node_id",
            "source_pin_name",
            "target_node_id",
            "target_pin_name",
        ],
        "frontend_status": "implemented_v1",
    },
    "compile_blueprint": {
        "tool_id": "editor_compile_blueprint",
        "title": "Compile Blueprint",
        "risk_flags": "MEDIUM",
        "summary": "Compile one Blueprint in the Unreal Editor after user confirmation.",
        "required_fields": ["blueprint_path"],
        "frontend_status": "implemented_v1",
    },
    "batch_rename_assets": {
        "tool_id": "editor_batch_rename_assets",
        "title": "Batch Rename Assets",
        "risk_flags": "HIGH",
        "summary": "Rename multiple Unreal assets in one confirmed editor transaction.",
        "required_fields": ["renames"],
        "frontend_status": "implemented_v1",
    },
    "move_assets": {
        "tool_id": "editor_move_assets",
        "title": "Move Assets",
        "risk_flags": "HIGH",
        "summary": "Move multiple Unreal assets to one target folder after user confirmation.",
        "required_fields": ["asset_paths", "target_folder"],
        "frontend_status": "implemented_v1",
    },
    "duplicate_asset": {
        "tool_id": "editor_duplicate_asset",
        "title": "Duplicate Asset",
        "risk_flags": "MEDIUM",
        "summary": "Duplicate one Unreal asset to a new /Game path after user confirmation.",
        "required_fields": ["source_asset_path", "new_name"],
        "frontend_status": "implemented_v1",
    },
    "fixup_redirectors": {
        "tool_id": "editor_fixup_redirectors",
        "title": "Fixup Redirectors",
        "risk_flags": "HIGH",
        "summary": "Fix redirectors under one bounded /Game folder after user confirmation.",
        "required_fields": ["folder_path"],
        "frontend_status": "implemented_v1",
    },
    "add_umg_widget": {
        "tool_id": "editor_add_umg_widget",
        "title": "Add UMG Widget",
        "risk_flags": "MEDIUM",
        "summary": "Add one simple widget to a Widget Blueprint after user confirmation.",
        "required_fields": ["widget_blueprint_path", "widget_name", "widget_class"],
        "frontend_status": "implemented_v1",
    },
    "set_umg_widget_text": {
        "tool_id": "editor_set_umg_widget_text",
        "title": "Set UMG Widget Text",
        "risk_flags": "MEDIUM",
        "summary": "Set text on one TextBlock in a Widget Blueprint after user confirmation.",
        "required_fields": ["widget_blueprint_path", "widget_name", "text"],
        "frontend_status": "implemented_v1",
    },
    "set_umg_widget_layout": {
        "tool_id": "editor_set_umg_widget_layout",
        "title": "Set UMG Widget Layout",
        "risk_flags": "MEDIUM",
        "summary": "Set CanvasPanelSlot layout fields on one UMG widget after user confirmation.",
        "required_fields": ["widget_blueprint_path", "widget_name", "layout"],
        "frontend_status": "implemented_v1",
    },
    "set_umg_widget_visibility": {
        "tool_id": "editor_set_umg_widget_visibility",
        "title": "Set UMG Widget Visibility",
        "risk_flags": "MEDIUM",
        "summary": "Set visibility on one UMG widget after user confirmation.",
        "required_fields": ["widget_blueprint_path", "widget_name", "visibility"],
        "frontend_status": "implemented_v1",
    },
    "set_umg_widget_appearance": {
        "tool_id": "editor_set_umg_widget_appearance",
        "title": "Set UMG Widget Appearance",
        "risk_flags": "MEDIUM",
        "summary": "Set safe visual fields such as render opacity, enabled state, TextBlock color, or font size.",
        "required_fields": ["widget_blueprint_path", "widget_name", "appearance"],
        "frontend_status": "implemented_v1",
    },
    "set_umg_widget_brush": {
        "tool_id": "editor_set_umg_widget_brush",
        "title": "Set UMG Widget Brush",
        "risk_flags": "MEDIUM",
        "summary": "Set a safe Image or Border brush texture/material reference on one widget.",
        "required_fields": ["widget_blueprint_path", "widget_name", "brush"],
        "frontend_status": "implemented_v1",
    },
    "set_umg_slot_layout_v2": {
        "tool_id": "editor_set_umg_slot_layout_v2",
        "title": "Set UMG Slot Layout v2",
        "risk_flags": "MEDIUM",
        "summary": "Set safe HorizontalBox, VerticalBox, or Overlay slot layout fields on one widget.",
        "required_fields": ["widget_blueprint_path", "widget_name", "slot_type", "layout"],
        "frontend_status": "implemented_v1",
    },
    "reparent_umg_widget": {
        "tool_id": "editor_reparent_umg_widget",
        "title": "Reparent UMG Widget",
        "risk_flags": "MEDIUM",
        "summary": "Move one existing widget under another existing panel widget after user confirmation.",
        "required_fields": ["widget_blueprint_path", "widget_name", "new_parent_name"],
        "frontend_status": "implemented_v1",
    },
    "duplicate_umg_widget": {
        "tool_id": "editor_duplicate_umg_widget",
        "title": "Duplicate UMG Widget",
        "risk_flags": "MEDIUM",
        "summary": "Duplicate one existing non-panel UMG widget under the same parent after user confirmation.",
        "required_fields": ["widget_blueprint_path", "widget_name", "new_widget_name"],
        "frontend_status": "implemented_v1",
    },
    "delete_umg_widget": {
        "tool_id": "editor_delete_umg_widget",
        "title": "Delete UMG Widget",
        "risk_flags": "HIGH",
        "summary": "Remove one existing non-root non-panel UMG widget after user confirmation.",
        "required_fields": ["widget_blueprint_path", "widget_name"],
        "frontend_status": "implemented_v1",
    },
    "place_actor_in_level": {
        "tool_id": "editor_place_actor_in_level",
        "title": "Place Actor In Level",
        "risk_flags": "MEDIUM",
        "summary": "Place one Actor class in the current editor level after user confirmation.",
        "required_fields": ["actor_class"],
        "frontend_status": "implemented_v1",
    },
    "select_level_actors": {
        "tool_id": "editor_select_level_actors",
        "title": "Select Level Actors",
        "risk_flags": "LOW",
        "summary": "Select a bounded Actor set in the current editor level after user confirmation.",
        "required_fields": ["selection"],
        "frontend_status": "implemented_v1",
    },
    "set_actor_folder": {
        "tool_id": "editor_set_actor_folder",
        "title": "Set Actor Folder",
        "risk_flags": "MEDIUM",
        "summary": "Move a bounded Actor set into one World Outliner folder after user confirmation.",
        "required_fields": ["selection", "target_folder_path"],
        "frontend_status": "implemented_v1",
    },
    "set_actor_tags": {
        "tool_id": "editor_set_actor_tags",
        "title": "Set Actor Tags",
        "risk_flags": "MEDIUM",
        "summary": "Replace, append, or remove tags on a bounded Actor set after user confirmation.",
        "required_fields": ["selection", "tags"],
        "frontend_status": "implemented_v1",
    },
    "set_actor_visibility": {
        "tool_id": "editor_set_actor_visibility",
        "title": "Set Actor Visibility",
        "risk_flags": "MEDIUM",
        "summary": "Set Hidden In Game on a bounded Actor set after user confirmation.",
        "required_fields": ["selection", "hidden_in_game"],
        "frontend_status": "implemented_v1",
    },
    "set_actor_transform": {
        "tool_id": "editor_set_actor_transform",
        "title": "Set Actor Transform",
        "risk_flags": "MEDIUM",
        "summary": "Modify one existing Actor transform in the current editor level after user confirmation.",
        "required_fields": ["actor_reference", "transform_mode"],
        "frontend_status": "implemented_v1",
    },
    "set_actor_metadata": {
        "tool_id": "editor_set_actor_metadata",
        "title": "Set Actor Metadata",
        "risk_flags": "MEDIUM",
        "summary": "Set one Actor label, folder, or tags after user confirmation.",
        "required_fields": ["actor_reference", "metadata"],
        "frontend_status": "implemented_v1",
    },
    "arrange_actors_pattern": {
        "tool_id": "editor_arrange_actors_pattern",
        "title": "Arrange Actors Pattern",
        "risk_flags": "MEDIUM",
        "summary": "Arrange a bounded Actor set with line, grid, or circle placement templates.",
        "required_fields": ["actor_references", "pattern"],
        "frontend_status": "implemented_v1",
    },
    "set_material_instance_parameter": {
        "tool_id": "editor_set_material_instance_parameter",
        "title": "Set Material Instance Parameter",
        "risk_flags": "MEDIUM",
        "summary": "Set one scalar or vector parameter on a Material Instance after user confirmation.",
        "required_fields": ["material_instance_path", "parameter_name", "parameter_type", "value"],
        "frontend_status": "implemented_v1",
    },
    "set_material_instance_texture_parameter": {
        "tool_id": "editor_set_material_instance_texture_parameter",
        "title": "Set Material Instance Texture Parameter",
        "risk_flags": "MEDIUM",
        "summary": "Set one texture parameter on a Material Instance after user confirmation.",
        "required_fields": ["material_instance_path", "parameter_name", "texture_path"],
        "frontend_status": "implemented_v1",
    },
    "set_material_instance_static_switch": {
        "tool_id": "editor_set_material_instance_static_switch",
        "title": "Set Material Instance Static Switch",
        "risk_flags": "MEDIUM",
        "summary": "Set one static switch parameter on a Material Instance after user confirmation.",
        "required_fields": ["material_instance_path", "parameter_name", "value"],
        "frontend_status": "implemented_v1",
    },
}

OPERATION_GROUPS: dict[str, dict[str, Any]] = {
    "asset": {
        "title": "Asset Operations",
        "summary": "Rename, move, and apply safe asset settings.",
        "operation_types": [
            "rename_selected_asset",
            "apply_static_mesh_basic_settings",
            "batch_rename_assets",
            "move_assets",
            "duplicate_asset",
            "fixup_redirectors",
        ],
    },
    "blueprint": {
        "title": "Blueprint Operations",
        "summary": "Create Blueprint assets and perform bounded Blueprint graph edits.",
        "operation_types": [
            "create_blueprint_asset",
            "add_blueprint_variable",
            "add_blueprint_component",
            "create_blueprint_event_stub",
            "add_blueprint_node_template",
            "connect_blueprint_nodes",
            "compile_blueprint",
        ],
    },
    "umg": {
        "title": "UMG Operations",
        "summary": "Inspect and edit simple Widget Blueprint structure and properties.",
        "operation_types": [
            "add_umg_widget",
            "set_umg_widget_text",
            "set_umg_widget_layout",
            "set_umg_widget_visibility",
            "set_umg_widget_appearance",
            "set_umg_widget_brush",
            "set_umg_slot_layout_v2",
            "reparent_umg_widget",
            "duplicate_umg_widget",
            "delete_umg_widget",
        ],
    },
    "level": {
        "title": "Level Operations",
        "summary": "Place actors and adjust transforms in the current editor level.",
        "operation_types": [
            "place_actor_in_level",
            "select_level_actors",
            "set_actor_folder",
            "set_actor_tags",
            "set_actor_visibility",
            "set_actor_transform",
            "set_actor_metadata",
            "arrange_actors_pattern",
        ],
    },
    "material": {
        "title": "Material Operations",
        "summary": "Edit safe Material Instance parameters.",
        "operation_types": [
            "set_material_instance_parameter",
            "set_material_instance_texture_parameter",
            "set_material_instance_static_switch",
        ],
    },
}

READ_ONLY_INSPECTION_SPECS: dict[str, dict[str, Any]] = {
    "inspect_assets": {
        "group": "asset",
        "tool_id": "editor_inspect_assets",
        "title": "Inspect Assets",
        "summary": "Read asset names, types, paths, dependencies, referencers, and captured settings from Project Inventory.",
        "required_fields": [],
        "frontend_status": "backend_read_only_v1",
        "endpoint": "/api/v1/editor-operations/inspect/assets",
        "boundary": "Read-only inventory search; no Asset Registry mutation, loading, rename, move, delete, or save.",
    },
    "inspect_asset_detail": {
        "group": "asset",
        "tool_id": "editor_inspect_asset_detail",
        "title": "Inspect Asset Detail",
        "summary": "Read one asset detail record from Project Inventory by id, path, name, or query.",
        "required_fields": ["asset_id"],
        "frontend_status": "backend_read_only_v1",
        "endpoint": "/api/v1/editor-operations/inspect/asset-detail",
        "boundary": "Read-only inventory detail lookup; no package load, asset edit, or save.",
    },
    "inspect_level_actors": {
        "group": "level",
        "tool_id": "editor_inspect_level_actors",
        "title": "Inspect Level Actors",
        "summary": "Read current level actor labels, classes, transforms, folders, tags, and component summaries from Project Inventory.",
        "required_fields": [],
        "frontend_status": "backend_read_only_v1",
        "endpoint": "/api/v1/editor-operations/inspect/level-actors",
        "boundary": "Read-only inventory; no level streaming, World Partition editing, or Actor mutation.",
    },
    "inspect_level_actor_detail": {
        "group": "level",
        "tool_id": "editor_inspect_level_actor_detail",
        "title": "Inspect Level Actor Detail",
        "summary": "Read one level Actor detail record from Project Inventory by label, object name, path, or query.",
        "required_fields": ["actor_reference"],
        "frontend_status": "backend_read_only_v1",
        "endpoint": "/api/v1/editor-operations/inspect/level-actor-detail",
        "boundary": "Read-only inventory detail lookup; no Actor mutation, level save, or component edit.",
    },
    "inspect_material_instance_parameters": {
        "group": "material",
        "tool_id": "editor_inspect_material_instance_parameters",
        "title": "Inspect Material Instance Parameters",
        "summary": "Read scalar, vector, texture, and static switch parameter names and current values from Project Inventory.",
        "required_fields": ["material_instance_path"],
        "frontend_status": "backend_read_only_v1",
        "endpoint": "/api/v1/editor-operations/inspect/material-instance-parameters",
        "boundary": "Read-only inspection; parent Material graph editing remains out of scope.",
    },
    "inspect_material_instance_detail": {
        "group": "material",
        "tool_id": "editor_inspect_material_instance_detail",
        "title": "Inspect Material Instance Detail",
        "summary": "Read one Material Instance record from Project Inventory by path, name, object path, or query.",
        "required_fields": ["material_instance_path"],
        "frontend_status": "backend_read_only_v1",
        "endpoint": "/api/v1/editor-operations/inspect/material-instance-detail",
        "boundary": "Read-only inspection; no parameter mutation, parent Material graph edit, or package save.",
    },
}

OPERATION_ROADMAP: dict[str, dict[str, Any]] = {}


class EditorOperationValidationError(ValueError):
    def __init__(self, reason: str, details: dict[str, Any] | None = None):
        super().__init__(reason)
        self.reason = reason
        self.details = details or {}
