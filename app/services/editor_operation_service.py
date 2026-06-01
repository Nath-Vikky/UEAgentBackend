from __future__ import annotations

import math
import re
import uuid
from collections import Counter
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.audit import AuditLogModel
from app.db.models.proposal import ProposalModel
from app.db.repositories.audit_logs import create_audit_log
from app.db.repositories.proposals import create_proposal, get_proposal, save_proposal
from app.db.repositories.tasks import get_task, save_task
from app.observability.audit import build_audit_entry
from app.schemas.requests import (
    EditorOperationProposalRequest,
    EditorOperationResultRequest,
    UnifiedTaskRequest,
)
from app.utils.time import now_utc

EDITOR_OPERATION_PROTOCOL_VERSION = "editor_operation_bridge_v1"
EDITOR_OPERATION_PROPOSAL_TYPE = "editor_operation"
EDITOR_OPERATION_FOLLOW_UP_MATERIALIZATION_VERSION = "editor_operation_follow_up_materialization_v1"

_ASSET_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,63}$")
_CLASS_NAME_RE = re.compile(r"^[A-Za-z_/][A-Za-z0-9_./:]*$")
_PARAMETER_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_ ]{0,79}$")
_SAFE_TEXT_RE = re.compile(r"^[A-Za-z0-9_./:-]+$")

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
        "required_fields": ["blueprint_path", "graph_name", "source_node_id", "source_pin_name", "target_node_id", "target_pin_name"],
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
}

OPERATION_ROADMAP: dict[str, dict[str, Any]] = {
}


class EditorOperationValidationError(ValueError):
    def __init__(self, reason: str, details: dict[str, Any] | None = None):
        super().__init__(reason)
        self.reason = reason
        self.details = details or {}


