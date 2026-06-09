from __future__ import annotations

from typing import Any

from app.tools.registry import get_tool_spec

TOOL_PLAN_SELF_CHECK_VERSION = "tool_plan_self_check_v1"


def check_tool_plan_consistency(
    *,
    intent_draft: dict[str, Any],
    verified_intent: dict[str, Any],
    context_resolution: dict[str, Any],
    tool_plan: dict[str, Any],
    routing: dict[str, Any],
) -> dict[str, Any]:
    """Validate the structured Agent plan without changing execution.

    The check is intentionally diagnostic-only. It helps Debug View and eval
    catch route/tool/context mismatches while the existing handler path remains
    unchanged.
    """

    tool_id = _optional_text(tool_plan.get("tool_id") or verified_intent.get("selected_tool_id"))
    spec = get_tool_spec(tool_id) if tool_id else None
    mode = _optional_text(tool_plan.get("mode")) or "direct_answer"
    side_effect_level = _optional_text(tool_plan.get("side_effect_level")) or (spec.side_effect_level if spec else "none")
    context_status = _optional_text(context_resolution.get("status")) or "not_required"
    route_type = _optional_text((routing.get("intent") or {}).get("route_type"))
    checks: list[dict[str, Any]] = []

    _add_check(
        checks,
        check_id="missing_context_uses_context_gate",
        ok=context_status != "missing_active_context" or mode == "ask_for_context",
        severity="error",
        details={
            "context_status": context_status,
            "mode": mode,
            "target_kind": context_resolution.get("target_kind"),
        },
    )
    _add_check(
        checks,
        check_id="write_tool_requires_proposal",
        ok=side_effect_level in {"none", "read_only", "plan_only"} or bool(tool_plan.get("requires_proposal")),
        severity="error",
        details={
            "tool_id": tool_id,
            "side_effect_level": side_effect_level,
            "requires_proposal": bool(tool_plan.get("requires_proposal")),
        },
    )
    _add_check(
        checks,
        check_id="read_only_tool_not_marked_as_proposal",
        ok=side_effect_level != "read_only" or mode in {"read_only", "direct_answer", "ask_for_context", "blocked"},
        severity="warning",
        details={"tool_id": tool_id, "side_effect_level": side_effect_level, "mode": mode},
    )
    _add_check(
        checks,
        check_id="verified_intent_matches_tool_plan",
        ok=_optional_text(verified_intent.get("selected_tool_id")) in {"", tool_id},
        severity="warning",
        details={"verified_tool_id": verified_intent.get("selected_tool_id"), "tool_plan_tool_id": tool_id},
    )
    _add_check(
        checks,
        check_id="direct_answer_has_no_tool",
        ok=mode != "direct_answer" or not tool_id,
        severity="warning",
        details={"mode": mode, "tool_id": tool_id},
    )
    _add_check(
        checks,
        check_id="proposal_mode_aligns_with_route",
        ok=mode != "proposal" or route_type in {"proposal_wait", "single_tool", "workflow"},
        severity="warning",
        details={"mode": mode, "route_type": route_type},
    )

    failed = [item for item in checks if not item["ok"]]
    error_count = sum(1 for item in failed if item["severity"] == "error")
    warning_count = sum(1 for item in failed if item["severity"] == "warning")
    return {
        "version": TOOL_PLAN_SELF_CHECK_VERSION,
        "status": "error" if error_count else ("warning" if warning_count else "ok"),
        "error_count": error_count,
        "warning_count": warning_count,
        "failed_check_ids": [str(item["check_id"]) for item in failed],
        "should_block_execution": False,
        "policy": "diagnostic_only_no_execution_change",
        "summary": {
            "tool_id": tool_id,
            "mode": mode,
            "side_effect_level": side_effect_level,
            "context_status": context_status,
            "intent_type": intent_draft.get("intent_type"),
            "route_type": route_type,
        },
        "checks": checks,
    }


def _add_check(
    checks: list[dict[str, Any]],
    *,
    check_id: str,
    ok: bool,
    severity: str,
    details: dict[str, Any],
) -> None:
    checks.append(
        {
            "check_id": check_id,
            "ok": bool(ok),
            "severity": severity,
            "details": details,
        }
    )


def _optional_text(value: Any) -> str:
    return str(value or "").strip()


__all__ = ["TOOL_PLAN_SELF_CHECK_VERSION", "check_tool_plan_consistency"]
