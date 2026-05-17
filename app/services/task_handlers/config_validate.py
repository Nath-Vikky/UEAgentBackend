from __future__ import annotations

from typing import Any

from app.agent.context_builder import build_context_summary
from app.i18n.language import localized as _localized
from app.schemas.common import UserViewBlock
from app.services.task_handlers.base import TaskExecutionContext
from app.tools.context import ToolContext
from app.tools.executor_runtime import execute_tool_with_context
from app.tools.registry import get_tool_spec


class ConfigValidateHandler:
    """Runs deterministic design/config schema validation."""

    handler_id = "config_validate"

    def execute(self, host: Any, context: TaskExecutionContext) -> dict[str, Any]:
        request = context.request
        routing = context.routing
        output_language = context.output_language

        base_debug = host._base_debug(
            request=request,
            routing=routing,
            trace_id=context.trace_id,
        )
        spec = get_tool_spec("validate_design_config")
        assert spec is not None
        tool_context = ToolContext.from_request(
            spec=spec,
            request=request,
            task_id=context.task_id,
            run_id=context.run_id,
            trace_id=context.trace_id,
        )
        tool_result = execute_tool_with_context(tool_context)
        result = tool_result.output
        step_results = [
            {
                "step_id": "validate_config",
                "title": "Validate Config",
                "status": "completed",
                "summary": _localized(
                    output_language,
                    f"发现 {len(result['errors'])} 个错误和 {len(result['warnings'])} 个告警。",
                    f"Found {len(result['errors'])} error(s) and {len(result['warnings'])} warning(s).",
                ),
                "details": result["validation_summary"],
            }
        ]
        is_valid = result["validation_summary"]["is_valid"]
        user_text = _localized(
            output_language,
            "配置结构有效。" if is_valid else "配置结构存在问题，请先修正错误项。",
            "The config structure is valid."
            if is_valid
            else "The config structure contains problems that should be fixed first.",
        )
        user_view = {
            "title": _localized(output_language, "配置校验结果", "Config Validation Result"),
            "text": user_text,
            "blocks": [
                UserViewBlock(
                    block_type="summary",
                    title=_localized(output_language, "校验摘要", "Validation Summary"),
                    text=_localized(
                        output_language,
                        f"错误 {len(result['errors'])} 条，告警 {len(result['warnings'])} 条。",
                        f"Errors: {len(result['errors'])}, warnings: {len(result['warnings'])}.",
                    ),
                    data=result["validation_summary"],
                ).model_dump(mode="json")
            ],
            "citations_preview": [],
            "quick_actions": [],
            "status_hint": "valid" if is_valid else "invalid",
        }
        data = {
            **result,
            "sources": [],
            "citations": [],
            "context_summary": build_context_summary(request),
        }
        base_debug["retrieval"] = {
            "mode": "not_used",
            "degraded_mode": False,
            "reason": "route_config_validate",
            "filters_applied": {},
            "retrieved_docs": [],
        }
        base_debug["tools"] = [tool_result.to_debug_entry(context=tool_context)]
        base_debug["step_results"] = step_results
        base_debug["raw_result"] = data
        base_debug["warnings"] = [item["message"] for item in result["warnings"]]
        return {
            "user_view": user_view,
            "debug_view": base_debug,
            "data": data,
            "retrieval_trace": base_debug["retrieval"],
            "planner_diagnostics": routing["route"],
            "step_results": step_results,
            "action_proposals": [],
            "errors": [],
            "assistant_message": user_text,
            "artifacts": [
                {
                    "artifact_type": "config_validation_report",
                    "label": "Config Validation Report",
                    "filename": "config_validation_report.json",
                    "content": result,
                }
            ],
        }
