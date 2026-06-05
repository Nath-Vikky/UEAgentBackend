from __future__ import annotations

from typing import Any

from app.services.editor_operations.catalog import OPERATION_SPECS
from app.tools.registry import ToolSpec, get_tool_spec

TOOL_REGISTRY_PROPOSAL_BRIDGE_VERSION = "tool_registry_proposal_bridge_v1"
TOOL_ID_TO_OPERATION_ALIASES = {
    "editor_blueprint_add_step": "add_blueprint_node_template",
}
BLUEPRINT_STEP_NAME_TO_TEMPLATE_ID = {
    "print": "print_string",
    "printstring": "print_string",
    "print_string": "print_string",
    "print string": "print_string",
    "delay": "delay_print_string",
    "delay print": "delay_print_string",
    "delay print string": "delay_print_string",
    "branch": "branch_print_string",
    "branch print": "branch_print_string",
    "sequence": "sequence_print_strings",
    "sequence print": "sequence_print_strings",
    "custom event": "custom_event_print_string",
    "custom event print": "custom_event_print_string",
    "enhanced input": "enhanced_input_print_string",
    "enhanced input print": "enhanced_input_print_string",
}


class ToolProposalBridgeService:
    """Map confirmed-write ToolSpec calls to editor-operation Proposal requests."""

    @staticmethod
    def tool_to_operation_map() -> dict[str, str]:
        mapping = {
            str(spec["tool_id"]): operation_type
            for operation_type, spec in OPERATION_SPECS.items()
        }
        mapping.update(TOOL_ID_TO_OPERATION_ALIASES)
        return mapping

    @classmethod
    def prepare_proposal(
        cls,
        *,
        tool_id: str,
        arguments: dict[str, Any] | None = None,
        reason: str | None = None,
        requested_by: str | None = None,
        source_task_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_tool_id = str(tool_id or "").strip()
        spec = get_tool_spec(clean_tool_id)
        if not spec:
            return cls._blocked(
                tool_id=clean_tool_id,
                reason="tool_not_registered",
                message="Tool id is not registered in the local Tool Registry.",
            )
        if not spec.enabled:
            return cls._blocked(
                tool_id=spec.tool_id,
                spec=spec,
                reason="tool_disabled",
                message="Tool is disabled by registry configuration.",
            )
        if spec.side_effect_level != "confirmed_write" or not spec.effective_requires_confirmation:
            return cls._blocked(
                tool_id=spec.tool_id,
                spec=spec,
                reason="tool_is_not_confirmed_write",
                message="Only confirmed-write editor tools can be converted to Proposal requests.",
            )

        operation_type = cls.tool_to_operation_map().get(spec.tool_id)
        if not operation_type:
            return cls._blocked(
                tool_id=spec.tool_id,
                spec=spec,
                reason="tool_not_mapped_to_editor_operation",
                message="Tool has no matching editor operation proposal type.",
            )

        arguments_with_context = cls._apply_context_defaults(
            tool_id=spec.tool_id,
            operation_type=operation_type,
            arguments=dict(arguments or {}),
            context=dict(context or {}),
        )
        payload = cls._normalize_arguments(
            tool_id=spec.tool_id,
            operation_type=operation_type,
            arguments=arguments_with_context,
        )
        proposal_request = {
            "operation_type": operation_type,
            "payload": payload,
            "reason": reason or f"Tool Registry bridge prepared a Proposal for {spec.title}.",
            "source_task_id": source_task_id,
            "requested_by": requested_by or "tool_registry_proposal_bridge",
            "context": dict(context or {}),
        }
        return {
            "schema_version": TOOL_REGISTRY_PROPOSAL_BRIDGE_VERSION,
            "status": "prepared",
            "tool_id": spec.tool_id,
            "tool_title": spec.title,
            "operation_type": operation_type,
            "side_effect_level": spec.side_effect_level,
            "requires_user_confirmation": True,
            "auto_execute": False,
            "direct_editor_write_allowed": False,
            "proposal_request": proposal_request,
            "proposal_request_hint": {
                "method": "POST",
                "path": "/api/v1/editor-operations/proposals",
                "json": proposal_request,
            },
            "safety_policy": {
                "llm_output_never_executes_editor_write_directly": True,
                "backend_only_creates_pending_proposals": True,
                "ue_plugin_executes_after_user_confirmation": True,
            },
        }

    @classmethod
    def _normalize_arguments(
        cls,
        *,
        tool_id: str,
        operation_type: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if tool_id != "editor_blueprint_add_step" or operation_type != "add_blueprint_node_template":
            return arguments
        payload = dict(arguments)
        step_name = str(
            payload.pop("step_name", "")
            or payload.pop("name", "")
            or payload.pop("node_name", "")
            or payload.get("template_id", "")
        ).strip()
        template_id = str(payload.get("template_id") or "").strip()
        if not template_id and step_name:
            template_id = BLUEPRINT_STEP_NAME_TO_TEMPLATE_ID.get(_normalize_step_name(step_name), "")
        if template_id:
            payload["template_id"] = template_id
        if "message" not in payload and "text" in payload:
            payload["message"] = payload.pop("text")
        else:
            payload.pop("text", None)
        return payload

    @classmethod
    def _apply_context_defaults(
        cls,
        *,
        tool_id: str,
        operation_type: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        del tool_id
        if operation_type not in {
            "add_blueprint_node_template",
            "connect_blueprint_nodes",
            "compile_blueprint",
        }:
            return arguments
        blueprint_context = _blueprint_edit_context(context)
        if not blueprint_context:
            return arguments
        payload = dict(arguments)
        _set_missing(payload, "blueprint_path", blueprint_context.get("blueprint_path"))
        if operation_type in {"add_blueprint_node_template", "connect_blueprint_nodes"}:
            _set_missing(payload, "graph_name", blueprint_context.get("graph_name"))
        if operation_type == "connect_blueprint_nodes":
            cursor_node = blueprint_context.get("cursor_node")
            cursor_node = cursor_node if isinstance(cursor_node, dict) else {}
            _set_missing(payload, "source_node_id", cursor_node.get("node_id"))
            _set_missing(payload, "source_pin_name", _first_pin_name(cursor_node, direction="output", fallback="then"))
        return payload

    @classmethod
    def _blocked(
        cls,
        *,
        tool_id: str,
        reason: str,
        message: str,
        spec: ToolSpec | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": TOOL_REGISTRY_PROPOSAL_BRIDGE_VERSION,
            "status": "blocked",
            "tool_id": tool_id,
            "tool_title": spec.title if spec else "",
            "operation_type": "",
            "side_effect_level": spec.side_effect_level if spec else "",
            "requires_user_confirmation": bool(spec.effective_requires_confirmation) if spec else False,
            "auto_execute": False,
            "direct_editor_write_allowed": False,
            "block_reason": reason,
            "message": message,
            "proposal_request": {},
            "proposal_request_hint": {},
            "safety_policy": {
                "llm_output_never_executes_editor_write_directly": True,
                "backend_only_creates_pending_proposals": True,
                "ue_plugin_executes_after_user_confirmation": True,
            },
        }


def _normalize_step_name(value: str) -> str:
    return " ".join(value.replace("-", " ").replace("_", " ").strip().lower().split())


def _blueprint_edit_context(context: dict[str, Any]) -> dict[str, Any]:
    direct = context.get("blueprint_edit_context")
    if isinstance(direct, dict):
        return direct
    active_context = context.get("active_context")
    if isinstance(active_context, dict):
        nested = active_context.get("blueprint_edit_context")
        if isinstance(nested, dict):
            return nested
        blueprint = active_context.get("blueprint")
        if isinstance(blueprint, dict):
            return {
                "blueprint_path": blueprint.get("current_blueprint_path"),
                "graph_name": blueprint.get("current_graph_name"),
                "cursor_node": blueprint.get("current_node_summary"),
            }
    return {}


def _set_missing(payload: dict[str, Any], key: str, value: Any) -> None:
    if payload.get(key) in (None, "") and value not in (None, ""):
        payload[key] = value


def _first_pin_name(cursor_node: dict[str, Any], *, direction: str, fallback: str) -> str:
    for pin in cursor_node.get("pins") or []:
        if not isinstance(pin, dict):
            continue
        pin_direction = str(pin.get("direction") or pin.get("pin_direction") or "").strip().lower()
        pin_type = str(pin.get("pin_type") or pin.get("type") or pin.get("category") or "").strip().lower()
        if direction and pin_direction and direction not in pin_direction:
            continue
        if pin_type and "exec" not in pin_type:
            continue
        name = str(pin.get("pin_name") or pin.get("name") or "").strip()
        if name:
            return name
    return fallback
