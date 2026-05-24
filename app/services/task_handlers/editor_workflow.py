from __future__ import annotations

from typing import Any

from app.agent.context_builder import build_context_summary
from app.i18n.language import localized as _localized
from app.schemas.common import QuickAction, UserViewBlock
from app.services.editor_workflow_planner_service import EditorWorkflowPlannerService
from app.services.task_handlers.base import TaskExecutionContext


class EditorWorkflowPlanHandler:
    """Returns plan-only multi-step editor workflows from Agent Chat."""

    handler_id = "editor_workflow_plan"

    def __init__(self, workflow_request: dict[str, Any]):
        self.workflow_request = workflow_request

    def execute(self, host: Any, context: TaskExecutionContext) -> dict[str, Any]:
        request = context.request
        routing = context.routing
        output_language = context.output_language
        deps = context.dependencies
        base_debug_builder = deps.base_debug_builder if deps else host._base_debug

        base_debug = base_debug_builder(
            request=request,
            routing=routing,
            trace_id=context.trace_id,
            context_bundle=context.context_bundle,
        )
        plan = EditorWorkflowPlannerService().plan_workflow(
            goal=str(self.workflow_request.get("goal") or ""),
            workflow_type=str(self.workflow_request.get("workflow_type") or ""),
            payload=dict(self.workflow_request.get("payload") or {}),
            context=dict(self.workflow_request.get("context") or {}),
            requested_by=str(self.workflow_request.get("requested_by") or "agent_chat_workflow_planner"),
        )
        ready_step_count = int(plan.get("ready_step_count") or 0)
        step_count = int(plan.get("step_count") or 0)
        text = _localized(
            output_language,
            f"已生成一个安全的多步编辑器工作流计划，共 {step_count} 步，其中 {ready_step_count} 步参数已就绪。后端不会自动执行这些步骤；每一步都需要先创建 Proposal 并由你确认。",
            f"Created a safe multi-step editor workflow plan with {step_count} steps; {ready_step_count} steps are ready. The backend will not auto-execute the steps; each step must become a Proposal and be confirmed by you.",
        )
        missing_steps = [
            {
                "step_id": step.get("step_id"),
                "title": step.get("title"),
                "missing_inputs": step.get("missing_inputs") or [],
            }
            for step in plan.get("steps", [])
            if step.get("missing_inputs")
        ]
        ready_actions = self._build_step_quick_actions(plan=plan, output_language=output_language)
        step_results = [
            {
                "step_id": step.get("step_id"),
                "title": step.get("title"),
                "status": "ready" if step.get("proposal_ready") else "needs_more_input",
                "summary": step.get("operation_type"),
                "details": {
                    "operation_type": step.get("operation_type"),
                    "tool_id": step.get("tool_id"),
                    "missing_inputs": step.get("missing_inputs") or [],
                },
            }
            for step in plan.get("steps", [])
        ]
        user_view = {
            "title": _localized(output_language, "多步编辑器工作流计划", "Editor Workflow Plan"),
            "text": text,
            "blocks": [
                UserViewBlock(
                    block_type="editor_workflow_plan",
                    title=_localized(output_language, "计划摘要", "Plan Summary"),
                    text=text,
                    data=plan,
                ).model_dump(mode="json"),
                UserViewBlock(
                    block_type="editor_workflow_steps",
                    title=_localized(output_language, "步骤", "Steps"),
                    text=_localized(
                        output_language,
                        "每一步都需要单独创建 Proposal 并确认后执行。",
                        "Each step must be submitted as a separate Proposal and confirmed before execution.",
                    ),
                    data={"steps": plan.get("steps", [])},
                ).model_dump(mode="json"),
            ],
            "citations_preview": [],
            "quick_actions": ready_actions,
            "status_hint": "workflow_plan",
        }
        if ready_actions:
            user_view["blocks"].append(
                UserViewBlock(
                    block_type="workflow_ready_actions",
                    title="Ready Proposal Actions",
                    text="Ready workflow steps can be converted into one pending Proposal at a time.",
                    data={"actions": ready_actions},
                ).model_dump(mode="json")
            )
        if missing_steps:
            user_view["blocks"].append(
                UserViewBlock(
                    block_type="missing_inputs",
                    title=_localized(output_language, "需要补充的信息", "Missing Inputs"),
                    text=_localized(
                        output_language,
                        "部分步骤缺少必要参数，补齐后才能创建 Proposal。",
                        "Some steps need more inputs before Proposal creation.",
                    ),
                    data={"missing_steps": missing_steps},
                ).model_dump(mode="json")
            )

        data = {
            "answer": text,
            "editor_workflow_plan": plan,
            "editor_workflow_quick_actions": ready_actions,
            "workflow_request": self.workflow_request,
            "context_summary": build_context_summary(request),
            "context_bundle": context.context_bundle,
            "warnings": [],
        }
        retrieval_trace = {
            "mode": "not_used",
            "degraded_mode": False,
            "reason": "editor_workflow_plan",
            "filters_applied": {},
            "retrieved_docs": [],
        }
        base_debug["tools"] = [
            {
                "tool_id": "editor_workflow_planner",
                "status": "planned",
                "summary": text,
                "approval_state": "not_required_until_step_proposal",
            }
        ]
        base_debug["workflow_trace"] = {
            "mode": "plan_only_editor_workflow_v1",
            "workflow_type": plan.get("workflow_type"),
            "status": plan.get("status"),
            "step_count": step_count,
            "ready_step_count": ready_step_count,
            "auto_execute": False,
        }
        base_debug["react_loop"] = base_debug["workflow_trace"]
        base_debug["side_effects"] = [
            {
                "proposal_type": "editor_workflow_plan",
                "side_effect_level": "plan_only",
                "execution_state": "not_executed",
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
            "action_proposals": [],
            "errors": [],
            "assistant_message": text,
            "artifacts": [],
            "usage": {},
        }

    @staticmethod
    def _build_step_quick_actions(*, plan: dict[str, Any], output_language: str) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        plan_id = str(plan.get("plan_id") or "")
        for step in plan.get("steps", []):
            if len(actions) >= 5:
                break
            if not isinstance(step, dict):
                continue
            if not bool(step.get("proposal_ready")) or step.get("missing_inputs"):
                continue

            step_id = str(step.get("step_id") or f"step_{len(actions)}")
            title = str(step.get("title") or step.get("operation_type") or step_id)
            action = QuickAction(
                action_id=f"create_workflow_step_proposal_{step_id}",
                label=_localized(
                    output_language,
                    f"Create Proposal: {title}",
                    f"Create Proposal: {title}",
                ),
                payload={
                    "action_type": "create_workflow_step_proposal",
                    "method": "POST",
                    "endpoint": "/api/v1/editor-operations/workflows/steps/proposal",
                    "workflow_plan_id": plan_id,
                    "workflow_step_id": step_id,
                    "step_index": step.get("step_index"),
                    "operation_type": step.get("operation_type"),
                    "request": {
                        "workflow_plan_id": plan_id,
                        "step": step,
                        "requested_by": "agent_chat_workflow_quick_action",
                    },
                    "safety": {
                        "auto_execute": False,
                        "creates_pending_proposal_only": True,
                        "requires_user_confirmation": True,
                    },
                },
            )
            actions.append(action.model_dump(mode="json"))
        return actions
