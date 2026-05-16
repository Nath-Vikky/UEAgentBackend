from __future__ import annotations

from typing import Any

from app.services.task_handlers.assets_inspect import AssetsInspectHandler
from app.services.task_handlers.base import TaskExecutionContext, TaskHandler
from app.services.task_handlers.code_generate import CodeGenerateHandler
from app.services.task_handlers.code_review import CodeReviewHandler
from app.services.task_handlers.config_generate import ConfigGenerateHandler
from app.services.task_handlers.config_validate import ConfigValidateHandler
from app.services.task_handlers.direct_answer import DirectAnswerHandler
from app.services.task_handlers.logs_analyze import LogsAnalyzeHandler
from app.services.task_handlers.placeholder import PlaceholderTaskHandler
from app.services.task_handlers.perf_analyze import PerfAnalyzeHandler


class EditorOperationProposalHandler:
    handler_id = "editor_operation_proposal"

    def __init__(self, editor_operation_request: Any):
        self.editor_operation_request = editor_operation_request

    def execute(self, host: Any, context: TaskExecutionContext) -> dict[str, Any]:
        return host._execute_editor_operation_proposal(
            request=context.request,
            routing=context.routing,
            trace_id=context.trace_id,
            output_language=context.output_language,
            editor_operation_request=self.editor_operation_request,
            context_bundle=context.context_bundle,
        )


class ProjectQAHandler:
    handler_id = "project_qa"

    def execute(self, host: Any, context: TaskExecutionContext) -> dict[str, Any]:
        return host._execute_project_qa_live(
            request=context.request,
            routing=context.routing,
            trace_id=context.trace_id,
            output_language=context.output_language,
            chat_config=context.chat_config,
            context_bundle=context.context_bundle,
            stream_sink=context.stream_sink,
            run_id=context.run_id,
            task_id=context.task_id,
        )


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

    def execute(self, host: Any, context: TaskExecutionContext) -> dict[str, Any]:
        handler = self.select_handler(host, context)
        result = handler.execute(host, context)
        self._annotate_handler(result, handler.handler_id)
        return result

    def select_handler(self, host: Any, context: TaskExecutionContext) -> TaskHandler:
        editor_operation_request = host._detect_editor_operation_request(context.request)
        if editor_operation_request:
            return EditorOperationProposalHandler(editor_operation_request)

        route_type = str(context.routing.get("intent", {}).get("route_type") or "")
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
