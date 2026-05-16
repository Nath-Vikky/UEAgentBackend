from __future__ import annotations

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
        selected_assets = list(request.context.selected_assets or [])
        if selected_assets:
            return str(selected_assets[0])
        asset_items = request.payload.get("asset_items") or request.payload.get("assets") or []
        if isinstance(asset_items, list) and asset_items:
            first = asset_items[0]
            if isinstance(first, dict):
                return str(first.get("asset_path") or first.get("package_path") or "")
            return str(first)
        return None

    @staticmethod
    def detect_request(request: UnifiedTaskRequest) -> EditorOperationProposalRequest | None:
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
