from __future__ import annotations

from typing import Any


TOOL_USE_SUMMARY_VERSION = "tool_use_summary_v1"

_TOOL_LABELS: dict[str, str] = {
    "query_project_inventory": "Project inventory",
    "retrieve_project_knowledge": "Knowledge retrieval",
    "read_project_file": "Project file",
    "mcp_get_asset_details": "Asset details",
    "mcp_get_selected_assets": "Selected assets",
    "mcp_get_static_mesh_details": "Static Mesh details",
    "mcp_get_selected_actors": "Selected actors",
    "mcp_get_level_actor_details": "Level Actor details",
    "mcp_get_blueprint_graph": "Blueprint graph",
    "mcp_get_blueprint_node_details": "Blueprint node details",
    "mcp_get_widget_tree": "Widget tree",
    "mcp_get_umg_widget_details": "Widget details",
    "mcp_get_material_instance_parameters": "Material parameters",
    "mcp_get_material_parameter_details": "Material parameter details",
    "llm_answer_synthesis": "Answer synthesis",
    "web_search_knowledge": "Web search",
}


def _count_items(value: Any) -> int | None:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        for key in ("items", "retrieved_docs", "citations", "errors", "warnings"):
            if isinstance(value.get(key), list):
                return len(value[key])
    return None


def _safe_keys(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    blocked = {
        "raw",
        "raw_payload",
        "structuredContent",
        "content",
        "result",
        "debug",
        "debug_view",
        "normalized_request",
    }
    return sorted(key for key in value.keys() if key not in blocked)[:12]


def _tool_label(tool_id: str) -> str:
    if tool_id in _TOOL_LABELS:
        return _TOOL_LABELS[tool_id]
    normalized = tool_id
    for prefix in ("mcp_get_", "editor_", "tool_", "ue_"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    return normalized.replace("_", " ").strip().title() or "Tool"


def _first_item(output: Any) -> dict[str, Any]:
    if not isinstance(output, dict):
        return {}
    item = output.get("item")
    if isinstance(item, dict):
        return item
    items = output.get("items")
    if isinstance(items, list):
        for candidate in items:
            if isinstance(candidate, dict):
                return candidate
    return output


def _compact_text(value: Any, *, limit: int = 180) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 3, 0)]}..."


def _as_bool_label(value: Any) -> str | None:
    if value is True:
        return "enabled"
    if value is False:
        return "disabled"
    return None


def _compact_list(values: list[str], *, limit: int = 4) -> str:
    cleaned = [value for value in values if value]
    if not cleaned:
        return ""
    head = cleaned[:limit]
    suffix = f", +{len(cleaned) - limit} more" if len(cleaned) > limit else ""
    return ", ".join(head) + suffix


def _names_from_parameters(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    names: list[str] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("parameter_name") or "").strip()
        if name:
            names.append(name)
    return names


def _target_names_from_output(output: Any) -> list[str]:
    if not isinstance(output, dict):
        return []
    candidates: list[dict[str, Any]] = []
    first = _first_item(output)
    if first:
        candidates.append(first)
    items = output.get("items")
    if isinstance(items, list):
        candidates.extend(item for item in items if isinstance(item, dict))
    names: list[str] = []
    name_keys = (
        "asset_name",
        "actor_label",
        "actor_name",
        "blueprint_name",
        "graph_name",
        "widget_name",
        "root_widget_name",
        "material_instance_name",
        "parameter_name",
        "name",
    )
    for item in candidates:
        for key in name_keys:
            value = str(item.get(key) or "").strip()
            if value and value not in names:
                names.append(value)
                break
    return names[:8]


