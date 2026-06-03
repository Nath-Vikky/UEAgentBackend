from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.services.editor_operations.blueprint_result_diagnostics import first_non_empty_text
from app.services.editor_operations.results import as_string_list


def operation_result_user_view(
    *,
    operation_result: dict[str, Any],
    follow_up: dict[str, Any],
    quick_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    result_summary = dict(operation_result.get("result_summary") or {})
    operation_type = str(operation_result.get("operation_type") or "editor_operation")
    needs_attention = bool(result_summary.get("needs_user_attention"))
    quick_action_count = len(quick_actions)
    status_hint = "needs_attention" if needs_attention else "completed"
    if quick_action_count:
        text = (
            f"`{operation_type}` result was recorded. The backend found "
            f"{quick_action_count} safe follow-up Proposal action(s). Review them before execution."
        )
    elif needs_attention:
        text = (
            f"`{operation_type}` result was recorded and needs attention. "
            "Check the diagnostics block for missing inputs or repair advice."
        )
    else:
        text = f"`{operation_type}` result was recorded successfully."

    blocks = [
        {
            "block_type": "editor_operation_result_summary",
            "title": "Editor Operation Result",
            "text": text,
            "data": result_summary,
        }
    ]
    graph_detail_block = blueprint_graph_result_detail_block(operation_result=operation_result)
    if graph_detail_block:
        blocks.append(graph_detail_block)
    if follow_up:
        blocks.append(
            {
                "block_type": "editor_operation_follow_ups",
                "title": "Follow-up Candidates",
                "text": (
                    "Ready candidates can be converted into one pending Proposal at a time."
                    if quick_action_count
                    else "No ready follow-up Proposal is available yet."
                ),
                "data": follow_up,
            }
        )

    return {
        "title": "Editor Operation Result",
        "text": text,
        "blocks": blocks,
        "citations_preview": [],
        "quick_actions": quick_actions,
        "status_hint": status_hint,
    }


def summarize_graph_node(value: Any) -> str:
    if isinstance(value, dict):
        role = str(value.get("role") or "").strip()
        name = str(value.get("node_name") or value.get("name") or value.get("id") or "").strip()
        node_id = str(value.get("node_id") or value.get("id") or value.get("guid") or "").strip()
        node_class = str(value.get("node_class") or "").strip()
        left = name or node_id
        if not left:
            return ""
        parts = []
        if role:
            parts.append(f"{role}:")
        parts.append(left)
        if node_class:
            parts.append(f"[{node_class}]")
        if node_id and node_id != left:
            parts.append(f"({node_id})")
        return " ".join(parts)
    return str(value or "").strip()


def summarize_graph_pin(value: Any) -> str:
    if isinstance(value, dict):
        summary = str(value.get("summary") or "").strip()
        if summary:
            return summary
        source = dict(value.get("source") or {}) if isinstance(value.get("source"), dict) else {}
        target = dict(value.get("target") or {}) if isinstance(value.get("target"), dict) else {}
        source_text = ".".join(
            item
            for item in (
                str(source.get("node_name") or source.get("node_id") or "").strip(),
                str(source.get("pin_name") or source.get("pin_id") or "").strip(),
            )
            if item
        )
        target_text = ".".join(
            item
            for item in (
                str(target.get("node_name") or target.get("node_id") or "").strip(),
                str(target.get("pin_name") or target.get("pin_id") or "").strip(),
            )
            if item
        )
        if source_text or target_text:
            return f"{source_text} -> {target_text}".strip()
        return ""
    return str(value or "").strip()


def summarize_limited_items(values: Any, summarizer: Callable[[Any], str], *, limit: int = 6) -> list[str]:
    if not isinstance(values, list):
        values = [values] if values else []
    items = [summarizer(item) for item in values[:limit]]
    items = [item for item in items if item]
    if len(values) > limit:
        items.append(f"+{len(values) - limit} more")
    return items


def blueprint_graph_result_detail_block(*, operation_result: dict[str, Any]) -> dict[str, Any] | None:
    result = dict(operation_result.get("result") or {})
    result_summary = dict(operation_result.get("result_summary") or {})
    diagnostics = dict(result_summary.get("operation_diagnostics") or {})
    if diagnostics.get("category") != "blueprint_graph":
        return None

    blueprint_path = first_non_empty_text(
        result.get("blueprint_path"),
        diagnostics.get("blueprint_path"),
    )
    graph_name = first_non_empty_text(
        result.get("graph_name"),
        diagnostics.get("graph_name"),
    )
    template_id = first_non_empty_text(
        result.get("template_id"),
        diagnostics.get("template_id"),
    )
    entry_node_id = first_non_empty_text(result.get("entry_node_id"))
    entry_node_name = first_non_empty_text(result.get("entry_node_name"))
    created_node_id = first_non_empty_text(result.get("created_node_id"))
    created_node_name = first_non_empty_text(result.get("created_node_name"))

    items: list[str] = []
    if blueprint_path:
        items.append(f"Blueprint: {blueprint_path}")
    if graph_name:
        items.append(f"Graph: {graph_name}")
    if template_id:
        items.append(f"Template: {template_id}")
    if entry_node_id or entry_node_name:
        items.append(f"Entry node: {entry_node_name or 'unknown'} ({entry_node_id or 'no stable id'})")
    if created_node_id or created_node_name:
        items.append(f"Primary created node: {created_node_name or 'unknown'} ({created_node_id or 'no stable id'})")

    created_nodes = result.get("created_nodes")
    for node_summary in summarize_limited_items(
        created_nodes,
        summarize_graph_node,
        limit=5,
    ):
        items.append(f"Created: {node_summary}")

    linked_pins = result.get("linked_pins")
    linked_pin_summaries = result.get("linked_pin_summaries")
    link_items = summarize_limited_items(
        linked_pins,
        summarize_graph_pin,
        limit=5,
    )
    if not link_items:
        link_items = as_string_list(linked_pin_summaries)[:5]
    for link_summary in link_items:
        items.append(f"Linked pin: {link_summary}")

    compile_status = first_non_empty_text(
        result.get("compile_status"),
        diagnostics.get("compile_status"),
    )
    if compile_status:
        items.append(f"Compile status: {compile_status}")
    dirty_packages = as_string_list(result.get("dirty_packages") or result_summary.get("dirty_packages"))
    if dirty_packages:
        items.append(f"Dirty packages: {', '.join(dirty_packages[:5])}")
    for failed_field in summarize_limited_items(
        result_summary.get("failed_fields") or result.get("failed_fields"),
        lambda item: (
            f"{item.get('field') or 'unknown'}: {item.get('reason') or item.get('message') or 'failed'}"
            if isinstance(item, dict)
            else str(item)
        ),
        limit=5,
    ):
        items.append(f"Failed field: {failed_field}")
    error_items = []
    for error_item in operation_result.get("errors") or []:
        if isinstance(error_item, dict):
            code = first_non_empty_text(
                error_item.get("code"),
                error_item.get("reason"),
                "unknown_error",
            )
            message = first_non_empty_text(error_item.get("message"))
            error_items.append(f"{code}: {message}" if message else code)
        else:
            error_items.append(str(error_item))
    for error_summary in error_items[:5]:
        items.append(f"UE error: {error_summary}")

    if not items:
        return None

    return {
        "block_type": "editor_operation_graph_details",
        "title": "Blueprint Graph Details",
        "text": "Stable node and pin details reported by UEAgentTool for follow-up repair or manual inspection.",
        "data": {
            "schema_version": "blueprint_graph_result_details_v1",
            "items": items,
            "blueprint_path": blueprint_path,
            "graph_name": graph_name,
            "template_id": template_id,
            "entry_node_id": entry_node_id,
            "entry_node_name": entry_node_name,
            "created_node_id": created_node_id,
            "created_node_name": created_node_name,
            "created_nodes": created_nodes or [],
            "linked_pins": linked_pins or [],
            "linked_pin_summaries": linked_pin_summaries or [],
            "compile_status": compile_status,
            "dirty_packages": dirty_packages,
        },
    }


__all__ = [
    "blueprint_graph_result_detail_block",
    "operation_result_user_view",
    "summarize_graph_node",
    "summarize_graph_pin",
    "summarize_limited_items",
]
