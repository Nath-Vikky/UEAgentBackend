from __future__ import annotations

from collections import Counter
from typing import Any


def history_fetch_limit(*, safe_limit: int, has_filters: bool, max_fetch: int = 500) -> int:
    if not has_filters:
        return safe_limit
    return min(max(safe_limit * 6, 80), max_fetch)


def operation_history_payload(
    proposals: list[Any],
    *,
    limit: int,
    operation_type: str | None = None,
    needs_user_attention: bool | None = None,
    diagnostic_flag: str | None = None,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for proposal in proposals:
        preview = dict(getattr(proposal, "dry_run_preview_json", None) or {})
        current_operation_type = str(preview.get("operation_type") or "")
        if operation_type and current_operation_type != operation_type:
            continue
        operation_result = dict(preview.get("operation_result") or {})
        result_summary = dict(operation_result.get("result_summary") or {})
        operation_diagnostics = dict(result_summary.get("operation_diagnostics") or {})
        if needs_user_attention is not None and bool(result_summary.get("needs_user_attention")) != needs_user_attention:
            continue
        if diagnostic_flag:
            diagnostic_flags = [str(item) for item in operation_diagnostics.get("diagnostic_flags") or []]
            if str(diagnostic_flag) not in diagnostic_flags:
                continue
        items.append(
            {
                "proposal_id": getattr(proposal, "proposal_id", None),
                "title": getattr(proposal, "title", None),
                "operation_type": current_operation_type,
                "tool_id": preview.get("tool_id"),
                "risk_flags": getattr(proposal, "risk_flags", None),
                "confirmation_state": getattr(proposal, "confirmation_state", None),
                "approval_state": preview.get("approval_state"),
                "created_at": _isoformat(getattr(proposal, "created_at", None)),
                "updated_at": _isoformat(getattr(proposal, "updated_at", None)),
                "preview_summary": preview.get("preview_summary", {}),
                "affected_targets": preview.get("affected_targets", []),
                "result_summary": result_summary,
                "execution_state": operation_result.get("execution_state"),
                "success": operation_result.get("success"),
            }
        )
        if len(items) >= limit:
            break
    return {
        "summary": {
            "item_count": len(items),
            "limit": limit,
            "operation_type": operation_type,
            "needs_user_attention": needs_user_attention,
            "diagnostic_flag": diagnostic_flag,
        },
        "items": items,
    }


def operation_diagnostics_summary_payload(
    proposals: list[Any],
    *,
    limit: int,
    operation_type: str | None = None,
) -> dict[str, Any]:
    inspected_count = 0
    executed_count = 0
    pending_count = 0
    success_count = 0
    failed_count = 0
    needs_user_attention_count = 0
    operation_type_counts: Counter[str] = Counter()
    diagnostic_flag_counts: Counter[str] = Counter()
    repair_action_counts: Counter[str] = Counter()
    repair_status_counts: Counter[str] = Counter()
    execution_state_counts: Counter[str] = Counter()
    confirmation_state_counts: Counter[str] = Counter()
    recent_attention_items: list[dict[str, Any]] = []

    for proposal in proposals:
        preview = dict(getattr(proposal, "dry_run_preview_json", None) or {})
        current_operation_type = str(preview.get("operation_type") or "")
        if operation_type and current_operation_type != operation_type:
            continue
        inspected_count += 1
        operation_type_counts[current_operation_type or "unknown"] += 1
        confirmation_state_counts[str(getattr(proposal, "confirmation_state", None) or "unknown")] += 1

        operation_result = dict(preview.get("operation_result") or {})
        result_summary = dict(operation_result.get("result_summary") or {})
        operation_diagnostics = dict(result_summary.get("operation_diagnostics") or {})
        diagnostic_flags = [str(item) for item in operation_diagnostics.get("diagnostic_flags") or []]
        diagnostic_flag_counts.update(diagnostic_flags)
        repair_advice = dict(operation_diagnostics.get("repair_advice") or result_summary.get("repair_advice") or {})
        repair_status = str(repair_advice.get("status") or "unknown")
        repair_status_counts[repair_status] += 1
        repair_actions = [str(item.get("action_id") or "") for item in repair_advice.get("actions") or []]
        repair_action_counts.update(item for item in repair_actions if item)

        if operation_result:
            executed_count += 1
            execution_state_counts[str(operation_result.get("execution_state") or "reported")] += 1
            if bool(operation_result.get("success")):
                success_count += 1
            else:
                failed_count += 1
        else:
            pending_count += 1
            execution_state_counts["pending_result"] += 1

        needs_attention = bool(result_summary.get("needs_user_attention"))
        if needs_attention:
            needs_user_attention_count += 1
            if len(recent_attention_items) < 10:
                recent_attention_items.append(
                    {
                        "proposal_id": getattr(proposal, "proposal_id", None),
                        "operation_type": current_operation_type,
                        "tool_id": preview.get("tool_id"),
                        "title": getattr(proposal, "title", None),
                        "confirmation_state": getattr(proposal, "confirmation_state", None),
                        "execution_state": operation_result.get("execution_state"),
                        "success": operation_result.get("success"),
                        "updated_at": _isoformat(getattr(proposal, "updated_at", None)),
                        "diagnostic_flags": diagnostic_flags,
                        "error_codes": list(result_summary.get("error_codes") or []),
                        "repair_advice": repair_advice,
                        "result_summary": result_summary,
                    }
                )

        if inspected_count >= limit:
            break

    attention_rate = needs_user_attention_count / executed_count if executed_count else 0.0
    return {
        "summary": {
            "schema_version": "editor_operation_diagnostics_summary_v1",
            "limit": limit,
            "operation_type": operation_type,
            "inspected_count": inspected_count,
            "executed_count": executed_count,
            "pending_count": pending_count,
            "success_count": success_count,
            "failed_count": failed_count,
            "needs_user_attention_count": needs_user_attention_count,
            "attention_rate": round(attention_rate, 4),
            "operation_type_counts": dict(operation_type_counts),
            "diagnostic_flag_counts": dict(diagnostic_flag_counts),
            "repair_status_counts": dict(repair_status_counts),
            "repair_action_counts": dict(repair_action_counts),
            "execution_state_counts": dict(execution_state_counts),
            "confirmation_state_counts": dict(confirmation_state_counts),
            "recent_attention_items": recent_attention_items,
        },
    }


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    return str(value)


__all__ = [
    "history_fetch_limit",
    "operation_diagnostics_summary_payload",
    "operation_history_payload",
]
