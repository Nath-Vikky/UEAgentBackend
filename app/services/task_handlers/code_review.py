from __future__ import annotations

from typing import Any

from app.agent.multi_agent import ReviewFixValidateChain
from app.services.task_handlers.base import TaskExecutionContext
from app.skills.executors import CodeReviewSkillExecutor


class CodeReviewHandler:
    """Runs single-agent or review/fix/validate code review workflows."""

    handler_id = "code_review"

    def execute(self, host: Any, context: TaskExecutionContext) -> dict[str, Any]:
        if host._multi_agent_requested(request=context.request, routing=context.routing):
            chain = ReviewFixValidateChain(
                kb_service=host.kb_service,
                llm_service=host.llm_service,
                base_debug_builder=host._base_debug,
            )
            return chain.run(
                request=context.request,
                routing=context.routing,
                task_id=context.task_id,
                run_id=context.run_id,
                trace_id=context.trace_id,
                output_language=context.output_language,
                chat_config=context.chat_config,
                context_bundle=context.context_bundle,
            )

        executor = CodeReviewSkillExecutor(
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
            context_bundle=context.context_bundle,
        )
