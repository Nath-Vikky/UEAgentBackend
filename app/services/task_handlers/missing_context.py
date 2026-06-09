from __future__ import annotations

from typing import Any

from app.agent.context_builder import build_context_summary
from app.i18n.language import localized as _localized
from app.schemas.common import QuickAction, UserViewBlock
from app.services.task_handlers.base import TaskExecutionContext


class MissingContextHandler:
    """Return a clear user prompt when the Agent needs selected editor context."""

    handler_id = "missing_context"

    def execute(self, host: Any, context: TaskExecutionContext) -> dict[str, Any]:
        request = context.request
        routing = context.routing
        output_language = context.output_language
        base_debug = host._base_debug(request=request, routing=routing, trace_id=context.trace_id)
        resolution = dict(context.context_bundle.get("context_resolution") or {})
        tool_plan = dict(context.context_bundle.get("tool_plan_v1") or {})
        target_kind = str(resolution.get("target_kind") or tool_plan.get("target_kind") or "selected target")
        title = _localized(output_language, "需要先选择目标", "Select a target first")
        text = _missing_context_text(output_language, target_kind)
        step_results = [
            {
                "step_id": "resolve_active_context",
                "title": "Resolve Active Context",
                "status": "blocked",
                "summary": str(resolution.get("source") or "missing_active_context"),
                "details": {
                    "context_resolution": resolution,
                    "tool_plan_v1": tool_plan,
                },
            }
        ]
        user_view = {
            "title": title,
            "text": text,
            "blocks": [
                UserViewBlock(
                    block_type="warning",
                    title=title,
                    text=text,
                    data={
                        "target_kind": target_kind,
                        "missing_fields": list(resolution.get("missing_fields") or []),
                    },
                ).model_dump(mode="json")
            ],
            "citations_preview": [],
            "quick_actions": [
                QuickAction(
                    action_id="sync_inventory",
                    label=_localized(output_language, "同步项目上下文", "Sync project context"),
                ).model_dump(mode="json"),
                QuickAction(
                    action_id="open_debug_view",
                    label=_localized(output_language, "查看调试信息", "Open debug view"),
                ).model_dump(mode="json"),
            ],
            "status_hint": "missing_active_context",
        }
        retrieval_trace = {
            "mode": "not_used",
            "degraded_mode": False,
            "reason": "missing_active_context_gate",
            "filters_applied": {},
            "retrieved_docs": [],
        }
        data = {
            "answer": text,
            "sources": [],
            "citations": [],
            "confidence": 0.0,
            "context_summary": build_context_summary(request),
            "context_resolution": resolution,
            "tool_plan_v1": tool_plan,
            "warnings": ["missing_active_context"],
        }
        base_debug["retrieval"] = retrieval_trace
        base_debug["step_results"] = step_results
        base_debug["raw_result"] = data
        base_debug["missing_context_gate"] = {
            "version": "missing_context_gate_v1",
            "status": "blocked",
            "target_kind": target_kind,
            "reason": str(resolution.get("source") or "missing_active_context"),
        }
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
        }


def _missing_context_text(output_language: str, target_kind: str) -> str:
    label = _target_label(output_language, target_kind)
    if output_language.startswith("zh"):
        return (
            f"我还没有拿到当前要分析的 {label}。请先在 UE 编辑器里选中对应对象，"
            "或等待插件完成 Project Inventory/Active Context 同步后再问一次。"
        )
    return (
        f"I do not have the current {label} yet. Select the target in Unreal Editor, "
        "or wait for the plugin to sync Project Inventory / Active Context, then ask again."
    )


def _target_label(output_language: str, target_kind: str) -> str:
    zh = {
        "selected_asset": "资产",
        "asset": "资产",
        "current_blueprint": "蓝图",
        "blueprint": "蓝图",
        "widget": "Widget/UI",
        "selected_actor": "Actor",
        "level_actor": "Actor",
        "selected_material_instance": "材质实例",
        "material": "材质实例",
        "current_code_file": "代码文件",
        "current_log": "日志",
    }
    en = {
        "selected_asset": "asset",
        "asset": "asset",
        "current_blueprint": "Blueprint",
        "blueprint": "Blueprint",
        "widget": "Widget/UI",
        "selected_actor": "Actor",
        "level_actor": "Actor",
        "selected_material_instance": "Material Instance",
        "material": "Material Instance",
        "current_code_file": "code file",
        "current_log": "log",
    }
    table = zh if output_language.startswith("zh") else en
    return table.get(target_kind, "target")


__all__ = ["MissingContextHandler"]
