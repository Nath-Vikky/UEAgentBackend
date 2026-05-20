from __future__ import annotations

import math
import re
import uuid
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
    "get_variable",
    "print_string",
    "sequence_print_strings",
    "set_variable",
}

BLUEPRINT_NODE_ENTRY_EVENTS = {
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
    def supported_operations() -> dict[str, Any]:
        return {
            "protocol_version": EDITOR_OPERATION_PROTOCOL_VERSION,
            "proposal_type": EDITOR_OPERATION_PROPOSAL_TYPE,
            "transport": "http",
            "mcp_like": True,
            "safety_policy": {
                "side_effect_level": "confirmed_write",
                "llm_direct_execution": False,
                "requires_frontend_confirmation": True,
                "ue_plugin_executes_editor_api": True,
            },
            "items": [
                {
                    "operation_type": operation_type,
                    "tool_id": spec["tool_id"],
                    "title": spec["title"],
                    "summary": spec["summary"],
                    "required_fields": spec["required_fields"],
                    "frontend_status": spec["frontend_status"],
                }
                for operation_type, spec in OPERATION_SPECS.items()
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
    def _selected_asset_path(request: UnifiedTaskRequest) -> str | None:
        selected_assets = EditorOperationService._candidate_asset_paths(request)
        if selected_assets:
            return selected_assets[0]
        return None

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

        if EditorOperationService._references_recent_target(query_text):
            recent_actor = EditorOperationService._recent_editor_operation_value(
                context_bundle=context_bundle,
                operation_types={"place_actor_in_level", "set_actor_transform"},
                keys=("actor_reference", "actor_label", "actor_name"),
            )
            if recent_actor:
                return str(recent_actor)
        return None

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
                operation_types={"set_material_instance_parameter", "set_material_instance_texture_parameter"},
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
            r"\b([A-Za-z][A-Za-z0-9_]*(?:Text|TextBlock|Label|Title|Name|Value))\b",
            query_text,
            flags=re.IGNORECASE,
        ):
            candidate = match.group(1)
            if not candidate.lower().startswith(("wbp_", "ui_")):
                return candidate
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
        ):
            if known_name.lower() in query_text.lower():
                return known_name
        match = re.search(
            r"(?:参数|parameter)\s*[:：]?\s*([A-Za-z][A-Za-z0-9_ ]{0,79})",
            query_text,
            flags=re.IGNORECASE,
        )
        return match.group(1).strip() if match else None

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

        wants_place_actor = any(
            token in query_lower or token in query_text
            for token in ("place", "spawn", "add to level", "put", "放置", "摆放", "放到", "放入", "加入关卡")
        ) and any(
            token in query_lower or token in query_text
            for token in ("actor", "blueprint", "bp_", "level", "world", "map", "蓝图", "关卡", "场景", "灯光", "相机")
        )
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
            for token in ("add", "create", "\u653e", "\u6dfb\u52a0", "\u521b\u5efa")
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
                    "graph_name": request.payload.get("graph_name") or "EventGraph",
                    "messages": request.payload.get("messages")
                    or [
                        request.payload.get("message") or "Sequence step 1 from UEAgent",
                        request.payload.get("message_2") or "Sequence step 2 from UEAgent",
                    ],
                    "entry_event": request.payload.get("entry_event") or "BeginPlay",
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
                    "graph_name": request.payload.get("graph_name") or "EventGraph",
                    "message": request.payload.get("message")
                    or request.payload.get("string_value")
                    or "Branch reached from UEAgent",
                    "entry_event": request.payload.get("entry_event") or "BeginPlay",
                    "condition_default": condition_default,
                    "branch_path": request.payload.get("branch_path") or ("false" if false_branch_signal else "true"),
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
                    "graph_name": request.payload.get("graph_name") or "EventGraph",
                    "variable_name": variable_name,
                    "entry_event": request.payload.get("entry_event") or ("BeginPlay" if template_id == "set_variable" else ""),
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
                        "graph_name": request.payload.get("graph_name") or "EventGraph",
                        "function_name": function_name,
                        "entry_event": request.payload.get("entry_event") or "BeginPlay",
                        "compile_after_edit": bool(request.payload.get("compile_after_edit", True)),
                    },
                    reason=query_text,
                    requested_by="agent_chat",
                    context=request.context.model_dump(mode="json"),
                )

        wants_blueprint_print_string = (
            ("蓝图" in query_text or "blueprint" in query_lower or "bp_" in query_lower)
            and any(token in query_lower or token in query_text for token in ("print string", "printstring", "打印字符串", "打印文本"))
            and any(token in query_lower or token in query_text for token in ("add", "create", "放", "添加", "创建"))
        )
        if wants_blueprint_print_string:
            blueprint_path = EditorOperationService._detect_blueprint_path_from_request(
                request,
                query_text,
                context_bundle,
            )
            return EditorOperationProposalRequest(
                operation_type="add_blueprint_node_template",
                payload={
                    "blueprint_path": blueprint_path or "",
                    "template_id": "print_string",
                    "graph_name": request.payload.get("graph_name") or "EventGraph",
                    "message": request.payload.get("message")
                    or request.payload.get("string_value")
                    or "Hello from UEAgent",
                    "entry_event": request.payload.get("entry_event")
                    or ("BeginPlay" if ("beginplay" in query_lower or "eventbeginplay" in query_lower or "开始播放" in query_text) else ""),
                    "compile_after_edit": bool(request.payload.get("compile_after_edit", True)),
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
        wants_blueprint_compile = selected_asset and (
            "blueprint" in query_lower or "蓝图" in query_text or str(selected_asset).lower().endswith("_c")
        ) and any(token in query_lower or token in query_text for token in ("compile", "编译"))
        if wants_blueprint_compile:
            return EditorOperationProposalRequest(
                operation_type="compile_blueprint",
                payload={"blueprint_path": selected_asset},
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
            "function": "call_function",
            "function_call": "call_function",
            "get": "get_variable",
            "get_var": "get_variable",
            "get_variable": "get_variable",
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
            "beginplay": "BeginPlay",
            "eventbeginplay": "BeginPlay",
            "receivebeginplay": "BeginPlay",
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
            if template_id in {"branch_print_string", "call_function", "sequence_print_strings", "set_variable"} and not str(entry_event_raw or "").strip():
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
            if template_id in {"branch_print_string", "print_string", "sequence_print_strings"}:
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
                "sequence_output_count",
                "function_name",
                "function_target",
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
        if operation_type in {
            "add_umg_widget",
            "set_umg_widget_text",
            "set_umg_widget_layout",
            "set_umg_widget_visibility",
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
        if operation_type in {"set_material_instance_parameter", "set_material_instance_texture_parameter"}:
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
                "sequence_output_count",
                "messages",
                "variable_name",
                "variable_scope",
                "variable_value",
                "function_name",
                "function_target",
                "created_nodes",
                "linked_nodes",
                "linked_pins",
                "compile_status",
                "dirty",
                "dirty_packages",
            ],
            "connect_blueprint_nodes": [
                "blueprint_path",
                "graph_name",
                "source_node_id",
                "source_pin_name",
                "target_node_id",
                "target_pin_name",
                "linked_pins",
                "compile_status",
                "dirty",
                "dirty_packages",
            ],
            "compile_blueprint": ["blueprint_path", "compile_status", "messages"],
            "batch_rename_assets": ["renamed_assets", "dirty_packages", "failed_items"],
            "move_assets": ["moved_assets", "dirty_packages", "failed_items"],
            "add_umg_widget": ["widget_blueprint_path", "widget_name", "dirty", "dirty_packages"],
            "set_umg_widget_text": ["widget_blueprint_path", "widget_name", "dirty", "dirty_packages"],
            "set_umg_widget_layout": ["widget_blueprint_path", "widget_name", "dirty", "dirty_packages"],
            "set_umg_widget_visibility": ["widget_blueprint_path", "widget_name", "dirty", "dirty_packages"],
            "place_actor_in_level": ["actor_label", "actor_path", "level_dirty", "dirty_packages"],
            "set_actor_transform": ["actor_reference", "transform_mode", "level_dirty", "dirty_packages"],
            "set_material_instance_parameter": ["material_instance_path", "parameter_name", "dirty", "dirty_packages"],
            "set_material_instance_texture_parameter": [
                "material_instance_path",
                "parameter_name",
                "texture_path",
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
            "needs_user_attention": (not request.success) or bool(error_codes) or failed_field_count > 0,
        }

    def list_operation_history(self, *, limit: int = 50, operation_type: str | None = None) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 200))
        fetch_limit = safe_limit if not operation_type else min(max(safe_limit * 4, 50), 500)
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
                    "result_summary": operation_result.get("result_summary", {}),
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
            },
            "items": items,
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
        return {
            "item": operation_result,
            "proposal": self._proposal_payload(proposal),
        }
