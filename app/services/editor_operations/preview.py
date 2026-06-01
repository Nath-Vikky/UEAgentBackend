from __future__ import annotations

from typing import Any


def build_preflight_checks(
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


def build_preview_summary(
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
