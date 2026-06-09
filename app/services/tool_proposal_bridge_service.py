from __future__ import annotations

from typing import Any

from app.services.editor_operations.catalog import OPERATION_SPECS
from app.services.mcp_tool_mapping import resolve_local_tool_id_from_name
from app.services.tool_proposal_bridge_payloads import (
    apply_context_defaults,
    normalize_tool_arguments,
)
from app.tools.registry import ToolSpec, get_tool_spec

TOOL_REGISTRY_PROPOSAL_BRIDGE_VERSION = "tool_registry_proposal_bridge_v1"
TOOL_ID_TO_OPERATION_ALIASES = {
    "editor_blueprint_add_step": "add_blueprint_node_template",
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
        requested_tool_name = str(tool_id or "").strip()
        clean_tool_id = resolve_local_tool_id_from_name(requested_tool_name) or requested_tool_name
        spec = get_tool_spec(clean_tool_id)
        if not spec:
            return cls._blocked(
                tool_id=clean_tool_id,
                requested_tool_name=requested_tool_name,
                reason="tool_not_registered",
                message="Tool id is not registered in the local Tool Registry.",
            )
        if not spec.enabled:
            return cls._blocked(
                tool_id=spec.tool_id,
                spec=spec,
                requested_tool_name=requested_tool_name,
                reason="tool_disabled",
                message="Tool is disabled by registry configuration.",
            )
        if spec.side_effect_level != "confirmed_write" or not spec.effective_requires_confirmation:
            return cls._blocked(
                tool_id=spec.tool_id,
                spec=spec,
                requested_tool_name=requested_tool_name,
                reason="tool_is_not_confirmed_write",
                message="Only confirmed-write editor tools can be converted to Proposal requests.",
            )

        operation_type = cls.tool_to_operation_map().get(spec.tool_id)
        if not operation_type:
            return cls._blocked(
                tool_id=spec.tool_id,
                spec=spec,
                requested_tool_name=requested_tool_name,
                reason="tool_not_mapped_to_editor_operation",
                message="Tool has no matching editor operation proposal type.",
            )

        arguments_with_context = apply_context_defaults(
            operation_type=operation_type,
            arguments=dict(arguments or {}),
            context=dict(context or {}),
        )
        payload = normalize_tool_arguments(
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
            "requested_tool_name": requested_tool_name,
            "tool_name_resolved_via_alias": requested_tool_name != spec.tool_id,
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
    def _blocked(
        cls,
        *,
        tool_id: str,
        reason: str,
        message: str,
        spec: ToolSpec | None = None,
        requested_tool_name: str | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": TOOL_REGISTRY_PROPOSAL_BRIDGE_VERSION,
            "status": "blocked",
            "tool_id": tool_id,
            "requested_tool_name": requested_tool_name or tool_id,
            "tool_name_resolved_via_alias": bool(requested_tool_name and requested_tool_name != tool_id),
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
