from __future__ import annotations

from typing import Any

from app.agent.context_builder import build_context_summary
from app.i18n.language import localized as _localized
from app.schemas.common import QuickAction, UserViewBlock
from app.services.task_handlers.base import TaskExecutionContext
from app.services.task_handlers.read_only_tool_summaries import (
    focused_blueprint_graph_result,
    local_tool_registry_readonly_result,
    live_mcp_readonly_result,
)


class PlaceholderTaskHandler:
    """Returns stable diagnostics for recognized task requests without executors."""

    handler_id = "task_placeholder"

    def execute(self, host: Any, context: TaskExecutionContext) -> dict[str, Any]:
        request = context.request
        routing = context.routing
        output_language = context.output_language

        base_debug = host._base_debug(request=request, routing=routing, trace_id=context.trace_id)
        selected_tool_id = str((routing.get("route") or {}).get("selected_tool_id") or "")
        if selected_tool_id in {
            "mcp_get_editor_context",
            "mcp_get_selected_assets",
            "mcp_get_asset_details",
            "mcp_get_static_mesh_details",
            "mcp_get_selected_actors",
            "mcp_get_level_actors",
            "mcp_get_level_actor_details",
            "mcp_get_blueprint_graph",
            "mcp_get_blueprint_node_details",
            "mcp_get_widget_tree",
            "mcp_get_umg_widget_details",
            "mcp_get_material_instance_parameters",
        }:
            live_result = live_mcp_readonly_result(
                context=context,
                base_debug=base_debug,
                output_language=output_language,
                selected_tool_id=selected_tool_id,
            )
            if live_result:
                return live_result
            local_result = local_tool_registry_readonly_result(
                context=context,
                base_debug=base_debug,
                output_language=output_language,
                selected_tool_id=selected_tool_id,
            )
            if local_result:
                return local_result
        if selected_tool_id == "mcp_get_blueprint_graph":
            graph_result = focused_blueprint_graph_result(
                context=context,
                base_debug=base_debug,
                output_language=output_language,
            )
            if graph_result:
                return graph_result

        placeholder_text = _localized(
            output_language,
            "系统已经识别到这是工程任务请求，但当前任务类型还未接入具体执行器，因此先返回任务路由和调试诊断。",
            "The system recognized this as an engineering task request, but this task type "
            "does not have a concrete executor yet, so it is returning routing diagnostics for now.",
        )
        step_results = [
            {
                "step_id": "classify_intent",
                "title": "Intent Classification",
                "status": "completed",
                "summary": routing["intent"]["reason"],
                "details": routing["intent"],
            }
        ]
        user_view = {
            "title": _localized(output_language, "任务路由结果", "Task Routing Result"),
            "text": placeholder_text,
            "blocks": [
                UserViewBlock(
                    block_type="summary",
                    title=_localized(output_language, "候选工具", "Candidate Tools"),
                    text=", ".join(routing["route"]["candidate_tool_ids"]) or "tool_registry_pending",
                ).model_dump(mode="json")
            ],
            "citations_preview": [],
            "quick_actions": [
                QuickAction(
                    action_id="open_debug_view",
                    label=_localized(output_language, "查看调试信息", "Open debug view"),
                ).model_dump(mode="json")
            ],
            "status_hint": "tool_placeholder",
        }
        retrieval_trace = {
            "mode": "not_used",
            "degraded_mode": False,
            "reason": "route_task_placeholder",
            "filters_applied": {},
            "retrieved_docs": [],
        }
        data = {
            "answer": placeholder_text,
            "sources": [],
            "citations": [],
            "confidence": 0.0,
            "context_summary": build_context_summary(request),
            "warnings": [],
        }
        base_debug["retrieval"] = retrieval_trace
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
            "assistant_message": placeholder_text,
            "artifacts": [],
        }
