from __future__ import annotations

from typing import Any

from app.agent.context_builder import build_context_summary
from app.i18n.language import localized as _localized
from app.schemas.common import QuickAction, UserViewBlock
from app.services.mcp_executor import MCPToolExecutor
from app.services.task_handlers.base import TaskExecutionContext
from app.services.tool_registry_readonly_call_service import ToolRegistryReadOnlyCallService


LIVE_MCP_TOOL_NAMES = {
    "mcp_get_editor_context": "get_editor_context",
    "mcp_get_blueprint_graph": "get_blueprint_graph",
    "mcp_get_widget_tree": "get_widget_tree",
}
LOCAL_INVENTORY_READONLY_TOOL_IDS = {"mcp_get_blueprint_graph", "mcp_get_widget_tree"}


def live_mcp_readonly_result(
    *,
    context: TaskExecutionContext,
    base_debug: dict[str, Any],
    output_language: str,
    selected_tool_id: str,
) -> dict[str, Any] | None:
    dependencies = context.dependencies
    if dependencies is None:
        return None
    tool_name = LIVE_MCP_TOOL_NAMES.get(selected_tool_id)
    if not tool_name:
        return None
    arguments = _live_mcp_arguments(context, selected_tool_id=selected_tool_id)
    if arguments is None:
        return None

    result = MCPToolExecutor(dependencies.settings).call_readonly_tool(tool_name, arguments)
    base_debug["mcp_live_attempt"] = {
        "tool_id": selected_tool_id,
        "tool_name": tool_name,
        "arguments": arguments,
        "status": result.get("status"),
        "reason": result.get("reason"),
        "transport": result.get("transport"),
    }
    tool_result = result.get("result") if isinstance(result.get("result"), dict) else {}
    if not result.get("ok") or tool_result.get("isError") is True:
        base_debug["mcp_live_attempt"]["errors"] = result.get("errors") or []
        base_debug["mcp_live_attempt"]["tool_error"] = _first_text_content(tool_result)
        return None

    answer = _live_mcp_answer(
        selected_tool_id=selected_tool_id,
        tool_result=tool_result,
        arguments=arguments,
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
            "step_id": "call_live_mcp_readonly_tool",
            "title": "Call Live MCP Read-only Tool",
            "status": "completed",
            "summary": f"Called {tool_name} through the optional MCP TCP adapter.",
            "details": {
                "tool_id": selected_tool_id,
                "tool_name": tool_name,
                "arguments": arguments,
                "transport": result.get("transport"),
            },
        },
    ]
    user_view = {
        "title": _localized(output_language, "UE 实时只读工具结果", "Live UE Read-only Tool Result"),
        "text": answer,
        "blocks": [
            UserViewBlock(
                block_type="summary",
                title=_localized(output_language, "工具结果摘要", "Tool Result Summary"),
                text=answer,
                data={
                    "tool_id": selected_tool_id,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "result": tool_result,
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
        "status_hint": "mcp_tcp_readonly_completed",
    }
    data = {
        "answer": answer,
        "sources": [
            {
                "source_type": "mcp_tcp",
                "title": tool_name,
                "path": arguments.get("blueprint_path") or arguments.get("widget_blueprint_path"),
            }
        ],
        "citations": [],
        "confidence": 0.78,
        "context_summary": build_context_summary(context.request),
        "warnings": [],
        "mcp_tool": {
            "tool_id": selected_tool_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "transport": result.get("transport"),
            "result": tool_result,
        },
    }
    base_debug["step_results"] = step_results
    base_debug["raw_result"] = data
    base_debug["tools"] = [
        {
            "tool_id": selected_tool_id,
            "status": "completed",
            "summary": f"Answered from live MCP TCP read-only tool {tool_name}.",
        }
    ]
    return {
        "user_view": user_view,
        "debug_view": base_debug,
        "data": data,
        "retrieval_trace": {
            "mode": "mcp_tcp_readonly",
            "degraded_mode": False,
            "reason": "live_mcp_readonly_tool_completed",
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


def local_tool_registry_readonly_result(
    *,
    context: TaskExecutionContext,
    base_debug: dict[str, Any],
    output_language: str,
    selected_tool_id: str,
) -> dict[str, Any] | None:
    dependencies = context.dependencies
    if dependencies is None or selected_tool_id not in LOCAL_INVENTORY_READONLY_TOOL_IDS:
        return None
    arguments = _live_mcp_arguments(context, selected_tool_id=selected_tool_id)
    if arguments is None:
        return None

    call = ToolRegistryReadOnlyCallService(dependencies.settings).call(selected_tool_id, arguments)
    base_debug["local_readonly_attempt"] = {
        "tool_id": selected_tool_id,
        "arguments": arguments,
        "status": call.get("status"),
        "reason": call.get("reason"),
        "transport": call.get("transport"),
    }
    if not call.get("ok"):
        base_debug["local_readonly_attempt"]["errors"] = call.get("errors") or []
        return None
    tool_result = call.get("result") if isinstance(call.get("result"), dict) else {}
    if _local_readonly_result_is_empty(selected_tool_id=selected_tool_id, tool_result=tool_result):
        base_debug["local_readonly_attempt"]["empty_reason"] = (
            (tool_result.get("structuredContent") or {}).get("empty_reason")
            if isinstance(tool_result.get("structuredContent"), dict)
            else ""
        )
        return None

    answer = _live_mcp_answer(
        selected_tool_id=selected_tool_id,
        tool_result=tool_result,
        arguments=arguments,
        output_language=output_language,
        source_label_zh="本地 Project Inventory 只读工具",
        source_label_en="local Project Inventory read-only tool",
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
            "step_id": "read_local_tool_registry_inventory",
            "title": "Read Local Tool Registry Inventory",
            "status": "completed",
            "summary": f"Used local Inventory-backed read-only tool {selected_tool_id}.",
            "details": {
                "tool_id": selected_tool_id,
                "arguments": arguments,
                "transport": call.get("transport"),
            },
        },
    ]
    user_view = {
        "title": _localized(output_language, "本地只读工具结果", "Local Read-only Tool Result"),
        "text": answer,
        "blocks": [
            UserViewBlock(
                block_type="summary",
                title=_localized(output_language, "工具结果摘要", "Tool Result Summary"),
                text=answer,
                data={
                    "tool_id": selected_tool_id,
                    "arguments": arguments,
                    "result": tool_result,
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
        "status_hint": "local_readonly_completed",
    }
    data = {
        "answer": answer,
        "sources": [
            {
                "source_type": "project_inventory",
                "title": selected_tool_id,
                "path": arguments.get("blueprint_path") or arguments.get("widget_blueprint_path"),
            }
        ],
        "citations": [],
        "confidence": 0.74,
        "context_summary": build_context_summary(context.request),
        "warnings": [],
        "local_tool": {
            "tool_id": selected_tool_id,
            "arguments": arguments,
            "transport": call.get("transport"),
            "result": tool_result,
        },
    }
    base_debug["step_results"] = step_results
    base_debug["raw_result"] = data
    base_debug["tools"] = [
        {
            "tool_id": selected_tool_id,
            "status": "completed",
            "summary": f"Answered from local Inventory-backed read-only tool {selected_tool_id}.",
        }
    ]
    return {
        "user_view": user_view,
        "debug_view": base_debug,
        "data": data,
        "retrieval_trace": {
            "mode": "local_tool_registry_readonly",
            "degraded_mode": True,
            "reason": "live_mcp_unavailable_local_inventory_tool_completed",
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


def _live_mcp_arguments(context: TaskExecutionContext, *, selected_tool_id: str) -> dict[str, Any] | None:
    request = context.request
    payload = dict(request.payload or {})
    editor_state = dict(getattr(request.context, "editor_state", {}) or {})
    inventory_context = dict((context.context_bundle or {}).get("project_inventory_context") or {})
    if selected_tool_id == "mcp_get_editor_context":
        return {}
    if selected_tool_id == "mcp_get_blueprint_graph":
        blueprint = inventory_context.get("current_blueprint") if isinstance(inventory_context, dict) else {}
        graph = inventory_context.get("current_blueprint_graph") if isinstance(inventory_context, dict) else {}
        blueprint_path = _first_non_empty(
            payload.get("blueprint_path"),
            editor_state.get("current_blueprint_path"),
            editor_state.get("blueprint_path"),
            blueprint.get("asset_path") if isinstance(blueprint, dict) else "",
        )
        if not blueprint_path:
            return None
        graph_name = _first_non_empty(
            payload.get("graph_name"),
            editor_state.get("current_graph_name"),
            graph.get("graph_name") if isinstance(graph, dict) else "",
        )
        arguments = {"blueprint_path": blueprint_path}
        if graph_name:
            arguments["graph_name"] = graph_name
        return arguments
    if selected_tool_id == "mcp_get_widget_tree":
        selected_assets = list(getattr(request.context, "selected_assets", []) or [])
        selected_inventory_assets = [
            item
            for item in list(inventory_context.get("selected_assets") or [])
            if isinstance(item, dict)
        ]
        widget_blueprint_path = _first_non_empty(
            payload.get("widget_blueprint_path"),
            payload.get("blueprint_path"),
            editor_state.get("current_widget_blueprint_path"),
            editor_state.get("widget_blueprint_path"),
            _first_widget_path_from_inventory(selected_inventory_assets),
            _first_widget_path_from_strings(selected_assets),
        )
        if not widget_blueprint_path:
            return None
        return {"widget_blueprint_path": widget_blueprint_path}
    return None


def _live_mcp_answer(
    *,
    selected_tool_id: str,
    tool_result: dict[str, Any],
    arguments: dict[str, Any],
    output_language: str,
    source_label_zh: str = "UEAgentTool TCP 只读工具",
    source_label_en: str = "UEAgentTool TCP read-only tool",
) -> str:
    structured = _structured_content_for_answer(selected_tool_id=selected_tool_id, tool_result=tool_result)
    if selected_tool_id == "mcp_get_editor_context":
        tool_summary = structured.get("tool_summary") if isinstance(structured.get("tool_summary"), dict) else {}
        editor_world = structured.get("editor_world") if isinstance(structured.get("editor_world"), dict) else {}
        parts = [
            _localized(
                output_language,
                f"已通过 {source_label_zh}读取当前编辑器上下文。",
                f"Read current editor context through {source_label_en}.",
            ),
            (
                f"- server_status={structured.get('server_status') or 'unknown'}"
                f"\n- editor_available={editor_world.get('editor_available')}"
                f"\n- world={editor_world.get('world_name') or 'n/a'}"
                f"\n- selected_actors={editor_world.get('selected_actor_count', 0)}"
                f"\n- tools={tool_summary.get('tool_count', 0)}"
                f" | read_only={tool_summary.get('read_only_tool_count', 0)}"
                f" | confirmed_write={tool_summary.get('confirmed_write_tool_count', 0)}"
            ),
        ]
        return "\n\n".join(parts)
    if selected_tool_id == "mcp_get_blueprint_graph":
        graphs = list(structured.get("graphs") or [])
        graph_lines = []
        for graph in graphs[:6]:
            if not isinstance(graph, dict):
                continue
            graph_lines.append(
                f"- {graph.get('graph_name') or 'Unknown'}"
                + (f" | type={graph.get('graph_type')}" if graph.get("graph_type") else "")
                + (f" | nodes={graph.get('node_count')}" if graph.get("node_count") is not None else "")
                + (f" | links={graph.get('link_count')}" if graph.get("link_count") is not None else "")
            )
        node_preview = _node_preview_text(graphs[0], output_language=output_language) if graphs else ""
        parts = [
            _localized(
                output_language,
                f"已通过 {source_label_zh}读取 Blueprint 图表：{arguments.get('blueprint_path')}",
                f"Read Blueprint graph through {source_label_en}: {arguments.get('blueprint_path')}",
            )
        ]
        if graph_lines:
            parts.append(_localized(output_language, "图表：", "Graphs:") + "\n" + "\n".join(graph_lines))
        if node_preview:
            parts.append(node_preview)
        return "\n\n".join(parts)
    if selected_tool_id == "mcp_get_widget_tree":
        widgets = list(structured.get("widgets") or [])
        widget_lines = []
        for widget in widgets[:10]:
            if not isinstance(widget, dict):
                continue
            widget_lines.append(
                f"- {widget.get('name') or 'Unknown'}"
                + (f" | class={widget.get('class')}" if widget.get("class") else "")
                + (f" | parent={widget.get('parent')}" if widget.get("parent") else "")
            )
        parts = [
            _localized(
                output_language,
                f"已通过 {source_label_zh}读取 Widget Tree：{arguments.get('widget_blueprint_path')}",
                f"Read Widget Tree through {source_label_en}: {arguments.get('widget_blueprint_path')}",
            )
        ]
        if structured.get("root"):
            parts.append(f"Root: {structured.get('root')}")
        if widget_lines:
            parts.append(_localized(output_language, "控件预览：", "Widget preview:") + "\n" + "\n".join(widget_lines))
        return "\n\n".join(parts)
    return _first_text_content(tool_result) or _localized(output_language, "只读工具调用已完成。", "Read-only tool call completed.")


def _structured_content_for_answer(*, selected_tool_id: str, tool_result: dict[str, Any]) -> dict[str, Any]:
    structured = tool_result.get("structuredContent") if isinstance(tool_result.get("structuredContent"), dict) else {}
    if selected_tool_id != "mcp_get_widget_tree":
        return structured
    widget_tree = structured.get("widget_tree") if isinstance(structured.get("widget_tree"), dict) else {}
    if not widget_tree:
        return structured
    merged = dict(structured)
    for key in ("root", "widgets", "children", "nodes"):
        if key in widget_tree and key not in merged:
            merged[key] = widget_tree[key]
    return merged


def _local_readonly_result_is_empty(*, selected_tool_id: str, tool_result: dict[str, Any]) -> bool:
    structured = tool_result.get("structuredContent") if isinstance(tool_result.get("structuredContent"), dict) else {}
    if selected_tool_id == "mcp_get_blueprint_graph":
        return not list(structured.get("graphs") or [])
    if selected_tool_id == "mcp_get_widget_tree":
        if structured.get("empty_reason"):
            return True
        normalized = _structured_content_for_answer(selected_tool_id=selected_tool_id, tool_result=tool_result)
        return not list(normalized.get("widgets") or normalized.get("children") or normalized.get("nodes") or [])
    return False


def _first_text_content(tool_result: dict[str, Any]) -> str:
    content = tool_result.get("content") if isinstance(tool_result.get("content"), list) else []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            return str(item.get("text") or "")
    return ""


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _first_widget_path_from_inventory(items: list[dict[str, Any]]) -> str:
    for item in items:
        asset_type = str(item.get("asset_type") or "").lower()
        asset_path = str(item.get("asset_path") or "").strip()
        asset_name = str(item.get("asset_name") or "").strip().lower()
        if asset_path and ("widget" in asset_type or asset_name.startswith("wbp_")):
            return asset_path
    return ""


def _first_widget_path_from_strings(values: list[str]) -> str:
    for value in values:
        text = str(value or "").strip()
        if text and ("WBP_" in text or "Widget" in text or "/UI/" in text):
            return text
    return ""


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
