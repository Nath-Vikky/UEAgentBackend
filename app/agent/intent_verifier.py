from __future__ import annotations

from typing import Any

from app.agent.intent_models import VerifiedIntent
from app.agent.tool_permission import decide_tool_permission
from app.tools.registry import get_tool_spec


def _active_targets(context_bundle: dict[str, Any]) -> dict[str, Any]:
    return dict((context_bundle.get("agent_turn_context") or {}).get("active_targets") or {})


def _target_available(target_kind: str, context_bundle: dict[str, Any]) -> bool:
    active = _active_targets(context_bundle)
    if target_kind in {"none", "knowledge_base", "project_inventory", "project_file"}:
        return True
    if target_kind == "selected_context":
        return any(bool(value.get("available")) for value in active.values() if isinstance(value, dict))
    mapping = {
        "selected_asset": "asset",
        "asset": "asset",
        "current_blueprint": "blueprint",
        "blueprint": "blueprint",
        "widget": "widget",
        "selected_actor": "level_actor",
        "level_actor": "level_actor",
        "selected_material_instance": "material",
        "material": "material",
        "current_code_file": "code",
        "current_log": "log",
    }
    key = mapping.get(target_kind)
    if not key:
        return False
    return bool(dict(active.get(key) or {}).get("available"))


def _target_resolution_status(draft: dict[str, Any], context_bundle: dict[str, Any]) -> str:
    target_kind = str(draft.get("target_kind") or "none")
    if target_kind in {"none", "knowledge_base", "project_inventory", "project_file"}:
        return "not_required"
    if _target_available(target_kind, context_bundle):
        return "resolved"
    return "missing_active_context"


def _verified_tool_id(draft: dict[str, Any], routing: dict[str, Any]) -> str | None:
    route_tool = (routing.get("route") or {}).get("selected_tool_id")
    if route_tool:
        return str(route_tool)
    for tool_id in list(draft.get("candidate_tools") or []):
        if get_tool_spec(str(tool_id)):
            return str(tool_id)
    return None


def verify_intent(
    *,
    draft: dict[str, Any],
    routing: dict[str, Any],
    context_bundle: dict[str, Any],
    free_chat: bool = False,
) -> dict[str, Any]:
    keyword_report = dict(draft.get("route_keyword_verifier") or {})
    selected_tool_id = _verified_tool_id(draft, routing)
    if keyword_report.get("pure_smalltalk_signal") and selected_tool_id:
        selected_tool_id = None
    permission = decide_tool_permission(selected_tool_id, free_chat=free_chat) if selected_tool_id else {}
    route_type = str((routing.get("intent") or {}).get("route_type") or "direct_answer")
    corrections: list[dict[str, Any]] = []
    safety_flags: list[str] = []
    target_status = _target_resolution_status(draft, context_bundle)

    if target_status == "missing_active_context":
        safety_flags.append("missing_active_context")
        corrections.append(
            {
                "correction_id": "selected_context_needs_active_target",
                "from": draft.get("target_kind"),
                "to": "ask_user_to_select_target",
                "reason": "The user used a selected/current-context reference, but no matching active UE target is available.",
            }
        )

    if permission:
        if permission["status"] == "proposal" and route_type != "proposal_wait":
            corrections.append(
                {
                    "correction_id": "write_tool_requires_proposal",
                    "from": route_type,
                    "to": "proposal_wait",
                    "reason": permission["reason"],
                }
            )
            route_type = "proposal_wait"
            safety_flags.append("requires_user_confirmation")
        elif permission["status"] in {"deny", "ask"}:
            safety_flags.append(f"tool_permission_{permission['status']}")
            corrections.append(
                {
                    "correction_id": "tool_permission_gate",
                    "from": selected_tool_id,
                    "to": permission["status"],
                    "reason": permission["reason"],
                }
            )

    if keyword_report.get("pure_smalltalk_signal") and _verified_tool_id(draft, routing):
        corrections.append(
            {
                "correction_id": "smalltalk_blocks_tool_selection",
                "from": _verified_tool_id(draft, routing),
                "to": "direct_answer",
                "reason": "Pure smalltalk should not call editor tools unless another task signal is present.",
            }
        )

    if keyword_report.get("hard_write_signal") and not selected_tool_id:
        safety_flags.append("write_signal_without_tool")

    if draft.get("requested_write") and not safety_flags:
        safety_flags.append("write_intent_detected")

    verified = VerifiedIntent(
        intent_type=str(draft.get("intent_type") or "unknown"),
        target_kind=str(draft.get("target_kind") or "none"),
        target_resolution_status=target_status,
        selected_tool_id=selected_tool_id,
        route_type=route_type,
        confidence=float(draft.get("confidence") or 0.0),
        corrections=corrections,
        safety_flags=safety_flags,
        permission_decision=permission,
    )
    return verified.model_dump()


__all__ = ["verify_intent"]
