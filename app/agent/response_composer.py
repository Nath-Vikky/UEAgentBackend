from __future__ import annotations

from typing import Any

from app.schemas.common import (
    DebugView,
    IntentDescriptor,
    LocaleDescriptor,
    Presentation,
    StepResult,
    TaskDescriptor,
    UserView,
)
from app.schemas.responses import UnifiedTaskResponse


def compose_unified_response(
    *,
    task: dict[str, Any],
    intent: dict[str, Any],
    locale: dict[str, Any],
    user_view_payload: dict[str, Any],
    debug_payload: dict[str, Any],
    data: dict[str, Any],
    usage: dict[str, Any],
    trace_summary: dict[str, Any],
    retrieval_trace: dict[str, Any],
    planner_diagnostics: dict[str, Any],
    step_results: list[dict[str, Any]],
    action_proposals: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    assistant_message: str | None = None,
) -> UnifiedTaskResponse:
    user_view = UserView(**user_view_payload)
    presentation = Presentation(user_title=user_view.title, user_text=user_view.text)
    return UnifiedTaskResponse(
        success=not errors,
        task=TaskDescriptor(**task),
        intent=IntentDescriptor(**intent),
        locale=LocaleDescriptor(**locale),
        user_view=user_view,
        debug_view=DebugView(**debug_payload),
        presentation=presentation,
        assistant_message=assistant_message or user_view.text,
        data=data,
        usage=usage,
        trace_summary=trace_summary,
        retrieval_trace=retrieval_trace,
        planner_diagnostics=planner_diagnostics,
        step_results=[StepResult(**item) for item in step_results],
        action_proposals=action_proposals,
        errors=errors,
    )
