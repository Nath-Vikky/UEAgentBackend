from __future__ import annotations

from typing import Any

from app.services.editor_operations.blueprint_graph_policy import (
    build_blueprint_graph_policy_preview,
)
from app.services.editor_operations.catalog import (
    EDITOR_OPERATION_PROPOSAL_TYPE,
    EDITOR_OPERATION_PROTOCOL_VERSION,
)


def build_editor_operation_action_proposal(
    *,
    proposal_id: str,
    operation_type: str,
    spec: dict[str, Any],
    normalized_payload: dict[str, Any],
    before_summary: str,
    after_summary: str,
    rationale: str,
    affected_targets: list[dict[str, Any]],
    preflight_checks: list[dict[str, Any]],
    expected_result_contract: dict[str, Any],
    preview_summary: dict[str, Any],
    source_task_id: str | None,
    context: dict[str, Any],
    policy_reason: str = "",
) -> dict[str, Any]:
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
        "source_task_id": source_task_id,
        "context": context,
        "execution_contract": {
            "executor": "ue_plugin",
            "execute_after_confirmation": True,
            "result_endpoint": "POST /api/v1/editor-operations/results",
            "llm_direct_execution": False,
            "undo_required": True,
            "auto_save": False,
        },
    }
    if operation_type == "add_blueprint_node_template":
        dry_run_preview["blueprint_graph_policy"] = build_blueprint_graph_policy_preview(
            normalized_payload,
            policy_reason,
        )

    display_hints = {
        "ui": "editor_operation_confirmation",
        "operation_type": operation_type,
        "tool_id": spec["tool_id"],
        "frontend_status": spec["frontend_status"],
        "requires_ue_plugin_execution": True,
        "confirm_endpoint": f"/api/v1/editor-operations/proposals/{proposal_id}/confirm",
        "reject_endpoint": f"/api/v1/editor-operations/proposals/{proposal_id}/reject",
        "generic_decision_endpoint": f"/api/v1/proposals/{proposal_id}/decision",
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
        "proposal_id": proposal_id,
        "title": spec["title"],
        "proposal_type": EDITOR_OPERATION_PROPOSAL_TYPE,
        "before_summary": before_summary,
        "after_summary": after_summary,
        "rationale": rationale,
        "risk_flags": spec["risk_flags"],
        "dry_run_preview": dry_run_preview,
        "display_hints": display_hints,
        "requires_confirmation": True,
        "confirmation": {
            "state": "pending",
            "decision_endpoint": f"/api/v1/proposals/{proposal_id}/decision",
        },
    }


__all__ = ["build_editor_operation_action_proposal"]
