from __future__ import annotations

from typing import Any

from app.services.task_handlers.assets_inspect import AssetsInspectHandler
from app.services.task_handlers.base import TaskExecutionContext, TaskHandler
from app.services.task_handlers.code_generate import CodeGenerateHandler
from app.services.task_handlers.code_review import CodeReviewHandler
from app.services.task_handlers.config_generate import ConfigGenerateHandler
from app.services.task_handlers.config_validate import ConfigValidateHandler
from app.services.task_handlers.direct_answer import DirectAnswerHandler
from app.services.task_handlers.editor_operation import EditorOperationProposalHandler
from app.services.task_handlers.editor_workflow import EditorWorkflowPlanHandler
from app.services.task_handlers.logs_analyze import LogsAnalyzeHandler
from app.services.task_handlers.missing_context import MissingContextHandler
from app.services.task_handlers.placeholder import PlaceholderTaskHandler
from app.services.task_handlers.perf_analyze import PerfAnalyzeHandler
from app.services.task_handlers.project_qa import ProjectQAHandler
from app.services.editor_operation_service import EditorOperationService
from app.services.editor_workflow_planner_service import EditorWorkflowPlannerService


HOW_TO_QUESTION_MARKERS = (
    "how do i",
    "how should",
    "how to",
    "what is",
    "what are",
    "why",
    "explain",
    "describe",
    "difference between",
    "best practice",
    "怎么",
    "如何",
    "是什么",
    "为什么",
    "请说明",
    "解释",
    "区别",
    "最佳实践",
)


def _request_query_text(context: TaskExecutionContext) -> str:
    payload_query = str(context.request.payload.get("user_query") or "").strip()
    if payload_query:
        return payload_query
    if context.request.session.messages:
        return str(context.request.session.messages[-1].content or "").strip()
    return ""


def _has_explicit_editor_operation_payload(context: TaskExecutionContext) -> bool:
    payload = context.request.payload
    return bool(payload.get("operation_type") or payload.get("operation_payload"))


def _should_keep_project_qa_for_how_to_question(context: TaskExecutionContext) -> bool:
    route_type = str(context.routing.get("intent", {}).get("route_type") or "")
    if route_type != "project_qa" or _has_explicit_editor_operation_payload(context):
        return False
    query = _request_query_text(context)
    lowered = query.lower()
    return any(marker in lowered or marker in query for marker in HOW_TO_QUESTION_MARKERS)


class RouteExecutionDispatcher:
    """Selects task handlers while preserving the existing TaskService contract.

    This is intentionally an adapter layer first. Concrete execution logic can
    move from TaskService into each handler in later, smaller migrations.
    """

    def __init__(self) -> None:
        self._task_handlers: dict[str, TaskHandler] = {
            "code_review": CodeReviewHandler(),
            "logs_analyze": LogsAnalyzeHandler(),
            "config_generate": ConfigGenerateHandler(),
            "perf_analyze": PerfAnalyzeHandler(),
            "config_validate": ConfigValidateHandler(),
            "assets_inspect": AssetsInspectHandler(),
            "code_generate": CodeGenerateHandler(),
        }
        self._project_qa_handler = ProjectQAHandler()
        self._direct_answer_handler = DirectAnswerHandler()
        self._placeholder_handler = PlaceholderTaskHandler()
        self._missing_context_handler = MissingContextHandler()

    def execute(self, host: Any, context: TaskExecutionContext) -> dict[str, Any]:
        handler = self.select_handler(host, context)
        result = handler.execute(host, context)
        self._annotate_handler(result, handler.handler_id)
        return result

    def select_handler(self, host: Any, context: TaskExecutionContext) -> TaskHandler:
        route_type = str(context.routing.get("intent", {}).get("route_type") or "")
        if _should_keep_project_qa_for_how_to_question(context):
            return self._project_qa_handler
        if _should_ask_for_missing_context(context):
            return self._missing_context_handler

        editor_workflow_request = EditorWorkflowPlannerService.detect_chat_workflow_request(
            context.request,
            context.context_bundle,
        )
        if editor_workflow_request:
            return EditorWorkflowPlanHandler(editor_workflow_request)

        editor_operation_request = EditorOperationService.detect_request(
            context.request,
            context.context_bundle,
        )
        if editor_operation_request:
            return EditorOperationProposalHandler(editor_operation_request)

        if route_type == "project_qa":
            return self._project_qa_handler
        if route_type == "direct_answer":
            return self._direct_answer_handler
        return self._task_handlers.get(context.actual_task_type, self._placeholder_handler)

    @staticmethod
    def _annotate_handler(result: dict[str, Any], handler_id: str) -> None:
        debug_view = result.get("debug_view")
        if isinstance(debug_view, dict):
            debug_view["task_handler"] = {
                "handler_id": handler_id,
                "strategy": "task_handler_adapter_v1",
            }


def _should_ask_for_missing_context(context: TaskExecutionContext) -> bool:
    if context.request.task_type not in {"agent_chat", "project_qa"}:
        return False
    tool_plan = dict(context.context_bundle.get("tool_plan_v1") or {})
    if tool_plan.get("mode") == "ask_for_context":
        return True
    resolution = dict(context.context_bundle.get("context_resolution") or {})
    return resolution.get("status") == "missing_active_context"
