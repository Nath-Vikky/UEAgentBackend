from __future__ import annotations

from typing import Any

from app.services.task_handlers.base import TaskExecutionContext
from app.skills.executors import CodeGenerateSkillExecutor


class CodeGenerateHandler:
    """Runs the code generation skill executor."""

    handler_id = "code_generate"

    def execute(self, host: Any, context: TaskExecutionContext) -> dict[str, Any]:
        executor = CodeGenerateSkillExecutor(
            kb_service=host.kb_service,
            llm_service=host.llm_service,
            base_debug_builder=host._base_debug,
        )
        return executor.execute(
            request=context.request,
            routing=context.routing,
            trace_id=context.trace_id,
            output_language=context.output_language,
            chat_config=context.chat_config,
            context_bundle=context.context_bundle,
        )
