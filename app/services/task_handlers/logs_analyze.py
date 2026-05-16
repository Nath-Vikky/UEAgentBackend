from __future__ import annotations

from typing import Any

from app.services.task_handlers.base import TaskExecutionContext
from app.skills.executors import LogsAnalyzeSkillExecutor


class LogsAnalyzeHandler:
    """Runs the UE log analysis skill executor."""

    handler_id = "logs_analyze"

    def execute(self, host: Any, context: TaskExecutionContext) -> dict[str, Any]:
        executor = LogsAnalyzeSkillExecutor(
            kb_service=host.kb_service,
            llm_service=host.llm_service,
            base_debug_builder=host._base_debug,
        )
        return executor.execute(
            request=context.request,
            routing=context.routing,
            task_id=context.task_id,
            run_id=context.run_id,
            trace_id=context.trace_id,
            output_language=context.output_language,
            chat_config=context.chat_config,
        )
