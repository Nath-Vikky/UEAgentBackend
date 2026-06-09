from __future__ import annotations

from typing import Any, Literal

from app.tools.registry import get_tool_spec


TOOL_PERMISSION_VERSION = "tool_permission_v1"
PermissionStatus = Literal["allow", "deny", "ask", "proposal"]


def _decision(
    *,
    status: PermissionStatus,
    tool_id: str,
    reason: str,
    side_effect_level: str = "unknown",
    requires_user_confirmation: bool = False,
    safe_to_run_automatically: bool = False,
    user_facing_notice: str | None = None,
    source: str = "tool_permission_policy",
) -> dict[str, Any]:
    return {
        "version": TOOL_PERMISSION_VERSION,
        "tool_id": tool_id,
        "status": status,
        "reason": reason,
        "source": source,
        "side_effect_level": side_effect_level,
        "requires_user_confirmation": requires_user_confirmation,
        "safe_to_run_automatically": safe_to_run_automatically,
        "user_facing_notice": user_facing_notice,
    }


def decide_tool_permission(
    tool_id: str | None,
    *,
    free_chat: bool = False,
    provider: str | None = None,
) -> dict[str, Any]:
    """Return the deterministic permission decision for a registered tool.

    LLM routing may suggest tools, but this gate owns execution safety. It is
    deliberately small and serializable so it can be shown in Debug View and
    reused by future MCP transports.
    """

    normalized_tool_id = str(tool_id or "").strip()
    if not normalized_tool_id:
        return _decision(
            status="deny",
            tool_id="",
            reason="missing_tool_id",
            user_facing_notice="No tool was selected for this request.",
        )
    spec = get_tool_spec(normalized_tool_id)
    if spec is None:
        return _decision(
            status="deny",
            tool_id=normalized_tool_id,
            reason="unregistered_tool",
            user_facing_notice="The requested tool is not registered.",
        )
    if not spec.enabled:
        return _decision(
            status="deny",
            tool_id=normalized_tool_id,
            reason="tool_disabled",
            side_effect_level=spec.side_effect_level,
            user_facing_notice="The selected tool is currently disabled.",
        )
    if spec.side_effect_level == "read_only":
        if free_chat and not spec.allowed_in_free_chat:
            return _decision(
                status="ask",
                tool_id=normalized_tool_id,
                reason="read_only_tool_not_free_chat_whitelisted",
                side_effect_level=spec.side_effect_level,
                requires_user_confirmation=False,
                safe_to_run_automatically=False,
                user_facing_notice="This read-only tool is available, but it is not enabled for automatic free-chat use.",
            )
        return _decision(
            status="allow",
            tool_id=normalized_tool_id,
            reason="read_only_tool_allowed",
            side_effect_level=spec.side_effect_level,
            requires_user_confirmation=False,
            safe_to_run_automatically=True,
        )
    if spec.side_effect_level == "plan_only":
        return _decision(
            status="allow",
            tool_id=normalized_tool_id,
            reason="plan_only_tool_allowed_without_side_effects",
            side_effect_level=spec.side_effect_level,
            requires_user_confirmation=False,
            safe_to_run_automatically=True,
        )
    if spec.effective_requires_confirmation:
        return _decision(
            status="proposal",
            tool_id=normalized_tool_id,
            reason=(
                "mcp_write_tool_must_map_to_proposal"
                if provider and provider.startswith("mcp")
                else "write_tool_requires_proposal_confirmation"
            ),
            side_effect_level=spec.side_effect_level,
            requires_user_confirmation=True,
            safe_to_run_automatically=False,
            user_facing_notice="This editor write operation needs a Proposal and user confirmation before execution.",
        )
    return _decision(
        status="ask",
        tool_id=normalized_tool_id,
        reason="non_readonly_tool_without_explicit_confirmation_policy",
        side_effect_level=spec.side_effect_level,
        requires_user_confirmation=True,
        safe_to_run_automatically=False,
        user_facing_notice="The selected tool has side effects and needs an explicit confirmation policy.",
    )


def annotate_tool_plan_permissions(
    tool_plan: dict[str, Any],
    *,
    free_chat: bool = False,
    provider: str | None = None,
) -> dict[str, Any]:
    calls = list(tool_plan.get("tool_calls") or [])
    decisions = [
        decide_tool_permission(
            str(call.get("tool_id") or ""),
            free_chat=free_chat,
            provider=provider,
        )
        for call in calls
        if isinstance(call, dict)
    ]
    blocked = [item for item in decisions if item["status"] in {"deny", "ask"}]
    proposal_required = [item for item in decisions if item["status"] == "proposal"]
    updated = dict(tool_plan)
    updated["permission_decisions"] = decisions
    updated["permission_summary"] = {
        "version": TOOL_PERMISSION_VERSION,
        "decision_count": len(decisions),
        "blocked_count": len(blocked),
        "proposal_required_count": len(proposal_required),
        "all_safe_to_run": not blocked and not proposal_required,
        "blocked_tool_ids": [item["tool_id"] for item in blocked],
        "proposal_tool_ids": [item["tool_id"] for item in proposal_required],
    }
    return updated


__all__ = [
    "TOOL_PERMISSION_VERSION",
    "annotate_tool_plan_permissions",
    "decide_tool_permission",
]
