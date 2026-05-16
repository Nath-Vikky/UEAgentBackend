from __future__ import annotations

from typing import Any

from app.agent.context_builder import build_context_summary
from app.i18n.language import localized as _localized
from app.schemas.common import QuickAction, UserViewBlock
from app.services.task_handlers.base import TaskExecutionContext
from app.services.task_handlers.view_helpers import citation_previews
from app.workflows.graphs import run_perf_analyze_workflow


class PerfAnalyzeHandler:
    """Runs deterministic performance-analysis workflow orchestration."""

    handler_id = "perf_analyze"

    def execute(self, host: Any, context: TaskExecutionContext) -> dict[str, Any]:
        request = context.request
        routing = context.routing
        output_language = context.output_language

        workflow = run_perf_analyze_workflow(
            request=request,
            kb_service=host.kb_service,
            task_id=context.task_id,
            run_id=context.run_id,
            output_language=output_language,
        )
        result = workflow["result"]
        base_debug = host._base_debug(request=request, routing=routing, trace_id=context.trace_id)
        user_text = _localized(
            output_language,
            f"已完成性能分析，识别到 {len(result['suspicious_points'])} 个可疑瓶颈信号。",
            f"Performance analysis completed and identified {len(result['suspicious_points'])} "
            "suspicious bottleneck signal(s).",
        )
        user_view = {
            "title": _localized(output_language, "性能分析结果", "Performance Analysis Result"),
            "text": user_text,
            "blocks": [
                UserViewBlock(
                    block_type="summary",
                    title=_localized(output_language, "指标摘要", "Metric Summary"),
                    text=result["summary"],
                    data=result["metric_summary"],
                ).model_dump(mode="json"),
                UserViewBlock(
                    block_type="list",
                    title=_localized(output_language, "优化建议", "Optimization Suggestions"),
                    text="\n".join(result["optimization_suggestions"][:4]),
                    data={"suspicious_points": result["suspicious_points"][:6]},
                ).model_dump(mode="json"),
            ],
            "citations_preview": citation_previews(result["retrieved_references"]),
            "quick_actions": [
                QuickAction(
                    action_id="open_debug_view",
                    label=_localized(output_language, "查看调试信息", "Open debug view"),
                ).model_dump(mode="json")
            ],
            "status_hint": "analysis_complete",
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