class EditorOperationService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _operation_group(operation_type: str) -> str:
        for group_id, group in OPERATION_GROUPS.items():
            if operation_type in set(group["operation_types"]):
                return group_id
        return "misc"

    @staticmethod
    def supported_operations() -> dict[str, Any]:
        risk_counts = Counter(str(spec["risk_flags"]) for spec in OPERATION_SPECS.values())
        frontend_status_counts = Counter(str(spec["frontend_status"]) for spec in OPERATION_SPECS.values())
        group_counts = Counter(
            EditorOperationService._operation_group(operation_type)
            for operation_type in OPERATION_SPECS
        )
        read_only_group_counts = Counter(str(item["group"]) for item in READ_ONLY_INSPECTION_SPECS.values())
        read_only_status_counts = Counter(str(item["frontend_status"]) for item in READ_ONLY_INSPECTION_SPECS.values())
        roadmap_group_counts = Counter(str(item["group"]) for item in OPERATION_ROADMAP.values())
        roadmap_status_counts = Counter(str(item["frontend_status"]) for item in OPERATION_ROADMAP.values())
        groups = [
            {
                "group_id": group_id,
                "title": group["title"],
                "summary": group["summary"],
                "operation_count": sum(1 for item in group["operation_types"] if item in OPERATION_SPECS),
                "read_only_count": read_only_group_counts.get(group_id, 0),
                "roadmap_count": roadmap_group_counts.get(group_id, 0),
                "operation_types": [item for item in group["operation_types"] if item in OPERATION_SPECS],
                "read_only_operation_types": [
                    operation_type
                    for operation_type, item in READ_ONLY_INSPECTION_SPECS.items()
                    if item["group"] == group_id
                ],
                "roadmap_operation_types": [
                    operation_type
                    for operation_type, item in OPERATION_ROADMAP.items()
                    if item["group"] == group_id
                ],
            }
            for group_id, group in OPERATION_GROUPS.items()
        ]
        return {
            "protocol_version": EDITOR_OPERATION_PROTOCOL_VERSION,
            "proposal_type": EDITOR_OPERATION_PROPOSAL_TYPE,
            "transport": "http",
            "mcp_like": True,
            "summary": {
                "operation_count": len(OPERATION_SPECS),
                "implemented_frontend_count": frontend_status_counts.get("implemented_v1", 0),
                "risk_flag_counts": dict(risk_counts),
                "frontend_status_counts": dict(frontend_status_counts),
                "group_counts": dict(group_counts),
                "group_count": len(groups),
                "read_only_operation_count": len(READ_ONLY_INSPECTION_SPECS),
                "read_only_group_counts": dict(read_only_group_counts),
                "read_only_status_counts": dict(read_only_status_counts),
                "roadmap_operation_count": len(OPERATION_ROADMAP),
                "roadmap_group_counts": dict(roadmap_group_counts),
                "roadmap_status_counts": dict(roadmap_status_counts),
            },
            "safety_policy": {
                "side_effect_level": "confirmed_write",
                "llm_direct_execution": False,
                "requires_frontend_confirmation": True,
                "ue_plugin_executes_editor_api": True,
                "auto_execute_follow_ups": False,
                "auto_save": False,
            },
            "groups": groups,
            "items": [
                {
                    "operation_type": operation_type,
                    "group": EditorOperationService._operation_group(operation_type),
                    "tool_id": spec["tool_id"],
                    "title": spec["title"],
                    "summary": spec["summary"],
                    "risk_flags": spec["risk_flags"],
                    "required_fields": spec["required_fields"],
                    "frontend_status": spec["frontend_status"],
                    "side_effect_level": "confirmed_write",
                    "requires_confirmation": True,
                    "auto_save": False,
                    "result_contract_fields": EditorOperationService._expected_result_contract(operation_type)[
                        "operation_result_fields"
                    ],
                }
                for operation_type, spec in OPERATION_SPECS.items()
            ],
            "read_only_items": [
                {
                    "operation_type": operation_type,
                    "group": item["group"],
                    "tool_id": item["tool_id"],
                    "title": item["title"],
                    "summary": item["summary"],
                    "required_fields": item["required_fields"],
                    "frontend_status": item["frontend_status"],
                    "side_effect_level": "read_only",
                    "requires_confirmation": False,
                    "auto_save": False,
                    "proposal_enabled": False,
                    "endpoint": item["endpoint"],
                    "boundary": item["boundary"],
                }
                for operation_type, item in READ_ONLY_INSPECTION_SPECS.items()
            ],
            "roadmap_items": [
                {
                    "operation_type": operation_type,
                    "group": item["group"],
                    "title": item["title"],
                    "summary": item["summary"],
                    "required_fields": item["required_fields"],
                    "frontend_status": item["frontend_status"],
                    "side_effect_level": item["side_effect_level"],
                    "requires_confirmation": item["side_effect_level"] != "read_only",
                    "auto_save": False,
                    "proposal_enabled": False,
                    "boundary": item["boundary"],
                }
                for operation_type, item in OPERATION_ROADMAP.items()
            ],
        }

    @staticmethod
    def _proposal_payload(proposal: ProposalModel) -> dict:
        return {
            "proposal_id": proposal.proposal_id,
            "title": proposal.title,
            "proposal_type": proposal.proposal_type,
            "before_summary": proposal.before_summary,
            "after_summary": proposal.after_summary,
            "rationale": proposal.rationale,
            "risk_flags": proposal.risk_flags,
            "dry_run_preview": proposal.dry_run_preview_json,
            "display_hints": proposal.display_hints_json,
            "requires_confirmation": proposal.requires_confirmation,
            "confirmation": {
                "state": proposal.confirmation_state,
                "decision_endpoint": proposal.decision_endpoint,
            },
        }

    @staticmethod
    def _clean_text(value: Any, *, max_length: int = 1024) -> str:
        text = str(value or "").strip()
        return text[:max_length]

    @staticmethod
    def _query_text(request: UnifiedTaskRequest) -> str:
        return str(
            request.payload.get("user_query")
            or request.payload.get("requirement_description")
            or (request.session.messages[-1].content if request.session.messages else "")
            or ""
        ).strip()

    @staticmethod
    def _extract_asset_name_from_text(text: str, default_name: str) -> str:
        for pattern in (
            r"\b(BP_[A-Za-z][A-Za-z0-9_]{1,63})\b",
            r"\b(SM_[A-Za-z][A-Za-z0-9_]{1,63})\b",
            r"\b(L_[A-Za-z][A-Za-z0-9_]{1,63})\b",
            r"(?:命名为|改成|改为|叫做|叫|named|name it|rename to|to)\s*([A-Za-z][A-Za-z0-9_]{1,63})",
        ):
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return default_name

    @staticmethod
    def _extract_duplicate_asset_new_name_from_text(text: str, source_asset_path: str | None) -> str:
        source_name = EditorOperationService._asset_name_from_path(source_asset_path or "")
        for pattern in (
            r"(?:duplicate|copy|clone)\s+(?:asset\s+)?(?:/[A-Za-z0-9_./-]+\s+)?(?:as|to|called|named|name it)\s+([A-Za-z][A-Za-z0-9_]{1,63})",
            r"(?:as|to|called|named|name it)\s+([A-Za-z][A-Za-z0-9_]{1,63})",
            r"(?:复制|拷贝|克隆).{0,32}(?:为|成|叫|命名为)\s*([A-Za-z][A-Za-z0-9_]{1,63})",
        ):
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1)
                if not source_name or candidate.lower() != source_name.lower():
                    return candidate
        return f"{source_name}_Copy" if source_name else "DuplicatedAsset"

    @staticmethod
    def _detect_redirector_folder_from_request(request: UnifiedTaskRequest, query_text: str) -> str:
        explicit_folder = str(
            request.payload.get("folder_path")
            or request.payload.get("target_folder")
            or request.payload.get("asset_folder")
            or ""
        ).strip()
        if explicit_folder:
            return explicit_folder
        for path in EditorOperationService._extract_unreal_paths_from_text(query_text):
            if path.startswith("/Game/"):
                leaf = path.rsplit("/", 1)[-1]
                if "." in leaf or leaf.startswith(("BP_", "WBP_", "SM_", "SK_", "MI_", "M_", "T_", "DA_", "ABP_")):
                    return path.rsplit("/", 1)[0]
                return path
        selected_asset = EditorOperationService._selected_asset_path(request)
        if selected_asset:
            return selected_asset.rsplit("/", 1)[0]
        return ""

    @staticmethod
    def _extract_blueprint_variable_name_from_text(text: str) -> str:
        for pattern in (
            r"(?:variable|var|property)\s+([A-Za-z][A-Za-z0-9_]{1,63})",
            r"(?:set|get)\s+([A-Za-z][A-Za-z0-9_]{1,63})",
            r"(?:变量|属性)\s*([A-Za-z][A-Za-z0-9_]{1,63})",
        ):
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return ""

    @staticmethod
    def _extract_blueprint_function_name_from_text(text: str) -> str:
        for pattern in (
            r"(?:function|func)\s+([A-Za-z][A-Za-z0-9_]{1,63})",
            r"(?:call|invoke|execute)\s+([A-Za-z][A-Za-z0-9_]{1,63})",
            r"(?:函数|方法)\s*([A-Za-z][A-Za-z0-9_]{1,63})",
            r"(?:调用|执行)\s*([A-Za-z][A-Za-z0-9_]{1,63})",
        ):
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return ""

    @staticmethod
    def _extract_delay_seconds_from_text(text: str, default: float = 1.0) -> float:
        for pattern in (
            r"(?:delay|after|wait)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:s|sec|second|seconds)?",
            r"([0-9]+(?:\.[0-9]+)?)\s*(?:s|sec|second|seconds)\s*(?:delay|later|wait)?",
            r"(?:延迟|等待)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:秒)?",
            r"([0-9]+(?:\.[0-9]+)?)\s*秒\s*(?:后|以后|之后)?",
        ):
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return float(match.group(1))
        return default

    @staticmethod
    def _detect_blueprint_graph_name_from_request(
        request: UnifiedTaskRequest,
        query_text: str,
    ) -> str:
        explicit_graph = str(request.payload.get("graph_name") or "").strip()
        if explicit_graph:
            return explicit_graph

        compact = query_text.replace("_", "").replace(" ", "").lower()
        query_lower = query_text.lower()
        if any(
            token in compact or token in query_lower or token in query_text
            for token in (
                "constructionscript",
                "userconstructionscript",
                "construction script",
                "构造脚本",
            )
        ):
            return "ConstructionScript"
        if any(
            token in compact or token in query_lower or token in query_text
            for token in ("eventgraph", "event graph", "事件图表", "事件图")
        ):
            return "EventGraph"

        for pattern in (
            r"(?:graph|图表|图谱)\s*[:：]?\s*([A-Za-z][A-Za-z0-9_]{1,63})",
            r"\b([A-Za-z][A-Za-z0-9_]{1,63})\s+(?:graph)\b",
        ):
            match = re.search(pattern, query_text, flags=re.IGNORECASE)
            if match:
                graph_name = match.group(1)
                if graph_name.lower() not in {"blueprint", "event", "node"}:
                    return graph_name
        return "EventGraph"

    @staticmethod
    def _detect_blueprint_entry_event_from_request(
        request: UnifiedTaskRequest,
        query_text: str,
        *,
        default: str = "",
    ) -> str:
        explicit_event = str(request.payload.get("entry_event") or "").strip()
        if explicit_event:
            return explicit_event
        compact = query_text.replace("_", "").replace(" ", "").lower()
        query_lower = query_text.lower()
        if any(
            token in compact or token in query_text
            for token in ("beginplay", "eventbeginplay", "receivebeginplay", "开始播放")
        ):
            return "BeginPlay"
        if any(
            token in compact or token in query_lower or token in query_text
            for token in (
                "actorbeginoverlap",
                "beginoverlap",
                "begin overlap",
                "overlap begin",
                "\u5f00\u59cb\u91cd\u53e0",
                "\u8fdb\u5165\u91cd\u53e0",
                "\u5f00\u59cb\u78b0\u649e",
            )
        ):
            return "ActorBeginOverlap"
        if any(
            token in compact or token in query_lower or token in query_text
            for token in (
                "actorendoverlap",
                "endoverlap",
                "end overlap",
                "overlap end",
                "\u7ed3\u675f\u91cd\u53e0",
                "\u79bb\u5f00\u91cd\u53e0",
                "\u7ed3\u675f\u78b0\u649e",
            )
        ):
            return "ActorEndOverlap"
        return default

    @staticmethod
    def _detect_unconnected_blueprint_node_intent(query_text: str) -> bool:
        query_lower = query_text.lower()
        compact = query_lower.replace("_", "").replace("-", "").replace(" ", "")
        return any(
            token in query_lower or token in compact
            for token in (
                "unconnected",
                "unlinked",
                "standalone",
                "without connection",
                "do not connect",
                "dont connect",
                "no link",
                "no connection",
                "\u4e0d\u8fde\u63a5",
                "\u4e0d\u8fde\u7ebf",
                "\u4ec5\u521b\u5efa",
                "\u53ea\u521b\u5efa",
                "\u4e0d\u8981\u8fde",
            )
        )

    @staticmethod
    def _detect_blueprint_event_name_from_request(
        request: UnifiedTaskRequest,
        query_text: str,
    ) -> str:
        explicit_event = str(request.payload.get("event_name") or "").strip()
        if explicit_event:
            return explicit_event

        compact = query_text.replace("_", "").replace(" ", "").lower()
        query_lower = query_text.lower()
        if any(
            token in compact or token in query_lower or token in query_text
            for token in (
                "actorbeginoverlap",
                "beginoverlap",
                "begin overlap",
                "overlap begin",
                "开始重叠",
                "进入重叠",
                "开始碰撞",
            )
        ):
            return "ActorBeginOverlap"
        if any(
            token in compact or token in query_lower or token in query_text
            for token in (
                "actorendoverlap",
                "endoverlap",
                "end overlap",
                "overlap end",
                "结束重叠",
                "离开重叠",
                "结束碰撞",
            )
        ):
            return "ActorEndOverlap"
        if any(
            token in compact or token in query_lower or token in query_text
            for token in ("beginplay", "eventbeginplay", "receivebeginplay", "开始播放")
        ):
            return "BeginPlay"
        if re.search(r"\btick\b", query_lower) is not None or any(
            token in query_text for token in ("每帧", "帧更新")
        ):
            return "Tick"
        return ""

    @staticmethod
    def _selected_asset_path(request: UnifiedTaskRequest) -> str | None:
        selected_assets = EditorOperationService._candidate_asset_paths(request)
        if selected_assets:
            return selected_assets[0]
        return None

    @staticmethod
    def _detect_asset_path_from_request(
        request: UnifiedTaskRequest,
        query_text: str,
        context_bundle: dict[str, Any] | None = None,
    ) -> str | None:
        explicit_path = str(
            request.payload.get("source_asset_path")
            or request.payload.get("asset_path")
            or request.payload.get("source_path")
            or ""
        ).strip()
        if explicit_path:
            return explicit_path
        paths = EditorOperationService._extract_unreal_paths_from_text(query_text)
        if paths:
            return paths[0]
        selected_asset = EditorOperationService._selected_asset_path(request)
        if selected_asset:
            return selected_asset
        named_candidate = EditorOperationService._find_named_candidate_path(
            request,
            query_text,
            prefixes=("BP_", "WBP_", "SM_", "SK_", "MI_", "M_", "T_", "DA_", "ABP_"),
        )
        if named_candidate:
            return named_candidate
        return EditorOperationService._find_inventory_candidate_path(
            context_bundle=context_bundle,
            query_text=query_text,
            accepted_type_tokens=(
                "asset",
                "blueprint",
                "widgetblueprint",
                "widget blueprint",
                "staticmesh",
                "static mesh",
                "skeletalmesh",
                "skeletal mesh",
                "material",
                "materialinstance",
                "material instance",
                "texture",
                "texture2d",
                "dataasset",
                "animationblueprint",
            ),
            prefixes=("BP_", "WBP_", "SM_", "SK_", "MI_", "M_", "T_", "DA_", "ABP_"),
        )

    @staticmethod
    def _candidate_asset_paths(request: UnifiedTaskRequest) -> list[str]:
        paths: list[str] = []
        for raw_path in list(request.context.selected_assets or []):
            path = str(raw_path or "").strip()
            if path:
                paths.append(path)
        asset_items = request.payload.get("asset_items") or request.payload.get("assets") or []
        if isinstance(asset_items, list):
            for first in asset_items:
                path = ""
                if isinstance(first, dict):
                    path = str(first.get("asset_path") or first.get("package_path") or "")
                else:
                    path = str(first or "")
                path = path.strip()
                if path and path not in paths:
                    paths.append(path)
        return paths

    @staticmethod
    def _extract_unreal_path_from_text(text: str) -> str | None:
        match = re.search(r"(/Game/[A-Za-z0-9_./-]+)", text)
        if not match:
            return None
        return match.group(1).rstrip(".,;:，。；：)）]")

    @staticmethod
    def _extract_unreal_paths_from_text(text: str) -> list[str]:
        paths: list[str] = []
        for match in re.finditer(r"(/Game/[A-Za-z0-9_./-]+)", text):
            path = match.group(1).rstrip(".,;:)]}")
            if path and path not in paths:
                paths.append(path)
        return paths

    @staticmethod
    def _asset_path_to_generated_class_path(asset_path: str) -> str:
        path = str(asset_path or "").strip().replace("\\", "/")
        if not path:
            return path
        if path.startswith("/Script/"):
            return path
        if path.endswith("_C") and "." in path:
            return path
        if path.endswith(".uasset"):
            path = path[: -len(".uasset")]
        if "." in path and path.startswith("/Game/"):
            package_path, object_name = path.rsplit(".", 1)
            if object_name.endswith("_C"):
                return path
            if package_path.endswith("/" + object_name):
                path = package_path
            else:
                return f"{package_path}.{object_name}_C"
        if path.startswith("/Game/"):
            asset_name = path.rstrip("/").rsplit("/", 1)[-1]
            return f"{path}.{asset_name}_C"
        return path

    @staticmethod
    def _asset_name_from_path(path: str) -> str:
        clean_path = str(path or "").rstrip("/")
        if "." in clean_path:
            clean_path = clean_path.rsplit(".", 1)[-1]
        return clean_path.rsplit("/", 1)[-1]

    @staticmethod
    def _find_named_candidate_path(request: UnifiedTaskRequest, query_text: str, *, prefixes: tuple[str, ...]) -> str | None:
        candidates = EditorOperationService._candidate_asset_paths(request)
        query_lower = query_text.lower()
        for path in candidates:
            asset_name = EditorOperationService._asset_name_from_path(path)
            if asset_name and asset_name.lower() in query_lower:
                return path
        for prefix in prefixes:
            match = re.search(rf"\b({re.escape(prefix)}[A-Za-z][A-Za-z0-9_]{{1,63}})\b", query_text, flags=re.IGNORECASE)
            if not match:
                continue
            target_name = match.group(1).lower()
            for path in candidates:
                if EditorOperationService._asset_name_from_path(path).lower() == target_name:
                    return path
        return None

    @staticmethod
    def _references_recent_target(query_text: str) -> bool:
        query_lower = query_text.lower()
        return any(
            token in query_lower or token in query_text
            for token in (
                "that",
                "same",
                "previous",
                "last",
                "recent",
                "again",
                "it",
                "刚才",
                "刚刚",
                "上一个",
                "上次",
                "那个",
                "这个",
                "同一个",
                "再",
            )
        )

    @staticmethod
    def _recent_editor_operations(context_bundle: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not isinstance(context_bundle, dict):
            return []
        items: list[dict[str, Any]] = []
        active_operation = (
            (context_bundle.get("active_context") or {})
            .get("editor_operation", {})
            .get("last_successful")
        )
        if isinstance(active_operation, dict):
            items.append(active_operation)
        for item in list(context_bundle.get("recent_editor_operations") or []):
            if isinstance(item, dict):
                items.append(item)

        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            key = str(item.get("proposal_id") or item.get("task_id") or len(seen))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    @staticmethod
    def _recent_editor_operation_value(
        *,
        context_bundle: dict[str, Any] | None,
        operation_types: set[str],
        keys: tuple[str, ...],
    ) -> Any | None:
        for item in EditorOperationService._recent_editor_operations(context_bundle):
            if not item.get("success", True):
                continue
            if operation_types and str(item.get("operation_type") or "") not in operation_types:
                continue
            for source_name in ("target", "operation_payload", "result"):
                source = item.get(source_name)
                if not isinstance(source, dict):
                    continue
                for key in keys:
                    value = source.get(key)
                    if value not in (None, "", [], {}):
                        return value
        return None

    @staticmethod
    def _inventory_actor_reference(
        context_bundle: dict[str, Any] | None,
        query_text: str,
    ) -> str | None:
        if not context_bundle:
            return None
        inventory_context = context_bundle.get("project_inventory_context")
        if not isinstance(inventory_context, dict):
            return None
        candidates: list[dict[str, Any]] = []
        for key in ("query_candidates", "top_level_actors"):
            values = inventory_context.get(key) or []
            if isinstance(values, list):
                candidates.extend(item for item in values if isinstance(item, dict))
        query_lower = query_text.lower()
        for item in candidates:
            if item.get("kind") not in {None, "", "level_actor"}:
                continue
            for key in ("actor_label", "actor_name", "actor_path"):
                value = str(item.get(key) or "").strip()
                if value and value.lower() in query_lower:
                    return value
        return None

    @staticmethod
    def _inventory_actor_references(
        context_bundle: dict[str, Any] | None,
        query_text: str,
    ) -> list[str]:
        if not context_bundle:
            return []
        inventory_context = context_bundle.get("project_inventory_context")
        if not isinstance(inventory_context, dict):
            return []
        candidates: list[dict[str, Any]] = []
        for key in ("query_candidates", "top_level_actors"):
            values = inventory_context.get(key) or []
            if isinstance(values, list):
                candidates.extend(item for item in values if isinstance(item, dict))
        query_lower = query_text.lower()
        references: list[str] = []
        for item in candidates:
            if item.get("kind") not in {None, "", "level_actor"}:
                continue
            label = str(item.get("actor_label") or "").strip()
            name = str(item.get("actor_name") or "").strip()
            path = str(item.get("actor_path") or "").strip()
            mentioned = any(value and value.lower() in query_lower for value in (label, name, path))
            if mentioned:
                references.append(label or name or path)
        return EditorOperationService._dedupe_strings(references)

    @staticmethod
    def _dedupe_strings(values: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = str(value or "").strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(normalized)
        return deduped

    @staticmethod
    def _detect_actor_reference_from_request(
        request: UnifiedTaskRequest,
        query_text: str,
        context_bundle: dict[str, Any] | None,
    ) -> str | None:
        for key in ("actor_reference", "actor_label", "actor_name"):
            explicit_value = str(request.payload.get(key) or "").strip()
            if explicit_value:
                return explicit_value

        editor_state = dict(request.context.editor_state or {})
        selected_actors = editor_state.get("selected_actors") or request.payload.get("selected_actors") or []
        if isinstance(selected_actors, list) and selected_actors:
            first = selected_actors[0]
            if isinstance(first, dict):
                for key in ("actor_label", "actor_name", "name", "label"):
                    value = str(first.get(key) or "").strip()
                    if value:
                        return value
            value = str(first or "").strip()
            if value:
                return value

        inventory_actor = EditorOperationService._inventory_actor_reference(context_bundle, query_text)
        if inventory_actor:
            return inventory_actor

        if EditorOperationService._references_recent_target(query_text):
            recent_actor = EditorOperationService._recent_editor_operation_value(
                context_bundle=context_bundle,
                operation_types={"place_actor_in_level", "set_actor_transform", "set_actor_metadata"},
                keys=("actor_reference", "actor_label", "actor_name"),
            )
            if recent_actor:
                return str(recent_actor)
        return None

    @staticmethod
    def _detect_actor_references_from_request(
        request: UnifiedTaskRequest,
        query_text: str,
        context_bundle: dict[str, Any] | None,
    ) -> list[str]:
        explicit_references = request.payload.get("actor_references")
        if isinstance(explicit_references, list):
            return EditorOperationService._dedupe_strings([str(item) for item in explicit_references])

        references: list[str] = []
        editor_state = dict(request.context.editor_state or {})
        selected_actors = editor_state.get("selected_actors") or request.payload.get("selected_actors") or []
        if isinstance(selected_actors, list):
            for item in selected_actors:
                if isinstance(item, dict):
                    for key in ("actor_label", "actor_name", "name", "label"):
                        value = str(item.get(key) or "").strip()
                        if value:
                            references.append(value)
                            break
                else:
                    value = str(item or "").strip()
                    if value:
                        references.append(value)

        references.extend(EditorOperationService._inventory_actor_references(context_bundle, query_text))
        references.extend(
            match.group(1)
            for match in re.finditer(r"\b([A-Za-z][A-Za-z0-9_]*_\d+)\b", query_text)
            if not match.group(1).lower().startswith(("x_", "y_", "z_"))
        )
        return EditorOperationService._dedupe_strings(references)

    @staticmethod
    def _detect_arrange_pattern_from_request(request: UnifiedTaskRequest, query_text: str) -> dict[str, Any]:
        pattern_payload = request.payload.get("pattern")
        if isinstance(pattern_payload, dict):
            return dict(pattern_payload)

        query_lower = query_text.lower()
        pattern: dict[str, Any] = {}
        if "circle" in query_lower or "圆" in query_text or "环" in query_text:
            pattern["type"] = "circle"
        elif "grid" in query_lower or "矩阵" in query_text or "网格" in query_text:
            pattern["type"] = "grid"
        else:
            pattern["type"] = "line"

        spacing_match = re.search(r"(?:spacing|space|间距)\s*(?:to|=|:)?\s*(-?\d+(?:\.\d+)?)", query_text, flags=re.IGNORECASE)
        if spacing_match:
            pattern["spacing"] = float(spacing_match.group(1))
        columns_match = re.search(r"(?:columns?|cols?|列)\s*(?:to|=|:)?\s*(\d+)", query_text, flags=re.IGNORECASE)
        if columns_match:
            pattern["columns"] = int(columns_match.group(1))
        radius_match = re.search(r"(?:radius|半径)\s*(?:to|=|:)?\s*(-?\d+(?:\.\d+)?)", query_text, flags=re.IGNORECASE)
        if radius_match:
            pattern["radius"] = float(radius_match.group(1))
        if "axis y" in query_lower or "along y" in query_lower or "y axis" in query_lower:
            pattern["axis"] = "y"
        elif "axis x" in query_lower or "along x" in query_lower or "x axis" in query_lower:
            pattern["axis"] = "x"
        origin = EditorOperationService._extract_transform_from_text(query_text).get("location")
        if origin:
            pattern["origin"] = origin
        return pattern

    @staticmethod
    def _directional_delta_from_text(query_text: str) -> dict[str, dict[str, float]]:
        direction_specs = (
            ("right", "y", 1.0),
            ("left", "y", -1.0),
            ("forward", "x", 1.0),
            ("backward", "x", -1.0),
            ("back", "x", -1.0),
            ("up", "z", 1.0),
            ("down", "z", -1.0),
            ("往右", "y", 1.0),
            ("向右", "y", 1.0),
            ("往左", "y", -1.0),
            ("向左", "y", -1.0),
            ("往前", "x", 1.0),
            ("向前", "x", 1.0),
            ("往后", "x", -1.0),
            ("向后", "x", -1.0),
            ("向上", "z", 1.0),
            ("往上", "z", 1.0),
            ("向下", "z", -1.0),
            ("往下", "z", -1.0),
        )
        query_lower = query_text.lower()
        for token, axis, sign in direction_specs:
            token_index = query_lower.find(token) if token.isascii() else query_text.find(token)
            if token_index < 0:
                continue
            window = query_text[token_index : token_index + 48]
            match = re.search(r"(-?\d+(?:\.\d+)?)", window)
            if not match:
                continue
            location = {"x": 0.0, "y": 0.0, "z": 0.0}
            location[axis] = float(match.group(1)) * sign
            return {"location": location}
        return {}

    @staticmethod
    def _extract_actor_transform_update_from_text(query_text: str) -> tuple[str, dict[str, Any]]:
        query_lower = query_text.lower()
        absolute_transform = EditorOperationService._extract_transform_from_text(query_text)
        if absolute_transform:
            return ("absolute", absolute_transform)

        scale_match = re.search(
            r"(?:set\s+scale|scale|放大|缩放)\s*(?:to|为|到)?\s*(-?\d+(?:\.\d+)?)",
            query_text,
            flags=re.IGNORECASE,
        )
        if scale_match:
            scale = float(scale_match.group(1))
            return ("absolute", {"scale": {"x": scale, "y": scale, "z": scale}})

        delta_transform = EditorOperationService._directional_delta_from_text(query_text)
        if delta_transform:
            return ("delta", delta_transform)

        rotation_match = re.search(
            r"(?:rotate|turn|旋转)\s*(?:yaw|around\s+z|z)?\s*(?:by|to|为|到)?\s*(-?\d+(?:\.\d+)?)",
            query_text,
            flags=re.IGNORECASE,
        )
        if rotation_match:
            yaw_delta = float(rotation_match.group(1))
            mode = "absolute" if any(token in query_lower or token in query_text for token in (" to ", "set", "为", "到")) else "delta"
            return (mode, {"rotation": {"pitch": 0.0, "yaw": yaw_delta, "roll": 0.0}})

        return ("absolute", {})

    @staticmethod
    def _inventory_asset_candidates(context_bundle: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not isinstance(context_bundle, dict):
            return []
        inventory_context = context_bundle.get("project_inventory_context")
        if not isinstance(inventory_context, dict):
            return []
        candidates: list[dict[str, Any]] = []
        for key in ("query_candidates", "selected_assets", "top_assets"):
            for item in list(inventory_context.get(key) or []):
                if isinstance(item, dict):
                    candidates.append(item)

        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in candidates:
            path = str(item.get("asset_path") or "").strip()
            name = str(item.get("asset_name") or "").strip()
            key = (path or name).lower()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    @staticmethod
    def _find_inventory_candidate_path(
        *,
        context_bundle: dict[str, Any] | None,
        query_text: str,
        accepted_type_tokens: tuple[str, ...],
        prefixes: tuple[str, ...],
        require_prefix_for_generic_material: bool = False,
    ) -> str | None:
        query_lower = query_text.lower()
        explicit_names: set[str] = set()
        for prefix in prefixes:
            for match in re.findall(
                rf"\b({re.escape(prefix)}[A-Za-z][A-Za-z0-9_]{{1,63}})\b",
                query_text,
                flags=re.IGNORECASE,
            ):
                explicit_names.add(match.lower())

        for item in EditorOperationService._inventory_asset_candidates(context_bundle):
            path = str(item.get("asset_path") or "").strip()
            name = str(item.get("asset_name") or EditorOperationService._asset_name_from_path(path)).strip()
            if not path or not name:
                continue
            name_lower = name.lower()
            path_lower = path.lower()
            leaf_lower = EditorOperationService._asset_name_from_path(path).lower()
            mentioned = (
                name_lower in query_lower
                or leaf_lower in query_lower
                or path_lower in query_lower
                or name_lower in explicit_names
                or leaf_lower in explicit_names
            )
            if not mentioned:
                continue

            asset_type = str(item.get("asset_type") or "").replace(" ", "").lower()
            has_prefix = any(name_lower.startswith(prefix.lower()) for prefix in prefixes)
            type_matches = any(token.replace(" ", "").lower() in asset_type for token in accepted_type_tokens)
            if accepted_type_tokens and not (type_matches or has_prefix):
                continue
            if require_prefix_for_generic_material and asset_type == "material" and not has_prefix:
                continue
            return path
        return None

    @staticmethod
    def _extract_actor_label_from_text(text: str) -> str | None:
        match = re.search(
            r"(?:label|name|命名为|命名|叫做|叫|名称为)\s*[:：]?\s*([A-Za-z][A-Za-z0-9_]{1,63})",
            text,
            flags=re.IGNORECASE,
        )
        return match.group(1) if match else None

    @staticmethod
    def _extract_transform_from_text(text: str) -> dict[str, Any]:
        transform: dict[str, Any] = {}
        location_match = re.search(
            r"(?:位置|坐标|location|loc|at)\s*[:：=]?\s*\(?\s*(-?\d+(?:\.\d+)?)\s*[,， ]\s*(-?\d+(?:\.\d+)?)\s*[,， ]\s*(-?\d+(?:\.\d+)?)",
            text,
            flags=re.IGNORECASE,
        )
        if location_match:
            transform["location"] = {
                "x": float(location_match.group(1)),
                "y": float(location_match.group(2)),
                "z": float(location_match.group(3)),
            }
        else:
            xyz_matches = {
                axis.lower(): float(value)
                for axis, value in re.findall(r"\b([XYZxyz])\s*[:=]\s*(-?\d+(?:\.\d+)?)", text)
            }
            if {"x", "y", "z"}.issubset(xyz_matches):
                transform["location"] = {"x": xyz_matches["x"], "y": xyz_matches["y"], "z": xyz_matches["z"]}

        rotation_match = re.search(
            r"(?:旋转|rotation|rot)\s*[:：=]?\s*\(?\s*(-?\d+(?:\.\d+)?)\s*[,， ]\s*(-?\d+(?:\.\d+)?)\s*[,， ]\s*(-?\d+(?:\.\d+)?)",
            text,
            flags=re.IGNORECASE,
        )
        if rotation_match:
            transform["rotation"] = {
                "pitch": float(rotation_match.group(1)),
                "yaw": float(rotation_match.group(2)),
                "roll": float(rotation_match.group(3)),
            }

        scale_match = re.search(
            r"(?:缩放|scale)\s*[:：=]?\s*\(?\s*(-?\d+(?:\.\d+)?)(?:\s*[,， ]\s*(-?\d+(?:\.\d+)?)\s*[,， ]\s*(-?\d+(?:\.\d+)?))?",
            text,
            flags=re.IGNORECASE,
        )
        if scale_match:
            x_value = float(scale_match.group(1))
            y_value = float(scale_match.group(2)) if scale_match.group(2) else x_value
            z_value = float(scale_match.group(3)) if scale_match.group(3) else x_value
            transform["scale"] = {"x": x_value, "y": y_value, "z": z_value}
        return transform

    @staticmethod
    def _detect_actor_class_from_request(
        request: UnifiedTaskRequest,
        query_text: str,
        query_lower: str,
        context_bundle: dict[str, Any] | None = None,
    ) -> str | None:
        explicit_class = str(request.payload.get("actor_class") or "").strip()
        if explicit_class:
            return explicit_class

        explicit_path = EditorOperationService._extract_unreal_path_from_text(query_text)
        if explicit_path and ("bp_" in explicit_path.lower() or explicit_path.lower().endswith("_c")):
            return EditorOperationService._asset_path_to_generated_class_path(explicit_path)

        named_candidate = EditorOperationService._find_named_candidate_path(request, query_text, prefixes=("BP_",))
        if named_candidate:
            return EditorOperationService._asset_path_to_generated_class_path(named_candidate)

        inventory_candidate = EditorOperationService._find_inventory_candidate_path(
            context_bundle=context_bundle,
            query_text=query_text,
            accepted_type_tokens=("blueprint",),
            prefixes=("BP_",),
        )
        if inventory_candidate:
            return EditorOperationService._asset_path_to_generated_class_path(inventory_candidate)

        if EditorOperationService._references_recent_target(query_text):
            recent_actor_class = EditorOperationService._recent_editor_operation_value(
                context_bundle=context_bundle,
                operation_types={"place_actor_in_level"},
                keys=("actor_class",),
            )
            if recent_actor_class:
                return str(recent_actor_class)

        selected_asset = EditorOperationService._selected_asset_path(request)
        if selected_asset and ("bp_" in selected_asset.lower() or "blueprint" in query_lower or "蓝图" in query_text):
            return EditorOperationService._asset_path_to_generated_class_path(selected_asset)

        if "point light" in query_lower or "pointlight" in query_lower or "点光" in query_text:
            return "/Script/Engine.PointLight"
        if "spot light" in query_lower or "spotlight" in query_lower or "聚光" in query_text:
            return "/Script/Engine.SpotLight"
        if "camera" in query_lower or "相机" in query_text:
            return "/Script/Engine.CameraActor"
        if "actor" in query_lower:
            return "/Script/Engine.Actor"
        return None

    @staticmethod
    def _detect_material_path_from_request(
        request: UnifiedTaskRequest,
        query_text: str,
        context_bundle: dict[str, Any] | None = None,
    ) -> str | None:
        explicit_path = str(request.payload.get("material_instance_path") or "").strip()
        if explicit_path:
            return explicit_path
        text_paths = EditorOperationService._extract_unreal_paths_from_text(query_text)
        for path in text_paths:
            asset_name = EditorOperationService._asset_name_from_path(path)
            if asset_name.lower().startswith("mi_") or "/materials/" in path.lower():
                return path
        if len(text_paths) == 1:
            asset_name = EditorOperationService._asset_name_from_path(text_paths[0])
            if not asset_name.lower().startswith(("t_", "tx_")):
                return text_paths[0]
        named_candidate = EditorOperationService._find_named_candidate_path(request, query_text, prefixes=("MI_",))
        if named_candidate:
            return named_candidate
        inventory_candidate = EditorOperationService._find_inventory_candidate_path(
            context_bundle=context_bundle,
            query_text=query_text,
            accepted_type_tokens=("materialinstance", "material instance"),
            prefixes=("MI_",),
            require_prefix_for_generic_material=True,
        )
        if inventory_candidate:
            return inventory_candidate
        selected_asset = EditorOperationService._selected_asset_path(request)
        if selected_asset and re.search(r"(^|[/._])MI_[A-Za-z0-9_]+", selected_asset):
            return selected_asset
        if EditorOperationService._references_recent_target(query_text):
            recent_material_path = EditorOperationService._recent_editor_operation_value(
                context_bundle=context_bundle,
                operation_types={
                    "set_material_instance_parameter",
                    "set_material_instance_texture_parameter",
                    "set_material_instance_static_switch",
                },
                keys=("material_instance_path", "asset_path", "final_asset_path"),
            )
            if recent_material_path:
                return str(recent_material_path)
        return None

    @staticmethod
    def _detect_texture_path_from_request(
        request: UnifiedTaskRequest,
        query_text: str,
        context_bundle: dict[str, Any] | None = None,
    ) -> str | None:
        explicit_path = str(
            request.payload.get("texture_path")
            or request.payload.get("texture_asset_path")
            or request.payload.get("texture")
            or ""
        ).strip()
        if explicit_path:
            return explicit_path

        named_candidate = EditorOperationService._find_named_candidate_path(
            request,
            query_text,
            prefixes=("T_", "TX_"),
        )
        if named_candidate:
            return named_candidate

        inventory_candidate = EditorOperationService._find_inventory_candidate_path(
            context_bundle=context_bundle,
            query_text=query_text,
            accepted_type_tokens=("texture", "texture2d"),
            prefixes=("T_", "TX_"),
        )
        if inventory_candidate:
            return inventory_candidate

        for selected_asset in EditorOperationService._candidate_asset_paths(request):
            if re.search(r"(^|[/._])(T_|TX_)[A-Za-z0-9_]+", selected_asset):
                return selected_asset

        for path in EditorOperationService._extract_unreal_paths_from_text(query_text):
            asset_name = EditorOperationService._asset_name_from_path(path)
            if asset_name.lower().startswith(("t_", "tx_")) or "texture" in path.lower():
                return path
        return None

    @staticmethod
    def _detect_material_resource_path_from_request(
        request: UnifiedTaskRequest,
        query_text: str,
        context_bundle: dict[str, Any] | None = None,
    ) -> str | None:
        brush = request.payload.get("brush") if isinstance(request.payload.get("brush"), dict) else {}
        explicit_path = str(
            brush.get("material_path")
            or brush.get("resource_path")
            or request.payload.get("material_path")
            or ""
        ).strip()
        if explicit_path:
            return explicit_path

        for path in EditorOperationService._extract_unreal_paths_from_text(query_text):
            asset_name = EditorOperationService._asset_name_from_path(path)
            if asset_name.lower().startswith(("m_", "mi_")) or "/materials/" in path.lower():
                return path

        named_candidate = EditorOperationService._find_named_candidate_path(
            request,
            query_text,
            prefixes=("MI_", "M_"),
        )
        if named_candidate:
            return named_candidate

        inventory_candidate = EditorOperationService._find_inventory_candidate_path(
            context_bundle=context_bundle,
            query_text=query_text,
            accepted_type_tokens=("material", "materialinstance", "material instance"),
            prefixes=("MI_", "M_"),
        )
        if inventory_candidate:
            return inventory_candidate

        for selected_asset in EditorOperationService._candidate_asset_paths(request):
            if re.search(r"(^|[/._])(MI_|M_)[A-Za-z0-9_]+", selected_asset):
                return selected_asset
        return None

    @staticmethod
    def _detect_input_action_path_from_request(
        request: UnifiedTaskRequest,
        query_text: str,
        context_bundle: dict[str, Any] | None = None,
    ) -> str | None:
        explicit_path = str(
            request.payload.get("input_action_path")
            or request.payload.get("input_action")
            or request.payload.get("input_action_asset")
            or ""
        ).strip()
        if explicit_path:
            return explicit_path

        for path in EditorOperationService._extract_unreal_paths_from_text(query_text):
            asset_name = EditorOperationService._asset_name_from_path(path)
            if asset_name.lower().startswith("ia_") or "/input/" in path.lower():
                return path

        named_candidate = EditorOperationService._find_named_candidate_path(
            request,
            query_text,
            prefixes=("IA_",),
        )
        if named_candidate and EditorOperationService._asset_name_from_path(named_candidate).lower().startswith("ia_"):
            return named_candidate

        inventory_candidate = EditorOperationService._find_inventory_candidate_path(
            context_bundle=context_bundle,
            query_text=query_text,
            accepted_type_tokens=("inputaction", "input action"),
            prefixes=("IA_",),
        )
        if inventory_candidate:
            return inventory_candidate

        for selected_asset in EditorOperationService._candidate_asset_paths(request):
            if re.search(r"(^|[/._])IA_[A-Za-z0-9_]+", selected_asset):
                return selected_asset

        match = re.search(r"\b(IA_[A-Za-z][A-Za-z0-9_]{1,63})\b", query_text, flags=re.IGNORECASE)
        if match:
            return f"/Game/Input/{match.group(1)}"
        return None

    @staticmethod
    def _detect_blueprint_path_from_request(
        request: UnifiedTaskRequest,
        query_text: str,
        context_bundle: dict[str, Any] | None = None,
    ) -> str | None:
        explicit_path = str(request.payload.get("blueprint_path") or "").strip()
        if explicit_path:
            return explicit_path
        text_paths = EditorOperationService._extract_unreal_paths_from_text(query_text)
        for path in text_paths:
            asset_name = EditorOperationService._asset_name_from_path(path)
            if asset_name.lower().startswith("bp_") or "/blueprint" in path.lower():
                return path
        named_candidate = EditorOperationService._find_named_candidate_path(request, query_text, prefixes=("BP_",))
        if named_candidate:
            return named_candidate
        inventory_candidate = EditorOperationService._find_inventory_candidate_path(
            context_bundle=context_bundle,
            query_text=query_text,
            accepted_type_tokens=("blueprint", "blueprintgeneratedclass"),
            prefixes=("BP_",),
        )
        if inventory_candidate:
            return inventory_candidate
        selected_asset = EditorOperationService._selected_asset_path(request)
        if selected_asset:
            asset_name = EditorOperationService._asset_name_from_path(selected_asset).lower()
            if asset_name.startswith("bp_") or "/blueprint" in selected_asset.lower():
                return selected_asset
        if EditorOperationService._references_recent_target(query_text):
            recent_blueprint_path = EditorOperationService._recent_editor_operation_value(
                context_bundle=context_bundle,
                operation_types={
                    "create_blueprint_asset",
                    "add_blueprint_variable",
                    "add_blueprint_component",
                    "create_blueprint_event_stub",
                    "add_blueprint_node_template",
                    "compile_blueprint",
                },
                keys=("blueprint_path", "asset_path", "final_asset_path", "target_path"),
            )
            if recent_blueprint_path:
                return str(recent_blueprint_path)
        return None

    @staticmethod
    def _detect_widget_blueprint_path_from_request(
        request: UnifiedTaskRequest,
        query_text: str,
        context_bundle: dict[str, Any] | None = None,
    ) -> str | None:
        explicit_path = str(
            request.payload.get("widget_blueprint_path")
            or request.payload.get("widget_path")
            or request.payload.get("umg_path")
            or ""
        ).strip()
        if explicit_path:
            return explicit_path

        for path in EditorOperationService._extract_unreal_paths_from_text(query_text):
            asset_name = EditorOperationService._asset_name_from_path(path)
            if asset_name.lower().startswith(("wbp_", "ui_")) or "/ui/" in path.lower():
                return path

        named_candidate = EditorOperationService._find_named_candidate_path(
            request,
            query_text,
            prefixes=("WBP_", "UI_"),
        )
        if named_candidate:
            return named_candidate

        inventory_candidate = EditorOperationService._find_inventory_candidate_path(
            context_bundle=context_bundle,
            query_text=query_text,
            accepted_type_tokens=("widgetblueprint", "widget blueprint", "userwidget", "blueprint"),
            prefixes=("WBP_", "UI_"),
        )
        if inventory_candidate:
            return inventory_candidate

        selected_asset = EditorOperationService._selected_asset_path(request)
        if selected_asset and re.search(r"(^|[/._])(WBP_|UI_)[A-Za-z0-9_]+", selected_asset):
            return selected_asset
        return None

    @staticmethod
    def _detect_widget_name_from_request(request: UnifiedTaskRequest, query_text: str) -> str | None:
        explicit_name = str(
            request.payload.get("widget_name")
            or request.payload.get("target_widget_name")
            or request.payload.get("text_block_name")
            or ""
        ).strip()
        if explicit_name:
            return explicit_name
        for match in re.finditer(
            r"\b([A-Za-z][A-Za-z0-9_]*(?:Text|TextBlock|Label|Title|Name|Value|Image|Icon|Border|Button|Panel|Box|Widget))\b",
            query_text,
            flags=re.IGNORECASE,
        ):
            candidate = match.group(1)
            if not candidate.lower().startswith(("wbp_", "ui_")):
                return candidate
        return None

    @staticmethod
    def _detect_new_parent_widget_name_from_request(request: UnifiedTaskRequest, query_text: str) -> str | None:
        explicit_name = str(
            request.payload.get("new_parent_name")
            or request.payload.get("parent_widget_name")
            or request.payload.get("target_parent_name")
            or ""
        ).strip()
        if explicit_name:
            return explicit_name

        patterns = (
            r"(?:under|inside|into|to parent|new parent)\s+([A-Za-z][A-Za-z0-9_]{1,79})",
            r"(?:parent|container)\s*(?:to|=|:)\s*([A-Za-z][A-Za-z0-9_]{1,79})",
            r"(?:放到|移到|挂到|作为子控件到|父控件)\s*([A-Za-z][A-Za-z0-9_]{1,79})",
        )
        for pattern in patterns:
            match = re.search(pattern, query_text, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                if not candidate.lower().startswith(("wbp_", "ui_")):
                    return candidate
        return None

    @staticmethod
    def _detect_new_widget_name_from_request(request: UnifiedTaskRequest, query_text: str, source_widget_name: str | None) -> str | None:
        explicit_name = str(
            request.payload.get("new_widget_name")
            or request.payload.get("target_widget_name")
            or request.payload.get("new_name")
            or ""
        ).strip()
        if explicit_name:
            return explicit_name

        patterns = (
            r"(?:as|to|called|named|name it)\s+([A-Za-z][A-Za-z0-9_]{1,79})",
            r"(?:duplicate|copy|clone)\s+[A-Za-z][A-Za-z0-9_]{1,79}\s+([A-Za-z][A-Za-z0-9_]{1,79})",
        )
        for pattern in patterns:
            match = re.search(pattern, query_text, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                if not candidate.lower().startswith(("wbp_", "ui_")):
                    return candidate

        if source_widget_name:
            return f"{source_widget_name}_Copy"
        return None

    @staticmethod
    def _detect_umg_text_from_request(request: UnifiedTaskRequest, query_text: str) -> str | None:
        explicit_text = request.payload.get("text")
        if explicit_text is not None:
            return str(explicit_text)
        quoted = re.search(r"[\"']([^\"']{1,240})[\"']", query_text)
        if quoted:
            return quoted.group(1)
        match = re.search(
            r"(?:text|label|content)\s*(?:to|=|:)\s*(.{1,240})$",
            query_text,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()
        return None

    @staticmethod
    def _extract_vector2_after_keyword(query_text: str, keyword: str) -> dict[str, float] | None:
        pattern = rf"(?:{keyword})\s*(?:to|=|:)?\s*\(?\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)"
        match = re.search(pattern, query_text, flags=re.IGNORECASE)
        if not match:
            return None
        return {"x": float(match.group(1)), "y": float(match.group(2))}

    @staticmethod
    def _detect_umg_layout_from_request(request: UnifiedTaskRequest, query_text: str) -> dict[str, Any]:
        layout = request.payload.get("layout")
        if isinstance(layout, dict):
            return dict(layout)

        detected: dict[str, Any] = {}
        if isinstance(request.payload.get("position"), dict | list | tuple):
            detected["position"] = request.payload["position"]
        if isinstance(request.payload.get("size"), dict | list | tuple):
            detected["size"] = request.payload["size"]
        if isinstance(request.payload.get("alignment"), dict | list | tuple):
            detected["alignment"] = request.payload["alignment"]
        if isinstance(request.payload.get("anchors"), dict):
            detected["anchors"] = request.payload["anchors"]

        position = EditorOperationService._extract_vector2_after_keyword(query_text, "position|pos|location")
        if position:
            detected["position"] = position
        size = EditorOperationService._extract_vector2_after_keyword(query_text, "size")
        if size:
            detected["size"] = size
        alignment = EditorOperationService._extract_vector2_after_keyword(query_text, "alignment|align")
        if alignment:
            detected["alignment"] = alignment
        return detected

    @staticmethod
    def _detect_umg_visibility_from_request(request: UnifiedTaskRequest, query_text: str) -> str | None:
        explicit_visibility = request.payload.get("visibility")
        if explicit_visibility is not None:
            return str(explicit_visibility)
        query_lower = query_text.lower()
        for alias, value in UMG_VISIBILITY_ALIASES.items():
            if re.search(rf"\b{re.escape(alias)}\b", query_lower):
                return value
        return None

    @staticmethod
    def _detect_umg_appearance_from_request(request: UnifiedTaskRequest, query_text: str) -> dict[str, Any]:
        appearance: dict[str, Any] = {}
        payload_appearance = request.payload.get("appearance")
        if isinstance(payload_appearance, dict):
            appearance.update(payload_appearance)
        for key in ("render_opacity", "opacity", "is_enabled", "enabled", "color_and_opacity", "font_size"):
            if key in request.payload:
                appearance[key] = request.payload[key]
        if appearance:
            return appearance

        opacity_match = re.search(
            r"(?:render\s*)?opacity\s*(?:to|=|:)?\s*(\d+(?:\.\d+)?%?)",
            query_text,
            flags=re.IGNORECASE,
        )
        if opacity_match:
            raw_opacity = opacity_match.group(1)
            appearance["render_opacity"] = float(raw_opacity.rstrip("%")) / 100.0 if raw_opacity.endswith("%") else float(raw_opacity)

        font_size_match = re.search(r"font\s*size\s*(?:to|=|:)?\s*(\d{1,3})", query_text, flags=re.IGNORECASE)
        if font_size_match:
            appearance["font_size"] = int(font_size_match.group(1))

        query_lower = query_text.lower()
        if any(token in query_lower for token in ("disable", "disabled", "not enabled")):
            appearance["is_enabled"] = False
        elif any(token in query_lower for token in ("enable", "enabled")):
            appearance["is_enabled"] = True

        color_match = re.search(r"#([0-9a-fA-F]{6})([0-9a-fA-F]{2})?", query_text)
        if color_match:
            rgb = color_match.group(1)
            alpha = color_match.group(2) or "FF"
            appearance["color_and_opacity"] = {
                "r": int(rgb[0:2], 16) / 255.0,
                "g": int(rgb[2:4], 16) / 255.0,
                "b": int(rgb[4:6], 16) / 255.0,
                "a": int(alpha, 16) / 255.0,
            }
        return appearance

    @staticmethod
    def _detect_umg_brush_from_request(
        request: UnifiedTaskRequest,
        query_text: str,
        context_bundle: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload_brush = request.payload.get("brush")
        if isinstance(payload_brush, dict) and payload_brush:
            return dict(payload_brush)

        brush: dict[str, Any] = {}
        for key in ("resource_type", "resource_path", "texture_path", "material_path"):
            if key in request.payload:
                brush[key] = request.payload[key]
        if brush:
            return brush

        query_lower = query_text.lower()
        wants_material = any(token in query_lower for token in ("material", "mi_", "m_"))
        if wants_material:
            brush["resource_type"] = "material"
            brush["resource_path"] = EditorOperationService._detect_material_resource_path_from_request(
                request,
                query_text,
                context_bundle,
            )
        else:
            brush["resource_type"] = "texture"
            brush["resource_path"] = EditorOperationService._detect_texture_path_from_request(
                request,
                query_text,
                context_bundle,
            )
        return brush

    @staticmethod
    def _detect_umg_slot_type_from_request(request: UnifiedTaskRequest, query_text: str) -> str | None:
        explicit_slot = str(request.payload.get("slot_type") or request.payload.get("slot") or "").strip()
        if explicit_slot:
            return explicit_slot
        query_lower = query_text.lower()
        if any(token in query_lower for token in ("horizontalbox", "horizontal box", "hbox")):
            return "HorizontalBoxSlot"
        if any(token in query_lower for token in ("verticalbox", "vertical box", "vbox")):
            return "VerticalBoxSlot"
        if "overlay" in query_lower:
            return "OverlaySlot"
        return None

    @staticmethod
    def _detect_umg_slot_layout_from_request(request: UnifiedTaskRequest, query_text: str) -> dict[str, Any]:
        payload_layout = request.payload.get("layout")
        if isinstance(payload_layout, dict):
            return dict(payload_layout)

        detected: dict[str, Any] = {}
        for key in ("padding", "horizontal_alignment", "vertical_alignment", "size"):
            if key in request.payload:
                detected[key] = request.payload[key]

        padding_match = re.search(
            r"(?:padding|margin)\s*(?:to|=|:)?\s*\(?\s*(-?\d+(?:\.\d+)?)(?:\s*[, ]\s*(-?\d+(?:\.\d+)?))?(?:\s*[, ]\s*(-?\d+(?:\.\d+)?))?(?:\s*[, ]\s*(-?\d+(?:\.\d+)?))?",
            query_text,
            flags=re.IGNORECASE,
        )
        if padding_match:
            values = [padding_match.group(index) for index in range(1, 5)]
            numbers = [float(value) for value in values if value is not None]
            if len(numbers) == 1:
                detected["padding"] = numbers[0]
            elif len(numbers) == 2:
                detected["padding"] = {
                    "left": numbers[0],
                    "top": numbers[1],
                    "right": numbers[0],
                    "bottom": numbers[1],
                }
            elif len(numbers) >= 4:
                detected["padding"] = {
                    "left": numbers[0],
                    "top": numbers[1],
                    "right": numbers[2],
                    "bottom": numbers[3],
                }

        query_lower = query_text.lower()
        for alignment in ("fill", "left", "center", "right"):
            if re.search(rf"(?:horizontal\s+alignment|halign|h-align)\s*(?:to|=|:)?\s*{alignment}\b", query_lower):
                detected["horizontal_alignment"] = alignment
                break
        for alignment in ("fill", "top", "center", "bottom"):
            if re.search(rf"(?:vertical\s+alignment|valign|v-align)\s*(?:to|=|:)?\s*{alignment}\b", query_lower):
                detected["vertical_alignment"] = alignment
                break

        size_match = re.search(
            r"(?:slot\s+size|size rule|size)\s*(?:to|=|:)?\s*(auto|fill)(?:\s+(-?\d+(?:\.\d+)?))?",
            query_text,
            flags=re.IGNORECASE,
        )
        if size_match:
            size: dict[str, Any] = {"rule": size_match.group(1).lower()}
            if size_match.group(2) is not None:
                size["value"] = float(size_match.group(2))
            detected["size"] = size
        return detected

    @staticmethod
    def _detect_actor_metadata_from_request(request: UnifiedTaskRequest, query_text: str) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        payload_metadata = request.payload.get("metadata")
        if isinstance(payload_metadata, dict):
            metadata.update(payload_metadata)
        for key in ("actor_label", "folder_path", "tags", "tag_mode"):
            if key in request.payload:
                metadata[key] = request.payload[key]
        if metadata:
            return metadata

        label_match = re.search(
            r"(?:label|name)\s*(?:to|=|:)\s*['\"]?([A-Za-z0-9_ \-]{1,120})",
            query_text,
            flags=re.IGNORECASE,
        )
        if not label_match:
            label_match = re.search(
                r"(?:标签|名字|名称)\s*(?:改成|改为|设置为|设为|为)\s*([A-Za-z0-9_ \-]{1,120})",
                query_text,
            )
        if label_match:
            metadata["actor_label"] = label_match.group(1).strip().strip("'\"")

        folder_match = re.search(
            r"(?:folder|folder path)\s*(?:to|=|:)\s*['\"]?([A-Za-z0-9_ /\-]{1,200})",
            query_text,
            flags=re.IGNORECASE,
        )
        if not folder_match:
            folder_match = re.search(r"(?:文件夹|目录)\s*(?:改成|改为|设置为|设为|为)\s*([A-Za-z0-9_ /\-]{1,200})", query_text)
        if folder_match:
            metadata["folder_path"] = folder_match.group(1).strip().strip("'\"")

        tag_mode = "replace"
        query_lower = query_text.lower()
        if any(token in query_lower or token in query_text for token in ("add tag", "append tag", "添加标签", "增加标签")):
            tag_mode = "append"
        if any(token in query_lower or token in query_text for token in ("remove tag", "delete tag", "移除标签", "删除标签")):
            tag_mode = "remove"
        tag_match = re.search(r"(?:tags?|标签)\s*(?:to|=|:|为|是)?\s*['\"]?([A-Za-z0-9_,，;； \-]{1,200})", query_text, flags=re.IGNORECASE)
        if tag_match:
            tags_text = tag_match.group(1).strip().strip("'\"")
            tags = [item.strip() for item in re.split(r"[,，;； ]+", tags_text) if item.strip()]
            if tags:
                metadata["tags"] = tags
                metadata["tag_mode"] = tag_mode
        return metadata

    @staticmethod
    def _detect_material_parameter_name(query_text: str) -> str | None:
        for known_name in (
            "Roughness",
            "Metallic",
            "Specular",
            "Opacity",
            "Alpha",
            "Emissive",
            "Base Color",
            "BaseColor",
            "Base Texture",
            "BaseTexture",
            "Albedo",
            "Diffuse",
            "Normal",
            "Mask",
            "Tint Color",
            "Tint",
            "UseDetail",
            "Use Detail",
            "UseNormal",
            "Use Normal",
            "UseEmissive",
            "Use Emissive",
        ):
            if known_name.lower() in query_text.lower():
                return known_name
        match = re.search(
            r"(?:参数|parameter|switch|开关)\s*[:：]?\s*([A-Za-z][A-Za-z0-9_ ]{0,79})",
            query_text,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()
        match = re.search(
            r"(?:的|the)\s*([A-Za-z][A-Za-z0-9_ ]{0,79})\s*(?:switch|开关|参数)",
            query_text,
            flags=re.IGNORECASE,
        )
        return match.group(1).strip() if match else None

    @staticmethod
    def _detect_bool_value(query_text: str) -> bool | None:
        query_lower = query_text.lower()
        false_tokens = ("false", "off", "disable", "disabled", "0", "关闭", "关掉", "禁用", "取消", "不启用")
        true_tokens = ("true", "on", "enable", "enabled", "1", "打开", "开启", "启用", "勾选", "使用")
        if any(token in query_lower or token in query_text for token in false_tokens):
            return False
        if any(token in query_lower or token in query_text for token in true_tokens):
            return True
        return None

    @staticmethod
    def _detect_material_value(query_text: str, parameter_name: str | None) -> tuple[str, Any] | None:
        color_values = {
            "红": {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0},
            "red": {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0},
            "绿": {"r": 0.0, "g": 1.0, "b": 0.0, "a": 1.0},
            "green": {"r": 0.0, "g": 1.0, "b": 0.0, "a": 1.0},
            "蓝": {"r": 0.0, "g": 0.0, "b": 1.0, "a": 1.0},
            "blue": {"r": 0.0, "g": 0.0, "b": 1.0, "a": 1.0},
            "白": {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0},
            "white": {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0},
            "黑": {"r": 0.0, "g": 0.0, "b": 0.0, "a": 1.0},
            "black": {"r": 0.0, "g": 0.0, "b": 0.0, "a": 1.0},
        }
        query_lower = query_text.lower()
        for token, value in color_values.items():
            if token in query_lower or token in query_text:
                return ("vector", value)
        rgb_match = re.search(
            r"(?:rgb|颜色|color)\s*[:：=]?\s*\(?\s*(-?\d+(?:\.\d+)?)\s*[,， ]\s*(-?\d+(?:\.\d+)?)\s*[,， ]\s*(-?\d+(?:\.\d+)?)(?:\s*[,， ]\s*(-?\d+(?:\.\d+)?))?",
            query_text,
            flags=re.IGNORECASE,
        )
        if rgb_match:
            return (
                "vector",
                {
                    "r": float(rgb_match.group(1)),
                    "g": float(rgb_match.group(2)),
                    "b": float(rgb_match.group(3)),
                    "a": float(rgb_match.group(4) or 1.0),
                },
            )
        value_match = re.search(r"(?:到|为|成|=|value|set to|to)\s*(-?\d+(?:\.\d+)?)", query_text, flags=re.IGNORECASE)
        if not value_match:
            value_match = re.search(r"(-?\d+(?:\.\d+)?)", query_text)
        if value_match:
            name = (parameter_name or "").lower()
            parameter_type = "vector" if any(token in name for token in ("color", "tint", "basecolor")) else "scalar"
            value = float(value_match.group(1))
            return (parameter_type, {"r": value, "g": value, "b": value, "a": 1.0} if parameter_type == "vector" else value)
        return None

    @staticmethod
    def detect_request(
        request: UnifiedTaskRequest,
        context_bundle: dict[str, Any] | None = None,
    ) -> EditorOperationProposalRequest | None:
        explicit_operation = request.payload.get("operation_type")
        if explicit_operation in OPERATION_SPECS:
            payload = request.payload.get("operation_payload")
            if not isinstance(payload, dict):
                payload = request.payload.get("payload") if isinstance(request.payload.get("payload"), dict) else request.payload
            return EditorOperationProposalRequest(
                operation_type=explicit_operation,
                payload=dict(payload or {}),
                reason=str(request.payload.get("reason") or request.payload.get("user_query") or ""),
                source_task_id=request.payload.get("source_task_id"),
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        query_text = EditorOperationService._query_text(request)
        if not query_text:
            return None
        query_lower = query_text.lower()

        place_action_signal = (
            re.search(r"\b(?:place|spawn|put)\b", query_lower) is not None
            or "add to level" in query_lower
            or any(
                token in query_text
                for token in (
                    "放置",
                    "摆放",
                    "放到",
                    "放入",
                    "加入关卡",
                    "鏀剧疆",
                    "鎽嗘斁",
                    "鏀惧埌",
                    "鏀惧叆",
                    "鍔犲叆鍏冲崱",
                )
            )
        )
        place_target_signal = (
            re.search(r"\b(?:actor|blueprint|level|world|map)\b", query_lower) is not None
            or "bp_" in query_lower
            or any(
                token in query_text
                for token in ("蓝图", "关卡", "场景", "灯光", "相机", "钃濆浘", "鍏冲崱", "鍦烘櫙", "鐏厜", "鐩告満")
            )
        )
        wants_place_actor = place_action_signal and place_target_signal
        if wants_place_actor:
            actor_class = EditorOperationService._detect_actor_class_from_request(
                request,
                query_text,
                query_lower,
                context_bundle,
            )
            payload: dict[str, Any] = {
                "actor_class": actor_class or "",
                "actor_label": request.payload.get("actor_label")
                or EditorOperationService._extract_actor_label_from_text(query_text),
            }
            transform = request.payload.get("transform") if isinstance(request.payload.get("transform"), dict) else {}
            if not transform:
                transform = EditorOperationService._extract_transform_from_text(query_text)
            if transform:
                payload["transform"] = transform
            return EditorOperationProposalRequest(
                operation_type="place_actor_in_level",
                payload=payload,
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        wants_actor_transform = any(
            token in query_lower or token in query_text
            for token in (
                "move",
                "translate",
                "rotate",
                "turn",
                "scale",
                "transform",
                "location",
                "移动",
                "平移",
                "旋转",
                "缩放",
                "放大",
                "往右",
                "往左",
                "向右",
                "向左",
                "向上",
                "向下",
                "往前",
                "往后",
            )
        ) and any(
            token in query_lower or token in query_text
            for token in ("actor", "that", "previous", "last", "刚才", "上一个", "那个", "这个", "场景物体")
        )
        if wants_actor_transform:
            actor_reference = EditorOperationService._detect_actor_reference_from_request(
                request,
                query_text,
                context_bundle,
            )
            transform_mode, transform_update = EditorOperationService._extract_actor_transform_update_from_text(query_text)
            payload: dict[str, Any] = {
                "actor_reference": actor_reference or "",
                "transform_mode": transform_mode,
            }
            if transform_mode == "delta":
                payload["transform_delta"] = transform_update
            else:
                payload["transform"] = transform_update
            return EditorOperationProposalRequest(
                operation_type="set_actor_transform",
                payload=payload,
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        actor_metadata_target_signal = any(
            token in query_lower or token in query_text
            for token in (
                "actor",
                "that actor",
                "selected actor",
                "level actor",
                "bp_",
                "场景物体",
                "关卡对象",
                "这个actor",
                "那个actor",
            )
        )
        actor_metadata_field_signal = bool(
            re.search(r"\b(?:label|name|folder|tag|tags|metadata|rename)\b", query_lower)
        ) or any(
            token in query_lower or token in query_text
            for token in ("标签", "名称", "名字", "文件夹", "目录")
        )
        actor_metadata_action_signal = bool(
            re.search(r"\b(?:set|change|rename|add|remove|update)\b", query_lower)
        ) or any(
            token in query_lower or token in query_text
            for token in ("设置", "改成", "改为", "添加", "移除", "删除")
        )
        wants_actor_metadata = (
            actor_metadata_target_signal
            and actor_metadata_field_signal
            and actor_metadata_action_signal
            and not any(
                token in query_lower or token in query_text
                for token in ("print string", "printstring", "打印字符串", "打印文本")
            )
        )
        if wants_actor_metadata:
            actor_reference = EditorOperationService._detect_actor_reference_from_request(
                request,
                query_text,
                context_bundle,
            )
            return EditorOperationProposalRequest(
                operation_type="set_actor_metadata",
                payload={
                    "actor_reference": actor_reference or "",
                    "metadata": EditorOperationService._detect_actor_metadata_from_request(request, query_text),
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        wants_arrange_actors = any(
            token in query_lower or token in query_text
            for token in ("arrange", "layout actors", "line up", "grid", "circle", "摆放", "排列", "阵列", "排成")
        ) and any(
            token in query_lower or token in query_text
            for token in ("actor", "actors", "level", "场景", "关卡")
        )
        if wants_arrange_actors:
            return EditorOperationProposalRequest(
                operation_type="arrange_actors_pattern",
                payload={
                    "actor_references": EditorOperationService._detect_actor_references_from_request(
                        request,
                        query_text,
                        context_bundle,
                    ),
                    "pattern": EditorOperationService._detect_arrange_pattern_from_request(request, query_text),
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        wants_umg_duplicate = any(
            token in query_lower
            for token in ("umg", "widget", "textblock", "text block", "image", "button", "hud", "wbp_")
        ) and any(
            token in query_lower or token in query_text
            for token in ("duplicate", "copy", "clone", "复制", "拷贝", "克隆")
        )
        if wants_umg_duplicate:
            widget_blueprint_path = EditorOperationService._detect_widget_blueprint_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            widget_name = EditorOperationService._detect_widget_name_from_request(request, query_text)
            new_widget_name = EditorOperationService._detect_new_widget_name_from_request(
                request,
                query_text,
                widget_name,
            )
            return EditorOperationProposalRequest(
                operation_type="duplicate_umg_widget",
                payload={
                    "widget_blueprint_path": widget_blueprint_path or "",
                    "widget_name": widget_name or "",
                    "new_widget_name": new_widget_name or "",
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        wants_umg_delete = any(
            token in query_lower
            for token in ("umg", "widget", "textblock", "text block", "image", "button", "hud", "wbp_")
        ) and any(
            token in query_lower or token in query_text
            for token in ("delete", "remove", "destroy", "移除", "删除", "删掉", "刪除")
        )
        if wants_umg_delete:
            widget_blueprint_path = EditorOperationService._detect_widget_blueprint_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            widget_name = EditorOperationService._detect_widget_name_from_request(request, query_text)
            return EditorOperationProposalRequest(
                operation_type="delete_umg_widget",
                payload={
                    "widget_blueprint_path": widget_blueprint_path or "",
                    "widget_name": widget_name or "",
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        wants_umg_reparent = any(
            token in query_lower
            for token in ("umg", "widget", "textblock", "text block", "hud", "wbp_")
        ) and any(
            token in query_lower or token in query_text
            for token in ("reparent", "move under", "move into", "under", "new parent", "parent widget", "放到", "移到", "挂到", "父控件")
        ) and any(
            token in query_lower or token in query_text
            for token in ("set", "change", "update", "move", "reparent", "放到", "移到", "挂到", "改到")
        )
        if wants_umg_reparent:
            widget_blueprint_path = EditorOperationService._detect_widget_blueprint_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            widget_name = EditorOperationService._detect_widget_name_from_request(request, query_text)
            new_parent_name = EditorOperationService._detect_new_parent_widget_name_from_request(request, query_text)
            return EditorOperationProposalRequest(
                operation_type="reparent_umg_widget",
                payload={
                    "widget_blueprint_path": widget_blueprint_path or "",
                    "widget_name": widget_name or "",
                    "new_parent_name": new_parent_name or "",
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        explicit_umg_text_request = (
            "text" in request.payload
            or re.search(r"\b(?:text|label|content)\s*(?:to|=|:)", query_lower) is not None
        )
        wants_umg_text = explicit_umg_text_request and any(
            token in query_lower
            for token in ("umg", "widget", "textblock", "text block", "hud", "wbp_")
        ) and any(
            token in query_lower
            for token in ("set", "change", "update", "replace")
        )
        if wants_umg_text:
            widget_blueprint_path = EditorOperationService._detect_widget_blueprint_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            widget_name = EditorOperationService._detect_widget_name_from_request(request, query_text)
            text_value = EditorOperationService._detect_umg_text_from_request(request, query_text)
            return EditorOperationProposalRequest(
                operation_type="set_umg_widget_text",
                payload={
                    "widget_blueprint_path": widget_blueprint_path or "",
                    "widget_name": widget_name or "",
                    "text": text_value if text_value is not None else "",
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        wants_umg_layout = any(
            token in query_lower
            for token in ("umg", "widget", "textblock", "text block", "hud", "wbp_")
        ) and any(
            token in query_lower
            for token in ("position", "pos", "layout", "size", "alignment", "align", "anchor")
        ) and any(
            token in query_lower
            for token in ("set", "change", "update", "move", "resize")
        ) and not any(
            token in query_lower
            for token in ("slot", "padding", "margin", "horizontalbox", "verticalbox", "overlay")
        )
        if wants_umg_layout:
            widget_blueprint_path = EditorOperationService._detect_widget_blueprint_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            widget_name = EditorOperationService._detect_widget_name_from_request(request, query_text)
            layout = EditorOperationService._detect_umg_layout_from_request(request, query_text)
            return EditorOperationProposalRequest(
                operation_type="set_umg_widget_layout",
                payload={
                    "widget_blueprint_path": widget_blueprint_path or "",
                    "widget_name": widget_name or "",
                    "layout": layout,
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        wants_umg_slot_layout_v2 = any(
            token in query_lower
            for token in ("umg", "widget", "textblock", "image", "button", "hud", "wbp_")
        ) and any(
            token in query_lower
            for token in ("slot", "padding", "margin", "horizontalbox", "verticalbox", "overlay", "halign", "valign")
        ) and any(
            token in query_lower
            for token in ("set", "change", "update", "adjust", "make")
        )
        if wants_umg_slot_layout_v2:
            widget_blueprint_path = EditorOperationService._detect_widget_blueprint_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            widget_name = EditorOperationService._detect_widget_name_from_request(request, query_text)
            return EditorOperationProposalRequest(
                operation_type="set_umg_slot_layout_v2",
                payload={
                    "widget_blueprint_path": widget_blueprint_path or "",
                    "widget_name": widget_name or "",
                    "slot_type": EditorOperationService._detect_umg_slot_type_from_request(request, query_text) or "",
                    "layout": EditorOperationService._detect_umg_slot_layout_from_request(request, query_text),
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        wants_umg_visibility = any(
            token in query_lower
            for token in ("umg", "widget", "textblock", "text block", "hud", "wbp_")
        ) and any(
            token in query_lower
            for token in ("visibility", "visible", "hidden", "collapsed", "hide", "show", "invisible")
        ) and any(
            token in query_lower
            for token in ("set", "change", "update", "make", "hide", "show")
        )
        if wants_umg_visibility:
            widget_blueprint_path = EditorOperationService._detect_widget_blueprint_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            widget_name = EditorOperationService._detect_widget_name_from_request(request, query_text)
            visibility = EditorOperationService._detect_umg_visibility_from_request(request, query_text)
            return EditorOperationProposalRequest(
                operation_type="set_umg_widget_visibility",
                payload={
                    "widget_blueprint_path": widget_blueprint_path or "",
                    "widget_name": widget_name or "",
                    "visibility": visibility or "",
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        wants_umg_appearance = any(
            token in query_lower
            for token in ("umg", "widget", "textblock", "text block", "hud", "wbp_")
        ) and any(
            token in query_lower
            for token in (
                "appearance",
                "opacity",
                "render opacity",
                "enabled",
                "disable",
                "font size",
                "color",
                "tint",
            )
        ) and any(
            token in query_lower
            for token in ("set", "change", "update", "make", "enable", "disable")
        )
        if wants_umg_appearance:
            widget_blueprint_path = EditorOperationService._detect_widget_blueprint_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            widget_name = EditorOperationService._detect_widget_name_from_request(request, query_text)
            return EditorOperationProposalRequest(
                operation_type="set_umg_widget_appearance",
                payload={
                    "widget_blueprint_path": widget_blueprint_path or "",
                    "widget_name": widget_name or "",
                    "appearance": EditorOperationService._detect_umg_appearance_from_request(request, query_text),
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        wants_umg_brush = any(
            token in query_lower
            for token in ("umg", "widget", "image", "border", "icon", "hud", "wbp_")
        ) and any(
            token in query_lower
            for token in ("brush", "texture", "material", "image", "icon", "background", "border", "t_", "tx_", "mi_", "m_")
        ) and any(
            token in query_lower
            for token in ("set", "change", "update", "assign", "use")
        )
        if wants_umg_brush:
            widget_blueprint_path = EditorOperationService._detect_widget_blueprint_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            widget_name = EditorOperationService._detect_widget_name_from_request(request, query_text)
            return EditorOperationProposalRequest(
                operation_type="set_umg_widget_brush",
                payload={
                    "widget_blueprint_path": widget_blueprint_path or "",
                    "widget_name": widget_name or "",
                    "brush": EditorOperationService._detect_umg_brush_from_request(request, query_text, context_bundle),
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        wants_material_static_switch = any(
            token in query_lower or token in query_text
            for token in (
                "static switch",
                "switch parameter",
                "switch",
                "开关参数",
                "静态开关",
                "开关",
            )
        ) and any(
            token in query_lower or token in query_text
            for token in ("material", "material instance", "mi_", "材质", "材质实例")
        ) and any(
            token in query_lower or token in query_text
            for token in ("set", "adjust", "change", "enable", "disable", "turn", "设置", "调整", "改成", "打开", "关闭", "启用", "禁用")
        )
        if wants_material_static_switch:
            material_path = EditorOperationService._detect_material_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            parameter_name = str(request.payload.get("parameter_name") or "").strip() or (
                EditorOperationService._detect_material_parameter_name(query_text) or ""
            )
            value = (
                request.payload.get("value")
                if "value" in request.payload
                else EditorOperationService._detect_bool_value(query_text)
            )
            return EditorOperationProposalRequest(
                operation_type="set_material_instance_static_switch",
                payload={
                    "material_instance_path": material_path or "",
                    "parameter_name": parameter_name,
                    "value": value,
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        wants_material_texture_parameter = any(
            token in query_lower or token in query_text
            for token in ("texture", "texture parameter", "t_", "tx_", "贴图", "纹理")
        ) and any(
            token in query_lower or token in query_text
            for token in ("material", "material instance", "mi_", "材质", "材质实例")
        ) and any(
            token in query_lower or token in query_text
            for token in ("set", "adjust", "change", "assign", "use", "设置", "调整", "改成", "改为", "使用")
        )
        if wants_material_texture_parameter:
            material_path = EditorOperationService._detect_material_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            texture_path = EditorOperationService._detect_texture_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            parameter_name = str(request.payload.get("parameter_name") or "").strip() or (
                EditorOperationService._detect_material_parameter_name(query_text) or ""
            )
            return EditorOperationProposalRequest(
                operation_type="set_material_instance_texture_parameter",
                payload={
                    "material_instance_path": material_path or "",
                    "parameter_name": parameter_name,
                    "texture_path": texture_path or "",
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        wants_material_parameter = any(
            token in query_lower or token in query_text
            for token in (
                "material instance",
                "material parameter",
                "material",
                "mi_",
                "材质实例",
                "材质参数",
                "材质",
            )
        ) and any(
            token in query_lower or token in query_text
            for token in ("set", "adjust", "tune", "change", "设置", "调整", "调到", "改成", "改为")
        )
        if wants_material_parameter:
            material_path = EditorOperationService._detect_material_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            parameter_name = str(request.payload.get("parameter_name") or "").strip() or (
                EditorOperationService._detect_material_parameter_name(query_text) or ""
            )
            value_result = (
                (str(request.payload.get("parameter_type") or "scalar").strip().lower(), request.payload.get("value"))
                if "value" in request.payload
                else EditorOperationService._detect_material_value(query_text, parameter_name)
            )
            parameter_type, value = value_result if value_result else ("", None)
            return EditorOperationProposalRequest(
                operation_type="set_material_instance_parameter",
                payload={
                    "material_instance_path": material_path or "",
                    "parameter_name": parameter_name,
                    "parameter_type": parameter_type,
                    "value": value,
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        blueprint_signal = "blueprint" in query_lower or "bp_" in query_lower or "\u84dd\u56fe" in query_text
        print_string_signal = any(
            token in query_lower or token in query_text
            for token in (
                "print string",
                "printstring",
                "\u6253\u5370\u5b57\u7b26\u4e32",
                "\u6253\u5370\u6587\u672c",
            )
        )
        add_signal = any(
            token in query_lower or token in query_text
            for token in (
                "add",
                "create",
                "insert",
                "\u653e",
                "\u6dfb\u52a0",
                "\u52a0\u4e0a",
                "\u52a0\u4e00\u4e2a",
                "\u52a0\u4e2a",
                "\u589e\u52a0",
                "\u63d2\u5165",
                "\u521b\u5efa",
            )
        )
        branch_signal = any(
            token in query_lower or token in query_text
            for token in (
                "branch",
                "ifthenelse",
                "if node",
                "condition",
                "\u5206\u652f",
                "\u6761\u4ef6",
                "\u5224\u65ad",
                "\u5982\u679c",
            )
        )
        sequence_signal = any(
            token in query_lower or token in query_text
            for token in (
                "sequence",
                "then 0",
                "then 1",
                "\u987a\u5e8f",
                "\u4f9d\u6b21",
                "\u5148",
                "\u7136\u540e",
            )
        )
        enhanced_input_signal = any(
            token in query_lower or token in query_text
            for token in (
                "enhanced input",
                "input action",
                "inputaction",
                "ia_",
                "enhancedinput",
                "\u589e\u5f3a\u8f93\u5165",
                "\u8f93\u5165\u52a8\u4f5c",
            )
        )
        overlap_signal = any(
            token in query_lower or token in query_text
            for token in (
                "overlap",
                "begin overlap",
                "end overlap",
                "actorbeginoverlap",
                "actorendoverlap",
                "\u91cd\u53e0",
                "\u78b0\u649e",
                "\u8fdb\u5165\u89e6\u53d1",
                "\u79bb\u5f00\u89e6\u53d1",
            )
        )
        if blueprint_signal and print_string_signal and add_signal and enhanced_input_signal:
            input_action_path = EditorOperationService._detect_input_action_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            if input_action_path:
                blueprint_path = EditorOperationService._detect_blueprint_path_from_request(
                    request,
                    query_text,
                    context_bundle,
                )
                return EditorOperationProposalRequest(
                    operation_type="add_blueprint_node_template",
                    payload={
                        "blueprint_path": blueprint_path or "",
                        "template_id": "enhanced_input_print_string",
                        "graph_name": EditorOperationService._detect_blueprint_graph_name_from_request(
                            request,
                            query_text,
                        ),
                        "input_action_path": input_action_path,
                        "message": request.payload.get("message")
                        or request.payload.get("string_value")
                        or f"{EditorOperationService._asset_name_from_path(input_action_path)} triggered",
                        "compile_after_edit": bool(request.payload.get("compile_after_edit", True)),
                    },
                    reason=query_text,
                    requested_by="agent_chat",
                    context=request.context.model_dump(mode="json"),
                )
        if blueprint_signal and print_string_signal and add_signal and overlap_signal:
            blueprint_path = EditorOperationService._detect_blueprint_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            entry_event = EditorOperationService._detect_blueprint_entry_event_from_request(
                request,
                query_text,
                default="ActorBeginOverlap",
            )
            return EditorOperationProposalRequest(
                operation_type="add_blueprint_node_template",
                payload={
                    "blueprint_path": blueprint_path or "",
                    "template_id": "print_string",
                    "graph_name": EditorOperationService._detect_blueprint_graph_name_from_request(
                        request,
                        query_text,
                    ),
                    "message": request.payload.get("message")
                    or request.payload.get("string_value")
                    or f"{entry_event} from UEAgent",
                    "entry_event": entry_event,
                    "compile_after_edit": bool(request.payload.get("compile_after_edit", True)),
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )
        if blueprint_signal and print_string_signal and add_signal and sequence_signal:
            blueprint_path = EditorOperationService._detect_blueprint_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            return EditorOperationProposalRequest(
                operation_type="add_blueprint_node_template",
                payload={
                    "blueprint_path": blueprint_path or "",
                    "template_id": "sequence_print_strings",
                    "graph_name": EditorOperationService._detect_blueprint_graph_name_from_request(
                        request,
                        query_text,
                    ),
                    "messages": request.payload.get("messages")
                    or [
                        request.payload.get("message") or "Sequence step 1 from UEAgent",
                        request.payload.get("message_2") or "Sequence step 2 from UEAgent",
                    ],
                    "entry_event": EditorOperationService._detect_blueprint_entry_event_from_request(
                        request,
                        query_text,
                        default="BeginPlay",
                    ),
                    "compile_after_edit": bool(request.payload.get("compile_after_edit", True)),
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )
        if blueprint_signal and print_string_signal and add_signal and branch_signal:
            blueprint_path = EditorOperationService._detect_blueprint_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            false_branch_signal = any(
                token in query_lower or token in query_text
                for token in ("false", "else", "\u5426", "\u5426\u5219", "\u5931\u8d25")
            )
            condition_default = request.payload.get("condition_default")
            if condition_default is None:
                condition_default = not false_branch_signal
            return EditorOperationProposalRequest(
                operation_type="add_blueprint_node_template",
                payload={
                    "blueprint_path": blueprint_path or "",
                    "template_id": "branch_print_string",
                    "graph_name": EditorOperationService._detect_blueprint_graph_name_from_request(
                        request,
                        query_text,
                    ),
                    "message": request.payload.get("message")
                    or request.payload.get("string_value")
                    or "Branch reached from UEAgent",
                    "entry_event": EditorOperationService._detect_blueprint_entry_event_from_request(
                        request,
                        query_text,
                        default="BeginPlay",
                    ),
                    "condition_default": condition_default,
                    "branch_path": request.payload.get("branch_path") or ("false" if false_branch_signal else "true"),
                    "compile_after_edit": bool(request.payload.get("compile_after_edit", True)),
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        delay_signal = any(
            token in query_lower or token in query_text
            for token in (
                "delay",
                "wait",
                "after",
                "later",
                "延迟",
                "等待",
                "秒后",
                "之后",
            )
        )
        if blueprint_signal and print_string_signal and add_signal and delay_signal:
            blueprint_path = EditorOperationService._detect_blueprint_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            return EditorOperationProposalRequest(
                operation_type="add_blueprint_node_template",
                payload={
                    "blueprint_path": blueprint_path or "",
                    "template_id": "delay_print_string",
                    "graph_name": EditorOperationService._detect_blueprint_graph_name_from_request(
                        request,
                        query_text,
                    ),
                    "message": request.payload.get("message")
                    or request.payload.get("string_value")
                    or "Delayed message from UEAgent",
                    "delay_seconds": request.payload.get("delay_seconds")
                    or request.payload.get("delay")
                    or EditorOperationService._extract_delay_seconds_from_text(query_text, default=1.0),
                    "entry_event": EditorOperationService._detect_blueprint_entry_event_from_request(
                        request,
                        query_text,
                        default="BeginPlay",
                    ),
                    "compile_after_edit": bool(request.payload.get("compile_after_edit", True)),
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        variable_signal = any(
            token in query_lower or token in query_text
            for token in ("variable", "property", "var ", "\u53d8\u91cf", "\u5c5e\u6027")
        )
        variable_node_signal = any(
            token in query_lower or token in query_text
            for token in ("node", "graph", "\u8282\u70b9", "\u56fe\u8868", "\u56fe\u8c31")
        )
        set_variable_signal = any(
            token in query_lower or token in query_text
            for token in ("set ", "assign", "write", "\u8bbe\u7f6e", "\u8d4b\u503c", "\u5199\u5165", "\u6539\u6210")
        )
        get_variable_signal = any(
            token in query_lower or token in query_text
            for token in ("get ", "read", "\u83b7\u53d6", "\u8bfb\u53d6")
        )
        if blueprint_signal and variable_signal and variable_node_signal and (set_variable_signal or get_variable_signal):
            variable_name = (
                str(request.payload.get("variable_name") or "").strip()
                or EditorOperationService._extract_blueprint_variable_name_from_text(query_text)
            )
            if variable_name:
                blueprint_path = EditorOperationService._detect_blueprint_path_from_request(
                    request,
                    query_text,
                    context_bundle,
                )
                template_id = "set_variable" if set_variable_signal else "get_variable"
                payload: dict[str, Any] = {
                    "blueprint_path": blueprint_path or "",
                    "template_id": template_id,
                    "graph_name": EditorOperationService._detect_blueprint_graph_name_from_request(
                        request,
                        query_text,
                    ),
                    "variable_name": variable_name,
                    "entry_event": EditorOperationService._detect_blueprint_entry_event_from_request(
                        request,
                        query_text,
                        default="BeginPlay" if template_id == "set_variable" else "",
                    ),
                    "compile_after_edit": bool(request.payload.get("compile_after_edit", True)),
                }
                if template_id == "set_variable":
                    payload["variable_value"] = request.payload.get(
                        "variable_value",
                        request.payload.get("default_value", ""),
                    )
                return EditorOperationProposalRequest(
                    operation_type="add_blueprint_node_template",
                    payload=payload,
                    reason=query_text,
                    requested_by="agent_chat",
                    context=request.context.model_dump(mode="json"),
                )

        function_signal = any(
            token in query_lower or token in query_text
            for token in ("function", "func", "\u51fd\u6570", "\u65b9\u6cd5")
        )
        call_function_signal = any(
            token in query_lower or token in query_text
            for token in ("call", "invoke", "execute", "\u8c03\u7528", "\u6267\u884c")
        )
        if blueprint_signal and function_signal and variable_node_signal and call_function_signal:
            function_name = (
                str(request.payload.get("function_name") or "").strip()
                or EditorOperationService._extract_blueprint_function_name_from_text(query_text)
            )
            if function_name:
                blueprint_path = EditorOperationService._detect_blueprint_path_from_request(
                    request,
                    query_text,
                    context_bundle,
                )
                return EditorOperationProposalRequest(
                    operation_type="add_blueprint_node_template",
                    payload={
                        "blueprint_path": blueprint_path or "",
                        "template_id": "call_function",
                        "graph_name": EditorOperationService._detect_blueprint_graph_name_from_request(
                            request,
                            query_text,
                        ),
                        "function_name": function_name,
                        "entry_event": EditorOperationService._detect_blueprint_entry_event_from_request(
                            request,
                            query_text,
                            default="BeginPlay",
                        ),
                        "compile_after_edit": bool(request.payload.get("compile_after_edit", True)),
                    },
                    reason=query_text,
                    requested_by="agent_chat",
                    context=request.context.model_dump(mode="json"),
                )

        wants_blueprint_print_string = (
            ("蓝图" in query_text or "blueprint" in query_lower or "bp_" in query_lower)
            and any(token in query_lower or token in query_text for token in ("print string", "printstring", "打印字符串", "打印文本"))
            and any(
                token in query_lower or token in query_text
                for token in (
                    "add",
                    "create",
                    "insert",
                    "放",
                    "添加",
                    "加上",
                    "加一个",
                    "加个",
                    "增加",
                    "插入",
                    "创建",
                )
            )
        )
        if wants_blueprint_print_string:
            blueprint_path = EditorOperationService._detect_blueprint_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            graph_name = EditorOperationService._detect_blueprint_graph_name_from_request(
                request,
                query_text,
            )
            entry_event_default = (
                "BeginPlay"
                if graph_name == "EventGraph"
                and not EditorOperationService._detect_unconnected_blueprint_node_intent(query_text)
                else ""
            )
            return EditorOperationProposalRequest(
                operation_type="add_blueprint_node_template",
                payload={
                    "blueprint_path": blueprint_path or "",
                    "template_id": "print_string",
                    "graph_name": graph_name,
                    "message": request.payload.get("message")
                    or request.payload.get("string_value")
                    or "Hello from UEAgent",
                    "entry_event": EditorOperationService._detect_blueprint_entry_event_from_request(
                        request,
                        query_text,
                        default=entry_event_default,
                    ),
                    "compile_after_edit": bool(request.payload.get("compile_after_edit", True)),
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        blueprint_event_name = EditorOperationService._detect_blueprint_event_name_from_request(
            request,
            query_text,
        )
        wants_blueprint_event_stub = (
            blueprint_signal
            and bool(blueprint_event_name)
            and add_signal
            and not print_string_signal
            and not variable_signal
            and not function_signal
        )
        if wants_blueprint_event_stub:
            blueprint_path = EditorOperationService._detect_blueprint_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            return EditorOperationProposalRequest(
                operation_type="create_blueprint_event_stub",
                payload={
                    "blueprint_path": blueprint_path or "",
                    "event_name": blueprint_event_name,
                    "graph_name": EditorOperationService._detect_blueprint_graph_name_from_request(
                        request,
                        query_text,
                    ),
                    "node_comment": request.payload.get("node_comment") or "",
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        wants_blueprint = (
            ("蓝图" in query_text or "blueprint" in query_lower or "bp_" in query_lower)
            and any(token in query_lower or token in query_text for token in ("创建", "新建", "生成", "create", "make"))
        )
        if wants_blueprint:
            parent_class = "/Script/Engine.Actor"
            if "character" in query_lower or "角色" in query_text:
                parent_class = "/Script/Engine.Character"
            elif "pawn" in query_lower:
                parent_class = "/Script/Engine.Pawn"
            asset_name = EditorOperationService._extract_asset_name_from_text(query_text, "BP_AgentCreatedActor")
            if not asset_name.startswith("BP_"):
                asset_name = f"BP_{asset_name}"
            return EditorOperationProposalRequest(
                operation_type="create_blueprint_asset",
                payload={
                    "parent_class": request.payload.get("parent_class") or parent_class,
                    "target_folder": request.payload.get("target_folder") or "/Game/Blueprints",
                    "asset_name": request.payload.get("asset_name") or asset_name,
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        selected_asset = EditorOperationService._selected_asset_path(request)
        wants_duplicate_asset = any(
            token in query_lower or token in query_text
            for token in ("duplicate", "copy", "clone", "复制", "拷贝", "克隆")
        ) and any(
            token in query_lower or token in query_text
            for token in ("asset", "blueprint", "bp_", "wbp_", "sm_", "mi_", "/game/", "资产", "蓝图", "材质")
        )
        if wants_duplicate_asset:
            source_asset_path = EditorOperationService._detect_asset_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            new_name = request.payload.get("new_name") or EditorOperationService._extract_duplicate_asset_new_name_from_text(
                query_text,
                source_asset_path,
            )
            return EditorOperationProposalRequest(
                operation_type="duplicate_asset",
                payload={
                    "source_asset_path": source_asset_path or "",
                    "new_name": new_name,
                    "target_folder": request.payload.get("target_folder") or "",
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        wants_fixup_redirectors = any(
            token in query_lower or token in query_text
            for token in ("redirector", "redirectors", "重定向器", "redirector修复")
        ) and any(
            token in query_lower or token in query_text
            for token in ("fix", "fixup", "repair", "clean", "cleanup", "修复", "清理")
        )
        if wants_fixup_redirectors:
            folder_path = EditorOperationService._detect_redirector_folder_from_request(request, query_text)
            return EditorOperationProposalRequest(
                operation_type="fixup_redirectors",
                payload={
                    "folder_path": request.payload.get("folder_path") or folder_path,
                    "recursive": request.payload.get("recursive", True),
                    "max_redirectors": request.payload.get("max_redirectors", 50),
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        wants_rename = selected_asset and any(
            token in query_lower or token in query_text
            for token in ("rename", "重命名", "改名", "改成", "改为")
        )
        if wants_rename:
            default_name = str(selected_asset).rstrip("/").rsplit("/", 1)[-1].split(".")[-1]
            new_name = request.payload.get("new_name") or EditorOperationService._extract_asset_name_from_text(
                query_text,
                default_name,
            )
            return EditorOperationProposalRequest(
                operation_type="rename_selected_asset",
                payload={"asset_path": selected_asset, "new_name": new_name},
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        wants_static_mesh_settings = selected_asset and (
            "nanite" in query_lower
            or "碰撞" in query_text
            or "collision" in query_lower
            or "lightmap" in query_lower
            or "lod" in query_lower
        )
        if wants_static_mesh_settings:
            settings: dict[str, Any] = {}
            if "nanite" in query_lower:
                settings["nanite_enabled"] = not any(
                    token in query_lower or token in query_text for token in ("disable", "off", "关闭", "禁用")
                )
            if "use_complex_as_simple" in query_lower or "复杂碰撞作为简单" in query_text:
                settings["collision_complexity"] = "use_complex_as_simple"
            elif "use_simple_as_complex" in query_lower or "简单碰撞作为复杂" in query_text:
                settings["collision_complexity"] = "use_simple_as_complex"
            elif "simple_and_complex" in query_lower or "简单和复杂" in query_text:
                settings["collision_complexity"] = "simple_and_complex"
            lightmap_match = re.search(
                r"lightmap(?:\s+resolution)?\s*(\d{1,4})|光照贴图(?:分辨率)?\s*(\d{1,4})",
                query_text,
                flags=re.IGNORECASE,
            )
            if lightmap_match:
                settings["lightmap_resolution"] = int(lightmap_match.group(1) or lightmap_match.group(2))
            if not settings:
                return None
            return EditorOperationProposalRequest(
                operation_type="apply_static_mesh_basic_settings",
                payload={"asset_path": selected_asset, "settings": settings},
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )
        compile_signal = any(
            token in query_lower or token in query_text
            for token in ("compile", "recompile", "build blueprint", "编译", "重新编译")
        )
        blueprint_compile_path = (
            EditorOperationService._detect_blueprint_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            if compile_signal
            else None
        )
        wants_blueprint_compile = compile_signal and (
            bool(blueprint_compile_path)
            or "blueprint" in query_lower
            or "bp_" in query_lower
            or "蓝图" in query_text
            or (bool(selected_asset) and str(selected_asset).lower().endswith("_c"))
        )
        if wants_blueprint_compile:
            return EditorOperationProposalRequest(
                operation_type="compile_blueprint",
                payload={"blueprint_path": blueprint_compile_path or selected_asset or ""},
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )
        return None

    @staticmethod
    def _normalize_asset_path(value: Any, *, require_game_root: bool = True) -> str:
        path = str(value or "").strip().replace("\\", "/")
        if path.endswith(".uasset"):
            path = path[: -len(".uasset")]
        if "." in path and path.startswith("/"):
            package_path, object_name = path.rsplit(".", 1)
            if object_name and package_path.endswith("/" + object_name):
                path = package_path
        if not path.startswith("/"):
            path = "/Game/" + path.lstrip("/")
        while "//" in path:
            path = path.replace("//", "/")
        if ".." in path.split("/"):
            raise EditorOperationValidationError("asset_path_contains_parent_traversal")
        if require_game_root and not (path == "/Game" or path.startswith("/Game/")):
            raise EditorOperationValidationError("asset_path_must_be_under_game", {"asset_path": path})
        if len(path) > 240:
            raise EditorOperationValidationError("asset_path_too_long", {"asset_path": path})
        return path

    @staticmethod
    def _normalize_folder(value: Any) -> str:
        folder = EditorOperationService._normalize_asset_path(value, require_game_root=True).rstrip("/")
        if "." in folder:
            raise EditorOperationValidationError("target_folder_must_not_be_object_path", {"target_folder": folder})
        return folder

    @staticmethod
    def _normalize_redirector_folder(value: Any) -> str:
        folder = EditorOperationService._normalize_folder(value)
        if folder == "/Game":
            raise EditorOperationValidationError(
                "redirector_folder_too_broad",
                {"folder_path": folder, "rule": "Use a bounded subfolder such as /Game/Blueprints."},
            )
        return folder

    @staticmethod
    def _normalize_asset_name(value: Any, field_name: str = "asset_name") -> str:
        name = str(value or "").strip()
        if not _ASSET_NAME_RE.match(name):
            raise EditorOperationValidationError(
                f"{field_name}_invalid",
                {
                    field_name: name,
                    "rule": "Use 2-64 characters. Start with a letter. Only letters, numbers, and underscore are allowed.",
                },
            )
        return name

    @staticmethod
    def _normalize_class_path(value: Any) -> str:
        class_path = str(value or "").strip()
        if not class_path:
            raise EditorOperationValidationError("parent_class_required")
        if ".." in class_path or "\\" in class_path:
            raise EditorOperationValidationError("parent_class_invalid", {"parent_class": class_path})
        if len(class_path) > 180 or not _CLASS_NAME_RE.match(class_path):
            raise EditorOperationValidationError("parent_class_invalid", {"parent_class": class_path})
        return class_path

    @staticmethod
    def _normalize_static_mesh_settings(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict) or not value:
            raise EditorOperationValidationError("settings_must_be_non_empty_object")
        unknown = sorted(set(value) - STATIC_MESH_SETTING_KEYS)
        if unknown:
            raise EditorOperationValidationError(
                "settings_contains_unsupported_fields",
                {"unsupported_fields": unknown, "allowed_fields": sorted(STATIC_MESH_SETTING_KEYS)},
            )

        normalized: dict[str, Any] = {}
        for key, raw_value in value.items():
            if key in {"nanite_enabled", "generate_lightmap_uv"}:
                if not isinstance(raw_value, bool):
                    raise EditorOperationValidationError(f"{key}_must_be_boolean")
                normalized[key] = raw_value
            elif key == "lightmap_resolution":
                if not isinstance(raw_value, int) or raw_value < 4 or raw_value > 4096:
                    raise EditorOperationValidationError(
                        "lightmap_resolution_out_of_range",
                        {"min": 4, "max": 4096},
                    )
                normalized[key] = raw_value
            elif key == "collision_complexity":
                text = str(raw_value or "").strip().lower()
                if text not in STATIC_MESH_COLLISION_VALUES:
                    raise EditorOperationValidationError(
                        "collision_complexity_invalid",
                        {"allowed_values": sorted(STATIC_MESH_COLLISION_VALUES)},
                    )
                normalized[key] = text
            elif key == "lod_group":
                text = str(raw_value or "").strip()
                if not text or len(text) > 80 or not _SAFE_TEXT_RE.match(text):
                    raise EditorOperationValidationError("lod_group_invalid")
                normalized[key] = text
        return normalized

    @staticmethod
    def _normalize_blueprint_variable_type(value: Any) -> str:
        text = str(value or "").strip()
        alias = BLUEPRINT_VARIABLE_TYPE_ALIASES.get(text.lower())
        if alias:
            return alias
        if text in BLUEPRINT_VARIABLE_TYPES:
            return text
        if not text or len(text) > 120 or not _CLASS_NAME_RE.match(text):
            raise EditorOperationValidationError("variable_type_invalid", {"variable_type": text})
        if not (text.startswith("/Script/") or text.startswith("/Game/")):
            raise EditorOperationValidationError(
                "variable_type_not_whitelisted",
                {
                    "variable_type": text,
                    "allowed_builtin_types": sorted(BLUEPRINT_VARIABLE_TYPES),
                    "allowed_aliases": sorted(BLUEPRINT_VARIABLE_TYPE_ALIASES),
                    "allowed_custom_prefixes": ["/Script/", "/Game/"],
                },
            )
        return text

    @staticmethod
    def _normalize_optional_string(value: Any, *, max_length: int = 120) -> str:
        text = str(value or "").strip()
        if len(text) > max_length:
            raise EditorOperationValidationError("text_field_too_long", {"max_length": max_length})
        return text

    @staticmethod
    def _normalize_graph_name(value: Any) -> str:
        text = str(value or "EventGraph").strip() or "EventGraph"
        if not _ASSET_NAME_RE.match(text):
            raise EditorOperationValidationError("graph_name_invalid", {"graph_name": text})
        return text

    @staticmethod
    def _normalize_blueprint_node_template_id(value: Any) -> str:
        text = str(value or "").strip().replace("-", "_").replace(" ", "_").lower()
        aliases = {
            "branch": "branch_print_string",
            "branch_print": "branch_print_string",
            "branch_printstring": "branch_print_string",
            "branch_print_string": "branch_print_string",
            "call": "call_function",
            "call_function": "call_function",
            "delay": "delay_print_string",
            "delay_print": "delay_print_string",
            "delay_printstring": "delay_print_string",
            "delay_print_string": "delay_print_string",
            "enhanced_input": "enhanced_input_action_event",
            "enhanced_input_action": "enhanced_input_action_event",
            "enhanced_input_action_event": "enhanced_input_action_event",
            "enhanced_input_print": "enhanced_input_print_string",
            "enhanced_input_printstring": "enhanced_input_print_string",
            "enhanced_input_print_string": "enhanced_input_print_string",
            "function": "call_function",
            "function_call": "call_function",
            "get": "get_variable",
            "get_var": "get_variable",
            "get_variable": "get_variable",
            "input_action_print": "enhanced_input_print_string",
            "input_action_printstring": "enhanced_input_print_string",
            "input_action_print_string": "enhanced_input_print_string",
            "if_print_string": "branch_print_string",
            "ifthenelse_print_string": "branch_print_string",
            "print": "print_string",
            "printstring": "print_string",
            "print_string": "print_string",
            "sequence": "sequence_print_strings",
            "sequence_print": "sequence_print_strings",
            "sequence_print_string": "sequence_print_strings",
            "sequence_print_strings": "sequence_print_strings",
            "set": "set_variable",
            "set_var": "set_variable",
            "set_variable": "set_variable",
            "variable_get": "get_variable",
            "variable_set": "set_variable",
            "延迟打印": "delay_print_string",
            "打印字符串": "print_string",
            "打印文本": "print_string",
        }
        text = aliases.get(text, text)
        if text not in BLUEPRINT_NODE_TEMPLATE_IDS:
            raise EditorOperationValidationError(
                "blueprint_node_template_not_supported_in_v1",
                {
                    "template_id": text,
                    "allowed_template_ids": sorted(BLUEPRINT_NODE_TEMPLATE_IDS),
                },
            )
        return text

    @staticmethod
    def _normalize_blueprint_node_entry_event(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        normalized = text.replace("_", "").replace(" ", "").lower()
        aliases = {
            "actorbeginoverlap": "ActorBeginOverlap",
            "beginoverlap": "ActorBeginOverlap",
            "beginplay": "BeginPlay",
            "actorendoverlap": "ActorEndOverlap",
            "endoverlap": "ActorEndOverlap",
            "eventbeginplay": "BeginPlay",
            "receivebeginplay": "BeginPlay",
            "\u5f00\u59cb\u91cd\u53e0": "ActorBeginOverlap",
            "\u8fdb\u5165\u91cd\u53e0": "ActorBeginOverlap",
            "\u7ed3\u675f\u91cd\u53e0": "ActorEndOverlap",
            "\u79bb\u5f00\u91cd\u53e0": "ActorEndOverlap",
            "开始播放": "BeginPlay",
        }
        event_name = aliases.get(normalized, text)
        if event_name not in BLUEPRINT_NODE_ENTRY_EVENTS:
            raise EditorOperationValidationError(
                "blueprint_node_entry_event_not_supported_in_v1",
                {
                    "entry_event": text,
                    "allowed_entry_events": sorted(BLUEPRINT_NODE_ENTRY_EVENTS),
                },
            )
        return event_name

    @staticmethod
    def _normalize_boolean_field(value: Any, field_name: str, *, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, int | float):
            return bool(value)
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "on"}:
            return True
        if text in {"0", "false", "no", "n", "off"}:
            return False
        raise EditorOperationValidationError(
            "boolean_field_invalid",
            {"field": field_name, "value": str(value)},
        )

    @staticmethod
    def _normalize_blueprint_branch_path(value: Any) -> str:
        text = str(value or "true").strip().replace("-", "_").replace(" ", "_").lower()
        aliases = {
            "1": "true",
            "then": "true",
            "true": "true",
            "true_pin": "true",
            "condition_true": "true",
            "0": "false",
            "else": "false",
            "false": "false",
            "false_pin": "false",
            "condition_false": "false",
        }
        text = aliases.get(text, text)
        if text not in BLUEPRINT_BRANCH_PATHS:
            raise EditorOperationValidationError(
                "blueprint_branch_path_not_supported_in_v1",
                {
                    "branch_path": text,
                    "allowed_branch_paths": sorted(BLUEPRINT_BRANCH_PATHS),
                },
            )
        return text

    @staticmethod
    def _normalize_blueprint_node_identifier(value: Any, field_name: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise EditorOperationValidationError(f"{field_name}_required")
        if len(text) > 120 or "\\" in text or ".." in text:
            raise EditorOperationValidationError(f"{field_name}_invalid", {field_name: text})
        if not re.match(r"^[A-Za-z0-9_.:-]+$", text):
            raise EditorOperationValidationError(
                f"{field_name}_invalid",
                {
                    field_name: text,
                    "rule": "Use a graph snapshot node_id or generated node_name. Letters, numbers, underscore, dash, dot and colon are allowed.",
                },
            )
        return text

    @staticmethod
    def _normalize_blueprint_pin_name(value: Any, field_name: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise EditorOperationValidationError(f"{field_name}_required")
        if len(text) > 120 or "\\" in text or ".." in text:
            raise EditorOperationValidationError(f"{field_name}_invalid", {field_name: text})
        if not re.match(r"^[A-Za-z0-9_ .:-]+$", text):
            raise EditorOperationValidationError(
                f"{field_name}_invalid",
                {
                    field_name: text,
                    "rule": "Use the exact pin_name from get_blueprint_graph. Letters, numbers, underscore, space, dash, dot and colon are allowed.",
                },
            )
        return text

    def _normalize_blueprint_template_messages(self, payload: dict[str, Any]) -> list[str]:
        raw_messages = payload.get("messages")
        messages: list[str] = []
        if isinstance(raw_messages, list):
            for item in raw_messages[:2]:
                cleaned = self._clean_text(item, max_length=240)
                if cleaned:
                    messages.append(cleaned)
        elif raw_messages is not None:
            cleaned = self._clean_text(raw_messages, max_length=240)
            if cleaned:
                messages.append(cleaned)

        for key in ("message", "message_1", "message_2", "string_value"):
            if len(messages) >= 2:
                break
            cleaned = self._clean_text(payload.get(key), max_length=240)
            if cleaned and cleaned not in messages:
                messages.append(cleaned)

        while len(messages) < 2:
            messages.append(f"Sequence step {len(messages) + 1} from UEAgent")
        return messages[:2]

    def _normalize_blueprint_node_position(self, value: Any) -> dict[str, float]:
        if not isinstance(value, dict):
            return {}
        return {
            "x": self._normalize_finite_float(value.get("x", value.get("X", 0.0)), "node_position_x"),
            "y": self._normalize_finite_float(value.get("y", value.get("Y", 0.0)), "node_position_y"),
        }

    def _normalize_batch_renames(self, value: Any) -> list[dict[str, str]]:
        if not isinstance(value, list) or not value:
            raise EditorOperationValidationError("renames_must_be_non_empty_array")
        if len(value) > 20:
            raise EditorOperationValidationError("batch_rename_too_many_items", {"max_items": 20})

        normalized: list[dict[str, str]] = []
        seen_sources: set[str] = set()
        seen_targets: set[str] = set()
        for index, raw_item in enumerate(value):
            if not isinstance(raw_item, dict):
                raise EditorOperationValidationError("rename_item_must_be_object", {"index": index})
            asset_path = self._normalize_asset_path(raw_item.get("asset_path"))
            new_name = self._normalize_asset_name(raw_item.get("new_name"), "new_name")
            folder = asset_path.rsplit("/", 1)[0]
            old_name = asset_path.rsplit("/", 1)[-1]
            target_path = f"{folder}/{new_name}"
            if old_name == new_name:
                raise EditorOperationValidationError(
                    "batch_rename_item_matches_current_name",
                    {"index": index, "asset_path": asset_path, "new_name": new_name},
                )
            if asset_path in seen_sources:
                raise EditorOperationValidationError("batch_rename_duplicate_source", {"asset_path": asset_path})
            if target_path in seen_targets:
                raise EditorOperationValidationError("batch_rename_duplicate_target", {"target_path": target_path})
            seen_sources.add(asset_path)
            seen_targets.add(target_path)
            normalized.append(
                {
                    "asset_path": asset_path,
                    "current_name": old_name,
                    "new_name": new_name,
                    "target_path": target_path,
                }
            )
        return normalized

    def _normalize_asset_paths_for_move(self, value: Any, target_folder: str) -> list[dict[str, str]]:
        if not isinstance(value, list) or not value:
            raise EditorOperationValidationError("asset_paths_must_be_non_empty_array")
        if len(value) > 20:
            raise EditorOperationValidationError("move_assets_too_many_items", {"max_items": 20})

        normalized: list[dict[str, str]] = []
        seen_sources: set[str] = set()
        seen_targets: set[str] = set()
        for index, raw_value in enumerate(value):
            asset_path = self._normalize_asset_path(raw_value)
            asset_name = asset_path.rsplit("/", 1)[-1]
            current_folder = asset_path.rsplit("/", 1)[0]
            if current_folder == target_folder:
                raise EditorOperationValidationError(
                    "move_asset_target_folder_matches_current",
                    {"index": index, "asset_path": asset_path, "target_folder": target_folder},
                )
            target_path = f"{target_folder}/{asset_name}"
            if asset_path in seen_sources:
                raise EditorOperationValidationError("move_assets_duplicate_source", {"asset_path": asset_path})
            if target_path in seen_targets:
                raise EditorOperationValidationError("move_assets_duplicate_target", {"target_path": target_path})
            seen_sources.add(asset_path)
            seen_targets.add(target_path)
            normalized.append(
                {
                    "asset_path": asset_path,
                    "asset_name": asset_name,
                    "target_folder": target_folder,
                    "target_path": target_path,
                }
            )
        return normalized

    @staticmethod
    def _normalize_umg_widget_class(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise EditorOperationValidationError("widget_class_required")
        alias = UMG_WIDGET_CLASS_ALIASES.get(text.replace("_", "").replace(" ", "").lower())
        if alias:
            return alias
        if text not in UMG_WIDGET_CLASS_ALLOWLIST:
            raise EditorOperationValidationError(
                "widget_class_not_supported_in_v1",
                {
                    "widget_class": text,
                    "allowed_aliases": sorted(UMG_WIDGET_CLASS_ALIASES),
                    "allowed_classes": sorted(UMG_WIDGET_CLASS_ALLOWLIST),
                },
            )
        return text

    @staticmethod
    def _normalize_umg_visibility(value: Any) -> str:
        text = str(value or "").strip().replace("-", "_").replace(" ", "_").lower()
        text = UMG_VISIBILITY_ALIASES.get(text.replace("_", " "), UMG_VISIBILITY_ALIASES.get(text, text))
        if text not in UMG_VISIBILITY_VALUES:
            raise EditorOperationValidationError(
                "widget_visibility_not_supported_in_v1",
                {"visibility": text, "allowed_values": sorted(UMG_VISIBILITY_VALUES)},
            )
        return text

    @staticmethod
    def _normalize_finite_float(
        value: Any,
        field_name: str,
        *,
        min_value: float = -1_000_000.0,
        max_value: float = 1_000_000.0,
    ) -> float:
        if isinstance(value, bool):
            raise EditorOperationValidationError(f"{field_name}_must_be_number")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise EditorOperationValidationError(f"{field_name}_must_be_number") from exc
        if not math.isfinite(number) or number < min_value or number > max_value:
            raise EditorOperationValidationError(
                f"{field_name}_out_of_range",
                {"min": min_value, "max": max_value, "value": value},
            )
        return number

    @staticmethod
    def _normalize_int_range(value: Any, field_name: str, *, min_value: int, max_value: int) -> int:
        if isinstance(value, bool):
            raise EditorOperationValidationError(f"{field_name}_must_be_integer")
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise EditorOperationValidationError(f"{field_name}_must_be_integer") from exc
        if number < min_value or number > max_value:
            raise EditorOperationValidationError(
                f"{field_name}_out_of_range",
                {"min": min_value, "max": max_value, "value": value},
            )
        return number

    def _normalize_vector3(
        self,
        value: Any,
        *,
        field_name: str,
        defaults: tuple[float, float, float],
        component_names: tuple[str, str, str] = ("x", "y", "z"),
        min_value: float = -1_000_000.0,
        max_value: float = 1_000_000.0,
    ) -> dict[str, float]:
        if value is None:
            values = list(defaults)
        elif isinstance(value, list | tuple) and len(value) == 3:
            values = list(value)
        elif isinstance(value, dict):
            values = [
                value.get(component_names[0], defaults[0]),
                value.get(component_names[1], defaults[1]),
                value.get(component_names[2], defaults[2]),
            ]
        else:
            raise EditorOperationValidationError(f"{field_name}_must_be_vector3")
        return {
            component_names[0]: self._normalize_finite_float(
                values[0],
                f"{field_name}_{component_names[0]}",
                min_value=min_value,
                max_value=max_value,
            ),
            component_names[1]: self._normalize_finite_float(
                values[1],
                f"{field_name}_{component_names[1]}",
                min_value=min_value,
                max_value=max_value,
            ),
            component_names[2]: self._normalize_finite_float(
                values[2],
                f"{field_name}_{component_names[2]}",
                min_value=min_value,
                max_value=max_value,
            ),
        }

    def _normalize_vector2(
        self,
        value: Any,
        *,
        field_name: str,
        defaults: tuple[float, float],
        min_value: float = -100_000.0,
        max_value: float = 100_000.0,
    ) -> dict[str, float]:
        if value is None:
            values = list(defaults)
        elif isinstance(value, list | tuple) and len(value) == 2:
            values = list(value)
        elif isinstance(value, dict):
            values = [value.get("x", value.get("X", defaults[0])), value.get("y", value.get("Y", defaults[1]))]
        else:
            raise EditorOperationValidationError(f"{field_name}_must_be_vector2")
        return {
            component: self._normalize_finite_float(
                values[index],
                f"{field_name}_{component}",
                min_value=min_value,
                max_value=max_value,
            )
            for index, component in enumerate(("x", "y"))
        }

    def _normalize_umg_anchors(self, value: Any) -> dict[str, dict[str, float]]:
        if not isinstance(value, dict):
            raise EditorOperationValidationError("anchors_must_be_object")
        if isinstance(value.get("minimum"), dict | list | tuple) or isinstance(value.get("maximum"), dict | list | tuple):
            minimum = self._normalize_vector2(
                value.get("minimum"),
                field_name="anchors_minimum",
                defaults=(0.0, 0.0),
                min_value=0.0,
                max_value=1.0,
            )
            maximum = self._normalize_vector2(
                value.get("maximum"),
                field_name="anchors_maximum",
                defaults=(0.0, 0.0),
                min_value=0.0,
                max_value=1.0,
            )
        else:
            minimum = {
                "x": self._normalize_finite_float(value.get("min_x", 0.0), "anchors_min_x", min_value=0.0, max_value=1.0),
                "y": self._normalize_finite_float(value.get("min_y", 0.0), "anchors_min_y", min_value=0.0, max_value=1.0),
            }
            maximum = {
                "x": self._normalize_finite_float(value.get("max_x", 0.0), "anchors_max_x", min_value=0.0, max_value=1.0),
                "y": self._normalize_finite_float(value.get("max_y", 0.0), "anchors_max_y", min_value=0.0, max_value=1.0),
            }
        if minimum["x"] > maximum["x"] or minimum["y"] > maximum["y"]:
            raise EditorOperationValidationError("anchors_minimum_must_not_exceed_maximum")
        return {"minimum": minimum, "maximum": maximum}

    def _normalize_umg_layout(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise EditorOperationValidationError("layout_must_be_object")
        normalized: dict[str, Any] = {}
        if "position" in value:
            normalized["position"] = self._normalize_vector2(value.get("position"), field_name="position", defaults=(0.0, 0.0))
        if "size" in value:
            normalized["size"] = self._normalize_vector2(value.get("size"), field_name="size", defaults=(100.0, 30.0), min_value=0.0)
        if "alignment" in value:
            normalized["alignment"] = self._normalize_vector2(
                value.get("alignment"),
                field_name="alignment",
                defaults=(0.0, 0.0),
                min_value=-10.0,
                max_value=10.0,
            )
        if "anchors" in value:
            normalized["anchors"] = self._normalize_umg_anchors(value.get("anchors"))
        if not normalized:
            raise EditorOperationValidationError("layout_requires_position_size_alignment_or_anchors")
        return normalized

    def _normalize_margin(self, value: Any, *, field_name: str = "padding") -> dict[str, float]:
        if isinstance(value, int | float | str):
            uniform = self._normalize_finite_float(value, field_name, min_value=-10_000.0, max_value=10_000.0)
            return {"left": uniform, "top": uniform, "right": uniform, "bottom": uniform}
        if isinstance(value, list | tuple):
            if len(value) == 2:
                horizontal = self._normalize_finite_float(value[0], f"{field_name}_horizontal", min_value=-10_000.0, max_value=10_000.0)
                vertical = self._normalize_finite_float(value[1], f"{field_name}_vertical", min_value=-10_000.0, max_value=10_000.0)
                return {"left": horizontal, "top": vertical, "right": horizontal, "bottom": vertical}
            if len(value) == 4:
                return {
                    component: self._normalize_finite_float(raw, f"{field_name}_{component}", min_value=-10_000.0, max_value=10_000.0)
                    for component, raw in zip(("left", "top", "right", "bottom"), value, strict=True)
                }
        if isinstance(value, dict):
            return {
                "left": self._normalize_finite_float(value.get("left", 0.0), f"{field_name}_left", min_value=-10_000.0, max_value=10_000.0),
                "top": self._normalize_finite_float(value.get("top", 0.0), f"{field_name}_top", min_value=-10_000.0, max_value=10_000.0),
                "right": self._normalize_finite_float(value.get("right", 0.0), f"{field_name}_right", min_value=-10_000.0, max_value=10_000.0),
                "bottom": self._normalize_finite_float(value.get("bottom", 0.0), f"{field_name}_bottom", min_value=-10_000.0, max_value=10_000.0),
            }
        raise EditorOperationValidationError(f"{field_name}_must_be_number_array_or_object")

    @staticmethod
    def _normalize_umg_slot_type(value: Any) -> str:
        raw = str(value or "").strip().replace(" ", "").replace("-", "_").lower()
        aliases = {
            "horizontalboxslot": "HorizontalBoxSlot",
            "horizontal_box_slot": "HorizontalBoxSlot",
            "hboxslot": "HorizontalBoxSlot",
            "hbox": "HorizontalBoxSlot",
            "verticalboxslot": "VerticalBoxSlot",
            "vertical_box_slot": "VerticalBoxSlot",
            "vboxslot": "VerticalBoxSlot",
            "vbox": "VerticalBoxSlot",
            "overlayslot": "OverlaySlot",
            "overlay_slot": "OverlaySlot",
            "overlay": "OverlaySlot",
        }
        normalized = aliases.get(raw)
        if not normalized:
            raise EditorOperationValidationError(
                "slot_type_not_supported",
                {"allowed_types": ["HorizontalBoxSlot", "VerticalBoxSlot", "OverlaySlot"]},
            )
        return normalized

    @staticmethod
    def _normalize_umg_alignment(value: Any, *, axis: str) -> str:
        raw = str(value or "").strip().replace(" ", "_").replace("-", "_").lower()
        if axis == "horizontal":
            aliases = {
                "fill": "fill",
                "left": "left",
                "center": "center",
                "centre": "center",
                "right": "right",
            }
        else:
            aliases = {
                "fill": "fill",
                "top": "top",
                "center": "center",
                "centre": "center",
                "bottom": "bottom",
            }
        if raw not in aliases:
            raise EditorOperationValidationError(f"{axis}_alignment_not_supported")
        return aliases[raw]

    def _normalize_umg_slot_size(self, value: Any) -> dict[str, float | str]:
        if isinstance(value, str):
            raw_rule = value.strip().lower()
            raw_value = 1.0
        elif isinstance(value, dict):
            raw_rule = str(value.get("rule") or value.get("size_rule") or value.get("type") or "").strip().lower()
            raw_value = value.get("value", value.get("weight", 1.0))
        else:
            raise EditorOperationValidationError("slot_size_must_be_string_or_object")
        raw_rule = {"automatic": "auto", "auto": "auto", "fill": "fill"}.get(raw_rule, raw_rule)
        if raw_rule not in {"auto", "fill"}:
            raise EditorOperationValidationError("slot_size_rule_not_supported", {"allowed_rules": ["auto", "fill"]})
        return {
            "rule": raw_rule,
            "value": self._normalize_finite_float(raw_value, "slot_size_value", min_value=0.0, max_value=1000.0),
        }

    def _normalize_umg_slot_layout_v2(self, value: Any, slot_type: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise EditorOperationValidationError("layout_must_be_object")
        normalized: dict[str, Any] = {}
        if "padding" in value or "margin" in value:
            normalized["padding"] = self._normalize_margin(value.get("padding", value.get("margin")))
        if "horizontal_alignment" in value or "halign" in value:
            normalized["horizontal_alignment"] = self._normalize_umg_alignment(
                value.get("horizontal_alignment", value.get("halign")),
                axis="horizontal",
            )
        if "vertical_alignment" in value or "valign" in value:
            normalized["vertical_alignment"] = self._normalize_umg_alignment(
                value.get("vertical_alignment", value.get("valign")),
                axis="vertical",
            )
        if "size" in value:
            if slot_type not in {"HorizontalBoxSlot", "VerticalBoxSlot"}:
                raise EditorOperationValidationError("slot_size_only_supported_for_box_slots")
            normalized["size"] = self._normalize_umg_slot_size(value.get("size"))
        if not normalized:
            raise EditorOperationValidationError("slot_layout_requires_padding_alignment_or_size")
        return normalized

    def _normalize_color_value(self, value: Any, field_name: str) -> dict[str, float]:
        if isinstance(value, list | tuple) and len(value) in {3, 4}:
            raw_values = {
                "r": value[0],
                "g": value[1],
                "b": value[2],
                "a": value[3] if len(value) == 4 else 1.0,
            }
        elif isinstance(value, dict):
            raw_values = {
                "r": value.get("r", value.get("x", 0.0)),
                "g": value.get("g", value.get("y", 0.0)),
                "b": value.get("b", value.get("z", 0.0)),
                "a": value.get("a", value.get("w", 1.0)),
            }
        else:
            raise EditorOperationValidationError(f"{field_name}_must_be_color_object_or_array")
        return {
            component: self._normalize_finite_float(
                raw_value,
                f"{field_name}_{component}",
                min_value=0.0,
                max_value=1.0,
            )
            for component, raw_value in raw_values.items()
        }

    def _normalize_umg_appearance(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise EditorOperationValidationError("appearance_must_be_object")
        normalized: dict[str, Any] = {}
        if "render_opacity" in value or "opacity" in value:
            normalized["render_opacity"] = self._normalize_finite_float(
                value.get("render_opacity", value.get("opacity")),
                "render_opacity",
                min_value=0.0,
                max_value=1.0,
            )
        if "is_enabled" in value or "enabled" in value:
            normalized["is_enabled"] = self._normalize_bool(value.get("is_enabled", value.get("enabled")), "is_enabled")
        if "color_and_opacity" in value or "tint_color" in value or "color" in value:
            normalized["color_and_opacity"] = self._normalize_color_value(
                value.get("color_and_opacity", value.get("tint_color", value.get("color"))),
                "color_and_opacity",
            )
        if "font_size" in value:
            normalized["font_size"] = int(
                self._normalize_finite_float(value.get("font_size"), "font_size", min_value=6.0, max_value=256.0)
            )
        if not normalized:
            raise EditorOperationValidationError("appearance_requires_opacity_enabled_color_or_font_size")
        return normalized

    def _normalize_umg_brush(self, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            raise EditorOperationValidationError("brush_must_be_object")
        resource_type = str(value.get("resource_type") or value.get("type") or "").strip().lower()
        if not resource_type:
            if value.get("texture_path"):
                resource_type = "texture"
            elif value.get("material_path"):
                resource_type = "material"
        resource_type = {
            "image": "texture",
            "texture2d": "texture",
            "material_instance": "material",
            "materialinstance": "material",
            "mat": "material",
        }.get(resource_type, resource_type)
        if resource_type not in {"texture", "material"}:
            raise EditorOperationValidationError(
                "brush_resource_type_not_supported",
                {"resource_type": resource_type, "allowed_types": ["texture", "material"]},
            )
        resource_path = (
            value.get("resource_path")
            or value.get("asset_path")
            or value.get("texture_path")
            or value.get("material_path")
        )
        if not resource_path:
            raise EditorOperationValidationError("brush_resource_path_required")
        return {
            "resource_type": resource_type,
            "resource_path": self._normalize_asset_path(resource_path),
        }

    def _normalize_actor_transform(self, value: Any) -> dict[str, dict[str, float]]:
        if value is None:
            value = {}
        if not isinstance(value, dict):
            raise EditorOperationValidationError("transform_must_be_object")
        return {
            "location": self._normalize_vector3(
                value.get("location"),
                field_name="location",
                defaults=(0.0, 0.0, 0.0),
            ),
            "rotation": self._normalize_vector3(
                value.get("rotation"),
                field_name="rotation",
                defaults=(0.0, 0.0, 0.0),
                component_names=("pitch", "yaw", "roll"),
                min_value=-360_000.0,
                max_value=360_000.0,
            ),
            "scale": self._normalize_vector3(
                value.get("scale"),
                field_name="scale",
                defaults=(1.0, 1.0, 1.0),
                min_value=0.001,
                max_value=1000.0,
            ),
        }

    def _normalize_actor_transform_update(self, value: Any, *, field_name: str) -> dict[str, dict[str, float]]:
        if value is None:
            value = {}
        if not isinstance(value, dict):
            raise EditorOperationValidationError(f"{field_name}_must_be_object")
        normalized: dict[str, dict[str, float]] = {}
        if "location" in value:
            normalized["location"] = self._normalize_vector3(
                value.get("location"),
                field_name=f"{field_name}_location",
                defaults=(0.0, 0.0, 0.0),
            )
        if "rotation" in value:
            normalized["rotation"] = self._normalize_vector3(
                value.get("rotation"),
                field_name=f"{field_name}_rotation",
                defaults=(0.0, 0.0, 0.0),
                component_names=("pitch", "yaw", "roll"),
                min_value=-360_000.0,
                max_value=360_000.0,
            )
        if "scale" in value:
            normalized["scale"] = self._normalize_vector3(
                value.get("scale"),
                field_name=f"{field_name}_scale",
                defaults=(1.0, 1.0, 1.0),
                min_value=0.001,
                max_value=1000.0,
            )
        if not normalized:
            raise EditorOperationValidationError(f"{field_name}_requires_location_rotation_or_scale")
        return normalized

    def _normalize_actor_references(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            raise EditorOperationValidationError("actor_references_must_be_list")
        references = self._dedupe_strings([str(item) for item in value])
        if len(references) < 2:
            raise EditorOperationValidationError("actor_references_require_at_least_two")
        if len(references) > 12:
            raise EditorOperationValidationError("actor_references_limit_exceeded", {"max_items": 12})
        return references

    def _normalize_arrange_pattern(self, value: Any, *, actor_count: int) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise EditorOperationValidationError("pattern_must_be_object")
        pattern_type = str(value.get("type") or value.get("pattern_type") or "line").strip().lower()
        if pattern_type not in {"line", "grid", "circle"}:
            raise EditorOperationValidationError(
                "arrange_pattern_type_not_supported",
                {"allowed_types": ["line", "grid", "circle"]},
            )
        pattern: dict[str, Any] = {"type": pattern_type}
        if "origin" in value:
            pattern["origin"] = self._normalize_vector3(
                value.get("origin"),
                field_name="arrange_origin",
                defaults=(0.0, 0.0, 0.0),
            )
        axis = str(value.get("axis") or "x").strip().lower()
        if axis not in {"x", "y"}:
            raise EditorOperationValidationError("arrange_axis_not_supported", {"allowed_axes": ["x", "y"]})
        pattern["axis"] = axis
        spacing = self._normalize_finite_float(value.get("spacing", 200.0), "arrange_spacing", min_value=1.0, max_value=100_000.0)
        pattern["spacing"] = spacing
        if pattern_type == "grid":
            raw_columns = value.get("columns", value.get("cols", 0))
            columns = int(self._normalize_finite_float(raw_columns or max(2, math.ceil(math.sqrt(actor_count))), "arrange_columns", min_value=1.0, max_value=12.0))
            pattern["columns"] = min(max(columns, 1), actor_count)
        if pattern_type == "circle":
            default_radius = max(spacing, actor_count * spacing / math.tau)
            pattern["radius"] = self._normalize_finite_float(value.get("radius", default_radius), "arrange_radius", min_value=1.0, max_value=100_000.0)
        return pattern

    @staticmethod
    def _normalize_transform_mode(value: Any) -> str:
        mode = str(value or "absolute").strip().lower()
        if mode not in {"absolute", "delta"}:
            raise EditorOperationValidationError(
                "transform_mode_not_supported",
                {"transform_mode": mode, "allowed_modes": ["absolute", "delta"]},
            )
        return mode

    @staticmethod
    def _normalize_material_parameter_type(value: Any) -> str:
        parameter_type = str(value or "").strip().lower()
        if parameter_type not in MATERIAL_PARAMETER_TYPES:
            raise EditorOperationValidationError(
                "material_parameter_type_not_supported_in_v1",
                {"parameter_type": parameter_type, "allowed_types": sorted(MATERIAL_PARAMETER_TYPES)},
            )
        return parameter_type

    @staticmethod
    def _normalize_bool(value: Any, field_name: str) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int | float) and value in {0, 1}:
            return bool(value)
        text = str(value or "").strip().lower()
        if text in {"true", "1", "on", "enable", "enabled", "yes", "y", "打开", "开启", "启用", "是"}:
            return True
        if text in {"false", "0", "off", "disable", "disabled", "no", "n", "关闭", "禁用", "否"}:
            return False
        raise EditorOperationValidationError(
            f"{field_name}_must_be_boolean",
            {"value": value, "allowed_values": ["true", "false", "on", "off", "1", "0"]},
        )

    @staticmethod
    def _normalize_string_list(value: Any, field_name: str, *, max_items: int = 32, max_length: int = 80) -> list[str]:
        if isinstance(value, str):
            raw_values = [item.strip() for item in re.split(r"[,，;；]", value) if item.strip()]
        elif isinstance(value, list | tuple):
            raw_values = [str(item).strip() for item in value if str(item).strip()]
        else:
            raise EditorOperationValidationError(f"{field_name}_must_be_string_or_array")
        normalized: list[str] = []
        for item in raw_values:
            if len(item) > max_length:
                raise EditorOperationValidationError(f"{field_name}_item_too_long", {"item": item, "max_length": max_length})
            if item not in normalized:
                normalized.append(item)
        if len(normalized) > max_items:
            raise EditorOperationValidationError(f"{field_name}_too_many_items", {"max_items": max_items})
        return normalized

    def _normalize_actor_metadata(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise EditorOperationValidationError("metadata_must_be_object")
        metadata: dict[str, Any] = {}
        actor_label = self._normalize_optional_string(value.get("actor_label") or value.get("label") or "", max_length=120)
        if actor_label:
            metadata["actor_label"] = actor_label
        folder_path = self._normalize_optional_string(value.get("folder_path") or value.get("folder") or "", max_length=200)
        if folder_path:
            metadata["folder_path"] = folder_path.replace("\\", "/").strip("/")
        if "tags" in value:
            metadata["tags"] = self._normalize_string_list(value.get("tags"), "tags", max_items=24, max_length=64)
            tag_mode = str(value.get("tag_mode") or "replace").strip().lower()
            if tag_mode not in {"replace", "append", "remove"}:
                raise EditorOperationValidationError(
                    "tag_mode_not_supported",
                    {"tag_mode": tag_mode, "allowed_modes": ["replace", "append", "remove"]},
                )
            metadata["tag_mode"] = tag_mode
        if not metadata:
            raise EditorOperationValidationError("metadata_requires_actor_label_folder_path_or_tags")
        return metadata

    @staticmethod
    def _normalize_parameter_name(value: Any) -> str:
        parameter_name = str(value or "").strip()
        if not _PARAMETER_NAME_RE.match(parameter_name):
            raise EditorOperationValidationError(
                "material_parameter_name_invalid",
                {
                    "parameter_name": parameter_name,
                    "rule": "Use 1-80 characters. Start with a letter. Only letters, numbers, spaces, and underscore are allowed.",
                },
            )
        return parameter_name

    def _normalize_material_vector_value(self, value: Any) -> dict[str, float]:
        if isinstance(value, list | tuple) and len(value) in {3, 4}:
            raw_values = {
                "r": value[0],
                "g": value[1],
                "b": value[2],
                "a": value[3] if len(value) == 4 else 1.0,
            }
        elif isinstance(value, dict):
            raw_values = {
                "r": value.get("r", value.get("x", 0.0)),
                "g": value.get("g", value.get("y", 0.0)),
                "b": value.get("b", value.get("z", 0.0)),
                "a": value.get("a", value.get("w", 1.0)),
            }
        else:
            raise EditorOperationValidationError("material_vector_value_must_be_color_object_or_array")
        return {
            component: self._normalize_finite_float(
                raw_value,
                f"material_vector_{component}",
                min_value=-10_000.0,
                max_value=10_000.0,
            )
            for component, raw_value in raw_values.items()
        }

    def _normalize_payload(self, operation_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        if operation_type == "rename_selected_asset":
            asset_path = self._normalize_asset_path(payload.get("asset_path"))
            new_name = self._normalize_asset_name(payload.get("new_name"), "new_name")
            folder = asset_path.rsplit("/", 1)[0]
            old_name = asset_path.rsplit("/", 1)[-1]
            if old_name == new_name:
                raise EditorOperationValidationError("new_name_matches_current_name")
            return {
                "asset_path": asset_path,
                "current_name": old_name,
                "new_name": new_name,
                "target_path": f"{folder}/{new_name}",
            }

        if operation_type == "apply_static_mesh_basic_settings":
            asset_path = self._normalize_asset_path(payload.get("asset_path"))
            settings = self._normalize_static_mesh_settings(payload.get("settings"))
            before_snapshot = payload.get("before_snapshot") if isinstance(payload.get("before_snapshot"), dict) else {}
            return {
                "asset_path": asset_path,
                "asset_type": "StaticMesh",
                "settings": settings,
                "before_snapshot": before_snapshot,
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "create_blueprint_asset":
            parent_class = self._normalize_class_path(payload.get("parent_class"))
            target_folder = self._normalize_folder(payload.get("target_folder"))
            asset_name = self._normalize_asset_name(payload.get("asset_name"), "asset_name")
            return {
                "parent_class": parent_class,
                "target_folder": target_folder,
                "asset_name": asset_name,
                "target_path": f"{target_folder}/{asset_name}",
                "blueprint_type": "Blueprint",
            }

        if operation_type == "add_blueprint_variable":
            blueprint_path = self._normalize_asset_path(payload.get("blueprint_path"))
            variable_name = self._normalize_asset_name(payload.get("variable_name"), "variable_name")
            variable_type = self._normalize_blueprint_variable_type(payload.get("variable_type"))
            category = self._normalize_optional_string(payload.get("category") or "Agent", max_length=80)
            return {
                "blueprint_path": blueprint_path,
                "variable_name": variable_name,
                "variable_type": variable_type,
                "category": category,
                "default_value": self._clean_text(payload.get("default_value"), max_length=120),
                "editable": bool(payload.get("editable", True)),
                "expose_on_spawn": bool(payload.get("expose_on_spawn", False)),
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "add_blueprint_component":
            blueprint_path = self._normalize_asset_path(payload.get("blueprint_path"))
            component_name = self._normalize_asset_name(payload.get("component_name"), "component_name")
            component_class = self._normalize_class_path(payload.get("component_class"))
            attach_to = self._normalize_optional_string(payload.get("attach_to") or "", max_length=80)
            return {
                "blueprint_path": blueprint_path,
                "component_name": component_name,
                "component_class": component_class,
                "attach_to": attach_to or None,
                "transform": payload.get("transform") if isinstance(payload.get("transform"), dict) else {},
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "create_blueprint_event_stub":
            blueprint_path = self._normalize_asset_path(payload.get("blueprint_path"))
            event_name = str(payload.get("event_name") or "").strip()
            if event_name not in BLUEPRINT_EVENT_NAMES:
                raise EditorOperationValidationError(
                    "event_name_not_supported_in_v1",
                    {"event_name": event_name, "allowed_events": sorted(BLUEPRINT_EVENT_NAMES)},
                )
            graph_name = self._normalize_graph_name(payload.get("graph_name"))
            return {
                "blueprint_path": blueprint_path,
                "event_name": event_name,
                "graph_name": graph_name,
                "node_comment": self._clean_text(payload.get("node_comment"), max_length=160),
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "add_blueprint_node_template":
            blueprint_path = self._normalize_asset_path(payload.get("blueprint_path"))
            template_id = self._normalize_blueprint_node_template_id(payload.get("template_id"))
            entry_event_raw = payload.get("entry_event")
            if template_id == "get_variable":
                entry_event_raw = ""
            if template_id in {"enhanced_input_action_event", "enhanced_input_print_string"}:
                entry_event_raw = ""
            if template_id in {
                "branch_print_string",
                "call_function",
                "delay_print_string",
                "sequence_print_strings",
                "set_variable",
            } and not str(entry_event_raw or "").strip():
                entry_event_raw = "BeginPlay"
            normalized: dict[str, Any] = {
                "blueprint_path": blueprint_path,
                "template_id": template_id,
                "graph_name": self._normalize_graph_name(payload.get("graph_name")),
                "node_comment": self._clean_text(payload.get("node_comment"), max_length=160),
                "entry_event": self._normalize_blueprint_node_entry_event(entry_event_raw),
                "compile_after_edit": bool(payload.get("compile_after_edit", True)),
                "save_policy": "mark_dirty_only",
            }
            if template_id in {
                "branch_print_string",
                "delay_print_string",
                "enhanced_input_print_string",
                "print_string",
                "sequence_print_strings",
            }:
                normalized["message"] = self._clean_text(
                    payload.get("message") or payload.get("string_value") or "Hello from UEAgent",
                    max_length=240,
                )
                normalized["duration"] = self._normalize_finite_float(
                    payload.get("duration", 2.0),
                    "print_string_duration",
                    min_value=0.0,
                    max_value=60.0,
                )
                normalized["print_to_screen"] = bool(payload.get("print_to_screen", True))
                normalized["print_to_log"] = bool(payload.get("print_to_log", True))
            if template_id == "delay_print_string":
                normalized["delay_seconds"] = self._normalize_finite_float(
                    payload.get("delay_seconds", payload.get("delay", 1.0)),
                    "delay_seconds",
                    min_value=0.0,
                    max_value=60.0,
                )
            if template_id == "branch_print_string":
                normalized["condition_default"] = self._normalize_boolean_field(
                    payload.get("condition_default"),
                    "condition_default",
                    default=True,
                )
                normalized["branch_path"] = self._normalize_blueprint_branch_path(payload.get("branch_path"))
            if template_id == "sequence_print_strings":
                normalized["messages"] = self._normalize_blueprint_template_messages(payload)
                normalized["sequence_output_count"] = len(normalized["messages"])
            if template_id in {"get_variable", "set_variable"}:
                normalized["variable_name"] = self._normalize_asset_name(
                    payload.get("variable_name"),
                    "variable_name",
                )
                normalized["variable_scope"] = "self"
            if template_id == "set_variable":
                normalized["variable_value"] = self._normalize_optional_string(
                    payload.get("variable_value", payload.get("default_value", "")),
                    max_length=240,
                )
            if template_id == "call_function":
                normalized["function_name"] = self._normalize_asset_name(
                    payload.get("function_name"),
                    "function_name",
                )
                normalized["function_target"] = "self"
            if template_id in {"enhanced_input_action_event", "enhanced_input_print_string"}:
                normalized["input_action_path"] = self._normalize_asset_path(payload.get("input_action_path"))
            node_position = self._normalize_blueprint_node_position(payload.get("node_position"))
            if node_position:
                normalized["node_position"] = node_position
            return normalized

        if operation_type == "connect_blueprint_nodes":
            blueprint_path = self._normalize_asset_path(payload.get("blueprint_path"))
            return {
                "blueprint_path": blueprint_path,
                "graph_name": self._normalize_graph_name(payload.get("graph_name")),
                "source_node_id": self._normalize_blueprint_node_identifier(
                    payload.get("source_node_id", payload.get("source_node_name")),
                    "source_node_id",
                ),
                "source_pin_name": self._normalize_blueprint_pin_name(
                    payload.get("source_pin_name"),
                    "source_pin_name",
                ),
                "target_node_id": self._normalize_blueprint_node_identifier(
                    payload.get("target_node_id", payload.get("target_node_name")),
                    "target_node_id",
                ),
                "target_pin_name": self._normalize_blueprint_pin_name(
                    payload.get("target_pin_name"),
                    "target_pin_name",
                ),
                "compile_after_edit": bool(payload.get("compile_after_edit", True)),
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "compile_blueprint":
            blueprint_path = self._normalize_asset_path(payload.get("blueprint_path"))
            return {
                "blueprint_path": blueprint_path,
                "compile_mode": self._normalize_optional_string(payload.get("compile_mode") or "default", max_length=40),
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "batch_rename_assets":
            renames = self._normalize_batch_renames(payload.get("renames"))
            return {
                "renames": renames,
                "item_count": len(renames),
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "move_assets":
            target_folder = self._normalize_folder(payload.get("target_folder"))
            moves = self._normalize_asset_paths_for_move(payload.get("asset_paths"), target_folder)
            return {
                "asset_paths": [item["asset_path"] for item in moves],
                "target_folder": target_folder,
                "moves": moves,
                "item_count": len(moves),
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "duplicate_asset":
            source_asset_path = self._normalize_asset_path(
                payload.get("source_asset_path") or payload.get("asset_path") or payload.get("source_path")
            )
            source_folder = source_asset_path.rsplit("/", 1)[0]
            target_folder = self._normalize_folder(payload.get("target_folder") or source_folder)
            new_name = self._normalize_asset_name(payload.get("new_name"), "new_name")
            target_path = f"{target_folder}/{new_name}"
            if target_path == source_asset_path:
                raise EditorOperationValidationError(
                    "duplicate_target_matches_source",
                    {"source_asset_path": source_asset_path, "target_path": target_path},
                )
            return {
                "source_asset_path": source_asset_path,
                "source_asset_name": source_asset_path.rsplit("/", 1)[-1],
                "target_folder": target_folder,
                "new_name": new_name,
                "target_path": target_path,
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "fixup_redirectors":
            max_redirectors = self._normalize_int_range(
                payload.get("max_redirectors", 50),
                "max_redirectors",
                min_value=1,
                max_value=200,
            )
            return {
                "folder_path": self._normalize_redirector_folder(payload.get("folder_path")),
                "recursive": bool(payload.get("recursive", True)),
                "max_redirectors": max_redirectors,
                "save_policy": "editor_fixup_redirectors",
            }

        if operation_type == "add_umg_widget":
            widget_blueprint_path = self._normalize_asset_path(payload.get("widget_blueprint_path"))
            widget_name = self._normalize_asset_name(payload.get("widget_name"), "widget_name")
            widget_class = self._normalize_umg_widget_class(payload.get("widget_class"))
            parent_widget_name = self._normalize_optional_string(payload.get("parent_widget_name") or "", max_length=80)
            return {
                "widget_blueprint_path": widget_blueprint_path,
                "widget_name": widget_name,
                "widget_class": widget_class,
                "parent_widget_name": parent_widget_name or None,
                "text": self._clean_text(payload.get("text"), max_length=160),
                "is_variable": bool(payload.get("is_variable", True)),
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "set_umg_widget_text":
            widget_blueprint_path = self._normalize_asset_path(payload.get("widget_blueprint_path"))
            widget_name = self._normalize_asset_name(payload.get("widget_name"), "widget_name")
            text_value = self._normalize_optional_string(payload.get("text") or "", max_length=500)
            if not text_value:
                raise EditorOperationValidationError("widget_text_required")
            return {
                "widget_blueprint_path": widget_blueprint_path,
                "widget_name": widget_name,
                "text": text_value,
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "set_umg_widget_layout":
            widget_blueprint_path = self._normalize_asset_path(payload.get("widget_blueprint_path"))
            widget_name = self._normalize_asset_name(payload.get("widget_name"), "widget_name")
            return {
                "widget_blueprint_path": widget_blueprint_path,
                "widget_name": widget_name,
                "layout": self._normalize_umg_layout(payload.get("layout")),
                "slot_type": "CanvasPanelSlot",
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "set_umg_widget_visibility":
            widget_blueprint_path = self._normalize_asset_path(payload.get("widget_blueprint_path"))
            widget_name = self._normalize_asset_name(payload.get("widget_name"), "widget_name")
            return {
                "widget_blueprint_path": widget_blueprint_path,
                "widget_name": widget_name,
                "visibility": self._normalize_umg_visibility(payload.get("visibility")),
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "set_umg_widget_appearance":
            widget_blueprint_path = self._normalize_asset_path(payload.get("widget_blueprint_path"))
            widget_name = self._normalize_asset_name(payload.get("widget_name"), "widget_name")
            appearance_input = payload.get("appearance") if isinstance(payload.get("appearance"), dict) else {
                key: payload.get(key)
                for key in ("render_opacity", "opacity", "is_enabled", "enabled", "color_and_opacity", "font_size")
                if key in payload
            }
            return {
                "widget_blueprint_path": widget_blueprint_path,
                "widget_name": widget_name,
                "appearance": self._normalize_umg_appearance(appearance_input),
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "set_umg_widget_brush":
            widget_blueprint_path = self._normalize_asset_path(payload.get("widget_blueprint_path"))
            widget_name = self._normalize_asset_name(payload.get("widget_name"), "widget_name")
            return {
                "widget_blueprint_path": widget_blueprint_path,
                "widget_name": widget_name,
                "brush": self._normalize_umg_brush(payload.get("brush")),
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "set_umg_slot_layout_v2":
            widget_blueprint_path = self._normalize_asset_path(payload.get("widget_blueprint_path"))
            widget_name = self._normalize_asset_name(payload.get("widget_name"), "widget_name")
            slot_type = self._normalize_umg_slot_type(payload.get("slot_type"))
            return {
                "widget_blueprint_path": widget_blueprint_path,
                "widget_name": widget_name,
                "slot_type": slot_type,
                "layout": self._normalize_umg_slot_layout_v2(payload.get("layout"), slot_type),
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "reparent_umg_widget":
            widget_blueprint_path = self._normalize_asset_path(payload.get("widget_blueprint_path"))
            widget_name = self._normalize_asset_name(payload.get("widget_name"), "widget_name")
            new_parent_name = self._normalize_asset_name(payload.get("new_parent_name"), "new_parent_name")
            if widget_name == new_parent_name:
                raise EditorOperationValidationError(
                    "widget_parent_must_differ_from_target",
                    {"widget_name": widget_name, "new_parent_name": new_parent_name},
                )
            return {
                "widget_blueprint_path": widget_blueprint_path,
                "widget_name": widget_name,
                "new_parent_name": new_parent_name,
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "duplicate_umg_widget":
            widget_blueprint_path = self._normalize_asset_path(payload.get("widget_blueprint_path"))
            widget_name = self._normalize_asset_name(payload.get("widget_name"), "widget_name")
            new_widget_name = self._normalize_asset_name(payload.get("new_widget_name"), "new_widget_name")
            if widget_name == new_widget_name:
                raise EditorOperationValidationError(
                    "new_widget_name_must_differ_from_source",
                    {"widget_name": widget_name, "new_widget_name": new_widget_name},
                )
            return {
                "widget_blueprint_path": widget_blueprint_path,
                "widget_name": widget_name,
                "source_widget_name": widget_name,
                "new_widget_name": new_widget_name,
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "delete_umg_widget":
            widget_blueprint_path = self._normalize_asset_path(payload.get("widget_blueprint_path"))
            widget_name = self._normalize_asset_name(payload.get("widget_name"), "widget_name")
            return {
                "widget_blueprint_path": widget_blueprint_path,
                "widget_name": widget_name,
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "place_actor_in_level":
            actor_class = self._normalize_class_path(payload.get("actor_class"))
            actor_label = self._normalize_optional_string(payload.get("actor_label") or "", max_length=80)
            return {
                "actor_class": actor_class,
                "actor_label": actor_label or None,
                "transform": self._normalize_actor_transform(payload.get("transform")),
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "set_actor_transform":
            actor_reference = self._normalize_optional_string(payload.get("actor_reference") or "", max_length=120)
            if not actor_reference:
                raise EditorOperationValidationError("actor_reference_required")
            transform_mode = self._normalize_transform_mode(payload.get("transform_mode"))
            transform_key = "transform_delta" if transform_mode == "delta" else "transform"
            transform_update = self._normalize_actor_transform_update(
                payload.get(transform_key),
                field_name=transform_key,
            )
            return {
                "actor_reference": actor_reference,
                "actor_name": self._normalize_optional_string(payload.get("actor_name") or "", max_length=120) or None,
                "actor_label": self._normalize_optional_string(payload.get("actor_label") or "", max_length=120) or None,
                "transform_mode": transform_mode,
                transform_key: transform_update,
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "set_actor_metadata":
            actor_reference = self._normalize_optional_string(payload.get("actor_reference") or "", max_length=120)
            if not actor_reference:
                raise EditorOperationValidationError("actor_reference_required")
            metadata_input = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {
                key: payload.get(key)
                for key in ("actor_label", "folder_path", "tags", "tag_mode")
                if key in payload
            }
            metadata = self._normalize_actor_metadata(metadata_input)
            return {
                "actor_reference": actor_reference,
                "metadata": metadata,
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "arrange_actors_pattern":
            actor_references = self._normalize_actor_references(payload.get("actor_references"))
            return {
                "actor_references": actor_references,
                "pattern": self._normalize_arrange_pattern(payload.get("pattern"), actor_count=len(actor_references)),
                "item_count": len(actor_references),
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "set_material_instance_parameter":
            material_instance_path = self._normalize_asset_path(payload.get("material_instance_path"))
            parameter_name = self._normalize_parameter_name(payload.get("parameter_name"))
            parameter_type = self._normalize_material_parameter_type(payload.get("parameter_type"))
            raw_value = payload.get("value")
            value = (
                self._normalize_finite_float(raw_value, "material_scalar_value")
                if parameter_type == "scalar"
                else self._normalize_material_vector_value(raw_value)
            )
            return {
                "material_instance_path": material_instance_path,
                "parameter_name": parameter_name,
                "parameter_type": parameter_type,
                "value": value,
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "set_material_instance_texture_parameter":
            material_instance_path = self._normalize_asset_path(payload.get("material_instance_path"))
            parameter_name = self._normalize_parameter_name(payload.get("parameter_name"))
            texture_path = self._normalize_asset_path(payload.get("texture_path"))
            return {
                "material_instance_path": material_instance_path,
                "parameter_name": parameter_name,
                "texture_path": texture_path,
                "save_policy": "mark_dirty_only",
            }

        if operation_type == "set_material_instance_static_switch":
            material_instance_path = self._normalize_asset_path(payload.get("material_instance_path"))
            parameter_name = self._normalize_parameter_name(payload.get("parameter_name"))
            value = self._normalize_bool(payload.get("value"), "static_switch_value")
            return {
                "material_instance_path": material_instance_path,
                "parameter_name": parameter_name,
                "value": value,
                "save_policy": "mark_dirty_only",
            }

        raise EditorOperationValidationError("unsupported_editor_operation", {"operation_type": operation_type})

    def _build_summaries(self, operation_type: str, payload: dict[str, Any]) -> tuple[str, str]:
        if operation_type == "rename_selected_asset":
            return (
                f"Current asset path: {payload['asset_path']}",
                f"Rename to: {payload['target_path']}",
            )
        if operation_type == "apply_static_mesh_basic_settings":
            fields = ", ".join(sorted(payload["settings"].keys()))
            return (
                f"Current Static Mesh settings snapshot will be compared for {payload['asset_path']}.",
                f"Apply whitelisted settings: {fields}. Asset package will be marked dirty, not auto-saved.",
            )
        if operation_type == "create_blueprint_asset":
            return (
                f"No Blueprint will be created before confirmation. Parent class: {payload['parent_class']}",
                f"Create Blueprint `{payload['asset_name']}` at {payload['target_path']}.",
            )
        if operation_type == "add_blueprint_variable":
            return (
                f"Blueprint before change: {payload['blueprint_path']}",
                f"Add variable `{payload['variable_name']}` of type `{payload['variable_type']}`.",
            )
        if operation_type == "add_blueprint_component":
            return (
                f"Blueprint before change: {payload['blueprint_path']}",
                f"Add component `{payload['component_name']}` of class `{payload['component_class']}`.",
            )
        if operation_type == "create_blueprint_event_stub":
            return (
                f"Blueprint graph before change: {payload['blueprint_path']}::{payload['graph_name']}",
                f"Create event stub `{payload['event_name']}`. No complex node graph is generated in v1.",
            )
        if operation_type == "add_blueprint_node_template":
            details = f"Add `{payload['template_id']}` node template to `{payload['graph_name']}`"
            if payload["template_id"] == "print_string":
                details += f" with message `{payload['message']}`"
            if payload["template_id"] == "delay_print_string":
                details += (
                    f" as Delay `{payload['delay_seconds']}` seconds"
                    f" then PrintString `{payload['message']}`"
                )
            if payload["template_id"] == "branch_print_string":
                details += (
                    f" with `{payload['branch_path']}` branch path connected to PrintString"
                    f" and condition default `{payload['condition_default']}`"
                )
            if payload["template_id"] == "sequence_print_strings":
                details += f" with `{payload['sequence_output_count']}` sequence outputs connected to PrintString nodes"
            if payload["template_id"] == "get_variable":
                details += f" for existing variable `{payload['variable_name']}`"
            if payload["template_id"] == "set_variable":
                details += f" for existing variable `{payload['variable_name']}`"
                if payload.get("variable_value"):
                    details += f" with default value `{payload['variable_value']}`"
            if payload["template_id"] == "call_function":
                details += f" for existing self function `{payload['function_name']}`"
            if payload["template_id"] == "enhanced_input_action_event":
                details += f" for Input Action `{payload['input_action_path']}`"
            if payload["template_id"] == "enhanced_input_print_string":
                details += (
                    f" for Input Action `{payload['input_action_path']}`"
                    f" and connect Triggered to PrintString `{payload['message']}`"
                )
            if payload.get("entry_event"):
                details += f" and connect from `{payload['entry_event']}`"
            if payload.get("compile_after_edit"):
                details += " and compile once after edit"
            return (
                f"Blueprint graph before change: {payload['blueprint_path']}::{payload['graph_name']}",
                f"{details}. The package is marked dirty, not auto-saved.",
            )
        if operation_type == "connect_blueprint_nodes":
            return (
                f"Blueprint graph before change: {payload['blueprint_path']}::{payload['graph_name']}",
                (
                    "Connect explicit pins "
                    f"`{payload['source_node_id']}.{payload['source_pin_name']}` -> "
                    f"`{payload['target_node_id']}.{payload['target_pin_name']}`"
                    ". The package is marked dirty, not auto-saved."
                ),
            )
        if operation_type == "compile_blueprint":
            return (
                f"Blueprint before compile: {payload['blueprint_path']}",
                "Compile the Blueprint in Unreal Editor and return compile status. The package is not auto-saved.",
            )
        if operation_type == "batch_rename_assets":
            preview = ", ".join(
                f"{item['asset_path']} -> {item['target_path']}"
                for item in payload["renames"][:5]
            )
            if payload["item_count"] > 5:
                preview += f", ... (+{payload['item_count'] - 5} more)"
            return (
                f"Batch rename {payload['item_count']} assets. No asset is changed before confirmation.",
                f"Rename plan: {preview}. Redirectors are not fixed automatically in this operation.",
            )
        if operation_type == "move_assets":
            preview = ", ".join(
                f"{item['asset_path']} -> {item['target_path']}"
                for item in payload["moves"][:5]
            )
            if payload["item_count"] > 5:
                preview += f", ... (+{payload['item_count'] - 5} more)"
            return (
                f"Move {payload['item_count']} assets to {payload['target_folder']}. No asset is changed before confirmation.",
                f"Move plan: {preview}. Redirectors are not fixed automatically in this operation.",
            )
        if operation_type == "duplicate_asset":
            return (
                f"Duplicate source asset: {payload['source_asset_path']}. No asset is changed before confirmation.",
                f"Create duplicate `{payload['target_path']}`. The duplicated package is marked dirty, not auto-saved.",
            )
        if operation_type == "fixup_redirectors":
            recursive_note = "recursively" if payload["recursive"] else "non-recursively"
            return (
                f"Fix redirectors under {payload['folder_path']} {recursive_note}. No asset is changed before confirmation.",
                (
                    "Run Unreal redirector fixup for at most "
                    f"{payload['max_redirectors']} redirectors. This may update referencers or redirector packages."
                ),
            )
        if operation_type == "add_umg_widget":
            parent = payload.get("parent_widget_name") or "root widget"
            return (
                f"Widget Blueprint before change: {payload['widget_blueprint_path']}",
                f"Add `{payload['widget_name']}` ({payload['widget_class']}) under {parent}. The package is not auto-saved.",
            )
        if operation_type == "set_umg_widget_text":
            return (
                f"Widget Blueprint before change: {payload['widget_blueprint_path']}",
                f"Set TextBlock `{payload['widget_name']}` text to `{payload['text']}`. The package is not auto-saved.",
            )
        if operation_type == "set_umg_widget_layout":
            fields = ", ".join(sorted(payload["layout"].keys()))
            return (
                f"Widget Blueprint before change: {payload['widget_blueprint_path']}",
                f"Set CanvasPanelSlot layout for `{payload['widget_name']}` fields: {fields}. The package is not auto-saved.",
            )
        if operation_type == "set_umg_widget_visibility":
            return (
                f"Widget Blueprint before change: {payload['widget_blueprint_path']}",
                f"Set widget `{payload['widget_name']}` visibility to `{payload['visibility']}`. The package is not auto-saved.",
            )
        if operation_type == "set_umg_widget_appearance":
            fields = ", ".join(sorted(payload["appearance"].keys()))
            return (
                f"Widget Blueprint before change: {payload['widget_blueprint_path']}",
                f"Set widget `{payload['widget_name']}` appearance fields: {fields}. The package is not auto-saved.",
            )
        if operation_type == "set_umg_widget_brush":
            brush = payload["brush"]
            return (
                f"Widget Blueprint before change: {payload['widget_blueprint_path']}",
                f"Set widget `{payload['widget_name']}` brush {brush['resource_type']} to `{brush['resource_path']}`. The package is not auto-saved.",
            )
        if operation_type == "set_umg_slot_layout_v2":
            fields = ", ".join(sorted(payload["layout"].keys()))
            return (
                f"Widget Blueprint before change: {payload['widget_blueprint_path']}",
                f"Set `{payload['slot_type']}` layout for `{payload['widget_name']}` fields: {fields}. The package is not auto-saved.",
            )
        if operation_type == "reparent_umg_widget":
            return (
                f"Widget Blueprint before change: {payload['widget_blueprint_path']}",
                f"Move widget `{payload['widget_name']}` under panel `{payload['new_parent_name']}`. The package is not auto-saved.",
            )
        if operation_type == "duplicate_umg_widget":
            return (
                f"Widget Blueprint before change: {payload['widget_blueprint_path']}",
                f"Duplicate widget `{payload['widget_name']}` as `{payload['new_widget_name']}` under the same parent. The package is not auto-saved.",
            )
        if operation_type == "delete_umg_widget":
            return (
                f"Widget Blueprint before change: {payload['widget_blueprint_path']}",
                f"Remove widget `{payload['widget_name']}` from its parent. The package is not auto-saved and editor Undo can restore it.",
            )
        if operation_type == "place_actor_in_level":
            location = payload["transform"]["location"]
            label = payload.get("actor_label") or "(default label)"
            return (
                f"Current level before change: no Actor is spawned before confirmation. Class: {payload['actor_class']}",
                f"Place Actor label `{label}` at ({location['x']}, {location['y']}, {location['z']}). The level is marked dirty, not auto-saved.",
            )
        if operation_type == "set_actor_transform":
            transform_key = "transform_delta" if payload["transform_mode"] == "delta" else "transform"
            fields = ", ".join(sorted(payload[transform_key].keys()))
            return (
                f"Actor before change: {payload['actor_reference']}",
                f"Apply {payload['transform_mode']} transform fields: {fields}. The level is marked dirty, not auto-saved.",
            )
        if operation_type == "set_actor_metadata":
            fields = ", ".join(sorted(payload["metadata"].keys()))
            return (
                f"Actor before change: {payload['actor_reference']}",
                f"Update Actor metadata fields: {fields}. The level is marked dirty, not auto-saved.",
            )
        if operation_type == "arrange_actors_pattern":
            pattern = payload["pattern"]
            return (
                f"Arrange {payload['item_count']} existing Actors. No Actor is moved before confirmation.",
                f"Apply `{pattern['type']}` pattern with spacing `{pattern['spacing']}`. The level is marked dirty, not auto-saved.",
            )
        if operation_type == "set_material_instance_parameter":
            return (
                f"Material Instance before change: {payload['material_instance_path']}",
                f"Set `{payload['parameter_name']}` {payload['parameter_type']} value. The package is marked dirty, not auto-saved.",
            )
        if operation_type == "set_material_instance_texture_parameter":
            return (
                f"Material Instance before change: {payload['material_instance_path']}",
                f"Set texture parameter `{payload['parameter_name']}` to `{payload['texture_path']}`. The package is marked dirty, not auto-saved.",
            )
        if operation_type == "set_material_instance_static_switch":
            return (
                f"Material Instance before change: {payload['material_instance_path']}",
                f"Set static switch `{payload['parameter_name']}` to `{payload['value']}`. The package is marked dirty, not auto-saved.",
            )
        return ("", "")

    @staticmethod
    def _build_affected_targets(operation_type: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        if operation_type == "rename_selected_asset":
            return [
                {
                    "kind": "asset",
                    "action": "rename",
                    "path": payload["asset_path"],
                    "target_path": payload["target_path"],
                }
            ]
        if operation_type == "apply_static_mesh_basic_settings":
            return [
                {
                    "kind": "static_mesh",
                    "action": "modify_settings",
                    "path": payload["asset_path"],
                    "fields": sorted(payload["settings"].keys()),
                }
            ]
        if operation_type == "create_blueprint_asset":
            return [
                {
                    "kind": "blueprint_asset",
                    "action": "create",
                    "path": payload["target_path"],
                    "parent_class": payload["parent_class"],
                }
            ]
        if operation_type in {
            "add_blueprint_variable",
            "add_blueprint_component",
            "create_blueprint_event_stub",
            "add_blueprint_node_template",
            "connect_blueprint_nodes",
            "compile_blueprint",
        }:
            target: dict[str, Any] = {
                "kind": "blueprint",
                "action": operation_type,
                "path": payload["blueprint_path"],
            }
            for key in (
                "variable_name",
                "component_name",
                "event_name",
                "template_id",
                "graph_name",
                "entry_event",
                "branch_path",
                "delay_seconds",
                "sequence_output_count",
                "function_name",
                "function_target",
                "input_action_path",
                "source_node_id",
                "source_pin_name",
                "target_node_id",
                "target_pin_name",
                "variable_scope",
                "variable_value",
            ):
                if payload.get(key):
                    target[key] = payload[key]
            return [target]
        if operation_type == "batch_rename_assets":
            return [
                {
                    "kind": "asset",
                    "action": "rename",
                    "path": item["asset_path"],
                    "target_path": item["target_path"],
                }
                for item in payload["renames"]
            ]
        if operation_type == "move_assets":
            return [
                {
                    "kind": "asset",
                    "action": "move",
                    "path": item["asset_path"],
                    "target_path": item["target_path"],
                }
                for item in payload["moves"]
            ]
        if operation_type == "duplicate_asset":
            return [
                {
                    "kind": "asset",
                    "action": "duplicate",
                    "path": payload["source_asset_path"],
                    "target_path": payload["target_path"],
                }
            ]
        if operation_type == "fixup_redirectors":
            return [
                {
                    "kind": "asset_folder",
                    "action": "fixup_redirectors",
                    "path": payload["folder_path"],
                    "recursive": payload["recursive"],
                    "max_redirectors": payload["max_redirectors"],
                }
            ]
        if operation_type in {
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
        }:
            target = {
                "kind": "umg_widget",
                "action": operation_type,
                "widget_blueprint_path": payload["widget_blueprint_path"],
                "widget_name": payload["widget_name"],
            }
            for key in ("widget_class", "slot_type", "visibility"):
                if payload.get(key):
                    target[key] = payload[key]
            if payload.get("appearance"):
                target["appearance_fields"] = sorted(payload["appearance"].keys())
            if payload.get("brush"):
                target["brush"] = dict(payload["brush"])
            if payload.get("layout"):
                target["layout_fields"] = sorted(payload["layout"].keys())
            if payload.get("new_parent_name"):
                target["new_parent_name"] = payload["new_parent_name"]
            if payload.get("new_widget_name"):
                target["new_widget_name"] = payload["new_widget_name"]
            return [target]
        if operation_type == "place_actor_in_level":
            return [
                {
                    "kind": "level_actor",
                    "action": "place_actor",
                    "actor_class": payload["actor_class"],
                    "actor_label": payload.get("actor_label"),
                }
            ]
        if operation_type == "set_actor_transform":
            return [
                {
                    "kind": "level_actor",
                    "action": "set_transform",
                    "actor_reference": payload["actor_reference"],
                    "transform_mode": payload["transform_mode"],
                }
            ]
        if operation_type == "set_actor_metadata":
            return [
                {
                    "kind": "level_actor",
                    "action": "set_metadata",
                    "actor_reference": payload["actor_reference"],
                    "metadata_fields": sorted(payload["metadata"].keys()),
                }
            ]
        if operation_type == "arrange_actors_pattern":
            return [
                {
                    "kind": "level_actor",
                    "action": "arrange_pattern",
                    "actor_reference": actor_reference,
                    "pattern_type": payload["pattern"]["type"],
                }
                for actor_reference in payload["actor_references"]
            ]
        if operation_type in {
            "set_material_instance_parameter",
            "set_material_instance_texture_parameter",
            "set_material_instance_static_switch",
        }:
            target = {
                "kind": "material_instance",
                "action": operation_type,
                "path": payload["material_instance_path"],
                "parameter_name": payload["parameter_name"],
            }
            if payload.get("parameter_type"):
                target["parameter_type"] = payload["parameter_type"]
            if payload.get("texture_path"):
                target["texture_path"] = payload["texture_path"]
            if "value" in payload:
                target["value"] = payload["value"]
            return [target]
        return [{"kind": "editor_operation", "action": operation_type}]

    @staticmethod
    def _expected_result_contract(operation_type: str) -> dict[str, Any]:
        operation_fields = {
            "rename_selected_asset": ["final_asset_path", "dirty", "dirty_packages"],
            "apply_static_mesh_basic_settings": ["dirty", "dirty_packages", "applied_fields", "failed_fields"],
            "create_blueprint_asset": ["asset_path", "dirty", "dirty_packages"],
            "add_blueprint_variable": ["blueprint_path", "variable_name", "dirty", "dirty_packages"],
            "add_blueprint_component": ["blueprint_path", "component_name", "dirty", "dirty_packages"],
            "create_blueprint_event_stub": ["blueprint_path", "event_name", "dirty", "dirty_packages"],
            "add_blueprint_node_template": [
                "blueprint_path",
                "template_id",
                "graph_name",
                "entry_event",
                "branch_path",
                "condition_default",
                "delay_seconds",
                "sequence_output_count",
                "messages",
                "variable_name",
                "variable_scope",
                "variable_value",
                "function_name",
                "function_target",
                "input_action_path",
                "input_action_name",
                "created_node_id",
                "created_node_name",
                "entry_node_id",
                "entry_node_name",
                "created_nodes",
                "linked_nodes",
                "linked_pins",
                "linked_pin_summaries",
                "compile_status",
                "dirty",
                "dirty_packages",
            ],
            "connect_blueprint_nodes": [
                "blueprint_path",
                "graph_name",
                "source_node_id",
                "source_node_name",
                "source_pin_name",
                "source_pin_id",
                "target_node_id",
                "target_node_name",
                "target_pin_name",
                "target_pin_id",
                "linked_pins",
                "linked_pin_summaries",
                "compile_status",
                "dirty",
                "dirty_packages",
            ],
            "compile_blueprint": ["blueprint_path", "compile_status", "messages"],
            "batch_rename_assets": ["renamed_assets", "dirty_packages", "failed_items"],
            "move_assets": ["moved_assets", "dirty_packages", "failed_items"],
            "duplicate_asset": ["source_asset_path", "target_path", "duplicated_asset_path", "dirty", "dirty_packages"],
            "fixup_redirectors": [
                "folder_path",
                "recursive",
                "redirector_count",
                "fixed_redirectors",
                "dirty",
                "dirty_packages",
            ],
            "add_umg_widget": ["widget_blueprint_path", "widget_name", "dirty", "dirty_packages"],
            "set_umg_widget_text": ["widget_blueprint_path", "widget_name", "dirty", "dirty_packages"],
            "set_umg_widget_layout": ["widget_blueprint_path", "widget_name", "dirty", "dirty_packages"],
            "set_umg_widget_visibility": ["widget_blueprint_path", "widget_name", "dirty", "dirty_packages"],
            "set_umg_widget_appearance": [
                "widget_blueprint_path",
                "widget_name",
                "render_opacity",
                "is_enabled",
                "color_and_opacity",
                "font_size",
                "dirty",
                "dirty_packages",
            ],
            "set_umg_widget_brush": [
                "widget_blueprint_path",
                "widget_name",
                "resource_type",
                "resource_path",
                "dirty",
                "dirty_packages",
            ],
            "set_umg_slot_layout_v2": [
                "widget_blueprint_path",
                "widget_name",
                "slot_type",
                "padding",
                "horizontal_alignment",
                "vertical_alignment",
                "size",
                "dirty",
                "dirty_packages",
            ],
            "reparent_umg_widget": [
                "widget_blueprint_path",
                "widget_name",
                "old_parent_name",
                "new_parent_name",
                "dirty",
                "dirty_packages",
            ],
            "duplicate_umg_widget": [
                "widget_blueprint_path",
                "source_widget_name",
                "new_widget_name",
                "parent_widget_name",
                "dirty",
                "dirty_packages",
            ],
            "delete_umg_widget": [
                "widget_blueprint_path",
                "widget_name",
                "old_parent_name",
                "removed_widgets",
                "dirty",
                "dirty_packages",
            ],
            "place_actor_in_level": ["actor_label", "actor_path", "level_dirty", "dirty_packages"],
            "set_actor_transform": ["actor_reference", "transform_mode", "level_dirty", "dirty_packages"],
            "set_actor_metadata": ["actor_reference", "actor_label", "folder_path", "tags", "level_dirty", "dirty_packages"],
            "arrange_actors_pattern": [
                "arranged_actors",
                "pattern_type",
                "item_count",
                "level_dirty",
                "dirty_packages",
            ],
            "set_material_instance_parameter": ["material_instance_path", "parameter_name", "dirty", "dirty_packages"],
            "set_material_instance_texture_parameter": [
                "material_instance_path",
                "parameter_name",
                "texture_path",
                "dirty",
                "dirty_packages",
            ],
            "set_material_instance_static_switch": [
                "material_instance_path",
                "parameter_name",
                "value",
                "dirty",
                "dirty_packages",
            ],
        }
        return {
            "schema_version": "editor_operation_result_v1",
            "result_endpoint": "POST /api/v1/editor-operations/results",
            "required_request_fields": ["proposal_id", "execution_state", "success"],
            "accepted_execution_states": ["completed", "failed", "blocked", "cancelled"],
            "common_result_fields": [
                "dirty",
                "dirty_packages",
                "save_policy",
                "applied_fields",
                "failed_fields",
                "undo_hint",
            ],
            "operation_result_fields": operation_fields.get(operation_type, []),
            "frontend_must_report_result": True,
        }

    @staticmethod
    def _build_preflight_checks(
        *,
        operation_type: str,
        spec: dict[str, Any],
        payload: dict[str, Any],
        affected_targets: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = [
            {
                "check_id": "payload_normalized",
                "status": "passed",
                "summary": "Backend normalized and validated the editor operation payload.",
                "details": {"required_fields": spec["required_fields"]},
            },
            {
                "check_id": "target_preview_built",
                "status": "passed",
                "summary": f"Preview includes {len(affected_targets)} affected target(s).",
                "details": {"target_count": len(affected_targets)},
            },
            {
                "check_id": "user_confirmation_required",
                "status": "pending",
                "summary": "No editor change is executed until the user confirms this proposal.",
            },
            {
                "check_id": "ue_plugin_execution_required",
                "status": "pending",
                "summary": "UEAgentTool must execute the operation inside the Unreal Editor process.",
            },
            {
                "check_id": "auto_save_disabled",
                "status": "passed",
                "summary": "The operation marks packages dirty but does not auto-save them.",
            },
        ]
        if operation_type in {"batch_rename_assets", "move_assets"}:
            checks.append(
                {
                    "check_id": "batch_size_limit",
                    "status": "passed",
                    "summary": "Batch operation is within the configured v1 safety limit.",
                    "details": {"item_count": payload.get("item_count"), "max_item_count": 20},
                }
            )
        return checks

    @staticmethod
    def _build_preview_summary(
        *,
        operation_type: str,
        spec: dict[str, Any],
        affected_targets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "operation_type": operation_type,
            "tool_id": spec["tool_id"],
            "risk_flags": spec["risk_flags"],
            "target_count": len(affected_targets),
            "writes_to_unreal_editor": True,
            "writes_to_backend": False,
            "requires_confirmation": True,
            "auto_save": False,
            "rollback_hint": "Use Unreal Editor Undo or revert dirty packages if the UE operation reports success.",
        }

    def build_action_proposal(
        self,
        request: EditorOperationProposalRequest,
        *,
        proposal_id: str | None = None,
    ) -> dict[str, Any]:
        operation_type = request.operation_type
        spec = OPERATION_SPECS[operation_type]
        normalized_payload = self._normalize_payload(operation_type, dict(request.payload or {}))
        before_summary, after_summary = self._build_summaries(operation_type, normalized_payload)
        resolved_proposal_id = proposal_id or f"proposal_{uuid.uuid4().hex}"
        affected_targets = self._build_affected_targets(operation_type, normalized_payload)
        preflight_checks = self._build_preflight_checks(
            operation_type=operation_type,
            spec=spec,
            payload=normalized_payload,
            affected_targets=affected_targets,
        )
        expected_result_contract = self._expected_result_contract(operation_type)
        preview_summary = self._build_preview_summary(
            operation_type=operation_type,
            spec=spec,
            affected_targets=affected_targets,
        )
        dry_run_preview = {
            "protocol_version": EDITOR_OPERATION_PROTOCOL_VERSION,
            "proposal_kind": "editor_operation",
            "operation_type": operation_type,
            "tool_id": spec["tool_id"],
            "transport": "http",
            "mcp_like": True,
            "side_effect_level": "confirmed_write",
            "approval_state": "pending",
            "operation_payload": normalized_payload,
            "affected_targets": affected_targets,
            "preflight_checks": preflight_checks,
            "expected_result_contract": expected_result_contract,
            "preview_summary": preview_summary,
            "source_task_id": request.source_task_id,
            "context": dict(request.context or {}),
            "execution_contract": {
                "executor": "ue_plugin",
                "execute_after_confirmation": True,
                "result_endpoint": "POST /api/v1/editor-operations/results",
                "llm_direct_execution": False,
                "undo_required": True,
                "auto_save": False,
            },
        }
        display_hints = {
            "ui": "editor_operation_confirmation",
            "operation_type": operation_type,
            "tool_id": spec["tool_id"],
            "frontend_status": spec["frontend_status"],
            "requires_ue_plugin_execution": True,
            "confirm_endpoint": f"/api/v1/editor-operations/proposals/{resolved_proposal_id}/confirm",
            "reject_endpoint": f"/api/v1/editor-operations/proposals/{resolved_proposal_id}/reject",
            "generic_decision_endpoint": f"/api/v1/proposals/{resolved_proposal_id}/decision",
            "result_endpoint": "/api/v1/editor-operations/results",
            "preview_fields": ["affected_targets", "preflight_checks", "expected_result_contract"],
            "confirmation_labels": {
                "confirm": "Confirm in Unreal Editor",
                "reject": "Cancel",
            },
            "risk_notes": [
                "This operation changes the open Unreal Editor project only after user confirmation.",
                "The backend does not execute Unreal Editor APIs directly.",
                "The UE plugin must return an operation result after execution.",
            ],
        }
        return {
            "proposal_id": resolved_proposal_id,
            "title": spec["title"],
            "proposal_type": EDITOR_OPERATION_PROPOSAL_TYPE,
            "before_summary": before_summary,
            "after_summary": after_summary,
            "rationale": self._clean_text(request.reason or spec["summary"]),
            "risk_flags": spec["risk_flags"],
            "dry_run_preview": dry_run_preview,
            "display_hints": display_hints,
            "requires_confirmation": True,
            "confirmation": {
                "state": "pending",
                "decision_endpoint": f"/api/v1/proposals/{resolved_proposal_id}/decision",
            },
        }

    def try_build_action_proposal(
        self,
        request: EditorOperationProposalRequest,
        *,
        proposal_id: str | None = None,
    ) -> dict[str, Any] | None:
        try:
            return self.build_action_proposal(request, proposal_id=proposal_id)
        except EditorOperationValidationError:
            return None

    def build_asset_inspect_rename_proposal(
        self,
        *,
        execution: dict[str, Any],
        request: UnifiedTaskRequest,
    ) -> dict[str, Any] | None:
        data = dict(execution.get("data") or {})
        summary = dict(data.get("summary") or {})
        if int(summary.get("asset_count") or 0) != 1:
            return None
        suggestions = list(data.get("rename_suggestions") or [])
        if not suggestions:
            suggestions = list(dict(data.get("localized_asset_view") or {}).get("rename_suggestions") or [])
        if not suggestions:
            return None
        for raw_suggestion in suggestions:
            suggestion = dict(raw_suggestion)
            asset_path = str(suggestion.get("asset_path") or "").strip()
            new_name = str(suggestion.get("suggested_name") or "").strip()
            if not asset_path or not new_name:
                continue
            proposal = self.try_build_action_proposal(
                EditorOperationProposalRequest(
                    operation_type="rename_selected_asset",
                    payload={"asset_path": asset_path, "new_name": new_name},
                    reason=str(suggestion.get("reason") or "Asset inspection generated a rename suggestion."),
                    requested_by="assets_inspect",
                    context=request.context.model_dump(mode="json"),
                )
            )
            if proposal:
                return proposal
        return None

    def create_operation_proposal(self, request: EditorOperationProposalRequest) -> dict[str, Any]:
        action_proposal = self.build_action_proposal(request)
        dry_run_preview = dict(action_proposal["dry_run_preview"])
        source_task = get_task(self.db, request.source_task_id) if request.source_task_id else None
        proposal = create_proposal(
            self.db,
            ProposalModel(
                proposal_id=action_proposal["proposal_id"],
                task_id=source_task.task_id if source_task else None,
                title=action_proposal["title"],
                proposal_type=action_proposal["proposal_type"],
                before_summary=action_proposal["before_summary"],
                after_summary=action_proposal["after_summary"],
                rationale=action_proposal["rationale"],
                risk_flags=action_proposal["risk_flags"],
                dry_run_preview_json=dry_run_preview,
                display_hints_json=action_proposal["display_hints"],
                requires_confirmation=True,
                confirmation_state="pending",
                decision_endpoint=action_proposal["confirmation"]["decision_endpoint"],
            ),
        )
        audit_entry = build_audit_entry(
            "editor_operation_proposal_created",
            {
                "proposal_id": action_proposal["proposal_id"],
                "operation_type": dry_run_preview.get("operation_type"),
                "tool_id": dry_run_preview.get("tool_id"),
                "requested_by": request.requested_by,
                "source_task_id": request.source_task_id,
            },
            task_id=source_task.task_id if source_task else None,
            session_id=source_task.session_id if source_task else None,
        )
        create_audit_log(
            self.db,
            AuditLogModel(
                audit_id=f"audit_{uuid.uuid4().hex}",
                task_id=source_task.task_id if source_task else None,
                session_id=source_task.session_id if source_task else None,
                event_type=audit_entry["event_type"],
                payload_json=audit_entry["payload"],
            ),
        )
        return {
            "item": self._proposal_payload(proposal),
            "operation": dry_run_preview,
        }

    @staticmethod
    def _as_string_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if str(item or "").strip()]
        text = str(value or "").strip()
        return [text] if text else []

    @staticmethod
    def _collection_count(value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, dict):
            return 1 if value else 0
        if isinstance(value, (list, tuple, set)):
            return len(value)
        return 1 if str(value or "").strip() else 0

    @staticmethod
    def _first_non_empty_text(*values: Any) -> str:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return ""

    @staticmethod
    def _blueprint_graph_result_diagnostics(
        *,
        request: EditorOperationResultRequest,
        preview: dict[str, Any],
        result: dict[str, Any],
        dirty_packages: list[str],
    ) -> dict[str, Any]:
        operation_type = str(preview.get("operation_type") or request.operation_type or "")
        graph_operations = {
            "add_blueprint_variable",
            "add_blueprint_component",
            "create_blueprint_event_stub",
            "add_blueprint_node_template",
            "connect_blueprint_nodes",
            "compile_blueprint",
        }
        if operation_type not in graph_operations:
            return {}

        payload = dict(preview.get("operation_payload") or {})
        template_id = EditorOperationService._first_non_empty_text(
            result.get("template_id"),
            payload.get("template_id"),
        )
        compile_status = EditorOperationService._first_non_empty_text(result.get("compile_status"))
        created_node_count = EditorOperationService._collection_count(result.get("created_nodes"))
        linked_node_count = EditorOperationService._collection_count(result.get("linked_nodes"))
        linked_pin_count = EditorOperationService._collection_count(result.get("linked_pins"))
        result_fields = list(
            dict(preview.get("expected_result_contract") or {}).get("operation_result_fields") or []
        )
        compile_requested = bool(payload.get("compile_after_edit"))
        expects_created_nodes = operation_type == "add_blueprint_node_template"
        expects_linked_pins = (
            operation_type == "connect_blueprint_nodes"
            or template_id
            in {
                "print_string",
                "branch_print_string",
                "enhanced_input_print_string",
                "sequence_print_strings",
                "set_variable",
                "call_function",
            }
        )

        diagnostic_flags: list[str] = []
        if request.success and expects_created_nodes and created_node_count == 0:
            diagnostic_flags.append("created_nodes_missing")
        if request.success and expects_linked_pins and linked_pin_count == 0:
            diagnostic_flags.append("expected_linked_pins_missing")
        if compile_requested and not compile_status:
            diagnostic_flags.append("compile_status_missing")
        if compile_status.lower() in {"failed", "error", "compile_failed", "blocked"}:
            diagnostic_flags.append("compile_failed")
        if request.success and "dirty_packages" in result_fields and not dirty_packages:
            diagnostic_flags.append("dirty_packages_missing")

        repair_advice = EditorOperationService._blueprint_graph_repair_advice(
            operation_type=operation_type,
            diagnostic_flags=diagnostic_flags,
            request=request,
            payload=payload,
            result=result,
            template_id=template_id,
            compile_status=compile_status,
        )
        return {
            "schema_version": "blueprint_graph_operation_diagnostics_v1",
            "category": "blueprint_graph",
            "operation_type": operation_type,
            "blueprint_path": EditorOperationService._first_non_empty_text(
                result.get("blueprint_path"),
                payload.get("blueprint_path"),
            ),
            "graph_name": EditorOperationService._first_non_empty_text(
                result.get("graph_name"),
                payload.get("graph_name"),
            ),
            "template_id": template_id,
            "entry_event": EditorOperationService._first_non_empty_text(
                result.get("entry_event"),
                payload.get("entry_event"),
            ),
            "compile_requested": compile_requested,
            "compile_status": compile_status,
            "created_node_count": created_node_count,
            "linked_node_count": linked_node_count,
            "linked_pin_count": linked_pin_count,
            "has_graph_changes": created_node_count > 0 or linked_pin_count > 0,
            "diagnostic_flags": diagnostic_flags,
            "needs_user_attention": (not request.success) or bool(diagnostic_flags),
            "repair_advice": repair_advice,
        }

    @staticmethod
    def _blueprint_graph_repair_advice(
        *,
        operation_type: str,
        diagnostic_flags: list[str],
        request: EditorOperationResultRequest,
        payload: dict[str, Any],
        result: dict[str, Any],
        template_id: str,
        compile_status: str,
    ) -> dict[str, Any]:
        actions: list[dict[str, Any]] = []
        flag_set = set(diagnostic_flags)
        blueprint_path = EditorOperationService._first_non_empty_text(
            result.get("blueprint_path"),
            payload.get("blueprint_path"),
        )
        graph_name = EditorOperationService._first_non_empty_text(
            result.get("graph_name"),
            payload.get("graph_name"),
        )
        entry_event = EditorOperationService._first_non_empty_text(
            result.get("entry_event"),
            payload.get("entry_event"),
        )

        if not request.success:
            actions.append(
                {
                    "action_id": "inspect_ue_execution_errors",
                    "severity": "error",
                    "title": "Inspect UE execution errors",
                    "details": (
                        "UEAgentTool reported that the editor operation did not complete successfully. "
                        "Check result.errors, Unreal Output Log, and the selected target before retrying."
                    ),
                    "next_step": "Fix the UE-side error or select a valid target, then create a new proposal.",
                }
            )
        if "created_nodes_missing" in flag_set:
            actions.append(
                {
                    "action_id": "verify_blueprint_graph_target",
                    "severity": "warning",
                    "title": "Verify Blueprint graph target",
                    "details": (
                        "The backend expected a Blueprint node to be created, but the UE result did not "
                        "report any created_nodes."
                    ),
                    "next_step": "Open the target Blueprint graph and confirm the graph exists before retrying.",
                    "context": {
                        "blueprint_path": blueprint_path,
                        "graph_name": graph_name,
                        "template_id": template_id,
                    },
                }
            )
        if "expected_linked_pins_missing" in flag_set:
            actions.append(
                {
                    "action_id": "connect_expected_exec_pins",
                    "severity": "warning",
                    "title": "Connect expected execution pins",
                    "details": (
                        "A graph template that normally connects execution pins reported zero linked_pins. "
                        "This usually means the entry node, graph name, or created node handle was not resolved."
                    ),
                    "next_step": (
                        "If UE returned node ids, create a connect_blueprint_nodes proposal; otherwise retry "
                        "after opening the graph and using an explicit event or graph name."
                    ),
                    "context": {
                        "blueprint_path": blueprint_path,
                        "graph_name": graph_name,
                        "entry_event": entry_event,
                        "template_id": template_id,
                    },
                }
            )
        if "compile_status_missing" in flag_set:
            actions.append(
                {
                    "action_id": "report_compile_status",
                    "severity": "warning",
                    "title": "Report Blueprint compile status",
                    "details": (
                        "The proposal requested compile_after_edit, but the UE result did not include compile_status."
                    ),
                    "next_step": "Make the UE execution path report compile_status and compile messages after compile.",
                }
            )
        if "compile_failed" in flag_set:
            actions.append(
                {
                    "action_id": "open_blueprint_compile_results",
                    "severity": "error",
                    "title": "Inspect Blueprint compile results",
                    "details": f"Blueprint compile status was `{compile_status}`.",
                    "next_step": (
                        "Open the Blueprint compiler messages, fix broken pins or missing references, then retry compile."
                    ),
                    "context": {
                        "blueprint_path": blueprint_path,
                        "graph_name": graph_name,
                    },
                }
            )
        if "dirty_packages_missing" in flag_set:
            actions.append(
                {
                    "action_id": "report_dirty_packages",
                    "severity": "info",
                    "title": "Report dirty package paths",
                    "details": (
                        "The operation succeeded, but UE did not report dirty_packages, so the backend cannot "
                        "tell which package needs saving."
                    ),
                    "next_step": "Return dirty_packages or an explicit save_policy from UEAgentTool.",
                }
            )

        known_flags = {
            "created_nodes_missing",
            "expected_linked_pins_missing",
            "compile_status_missing",
            "compile_failed",
            "dirty_packages_missing",
        }
        unknown_flags = sorted(flag_set - known_flags)
        if unknown_flags:
            actions.append(
                {
                    "action_id": "inspect_unknown_diagnostic_flags",
                    "severity": "warning",
                    "title": "Inspect unknown diagnostic flags",
                    "details": "The result included diagnostic flags without a dedicated repair rule.",
                    "next_step": "Check Debug View and update backend repair advice rules if this case is common.",
                    "context": {"unknown_flags": unknown_flags},
                }
            )

        if not actions:
            return {
                "schema_version": "blueprint_graph_repair_advice_v1",
                "status": "not_needed",
                "severity": "info",
                "can_auto_retry": False,
                "safe_next_step": "none",
                "actions": [],
            }

        severity = "error" if any(item["severity"] == "error" for item in actions) else "warning"
        return {
            "schema_version": "blueprint_graph_repair_advice_v1",
            "status": "suggested",
            "severity": severity,
            "can_auto_retry": False,
            "safe_next_step": "manual_review",
            "operation_type": operation_type,
            "actions": actions,
        }

    @staticmethod
    def _normalize_result_summary(
        *,
        request: EditorOperationResultRequest,
        preview: dict[str, Any],
    ) -> dict[str, Any]:
        result = dict(request.result or {})
        errors = list(request.errors or [])
        applied_fields = result.get("applied_fields") or {}
        failed_fields = result.get("failed_fields") or []
        dirty_packages = (
            EditorOperationService._as_string_list(result.get("dirty_packages"))
            or EditorOperationService._as_string_list(result.get("dirty_package"))
            or EditorOperationService._as_string_list(result.get("package_name"))
        )
        error_codes = [
            str(item.get("code") or item.get("reason") or item.get("message") or "unknown_error")
            for item in errors
            if isinstance(item, dict)
        ]
        error_codes.extend(str(item) for item in errors if not isinstance(item, dict))
        target_count = int(dict(preview.get("preview_summary") or {}).get("target_count") or 0)
        if isinstance(applied_fields, dict):
            applied_field_count = len(applied_fields)
        elif isinstance(applied_fields, list):
            applied_field_count = len(applied_fields)
        else:
            applied_field_count = 0
        if isinstance(failed_fields, dict):
            failed_field_count = len(failed_fields)
        elif isinstance(failed_fields, list):
            failed_field_count = len(failed_fields)
        else:
            failed_field_count = 0
        operation_diagnostics = EditorOperationService._blueprint_graph_result_diagnostics(
            request=request,
            preview=preview,
            result=result,
            dirty_packages=dirty_packages,
        )
        return {
            "schema_version": "editor_operation_result_summary_v1",
            "execution_state": request.execution_state,
            "success": request.success,
            "target_count": target_count,
            "applied_field_count": applied_field_count,
            "failed_field_count": failed_field_count,
            "dirty_packages": dirty_packages,
            "save_policy": result.get("save_policy"),
            "dirty": bool(result.get("dirty") or result.get("level_dirty")),
            "applied_fields": applied_fields,
            "failed_fields": failed_fields,
            "error_count": len(error_codes),
            "error_codes": error_codes,
            "operation_diagnostics": operation_diagnostics,
            "repair_advice": dict(operation_diagnostics.get("repair_advice") or {}),
            "needs_user_attention": (
                (not request.success)
                or bool(error_codes)
                or failed_field_count > 0
                or bool(operation_diagnostics.get("needs_user_attention"))
            ),
        }

    def list_operation_history(
        self,
        *,
        limit: int = 50,
        operation_type: str | None = None,
        needs_user_attention: bool | None = None,
        diagnostic_flag: str | None = None,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 200))
        has_filters = bool(operation_type or needs_user_attention is not None or diagnostic_flag)
        fetch_limit = safe_limit if not has_filters else min(max(safe_limit * 6, 80), 500)
        statement = (
            select(ProposalModel)
            .where(ProposalModel.proposal_type == EDITOR_OPERATION_PROPOSAL_TYPE)
            .order_by(ProposalModel.updated_at.desc())
            .limit(fetch_limit)
        )
        proposals = list(self.db.scalars(statement))
        items: list[dict[str, Any]] = []
        for proposal in proposals:
            preview = dict(proposal.dry_run_preview_json or {})
            current_operation_type = str(preview.get("operation_type") or "")
            if operation_type and current_operation_type != operation_type:
                continue
            operation_result = dict(preview.get("operation_result") or {})
            result_summary = dict(operation_result.get("result_summary") or {})
            operation_diagnostics = dict(result_summary.get("operation_diagnostics") or {})
            if needs_user_attention is not None and bool(
                result_summary.get("needs_user_attention")
            ) != needs_user_attention:
                continue
            if diagnostic_flag:
                diagnostic_flags = [str(item) for item in operation_diagnostics.get("diagnostic_flags") or []]
                if str(diagnostic_flag) not in diagnostic_flags:
                    continue
            items.append(
                {
                    "proposal_id": proposal.proposal_id,
                    "title": proposal.title,
                    "operation_type": current_operation_type,
                    "tool_id": preview.get("tool_id"),
                    "risk_flags": proposal.risk_flags,
                    "confirmation_state": proposal.confirmation_state,
                    "approval_state": preview.get("approval_state"),
                    "created_at": proposal.created_at.isoformat() if proposal.created_at else None,
                    "updated_at": proposal.updated_at.isoformat() if proposal.updated_at else None,
                    "preview_summary": preview.get("preview_summary", {}),
                    "affected_targets": preview.get("affected_targets", []),
                    "result_summary": result_summary,
                    "execution_state": operation_result.get("execution_state"),
                    "success": operation_result.get("success"),
                }
            )
            if len(items) >= safe_limit:
                break
        return {
            "summary": {
                "item_count": len(items),
                "limit": safe_limit,
                "operation_type": operation_type,
                "needs_user_attention": needs_user_attention,
                "diagnostic_flag": diagnostic_flag,
            },
            "items": items,
        }

    def operation_diagnostics_summary(
        self,
        *,
        limit: int = 200,
        operation_type: str | None = None,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 500))
        has_filters = bool(operation_type)
        fetch_limit = safe_limit if not has_filters else min(max(safe_limit * 6, 80), 500)
        statement = (
            select(ProposalModel)
            .where(ProposalModel.proposal_type == EDITOR_OPERATION_PROPOSAL_TYPE)
            .order_by(ProposalModel.updated_at.desc())
            .limit(fetch_limit)
        )
        proposals = list(self.db.scalars(statement))

        inspected_count = 0
        executed_count = 0
        pending_count = 0
        success_count = 0
        failed_count = 0
        needs_user_attention_count = 0
        operation_type_counts: Counter[str] = Counter()
        diagnostic_flag_counts: Counter[str] = Counter()
        repair_action_counts: Counter[str] = Counter()
        repair_status_counts: Counter[str] = Counter()
        execution_state_counts: Counter[str] = Counter()
        confirmation_state_counts: Counter[str] = Counter()
        recent_attention_items: list[dict[str, Any]] = []

        for proposal in proposals:
            preview = dict(proposal.dry_run_preview_json or {})
            current_operation_type = str(preview.get("operation_type") or "")
            if operation_type and current_operation_type != operation_type:
                continue
            inspected_count += 1
            operation_type_counts[current_operation_type or "unknown"] += 1
            confirmation_state_counts[str(proposal.confirmation_state or "unknown")] += 1

            operation_result = dict(preview.get("operation_result") or {})
            result_summary = dict(operation_result.get("result_summary") or {})
            operation_diagnostics = dict(result_summary.get("operation_diagnostics") or {})
            diagnostic_flags = [str(item) for item in operation_diagnostics.get("diagnostic_flags") or []]
            diagnostic_flag_counts.update(diagnostic_flags)
            repair_advice = dict(operation_diagnostics.get("repair_advice") or result_summary.get("repair_advice") or {})
            repair_status = str(repair_advice.get("status") or "unknown")
            repair_status_counts[repair_status] += 1
            repair_actions = [str(item.get("action_id") or "") for item in repair_advice.get("actions") or []]
            repair_action_counts.update(item for item in repair_actions if item)

            if operation_result:
                executed_count += 1
                execution_state_counts[str(operation_result.get("execution_state") or "reported")] += 1
                if bool(operation_result.get("success")):
                    success_count += 1
                else:
                    failed_count += 1
            else:
                pending_count += 1
                execution_state_counts["pending_result"] += 1

            needs_user_attention = bool(result_summary.get("needs_user_attention"))
            if needs_user_attention:
                needs_user_attention_count += 1
                if len(recent_attention_items) < 10:
                    recent_attention_items.append(
                        {
                            "proposal_id": proposal.proposal_id,
                            "operation_type": current_operation_type,
                            "tool_id": preview.get("tool_id"),
                            "title": proposal.title,
                            "confirmation_state": proposal.confirmation_state,
                            "execution_state": operation_result.get("execution_state"),
                            "success": operation_result.get("success"),
                            "updated_at": proposal.updated_at.isoformat() if proposal.updated_at else None,
                            "diagnostic_flags": diagnostic_flags,
                            "error_codes": list(result_summary.get("error_codes") or []),
                            "repair_advice": repair_advice,
                            "result_summary": result_summary,
                        }
                    )

            if inspected_count >= safe_limit:
                break

        attention_rate = needs_user_attention_count / executed_count if executed_count else 0.0
        return {
            "summary": {
                "schema_version": "editor_operation_diagnostics_summary_v1",
                "limit": safe_limit,
                "operation_type": operation_type,
                "inspected_count": inspected_count,
                "executed_count": executed_count,
                "pending_count": pending_count,
                "success_count": success_count,
                "failed_count": failed_count,
                "needs_user_attention_count": needs_user_attention_count,
                "attention_rate": round(attention_rate, 4),
                "operation_type_counts": dict(operation_type_counts),
                "diagnostic_flag_counts": dict(diagnostic_flag_counts),
                "repair_status_counts": dict(repair_status_counts),
                "repair_action_counts": dict(repair_action_counts),
                "execution_state_counts": dict(execution_state_counts),
                "confirmation_state_counts": dict(confirmation_state_counts),
                "recent_attention_items": recent_attention_items,
            },
        }

    @staticmethod
    def _node_identifier(value: Any) -> str:
        if isinstance(value, dict):
            for key in ("node_id", "id", "guid", "node_name", "name", "source", "target"):
                text = str(value.get(key) or "").strip()
                if text:
                    return text
            return ""
        return str(value or "").strip()

    @staticmethod
    def _first_node_identifier(value: Any) -> str:
        if isinstance(value, list):
            for item in value:
                identifier = EditorOperationService._node_identifier(item)
                if identifier:
                    return identifier
            return ""
        return EditorOperationService._node_identifier(value)

    @staticmethod
    def _entry_event_node_hint(entry_event: str) -> str:
        if not entry_event:
            return ""
        if entry_event == "BeginPlay":
            return "EventBeginPlay"
        if entry_event == "Tick":
            return "EventTick"
        if entry_event.startswith("Actor"):
            return f"Event{entry_event}"
        return f"Event{entry_event}"

    def operation_follow_up_candidates(self, proposal_id: str) -> dict[str, Any] | None:
        proposal = get_proposal(self.db, proposal_id)
        if not proposal:
            return None
        if proposal.proposal_type != EDITOR_OPERATION_PROPOSAL_TYPE:
            return {
                "follow_up": {
                    "schema_version": "editor_operation_follow_up_candidates_v1",
                    "proposal_id": proposal_id,
                    "status": "not_applicable",
                    "reason": "proposal_is_not_editor_operation",
                    "candidates": [],
                }
            }

        preview = dict(proposal.dry_run_preview_json or {})
        operation_result = dict(preview.get("operation_result") or {})
        if not operation_result:
            return {
                "follow_up": {
                    "schema_version": "editor_operation_follow_up_candidates_v1",
                    "proposal_id": proposal_id,
                    "source_operation_type": preview.get("operation_type"),
                    "status": "not_ready",
                    "reason": "operation_result_missing",
                    "candidates": [],
                }
            }

        result = dict(operation_result.get("result") or {})
        result_summary = dict(operation_result.get("result_summary") or {})
        operation_diagnostics = dict(result_summary.get("operation_diagnostics") or {})
        repair_advice = dict(operation_diagnostics.get("repair_advice") or result_summary.get("repair_advice") or {})
        actions = [dict(item) for item in repair_advice.get("actions") or [] if isinstance(item, dict)]
        action_ids = {str(item.get("action_id") or "") for item in actions}
        payload = dict(preview.get("operation_payload") or {})
        blueprint_path = self._first_non_empty_text(result.get("blueprint_path"), payload.get("blueprint_path"))
        graph_name = self._first_non_empty_text(result.get("graph_name"), payload.get("graph_name"), "EventGraph")
        entry_event = self._first_non_empty_text(result.get("entry_event"), payload.get("entry_event"))

        candidates: list[dict[str, Any]] = []
        if "connect_expected_exec_pins" in action_ids:
            source_node_id = self._first_non_empty_text(
                result.get("source_node_id"),
                result.get("entry_node_id"),
                result.get("event_node_id"),
                payload.get("source_node_id"),
                self._entry_event_node_hint(entry_event),
            )
            target_node_id = self._first_non_empty_text(
                result.get("target_node_id"),
                result.get("created_node_id"),
                self._first_node_identifier(result.get("created_nodes")),
                payload.get("target_node_id"),
            )
            follow_payload = {
                "blueprint_path": blueprint_path,
                "graph_name": graph_name,
                "source_node_id": source_node_id,
                "source_pin_name": str(result.get("source_pin_name") or payload.get("source_pin_name") or "then"),
                "target_node_id": target_node_id,
                "target_pin_name": str(result.get("target_pin_name") or payload.get("target_pin_name") or "execute"),
                "compile_after_edit": True,
            }
            missing_inputs = [
                key
                for key in ("blueprint_path", "graph_name", "source_node_id", "target_node_id")
                if not str(follow_payload.get(key) or "").strip()
            ]
            candidates.append(
                {
                    "candidate_id": "connect_expected_exec_pins",
                    "source_action_id": "connect_expected_exec_pins",
                    "operation_type": "connect_blueprint_nodes",
                    "proposal_ready": not missing_inputs,
                    "missing_inputs": missing_inputs,
                    "confidence": "medium" if not missing_inputs else "low",
                    "reason": "Connect the execution pins that the previous Blueprint node template expected.",
                    "payload": follow_payload,
                    "create_request_hint": {
                        "method": "POST",
                        "path": "/api/v1/editor-operations/proposals",
                        "json": {
                            "operation_type": "connect_blueprint_nodes",
                            "payload": follow_payload,
                            "reason": f"Follow up from proposal {proposal_id}: connect expected execution pins.",
                            "requested_by": "editor_operation_follow_up",
                            "context": {"source_proposal_id": proposal_id},
                        },
                    },
                    "requires_confirmation": True,
                    "auto_execute": False,
                    "safety_notes": [
                        "This candidate is only a proposal body; UEAgentTool still needs user confirmation.",
                        "Verify the node identifiers in the Blueprint graph before confirming.",
                    ],
                }
            )

        if "open_blueprint_compile_results" in action_ids or "report_compile_status" in action_ids:
            follow_payload = {
                "blueprint_path": blueprint_path,
                "compile_mode": "default",
            }
            missing_inputs = [
                key for key in ("blueprint_path",) if not str(follow_payload.get(key) or "").strip()
            ]
            candidates.append(
                {
                    "candidate_id": "retry_compile_blueprint",
                    "source_action_id": "open_blueprint_compile_results",
                    "operation_type": "compile_blueprint",
                    "proposal_ready": not missing_inputs,
                    "missing_inputs": missing_inputs,
                    "confidence": "medium" if not missing_inputs else "low",
                    "reason": "Run a confirmed Blueprint compile after the user inspects or fixes the compile issue.",
                    "payload": follow_payload,
                    "create_request_hint": {
                        "method": "POST",
                        "path": "/api/v1/editor-operations/proposals",
                        "json": {
                            "operation_type": "compile_blueprint",
                            "payload": follow_payload,
                            "reason": f"Follow up from proposal {proposal_id}: retry Blueprint compile.",
                            "requested_by": "editor_operation_follow_up",
                            "context": {"source_proposal_id": proposal_id},
                        },
                    },
                    "requires_confirmation": True,
                    "auto_execute": False,
                    "safety_notes": [
                        "Do not retry compile blindly; inspect the Blueprint compiler messages first.",
                        "This candidate only creates a new confirmed-write proposal.",
                    ],
                }
            )

        if bool(operation_result.get("success")):
            source_operation_type = str(preview.get("operation_type") or operation_result.get("operation_type") or "")
            for folder_path in self._redirector_follow_up_folders(
                operation_type=source_operation_type,
                payload=payload,
                result=result,
            ):
                folder_slug = re.sub(r"[^A-Za-z0-9_]+", "_", folder_path.strip("/"))[:48].strip("_") or "folder"
                follow_payload = {
                    "folder_path": folder_path,
                    "recursive": True,
                    "max_redirectors": 50,
                }
                candidates.append(
                    {
                        "candidate_id": f"fixup_redirectors_{folder_slug}",
                        "source_action_id": "fixup_redirectors_after_asset_change",
                        "operation_type": "fixup_redirectors",
                        "proposal_ready": True,
                        "missing_inputs": [],
                        "confidence": "medium",
                        "reason": "Fix redirectors in the source folder after an asset rename or move operation.",
                        "payload": follow_payload,
                        "create_request_hint": {
                            "method": "POST",
                            "path": "/api/v1/editor-operations/proposals",
                            "json": {
                                "operation_type": "fixup_redirectors",
                                "payload": follow_payload,
                                "reason": f"Follow up from proposal {proposal_id}: fix redirectors after asset path changes.",
                                "requested_by": "editor_operation_follow_up",
                                "context": {"source_proposal_id": proposal_id},
                            },
                        },
                        "requires_confirmation": True,
                        "auto_execute": False,
                        "safety_notes": [
                            "This only creates a pending redirector fixup Proposal.",
                            "Review the folder scope before confirming because Unreal may update referencer packages.",
                        ],
                    }
                )

        status = "suggested" if candidates else "not_needed"
        if candidates and not any(bool(item.get("proposal_ready")) for item in candidates):
            status = "needs_manual_input"
        return {
            "follow_up": {
                "schema_version": "editor_operation_follow_up_candidates_v1",
                "proposal_id": proposal_id,
                "source_operation_type": preview.get("operation_type"),
                "source_tool_id": preview.get("tool_id"),
                "source_result_success": operation_result.get("success"),
                "source_execution_state": operation_result.get("execution_state"),
                "status": status,
                "candidate_count": len(candidates),
                "ready_candidate_count": sum(1 for item in candidates if bool(item.get("proposal_ready"))),
                "auto_execute": False,
                "requires_user_confirmation": True,
                "repair_advice_status": repair_advice.get("status"),
                "diagnostic_flags": list(operation_diagnostics.get("diagnostic_flags") or []),
                "candidates": candidates,
            }
        }

    @staticmethod
    def _redirector_follow_up_folders(
        *,
        operation_type: str,
        payload: dict[str, Any],
        result: dict[str, Any],
    ) -> list[str]:
        if operation_type not in {"rename_selected_asset", "batch_rename_assets", "move_assets"}:
            return []

        folders: list[str] = []

        def add_folder_from_asset_path(value: Any) -> None:
            path = str(value or "").strip().replace("\\", "/")
            if not path.startswith("/Game/") or "/" not in path.strip("/"):
                return
            folder = path.rsplit("/", 1)[0]
            if folder == "/Game" or not folder.startswith("/Game/"):
                return
            if folder not in folders:
                folders.append(folder)

        if operation_type == "rename_selected_asset":
            add_folder_from_asset_path(payload.get("asset_path") or result.get("old_asset_path"))
        elif operation_type == "batch_rename_assets":
            for item in payload.get("renames") or result.get("renamed_assets") or []:
                if isinstance(item, dict):
                    add_folder_from_asset_path(item.get("asset_path") or item.get("old_asset_path"))
        elif operation_type == "move_assets":
            for item in payload.get("moves") or result.get("moved_assets") or []:
                if isinstance(item, dict):
                    add_folder_from_asset_path(item.get("asset_path") or item.get("old_asset_path"))
            for asset_path in payload.get("asset_paths") or []:
                add_folder_from_asset_path(asset_path)

        return folders[:5]

    @staticmethod
    def _follow_up_quick_actions(*, proposal_id: str, follow_up: dict[str, Any]) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for candidate in follow_up.get("candidates") or []:
            if len(actions) >= 5:
                break
            if not isinstance(candidate, dict):
                continue
            if not bool(candidate.get("proposal_ready")) or candidate.get("missing_inputs"):
                continue

            candidate_id = str(candidate.get("candidate_id") or f"candidate_{len(actions)}")
            operation_type = str(candidate.get("operation_type") or "editor_operation")
            actions.append(
                {
                    "action_id": f"create_editor_operation_follow_up_{proposal_id}_{candidate_id}",
                    "label": f"Create Follow-up Proposal: {operation_type}",
                    "payload": {
                        "action_type": "create_editor_operation_follow_up_proposal",
                        "method": "POST",
                        "endpoint": f"/api/v1/editor-operations/proposals/{proposal_id}/follow-ups/proposal",
                        "source_proposal_id": proposal_id,
                        "candidate_id": candidate_id,
                        "operation_type": operation_type,
                        "request": {
                            "candidate": candidate,
                            "requested_by": "editor_operation_result_quick_action",
                        },
                        "safety": {
                            "auto_execute": False,
                            "creates_pending_proposal_only": True,
                            "requires_user_confirmation": True,
                        },
                    },
                }
            )
        return actions

    @staticmethod
    def _operation_result_user_view(
        *,
        operation_result: dict[str, Any],
        follow_up: dict[str, Any],
        quick_actions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        result_summary = dict(operation_result.get("result_summary") or {})
        operation_type = str(operation_result.get("operation_type") or "editor_operation")
        needs_attention = bool(result_summary.get("needs_user_attention"))
        quick_action_count = len(quick_actions)
        status_hint = "needs_attention" if needs_attention else "completed"
        if quick_action_count:
            text = (
                f"`{operation_type}` result was recorded. The backend found "
                f"{quick_action_count} safe follow-up Proposal action(s). Review them before execution."
            )
        elif needs_attention:
            text = (
                f"`{operation_type}` result was recorded and needs attention. "
                "Check the diagnostics block for missing inputs or repair advice."
            )
        else:
            text = f"`{operation_type}` result was recorded successfully."

        blocks = [
            {
                "block_type": "editor_operation_result_summary",
                "title": "Editor Operation Result",
                "text": text,
                "data": result_summary,
            }
        ]
        graph_detail_block = EditorOperationService._blueprint_graph_result_detail_block(
            operation_result=operation_result
        )
        if graph_detail_block:
            blocks.append(graph_detail_block)
        if follow_up:
            blocks.append(
                {
                    "block_type": "editor_operation_follow_ups",
                    "title": "Follow-up Candidates",
                    "text": (
                        "Ready candidates can be converted into one pending Proposal at a time."
                        if quick_action_count
                        else "No ready follow-up Proposal is available yet."
                    ),
                    "data": follow_up,
                }
            )

        return {
            "title": "Editor Operation Result",
            "text": text,
            "blocks": blocks,
            "citations_preview": [],
            "quick_actions": quick_actions,
            "status_hint": status_hint,
        }

    @staticmethod
    def _summarize_graph_node(value: Any) -> str:
        if isinstance(value, dict):
            role = str(value.get("role") or "").strip()
            name = str(value.get("node_name") or value.get("name") or value.get("id") or "").strip()
            node_id = str(value.get("node_id") or value.get("id") or value.get("guid") or "").strip()
            node_class = str(value.get("node_class") or "").strip()
            left = name or node_id
            if not left:
                return ""
            parts = []
            if role:
                parts.append(f"{role}:")
            parts.append(left)
            if node_class:
                parts.append(f"[{node_class}]")
            if node_id and node_id != left:
                parts.append(f"({node_id})")
            return " ".join(parts)
        return str(value or "").strip()

    @staticmethod
    def _summarize_graph_pin(value: Any) -> str:
        if isinstance(value, dict):
            summary = str(value.get("summary") or "").strip()
            if summary:
                return summary
            source = dict(value.get("source") or {}) if isinstance(value.get("source"), dict) else {}
            target = dict(value.get("target") or {}) if isinstance(value.get("target"), dict) else {}
            source_text = ".".join(
                item
                for item in (
                    str(source.get("node_name") or source.get("node_id") or "").strip(),
                    str(source.get("pin_name") or source.get("pin_id") or "").strip(),
                )
                if item
            )
            target_text = ".".join(
                item
                for item in (
                    str(target.get("node_name") or target.get("node_id") or "").strip(),
                    str(target.get("pin_name") or target.get("pin_id") or "").strip(),
                )
                if item
            )
            if source_text or target_text:
                return f"{source_text} -> {target_text}".strip()
            return ""
        return str(value or "").strip()

    @staticmethod
    def _summarize_limited_items(values: Any, summarizer: Callable[[Any], str], *, limit: int = 6) -> list[str]:
        if not isinstance(values, list):
            values = [values] if values else []
        items = [summarizer(item) for item in values[:limit]]
        items = [item for item in items if item]
        if len(values) > limit:
            items.append(f"+{len(values) - limit} more")
        return items

    @staticmethod
    def _blueprint_graph_result_detail_block(*, operation_result: dict[str, Any]) -> dict[str, Any] | None:
        result = dict(operation_result.get("result") or {})
        result_summary = dict(operation_result.get("result_summary") or {})
        diagnostics = dict(result_summary.get("operation_diagnostics") or {})
        if diagnostics.get("category") != "blueprint_graph":
            return None

        blueprint_path = EditorOperationService._first_non_empty_text(
            result.get("blueprint_path"),
            diagnostics.get("blueprint_path"),
        )
        graph_name = EditorOperationService._first_non_empty_text(
            result.get("graph_name"),
            diagnostics.get("graph_name"),
        )
        template_id = EditorOperationService._first_non_empty_text(
            result.get("template_id"),
            diagnostics.get("template_id"),
        )
        entry_node_id = EditorOperationService._first_non_empty_text(result.get("entry_node_id"))
        entry_node_name = EditorOperationService._first_non_empty_text(result.get("entry_node_name"))
        created_node_id = EditorOperationService._first_non_empty_text(result.get("created_node_id"))
        created_node_name = EditorOperationService._first_non_empty_text(result.get("created_node_name"))

        items: list[str] = []
        if blueprint_path:
            items.append(f"Blueprint: {blueprint_path}")
        if graph_name:
            items.append(f"Graph: {graph_name}")
        if template_id:
            items.append(f"Template: {template_id}")
        if entry_node_id or entry_node_name:
            items.append(f"Entry node: {entry_node_name or 'unknown'} ({entry_node_id or 'no stable id'})")
        if created_node_id or created_node_name:
            items.append(f"Primary created node: {created_node_name or 'unknown'} ({created_node_id or 'no stable id'})")

        created_nodes = result.get("created_nodes")
        for node_summary in EditorOperationService._summarize_limited_items(
            created_nodes,
            EditorOperationService._summarize_graph_node,
            limit=5,
        ):
            items.append(f"Created: {node_summary}")

        linked_pins = result.get("linked_pins")
        linked_pin_summaries = result.get("linked_pin_summaries")
        link_items = EditorOperationService._summarize_limited_items(
            linked_pins,
            EditorOperationService._summarize_graph_pin,
            limit=5,
        )
        if not link_items:
            link_items = EditorOperationService._as_string_list(linked_pin_summaries)[:5]
        for link_summary in link_items:
            items.append(f"Linked pin: {link_summary}")

        compile_status = EditorOperationService._first_non_empty_text(
            result.get("compile_status"),
            diagnostics.get("compile_status"),
        )
        if compile_status:
            items.append(f"Compile status: {compile_status}")
        dirty_packages = EditorOperationService._as_string_list(
            result.get("dirty_packages") or result_summary.get("dirty_packages")
        )
        if dirty_packages:
            items.append(f"Dirty packages: {', '.join(dirty_packages[:5])}")

        if not items:
            return None

        return {
            "block_type": "editor_operation_graph_details",
            "title": "Blueprint Graph Details",
            "text": "Stable node and pin details reported by UEAgentTool for follow-up repair or manual inspection.",
            "data": {
                "schema_version": "blueprint_graph_result_details_v1",
                "items": items,
                "blueprint_path": blueprint_path,
                "graph_name": graph_name,
                "template_id": template_id,
                "entry_node_id": entry_node_id,
                "entry_node_name": entry_node_name,
                "created_node_id": created_node_id,
                "created_node_name": created_node_name,
                "created_nodes": created_nodes or [],
                "linked_pins": linked_pins or [],
                "linked_pin_summaries": linked_pin_summaries or [],
                "compile_status": compile_status,
                "dirty_packages": dirty_packages,
            },
        }

    @staticmethod
    def prepare_follow_up_proposal_request(
        *,
        source_proposal_id: str,
        candidate: dict[str, Any] | None = None,
        create_request: dict[str, Any] | None = None,
        requested_by: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        safe_candidate = dict(candidate or {})
        if isinstance(safe_candidate.get("candidates"), list) or isinstance(create_request, list):
            raise ValueError("follow_up_materialization_accepts_one_candidate_only")

        missing_inputs = list(safe_candidate.get("missing_inputs") or [])
        if safe_candidate and (safe_candidate.get("proposal_ready") is False or missing_inputs):
            raise ValueError("follow_up_candidate_not_ready_for_proposal")

        hint = dict(safe_candidate.get("create_request_hint") or {})
        request_json = dict(create_request or hint.get("json") or {})
        if not request_json:
            raise ValueError("follow_up_create_request_missing")

        operation_type = str(request_json.get("operation_type") or "").strip()
        if operation_type not in OPERATION_SPECS:
            raise ValueError("follow_up_operation_type_invalid")

        payload = request_json.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("follow_up_payload_must_be_object")

        base_context = dict(request_json.get("context") or {})
        external_context = dict(context or {})
        candidate_id = str(safe_candidate.get("candidate_id") or base_context.get("candidate_id") or "").strip()
        materialized_context = {
            **base_context,
            **external_context,
            "follow_up_materialization": {
                "schema_version": EDITOR_OPERATION_FOLLOW_UP_MATERIALIZATION_VERSION,
                "source_proposal_id": source_proposal_id,
                "candidate_id": candidate_id,
                "source": "editor_operation_follow_up_materialization",
                "auto_execute": False,
            },
        }
        proposal_request = EditorOperationProposalRequest(
            operation_type=operation_type,  # type: ignore[arg-type]
            payload=dict(payload),
            reason=str(request_json.get("reason") or "").strip()
            or f"Create a follow-up Proposal from {source_proposal_id}.",
            source_task_id=str(request_json.get("source_task_id") or "").strip() or None,
            requested_by=requested_by or str(request_json.get("requested_by") or "").strip() or "editor_operation_follow_up",
            context=materialized_context,
        )
        return {
            "schema_version": EDITOR_OPERATION_FOLLOW_UP_MATERIALIZATION_VERSION,
            "source_proposal_id": source_proposal_id,
            "candidate_id": candidate_id,
            "operation_type": operation_type,
            "tool_id": OPERATION_SPECS[operation_type]["tool_id"],
            "proposal_ready": True,
            "auto_execute": False,
            "requires_user_confirmation": True,
            "proposal_request": proposal_request.model_dump(mode="json"),
        }

    def record_operation_result(self, request: EditorOperationResultRequest) -> dict[str, Any] | None:
        proposal = get_proposal(self.db, request.proposal_id)
        if not proposal:
            return None
        if proposal.proposal_type != EDITOR_OPERATION_PROPOSAL_TYPE:
            raise EditorOperationValidationError(
                "proposal_is_not_editor_operation",
                {"proposal_type": proposal.proposal_type},
            )
        if proposal.confirmation_state != "confirmed":
            raise EditorOperationValidationError(
                "proposal_must_be_confirmed_before_execution_result",
                {"confirmation_state": proposal.confirmation_state},
            )

        preview = dict(proposal.dry_run_preview_json or {})
        operation_type = str(request.operation_type or preview.get("operation_type") or "")
        if operation_type and operation_type != str(preview.get("operation_type") or ""):
            raise EditorOperationValidationError(
                "operation_type_mismatch",
                {"expected": preview.get("operation_type"), "received": operation_type},
            )

        result_summary = self._normalize_result_summary(request=request, preview=preview)
        operation_result = {
            "received_at": now_utc().isoformat(),
            "proposal_id": request.proposal_id,
            "operation_type": preview.get("operation_type"),
            "tool_id": preview.get("tool_id"),
            "execution_state": request.execution_state,
            "success": request.success,
            "executed_by": request.executed_by,
            "transaction_id": request.transaction_id,
            "undo_hint": request.undo_hint,
            "result": dict(request.result or {}),
            "result_summary": result_summary,
            "errors": list(request.errors or []),
            "metadata": dict(request.metadata or {}),
        }
        preview["operation_result"] = operation_result
        preview["approval_state"] = "executed" if request.success else request.execution_state
        proposal.dry_run_preview_json = preview
        save_proposal(self.db, proposal)

        task = get_task(self.db, proposal.task_id) if proposal.task_id else None
        if task:
            data = dict(task.data_json or {})
            debug_view = dict(task.debug_view_json or {})
            raw_response = dict(task.raw_response_json or {})
            action_proposals = list(task.action_proposals_json or [])

            editor_operation = dict(data.get("editor_operation") or {})
            if not editor_operation:
                editor_operation = {
                    "operation_type": preview.get("operation_type"),
                    "proposal_created": True,
                }
            editor_operation["operation_result"] = operation_result
            data["editor_operation"] = editor_operation
            data["editor_operation_results"] = list(data.get("editor_operation_results") or []) + [
                operation_result
            ]

            side_effects = list(debug_view.get("side_effects") or [])
            updated_side_effects: list[dict[str, Any]] = []
            matched_side_effect = False
            for item in side_effects:
                current = dict(item)
                if current.get("proposal_id") == request.proposal_id:
                    current["execution_state"] = request.execution_state
                    current["operation_result"] = operation_result
                    current["written_by_backend"] = False
                    matched_side_effect = True
                updated_side_effects.append(current)
            if not matched_side_effect:
                updated_side_effects.append(
                    {
                        "proposal_id": request.proposal_id,
                        "proposal_type": proposal.proposal_type,
                        "operation_type": preview.get("operation_type"),
                        "tool_id": preview.get("tool_id"),
                        "side_effect_level": "confirmed_write",
                        "execution_state": request.execution_state,
                        "written_by_backend": False,
                        "operation_result": operation_result,
                    }
                )
            debug_view["side_effects"] = updated_side_effects

            updated_action_proposals: list[dict[str, Any]] = []
            for item in action_proposals:
                current = dict(item)
                if current.get("proposal_id") == request.proposal_id:
                    current["dry_run_preview"] = preview
                updated_action_proposals.append(current)
            task.action_proposals_json = updated_action_proposals
            task.data_json = data
            task.debug_view_json = debug_view
            if raw_response:
                raw_response["data"] = data
                raw_response["debug_view"] = debug_view
                raw_response["action_proposals"] = updated_action_proposals
                task.raw_response_json = raw_response
            save_task(self.db, task)

        audit_entry = build_audit_entry(
            "editor_operation_result_recorded",
            operation_result,
            task_id=task.task_id if task else None,
            session_id=task.session_id if task else None,
        )
        create_audit_log(
            self.db,
            AuditLogModel(
                audit_id=f"audit_{uuid.uuid4().hex}",
                task_id=task.task_id if task else None,
                session_id=task.session_id if task else None,
                event_type=audit_entry["event_type"],
                payload_json=audit_entry["payload"],
            ),
        )
        follow_up_payload = self.operation_follow_up_candidates(request.proposal_id) or {}
        follow_up = dict(follow_up_payload.get("follow_up") or {})
        quick_actions = self._follow_up_quick_actions(proposal_id=request.proposal_id, follow_up=follow_up)
        return {
            "task": {
                "task_type": "editor_operation_result",
                "status": "completed",
                "finish_reason": "completed",
                "output_complete": True,
            },
            "item": operation_result,
            "proposal": self._proposal_payload(proposal),
            "user_view": self._operation_result_user_view(
                operation_result=operation_result,
                follow_up=follow_up,
                quick_actions=quick_actions,
            ),
            "follow_up": follow_up,
            "follow_up_quick_actions": quick_actions,
        }
