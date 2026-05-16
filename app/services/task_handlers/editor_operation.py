from __future__ import annotations

from typing import Any

from app.agent.context_builder import build_context_summary
from app.i18n.language import localized as _localized
from app.schemas.common import QuickAction, UserViewBlock
from app.schemas.requests import EditorOperationProposalRequest
from app.services.editor_operation_service import EditorOperationService
from app.services.task_handlers.base import TaskExecutionContext


class EditorOperationProposalHandler:
    """Builds safe editor-operation proposals without executing UE writes."""

    handler_id = "editor_operation_proposal"

    def __init__(self, editor_operation_request: EditorOperationProposalRequest):
        self.editor_operation_request = editor_operation_request

    def execute(self, host: Any, context: TaskExecutionContext) -> dict[str, Any]:
        request = context.request
        routing = context.routing
        output_language = context.output_language

        base_debug = host._base_debug(
            request=request,
            routing=routing,
            trace_id=context.trace_id,
            context_bundle=context.context_bundle,
        )
        proposal = EditorOperationService(host.db).try_build_action_proposal(self.editor_operation_request)
        if not proposal:
            text = _localized(
                output_language,
                "已识别到编辑器操作意图，但参数未通过安全校验，因此没有生成执行提案。",
                "An editor operation intent was detected, but the parameters failed safety "
                "validation, so no proposal was created.",
            )
            status = "blocked"
            proposals: list[dict[str, Any]] = []
        else:
            text = _localized(
                output_language,
                "已生成编辑器操作 Proposal。后端不会直接操作 UE 编辑器，请在 UE 插件中确认后执行。",
                "Created an editor operation proposal. The backend will not operate Unreal "
                "Editor directly; confirm it in the UE plugin before execution.",
            )
            status = "waiting_confirmation"
            proposals = [proposal]
        step_results = [
            {
                "step_id": "plan_editor_operation",
                "title": "Plan Editor Operation",
                "status": "completed" if proposals else "blocked",
                "summary": text,
                "details": {
                    "operation_type": self.editor_operation_request.operation_type,
                    "proposal_count": len(proposals),
                },
            }
        ]
        user_view = {
            "title": _localized(output_language, "编辑器操作提案", "Editor Operation Proposal"),
            "text": text,
            "blocks": [
                UserViewBlock(
                    block_type="summary",
                    title=_localized(output_language, "安全确认", "Safety Confirmation"),
                    text=text,
                    data={
                        "operation_type": self.editor_operation_request.operation_type,
                        "proposal": proposal or {},
                    },
                ).model_dump(mode="json")
            ],
            "citations_preview": [],
            "quick_actions": [
                QuickAction(
                    action_id="open_proposal",
                    label=_localized(output_language, "查看确认提案", "Open proposal"),
                    payload={"proposal_id": proposal.get("proposal_id") if proposal else None},
                ).model_dump(mode="json")
            ]
            if proposal
            else [],
            "status_hint": status,
        }
        data = {
            "answer": text,
            "editor_operation": {
                "operation_type": self.editor_operation_request.operation_type,
                "proposal": proposal or {},
                "proposal_created": bool(proposal),
                "safety_policy": {
                    "llm_direct_execution": False,
                    "requires_frontend_confirmation": True,
                    "ue_plugin_executes_editor_api": True,
                },
            },
            "context_summary": build_context_summary(request),
            "context_bundle": context.context_bundle,
            "warnings": [],
        }
        retrieval_trace = {
            "mode": "not_used",
            "degraded_mode": False,
            "reason": "editor_operation_proposal",
            "filters_applied": {},
            "retrieved_docs": [],
        }
        base_debug["tools"] = [
            {
                "tool_id": proposal["dry_run_preview"]["tool_id"] if proposal else "editor_operation_proposal",
                "status": "waiting_confirmation" if proposal else "blocked",
                "summary": text,
                "approval_state": "required" if proposal else "blocked",
            }
        ]
        base_debug["side_effects"] = [
            {
                "proposal_id": proposal.get("proposal_id") if proposal else None,
                "proposal_type": "editor_operation",
                "operation_type": self.editor_operation_request.operation_type,
                "side_effect_level": "confirmed_write",
                "execution_state": "not_executed_without_confirmation",
                "written_by_backend": False,
            }
        ]
        base_debug["step_results"] = step_results
        base_debug["raw_result"] = data
        return {
            "user_view": user_view,
            "debug_view": base_debug,
            "data": data,
            "retrieval_trace": retrieval_trace,
            "planner_diagnostics": routing["route"],
            "step_results": step_results,
            "action_proposals": proposals,
            "errors": [],
            "assistant_message": text,
            "artifacts": [],
            "usage": {},
        }
