from __future__ import annotations

from typing import Any

from app.schemas.requests import EditorOperationResultRequest


def build_operation_result_payload(
    *,
    request: EditorOperationResultRequest,
    preview: dict[str, Any],
    result_summary: dict[str, Any],
    received_at: str,
) -> dict[str, Any]:
    return {
        "received_at": received_at,
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


def apply_operation_result_to_task_payloads(
    *,
    data: dict[str, Any],
    debug_view: dict[str, Any],
    raw_response: dict[str, Any],
    action_proposals: list[Any],
    proposal_id: str,
    proposal_type: str,
    preview: dict[str, Any],
    operation_result: dict[str, Any],
    execution_state: str,
) -> dict[str, Any]:
    updated_data = dict(data or {})
    updated_debug_view = dict(debug_view or {})
    updated_raw_response = dict(raw_response or {})
    updated_action_proposals = _updated_action_proposals(
        action_proposals=action_proposals,
        proposal_id=proposal_id,
        preview=preview,
    )

    editor_operation = dict(updated_data.get("editor_operation") or {})
    if not editor_operation:
        editor_operation = {
            "operation_type": preview.get("operation_type"),
            "proposal_created": True,
        }
    editor_operation["operation_result"] = operation_result
    updated_data["editor_operation"] = editor_operation
    updated_data["editor_operation_results"] = list(updated_data.get("editor_operation_results") or []) + [
        operation_result
    ]

    updated_debug_view["side_effects"] = _updated_side_effects(
        side_effects=updated_debug_view.get("side_effects"),
        proposal_id=proposal_id,
        proposal_type=proposal_type,
        preview=preview,
        operation_result=operation_result,
        execution_state=execution_state,
    )

    if updated_raw_response:
        updated_raw_response["data"] = updated_data
        updated_raw_response["debug_view"] = updated_debug_view
        updated_raw_response["action_proposals"] = updated_action_proposals

    return {
        "data": updated_data,
        "debug_view": updated_debug_view,
        "raw_response": updated_raw_response,
        "action_proposals": updated_action_proposals,
    }


def _updated_side_effects(
    *,
    side_effects: Any,
    proposal_id: str,
    proposal_type: str,
    preview: dict[str, Any],
    operation_result: dict[str, Any],
    execution_state: str,
) -> list[dict[str, Any]]:
    updated_side_effects: list[dict[str, Any]] = []
    matched_side_effect = False
    for item in list(side_effects or []):
        current = dict(item)
        if current.get("proposal_id") == proposal_id:
            current["execution_state"] = execution_state
            current["operation_result"] = operation_result
            current["written_by_backend"] = False
            matched_side_effect = True
        updated_side_effects.append(current)
    if not matched_side_effect:
        updated_side_effects.append(
            {
                "proposal_id": proposal_id,
                "proposal_type": proposal_type,
                "operation_type": preview.get("operation_type"),
                "tool_id": preview.get("tool_id"),
                "side_effect_level": "confirmed_write",
                "execution_state": execution_state,
                "written_by_backend": False,
                "operation_result": operation_result,
            }
        )
    return updated_side_effects


def _updated_action_proposals(
    *,
    action_proposals: list[Any],
    proposal_id: str,
    preview: dict[str, Any],
) -> list[dict[str, Any]]:
    updated_action_proposals: list[dict[str, Any]] = []
    for item in action_proposals:
        current = dict(item)
        if current.get("proposal_id") == proposal_id:
            current["dry_run_preview"] = preview
        updated_action_proposals.append(current)
    return updated_action_proposals


__all__ = [
    "apply_operation_result_to_task_payloads",
    "build_operation_result_payload",
]