def _domain_summary(tool_id: str, output: Any, *, item_count: int | None, status: str) -> tuple[str, str, list[str]]:
    label = _tool_label(tool_id)
    if not isinstance(output, dict):
        return f"{label} completed with status {status}.", "generic", []

    item = _first_item(output)
    target_names = _target_names_from_output(output)
    lower_tool = tool_id.lower()

    if "asset" in lower_tool or "static_mesh" in lower_tool:
        return _asset_summary(item, label=label, item_count=item_count, status=status), "asset", target_names
    if "actor" in lower_tool:
        return _actor_summary(item, label=label, item_count=item_count, status=status), "level_actor", target_names
    if "blueprint" in lower_tool:
        return _blueprint_summary(item, output, label=label, item_count=item_count, status=status), "blueprint", target_names
    if "widget" in lower_tool or "umg" in lower_tool:
        return _widget_summary(item, output, label=label, item_count=item_count, status=status), "widget", target_names
    if "material" in lower_tool:
        return _material_summary(item, label=label, item_count=item_count, status=status), "material", target_names
    if tool_id == "query_project_inventory":
        return _inventory_summary(output, label=label, item_count=item_count, status=status), "project_inventory", target_names

    count_text = f" returned {item_count} item{'s' if item_count != 1 else ''}." if item_count is not None else ""
    return f"{label}{count_text or f' completed with status {status}.'}", "generic", target_names


def _asset_summary(item: dict[str, Any], *, label: str, item_count: int | None, status: str) -> str:
    name = str(item.get("asset_name") or item.get("name") or item.get("asset_path") or "").strip()
    asset_type = str(item.get("asset_type") or item.get("class") or item.get("type") or "").strip()
    static_mesh = item.get("static_mesh") if isinstance(item.get("static_mesh"), dict) else {}
    parts = [f"{label}: {name}" if name else f"{label} completed with status {status}"]
    if asset_type:
        parts.append(f"type: {asset_type}")
    nanite = _as_bool_label(static_mesh.get("nanite_enabled"))
    if nanite:
        parts.append(f"Nanite: {nanite}")
    collision = str(static_mesh.get("collision_complexity") or static_mesh.get("collision_trace_flag") or "").strip()
    if collision:
        parts.append(f"collision: {collision}")
    if item_count and item_count > 1:
        parts.append(f"items: {item_count}")
    return "; ".join(parts) + "."


def _actor_summary(item: dict[str, Any], *, label: str, item_count: int | None, status: str) -> str:
    name = str(item.get("actor_label") or item.get("actor_name") or item.get("name") or "").strip()
    actor_class = str(item.get("actor_class") or item.get("class") or "").strip()
    components = item.get("components") if isinstance(item.get("components"), list) else []
    parts = [f"{label}: {name}" if name else f"{label} completed with status {status}"]
    if actor_class:
        parts.append(f"class: {actor_class}")
    if components:
        parts.append(f"{len(components)} component{'s' if len(components) != 1 else ''}")
    if item_count and item_count > 1:
        parts.append(f"items: {item_count}")
    return "; ".join(parts) + "."


def _blueprint_summary(
    item: dict[str, Any], output: dict[str, Any], *, label: str, item_count: int | None, status: str
) -> str:
    name = str(item.get("asset_name") or item.get("blueprint_name") or item.get("name") or "").strip()
    graph_name = str(item.get("graph_name") or output.get("graph_name") or "").strip()
    nodes = item.get("nodes") if isinstance(item.get("nodes"), list) else output.get("nodes")
    node_count = len(nodes) if isinstance(nodes, list) else None
    parts = [f"{label}: {name}" if name else f"{label} completed with status {status}"]
    if graph_name:
        parts.append(f"graph: {graph_name}")
    if node_count is not None:
        parts.append(f"{node_count} node{'s' if node_count != 1 else ''}")
    if item_count and item_count > 1:
        parts.append(f"items: {item_count}")
    return "; ".join(parts) + "."


def _widget_summary(
    item: dict[str, Any], output: dict[str, Any], *, label: str, item_count: int | None, status: str
) -> str:
    name = str(item.get("widget_name") or output.get("widget_name") or item.get("root_widget_name") or "").strip()
    widget_class = str(item.get("widget_class") or item.get("class") or "").strip()
    parent = str(item.get("parent_widget_name") or output.get("parent_widget_name") or "").strip()
    visibility = str(item.get("visibility") or output.get("visibility") or "").strip()
    widgets = output.get("widgets") if isinstance(output.get("widgets"), list) else item.get("widgets")
    widget_count = len(widgets) if isinstance(widgets, list) else None
    parts = [f"{label}: {name}" if name else f"{label} completed with status {status}"]
    if widget_class:
        parts.append(f"class: {widget_class}")
    if parent:
        parts.append(f"parent: {parent}")
    if visibility:
        parts.append(f"visibility: {visibility}")
    if widget_count is not None:
        parts.append(f"{widget_count} widget{'s' if widget_count != 1 else ''}")
    if item_count and item_count > 1:
        parts.append(f"items: {item_count}")
    return "; ".join(parts) + "."


