from __future__ import annotations

from typing import Any

from app.agent.context_builder import build_context_summary
from app.i18n.language import localized as _localized
from app.schemas.common import QuickAction, UserViewBlock
from app.services.task_handlers.base import TaskExecutionContext
from app.services.task_handlers.view_helpers import citation_previews
from app.workflows.graphs import run_config_generate_workflow


class ConfigGenerateHandler:
    """Runs design/config generation workflow orchestration."""

    handler_id = "config_generate"

    def execute(self, host: Any, context: TaskExecutionContext) -> dict[str, Any]:
        request = context.request
        routing = context.routing
        output_language = context.output_language

        workflow = run_config_generate_workflow(
            request=request,
            kb_service=host.kb_service,
            task_id=context.task_id,
            run_id=context.run_id,
            output_language=output_language,
        )
        result = workflow["result"]
        base_debug = host._base_debug(request=request, routing=routing, trace_id=context.trace_id)
        validation = result["validation_results"]["validation_summary"]
        user_text = _localized(
            output_language,
            "已生成配置草稿并完成基础结构校验，当前等待人工确认后再进入后续采用流程。",
            "Generated a config draft and completed baseline structural validation. "
            "The run is now waiting for human confirmation before downstream adoption.",
        )
        user_view = {
            "title": _localized(output_language, "配置生成结果", "Config Generation Result"),
            "text": user_text,
            "blocks": [
                UserViewBlock(
                    block_type="summary",
                    title=_localized(output_language, "校验摘要", "Validation Summary"),
                    text=_localized(
                        output_language,
                        f"错误 {validation['error_count']} 条，告警 {validation['warning_count']} 条。",
                        f"Errors: {validation['error_count']}, warnings: {validation['warning_count']}.",
                    ),
                    data=validation,
                ).model_dump(mode="json"),
                UserViewBlock(
                    block_type="json_preview",
                    title=_localized(output_language, "草稿预览", "Draft Preview"),
                    text=str(result["draft_config"])[:400],
                    data={"draft_config": result["draft_config"]},
                ).model_dump(mode="json"),
            ],
            "citations_preview": citation_previews(result["retrieved_references"]),
            "quick_actions": [
                QuickAction(
                    action_id="open_proposal_panel",
                    label=_localized(output_language, "查看待确认 Proposal", "Open pending proposal"),
                ).model_dump(mode="json")
            ],
            "status_hint": "waiting_confirmation",
        }
        data = {
            **result,
            "sources": [
                {"title": item["title"], "source": item["source"]}
                for item in result["retrieved_references"]
            ],
            "citations": result["retrieved_references"],
            "context_summary": build_context_summary(request),
            "warnings": workflow["warnings"],
        }
        base_debug["retrieval"] = workflow["retrieval_trace"]
        base_debug["tools"] = workflow["tools"]
        base_debug["step_results"] = workflow["step_results"]
        base_debug["raw_result"] = data
        base_debug["warnings"] = workflow["warnings"]
        return {
            "user_view": user_view,
            "debug_view": base_debug,
            "data": data,
            "retrieval_trace": workflow["retrieval_trace"],
            "planner_diagnostics": routing["route"],
            "step_results": workflow["step_results"],
            "action_proposals": workflow["action_proposals"],
            "errors": [],
            "assistant_message": user_text,
            "artifacts": workflow["artifacts"],
        }
