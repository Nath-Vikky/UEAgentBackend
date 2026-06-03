from __future__ import annotations

import re
from typing import Any

from app.services.editor_operations.blueprint_result_diagnostics import first_non_empty_text


def redirector_follow_up_folders(
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


def operation_follow_up_payload(
    *,
    proposal_id: str,
    preview: dict[str, Any],
    is_editor_operation: bool,
) -> dict[str, Any]:
    if not is_editor_operation:
        return {
            "follow_up": {
                "schema_version": "editor_operation_follow_up_candidates_v1",
                "proposal_id": proposal_id,
                "status": "not_applicable",
                "reason": "proposal_is_not_editor_operation",
                "candidates": [],
            }
        }

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
    blueprint_path = first_non_empty_text(result.get("blueprint_path"), payload.get("blueprint_path"))
    graph_name = first_non_empty_text(result.get("graph_name"), payload.get("graph_name"), "EventGraph")
    entry_event = first_non_empty_text(result.get("entry_event"), payload.get("entry_event"))

    candidates: list[dict[str, Any]] = []
    if "connect_expected_exec_pins" in action_ids:
        candidates.append(
            _connect_expected_exec_pins_candidate(
                proposal_id=proposal_id,
                result=result,
                payload=payload,
                blueprint_path=blueprint_path,
                graph_name=graph_name,
                entry_event=entry_event,
            )
        )

    if "open_blueprint_compile_results" in action_ids or "report_compile_status" in action_ids:
        candidates.append(
            _retry_compile_blueprint_candidate(
                proposal_id=proposal_id,
                blueprint_path=blueprint_path,
            )
        )

    if bool(operation_result.get("success")):
        source_operation_type = str(preview.get("operation_type") or operation_result.get("operation_type") or "")
        for folder_path in redirector_follow_up_folders(
            operation_type=source_operation_type,
            payload=payload,
            result=result,
        ):
            candidates.append(_fixup_redirectors_candidate(proposal_id=proposal_id, folder_path=folder_path))

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


def node_identifier(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("node_id", "id", "guid", "node_name", "name", "source", "target"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
        return ""
    return str(value or "").strip()


def first_node_identifier(value: Any) -> str:
    if isinstance(value, list):
        for item in value:
            identifier = node_identifier(item)
            if identifier:
                return identifier
        return ""
    return node_identifier(value)


def entry_event_node_hint(entry_event: str) -> str:
    if not entry_event:
        return ""
    if entry_event == "BeginPlay":
        return "EventBeginPlay"
    if entry_event == "Tick":
        return "EventTick"
    if entry_event.startswith("Actor"):
        return f"Event{entry_event}"
    return f"Event{entry_event}"


def follow_up_quick_actions(*, proposal_id: str, follow_up: dict[str, Any]) -> list[dict[str, Any]]:
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


def follow_up_folder_slug(folder_path: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", folder_path.strip("/"))[:48].strip("_") or "folder"


def _connect_expected_exec_pins_candidate(
    *,
    proposal_id: str,
    result: dict[str, Any],
    payload: dict[str, Any],
    blueprint_path: str,
    graph_name: str,
    entry_event: str,
) -> dict[str, Any]:
    source_node_id = first_non_empty_text(
        result.get("source_node_id"),
        result.get("entry_node_id"),
        result.get("event_node_id"),
        payload.get("source_node_id"),
        entry_event_node_hint(entry_event),
    )
    target_node_id = first_non_empty_text(
        result.get("target_node_id"),
        result.get("created_node_id"),
        first_node_identifier(result.get("created_nodes")),
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
    return {
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


def _retry_compile_blueprint_candidate(*, proposal_id: str, blueprint_path: str) -> dict[str, Any]:
    follow_payload = {
        "blueprint_path": blueprint_path,
        "compile_mode": "default",
    }
    missing_inputs = [key for key in ("blueprint_path",) if not str(follow_payload.get(key) or "").strip()]
    return {
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


def _fixup_redirectors_candidate(*, proposal_id: str, folder_path: str) -> dict[str, Any]:
    folder_slug = follow_up_folder_slug(folder_path)
    follow_payload = {
        "folder_path": folder_path,
        "recursive": True,
        "max_redirectors": 50,
    }
    return {
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


__all__ = [
    "entry_event_node_hint",
    "first_node_identifier",
    "follow_up_folder_slug",
    "follow_up_quick_actions",
    "node_identifier",
    "operation_follow_up_payload",
    "redirector_follow_up_folders",
]