def _material_summary(item: dict[str, Any], *, label: str, item_count: int | None, status: str) -> str:
    name = str(
        item.get("material_instance_name")
        or item.get("material_instance_path")
        or item.get("material_name")
        or item.get("name")
        or ""
    ).strip()
    parent = str(item.get("parent_material") or "").strip()
    scalar_names = _names_from_parameters(item.get("scalar_parameters"))
    vector_names = _names_from_parameters(item.get("vector_parameters"))
    texture_names = _names_from_parameters(item.get("texture_parameters"))
    static_switch_names = _names_from_parameters(item.get("static_switch_parameters"))
    parameter_names = scalar_names + vector_names + texture_names + static_switch_names
    parts = [f"{label}: {name}" if name else f"{label} completed with status {status}"]
    if parent:
        parts.append(f"parent: {parent}")
    if parameter_names:
        parts.append(f"parameters: {_compact_list(parameter_names)}")
    if item_count and item_count > 1:
        parts.append(f"items: {item_count}")
    return "; ".join(parts) + "."


def _inventory_summary(output: dict[str, Any], *, label: str, item_count: int | None, status: str) -> str:
    summary = output.get("summary") if isinstance(output.get("summary"), dict) else {}
    parts = [label]
    for key, text in (
        ("asset_count", "assets"),
        ("blueprint_count", "Blueprints"),
        ("level_actor_count", "level actors"),
        ("material_instance_count", "material instances"),
        ("code_file_count", "code files"),
    ):
        value = summary.get(key)
        if isinstance(value, int):
            parts.append(f"{value} {text}")
    if len(parts) == 1:
        if item_count is not None:
            parts.append(f"{item_count} item{'s' if item_count != 1 else ''}")
        else:
            parts.append(f"completed with status {status}")
    return "; ".join(parts) + "."


def summarize_tool_use(
    *,
    tool_id: str,
    result: dict[str, Any] | None = None,
    status: str | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    result = dict(result or {})
    resolved_status = status or str(result.get("status") or "completed")
    output = result.get("output") if isinstance(result.get("output"), dict) else result
    item_count = _count_items(output)
    warning_count = len(output.get("warnings") or []) if isinstance(output, dict) else 0
    error_count = len(output.get("errors") or []) if isinstance(output, dict) else 0
    tool_label = _tool_label(tool_id)
    domain_summary, evidence_kind, target_names = _domain_summary(
        tool_id,
        output,
        item_count=item_count,
        status=resolved_status,
    )
    user_summary = (summary or result.get("summary") or output.get("answer")) if isinstance(output, dict) else summary
    if not user_summary:
        user_summary = domain_summary
    return {
        "version": TOOL_USE_SUMMARY_VERSION,
        "tool_id": tool_id,
        "tool_label": tool_label,
        "status": resolved_status,
        "user_summary": _compact_text(user_summary),
        "evidence_kind": evidence_kind,
        "target_names": target_names,
        "item_count": item_count,
        "warning_count": warning_count,
        "error_count": error_count,
        "safe_output_keys": _safe_keys(output),
        "raw_payload_hidden": True,
    }


def summarize_tool_uses(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        summaries.append(
            summarize_tool_use(
                tool_id=str(item.get("tool_id") or "unknown_tool"),
                result=item,
                status=str(item.get("status") or ""),
                summary=str(item.get("summary") or ""),
            )
        )
    return summaries


__all__ = ["TOOL_USE_SUMMARY_VERSION", "summarize_tool_use", "summarize_tool_uses"]
