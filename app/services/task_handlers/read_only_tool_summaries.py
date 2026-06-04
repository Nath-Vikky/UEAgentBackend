from __future__ import annotations

from typing import Any

from app.agent.context_builder import build_context_summary
from app.i18n.language import localized as _localized
from app.schemas.common import QuickAction, UserViewBlock
from app.services.task_handlers.base import TaskExecutionContext


def focused_blueprint_graph_result(
    *,
    context: TaskExecutionContext,
    base_debug: dict[str, Any],
    output_language: str,
) -> dict[str, Any] | None:
    inventory_context = dict((context.context_bundle or {}).get("project_inventory_context") or {})
    blueprint = inventory_context.get("current_blueprint")
    graph = inventory_context.get("current_blueprint_graph")
    node = inventory_context.get("current_blueprint_node")
    if not isinstance(blueprint, dict) or not isinstance(graph, dict):
        return None

    answer = _focused_graph_answer(
        blueprint=blueprint,
        graph=graph,
        node=node if isinstance(node, dict) else None,
        output_language=output_language,
    )
    step_results = [
        {
            "step_id": "classify_intent",
            "title": "Intent Classification",
            "status": "completed",
            "summary": context.routing["intent"]["reason"],
            "details": context.routing["intent"],
        },
        {
            "step_id": "read_project_inventory_focus",
            "title": "Read Project Inventory Focus",
            "status": "completed",
            "summary": "Used current Blueprint graph focus from Project Inventory.",
            "details": {
                "current_blueprint": blueprint,
                "current_blueprint_graph": graph,
                "current_blueprint_node": node,
            },
        },
    ]
    user_view = {
        "title": _localized(output_language, "当前蓝图图表摘要", "Current Blueprint Graph Summary"),
        "text": answer,
        "blocks": [
            UserViewBlock(
                block_type="summary",
                title=_localized(output_language, "图表摘要", "Graph Summary"),
                text=answer,
                data={
                    "current_blueprint": blueprint,
                    "current_blueprint_graph": graph,
                    "current_blueprint_node": node,
                },
            ).model_dump(mode="json")
        ],
        "citations_preview": [],
        "quick_actions": [
            QuickAction(
                action_id="open_debug_view",
                label=_localized(output_language, "查看调试信息", "Open debug view"),
            ).model_dump(mode="json")
        ],
        "status_hint": "inventory_focus_summary",
    }
    data = {
        "answer": answer,
        "sources": [
            {
                "source_type": "project_inventory",
                "title": "current_blueprint_graph",
                "path": blueprint.get("asset_path"),
            }
        ],
        "citations": [],
        "confidence": 0.72,
        "context_summary": build_context_summary(context.request),
        "warnings": [],
        "current_blueprint": blueprint,
        "current_blueprint_graph": graph,
        "current_blueprint_node": node,
    }
    base_debug["step_results"] = step_results
    base_debug["raw_result"] = data
    base_debug["tools"] = [
        {
            "tool_id": "mcp_get_blueprint_graph",
            "status": "completed",
            "summary": "Answered from Project Inventory current Blueprint graph focus.",
        }
    ]
    return {
        "user_view": user_view,
        "debug_view": base_debug,
        "data": data,
        "retrieval_trace": {
            "mode": "project_inventory_focus",
            "degraded_mode": False,
            "reason": "focused_blueprint_graph_context",
            "filters_applied": {},
            "retrieved_docs": [],
        },
        "planner_diagnostics": context.routing["route"],
        "step_results": step_results,
        "action_proposals": [],
        "errors": [],
        "assistant_message": answer,
        "artifacts": [],
    }


def _focused_graph_answer(
    *,
    blueprint: dict[str, Any],
    graph: dict[str, Any],
    node: dict[str, Any] | None,
    output_language: str,
) -> str:
    answer_parts = [
        _localized(
            output_language,
            (
                "我从 Project Inventory 里读取到了当前 Blueprint 图表摘要：\n"
                f"- Blueprint: {blueprint.get('asset_name') or blueprint.get('asset_path')}\n"
                f"- Graph: {graph.get('graph_name') or 'Unknown'}"
                f" | type={graph.get('graph_type') or 'n/a'}"
                f" | nodes={graph.get('node_count') or len(graph.get('nodes') or [])}"
                f" | pins={graph.get('pin_count') or 'n/a'}"
                f" | links={graph.get('link_count') or 'n/a'}"
            ),
            (
                "I found the current Blueprint graph summary in Project Inventory:\n"
                f"- Blueprint: {blueprint.get('asset_name') or blueprint.get('asset_path')}\n"
                f"- Graph: {graph.get('graph_name') or 'Unknown'}"
                f" | type={graph.get('graph_type') or 'n/a'}"
                f" | nodes={graph.get('node_count') or len(graph.get('nodes') or [])}"
                f" | pins={graph.get('pin_count') or 'n/a'}"
                f" | links={graph.get('link_count') or 'n/a'}"
            ),
        )
    ]
    node_preview = _node_preview_text(graph, output_language=output_language)
    if node_preview:
        answer_parts.append(node_preview)
    focused_node_text = _focused_node_text(node, output_language=output_language)
    if focused_node_text:
        answer_parts.append(focused_node_text)
    return "\n\n".join(answer_parts)


def _node_preview_text(graph: dict[str, Any], *, output_language: str) -> str:
    node_lines = []
    for item in list(graph.get("nodes") or [])[:8]:
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("node_name") or item.get("node_class") or "Unknown"
        node_lines.append(
            f"- {title}"
            + (f" | class={item.get('node_class')}" if item.get("node_class") else "")
            + (f" | id={item.get('node_id')}" if item.get("node_id") else "")
        )
    if not node_lines:
        return ""
    return _localized(output_language, "节点预览：", "Node preview:") + "\n" + "\n".join(node_lines)


def _focused_node_text(node: dict[str, Any] | None, *, output_language: str) -> str:
    if not isinstance(node, dict):
        return ""
    pin_names = [
        str(pin.get("pin_name") or pin.get("pin_id") or "").strip()
        for pin in list(node.get("pins") or [])
        if isinstance(pin, dict) and str(pin.get("pin_name") or pin.get("pin_id") or "").strip()
    ]
    line = (
        f"- {node.get('title') or node.get('node_name') or 'Unknown'}"
        + (f" | class={node.get('node_class')}" if node.get("node_class") else "")
        + (f" | id={node.get('node_id')}" if node.get("node_id") else "")
        + (f" | pins={', '.join(pin_names[:8])}" if pin_names else "")
    )
    return "\n".join([_localized(output_language, "当前聚焦节点：", "Focused node:"), line])
