from __future__ import annotations

import math
import re
import uuid
from typing import Any

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
        text_path = EditorOperationService._extract_unreal_path_from_text(query_text)
        if text_path:
            return text_path
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
                operation_types={"set_material_instance_parameter"},
                keys=("material_instance_path", "asset_path", "final_asset_path"),
            )
            if recent_material_path:
                return str(recent_material_path)
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
        return ("", "")

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
