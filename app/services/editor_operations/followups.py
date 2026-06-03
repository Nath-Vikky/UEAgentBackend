from __future__ import annotations

import re
from typing import Any


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


__all__ = [
    "follow_up_folder_slug",
    "follow_up_quick_actions",
    "redirector_follow_up_folders",
]
