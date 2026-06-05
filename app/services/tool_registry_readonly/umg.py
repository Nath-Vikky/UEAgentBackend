from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def find_widget_blueprint(
    *,
    inventory: Any,
    project_id: str | None,
    widget_query: str,
) -> dict[str, Any] | None:
    asset = inventory.get_asset(widget_query, project_id) if widget_query else None
    if asset:
        return asset
    matches = inventory.list_assets(
        project_id=project_id,
        query=widget_query or None,
        asset_type="WidgetBlueprint",
        limit=1,
    )
    return matches[0] if matches else None


def extract_widget_tree(
    *,
    blueprint: dict[str, Any],
    properties: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    for source in (blueprint, properties, metadata):
        for key in ("widget_tree", "widgets", "designer_tree", "hierarchy"):
            value = source.get(key)
            if isinstance(value, dict):
                return value
            if isinstance(value, list):
                return {"widgets": value}
    return {}


def build_umg_widget_detail_result(
    *,
    inventory: Any,
    summary: dict[str, Any],
    project_id: str | None,
    args: dict[str, Any],
) -> dict[str, Any]:
    widget_query = _first_text(
        args.get("widget_blueprint_path"),
        args.get("blueprint_path"),
        args.get("asset_path"),
        args.get("widget_blueprint_query"),
        args.get("query"),
    )
    widget_name = _first_text(args.get("widget_name"), args.get("target_widget"), args.get("cursor_widget"))
    asset = find_widget_blueprint(inventory=inventory, project_id=project_id, widget_query=widget_query)
    blueprint = _as_dict(asset.get("blueprint") if asset else {})
    properties = _as_dict(asset.get("properties") if asset else {})
    metadata = _as_dict(asset.get("metadata") if asset else {})
    widget_tree = extract_widget_tree(blueprint=blueprint, properties=properties, metadata=metadata)
    widgets = _flatten_widgets(widget_tree)
    widget = _find_widget(widgets, widget_name)
    children = _widget_children(widgets, widget)
    empty_reason = ""
    if not summary.get("has_snapshot"):
        empty_reason = "no_project_inventory_snapshot"
    elif not asset:
        empty_reason = "no_matching_widget_blueprint"
    elif not widget_tree:
        empty_reason = "widget_tree_not_in_inventory_snapshot"
    elif not widget:
        empty_reason = "no_matching_widget"
    resolved_widget_name = _widget_name(widget)
    resolved_widget_class = _widget_class(widget)
    parent_widget_name = _widget_parent(widget)
    return {
        "content": [
            {
                "type": "text",
                "text": _widget_detail_text(
                    widget_blueprint_name=asset.get("asset_name") if asset else widget_query,
                    widget_name=resolved_widget_name or widget_name,
                    widget_class=resolved_widget_class,
                    parent_widget_name=parent_widget_name,
                    empty_reason=empty_reason,
                ),
            }
        ],
        "structuredContent": {
            "schema_version": "inventory_umg_widget_detail_v1",
            "widget_blueprint_path": asset.get("asset_path") if asset else widget_query,
            "widget_blueprint_name": asset.get("asset_name") if asset else "",
            "parent_class": asset.get("parent_class") or blueprint.get("parent_class") if asset else "",
            "widget_name": resolved_widget_name or widget_name,
            "widget_class": resolved_widget_class,
            "parent_widget_name": parent_widget_name,
            "widget": widget,
            "slot": _widget_slot(widget),
            "layout": _widget_layout(widget),
            "properties": _widget_properties(widget),
            "style": _widget_style(widget),
            "children": children[:64],
            "widget_tree_summary": {
                "widget_count": len(widgets),
                "root_widget_name": _first_text(widget_tree.get("root"), widget_tree.get("root_widget")),
            },
            "summary": summary,
            "empty_reason": empty_reason,
        },
    }


def _flatten_widgets(widget_tree: dict[str, Any]) -> list[dict[str, Any]]:
    widgets: list[dict[str, Any]] = []

    def walk(value: Any, *, parent_name: str = "") -> None:
        if isinstance(value, list):
            for item in value:
                walk(item, parent_name=parent_name)
            return
        if not isinstance(value, dict):
            return

        name = _first_text(
            value.get("name"),
            value.get("widget_name"),
            value.get("id"),
            value.get("display_name"),
            value.get("object_name"),
        )
        widget_class = _first_text(value.get("class"), value.get("widget_class"), value.get("type"))
        if name or widget_class:
            item = dict(value)
            if parent_name and not _widget_parent(item):
                item["parent"] = parent_name
            widgets.append(item)
        next_parent = name or parent_name
        for key in ("widgets", "children", "nodes"):
            walk(value.get(key), parent_name=next_parent)

    for key in ("widgets", "children", "nodes"):
        walk(widget_tree.get(key), parent_name="")
    if not widgets:
        walk(widget_tree, parent_name="")
    return widgets


def _find_widget(widgets: list[dict[str, Any]], widget_name: str) -> dict[str, Any]:
    query = _norm(widget_name)
    if not query:
        return widgets[0] if widgets else {}
    for widget in widgets:
        if any(_norm(value) == query for value in _widget_identity_values(widget)):
            return widget
    for widget in widgets:
        if any(query in _norm(value) for value in _widget_identity_values(widget)):
            return widget
    return {}


def _widget_identity_values(widget: dict[str, Any]) -> list[str]:
    return [
        _first_text(widget.get("name")),
        _first_text(widget.get("widget_name")),
        _first_text(widget.get("id")),
        _first_text(widget.get("display_name")),
        _first_text(widget.get("object_name")),
    ]


def _widget_name(widget: dict[str, Any]) -> str:
    return _first_text(
        widget.get("name"),
        widget.get("widget_name"),
        widget.get("id"),
        widget.get("display_name"),
        widget.get("object_name"),
    )


def _widget_class(widget: dict[str, Any]) -> str:
    return _first_text(widget.get("class"), widget.get("widget_class"), widget.get("type"))


def _widget_parent(widget: dict[str, Any]) -> str:
    return _first_text(
        widget.get("parent"),
        widget.get("parent_name"),
        widget.get("parent_widget"),
        widget.get("parent_widget_name"),
        _as_dict(widget.get("slot")).get("parent"),
        _as_dict(widget.get("slot")).get("parent_widget_name"),
    )


def _widget_children(widgets: list[dict[str, Any]], widget: dict[str, Any]) -> list[dict[str, Any]]:
    widget_name = _norm(_widget_name(widget))
    if not widget_name:
        return []
    children: list[dict[str, Any]] = []
    for item in widgets:
        parent_name = _norm(_widget_parent(item))
        if parent_name == widget_name:
            children.append(
                {
                    "widget_name": _widget_name(item),
                    "widget_class": _widget_class(item),
                }
            )
    return children


def _widget_slot(widget: dict[str, Any]) -> dict[str, Any]:
    return dict(_as_dict(widget.get("slot") or widget.get("slot_data") or widget.get("layout_slot")))


def _widget_layout(widget: dict[str, Any]) -> dict[str, Any]:
    layout = dict(_as_dict(widget.get("layout") or widget.get("layout_data")))
    for key in ("position", "size", "anchors", "alignment", "padding", "offsets"):
        if key in widget and key not in layout:
            layout[key] = widget[key]
    return layout


def _widget_style(widget: dict[str, Any]) -> dict[str, Any]:
    source_key = "style"
    source = widget.get("style")
    if not isinstance(source, dict):
        source_key = "appearance"
        source = widget.get("appearance")
    if not isinstance(source, dict):
        source_key = "brush"
        source = widget.get("brush")
    style = dict(_as_dict(source))
    for key in ("color", "opacity", "font", "brush", "tint"):
        if key != source_key and key in widget and key not in style:
            style[key] = widget[key]
    return style


def _widget_properties(widget: dict[str, Any]) -> dict[str, Any]:
    properties = dict(_as_dict(widget.get("properties") or widget.get("details")))
    ignored = {
        "children",
        "widgets",
        "nodes",
        "properties",
        "details",
        "slot",
        "slot_data",
        "layout_slot",
        "layout",
        "layout_data",
        "style",
        "appearance",
        "brush",
    }
    for key, value in widget.items():
        if key not in ignored and key not in properties:
            properties[key] = value
    return properties


def _widget_detail_text(
    *,
    widget_blueprint_name: Any,
    widget_name: str,
    widget_class: str,
    parent_widget_name: str,
    empty_reason: str,
) -> str:
    if empty_reason:
        return f"UMG widget detail unavailable: {empty_reason}."
    parts = [f"Found {widget_name or 'widget'}"]
    if widget_class:
        parts.append(f"class={widget_class}")
    if parent_widget_name:
        parts.append(f"parent={parent_widget_name}")
    if widget_blueprint_name:
        parts.append(f"in {widget_blueprint_name}")
    return "; ".join(parts) + "."

