from __future__ import annotations

from typing import Any

from app.core.settings import Settings
from app.services.project_inventory_service import ProjectInventoryService
from app.tools.registry import ToolSpec, get_tool_spec, iter_tool_specs

TOOL_REGISTRY_READONLY_CALL_VERSION = "tool_registry_readonly_call_v1"
LOCAL_READONLY_CALL_PATH = "POST /api/v1/mcp/tool-registry/tools/{tool}/call"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _truthy(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _stable_tool_name(spec: ToolSpec) -> str:
    return spec.mcp_tool_name if spec.transport.startswith("mcp") and spec.mcp_tool_name else spec.tool_id


class ToolRegistryReadOnlyCallService:
    """Execute safe local read-only ToolSpec calls.

    This is intentionally separate from the external MCP adapter. It lets debug
    panels, smoke scripts, and future MCP-compatible clients call inventory-backed
    read-only tools without enabling an external MCP process, while preserving the
    Proposal-only boundary for writes.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.inventory = ProjectInventoryService(settings)

    def call(self, tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        spec = self._resolve_spec(tool)
        args = arguments if isinstance(arguments, dict) else {}
        if not spec:
            return self._blocked(
                tool_id=str(tool or "").strip(),
                reason="tool_not_registered",
                message="Tool is not registered in the local Tool Registry.",
            )
        if not spec.enabled:
            return self._blocked(
                spec=spec,
                reason="tool_disabled",
                message="Tool is disabled by Tool Registry configuration.",
            )
        if spec.side_effect_level != "read_only":
            return self._blocked(
                spec=spec,
                reason="tool_is_not_read_only",
                message="Local Tool Registry calls only execute read-only tools. Write tools must create Proposals.",
            )

        handlers = {
            "mcp_get_blueprint_graph": self._call_blueprint_graph,
            "editor_inspect_blueprint_node_detail": self._call_inspect_blueprint_node_detail,
            "mcp_get_widget_tree": self._call_widget_tree,
            "editor_inspect_umg_widget_detail": self._call_inspect_umg_widget_detail,
            "editor_inspect_assets": self._call_inspect_assets,
            "editor_inspect_asset_detail": self._call_inspect_asset_detail,
            "editor_inspect_level_actors": self._call_inspect_level_actors,
            "editor_inspect_level_actor_detail": self._call_inspect_level_actor_detail,
            "editor_inspect_material_instance_parameters": self._call_inspect_material_instance_parameters,
            "editor_inspect_material_instance_detail": self._call_inspect_material_instance_detail,
        }
        handler = handlers.get(spec.tool_id)
        if not handler:
            return self._blocked(
                spec=spec,
                reason="local_readonly_executor_missing",
                message="This read-only tool is registered, but no local read-only executor is available yet.",
            )

        result = handler(spec, args)
        return {
            "ok": True,
            "status": "completed",
            "reason": "local_readonly_tool_completed",
            "protocol_version": TOOL_REGISTRY_READONLY_CALL_VERSION,
            "tool_id": spec.tool_id,
            "tool_name": _stable_tool_name(spec),
            "side_effect_level": spec.side_effect_level,
            "transport": "local_tool_registry",
            "source": "project_inventory",
            "result": result,
            "errors": [],
        }

    def _resolve_spec(self, tool: str) -> ToolSpec | None:
        requested = str(tool or "").strip()
        spec = get_tool_spec(requested)
        if spec:
            return spec
        for candidate in iter_tool_specs(include_disabled=True):
            if candidate.mcp_tool_name and candidate.mcp_tool_name == requested:
                return candidate
        return None

    def _summary(self, project_id: str | None) -> dict[str, Any]:
        return self.inventory.summary(project_id)

    def _call_blueprint_graph(self, spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
        del spec
        project_id = _first_text(args.get("project_id")) or None
        blueprint_query = _first_text(
            args.get("blueprint_path"),
            args.get("asset_path"),
            args.get("blueprint_query"),
            args.get("query"),
        )
        graph_name = _first_text(args.get("graph_name")) or None
        include_nodes = _truthy(args.get("include_nodes"), default=True)
        limit = _bounded_int(args.get("limit"), default=20, minimum=1, maximum=100)
        graphs = self.inventory.list_blueprint_graphs(
            project_id=project_id,
            blueprint_query=blueprint_query or None,
            graph_name=graph_name,
            include_nodes=include_nodes,
            limit=limit,
        )
        blueprints = self.inventory.list_blueprints(
            project_id=project_id,
            query=blueprint_query or None,
            limit=1,
        )
        blueprint = blueprints[0] if blueprints else {}
        summary = self._summary(project_id)
        graph_metrics = {
            "graph_count": len(graphs),
            "node_count": sum(int(item.get("node_count") or len(item.get("nodes") or [])) for item in graphs),
            "pin_count": sum(int(item.get("pin_count") or 0) for item in graphs),
            "link_count": sum(int(item.get("link_count") or 0) for item in graphs),
        }
        target = blueprint_query or blueprint.get("asset_path") or "current project inventory"
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Found {len(graphs)} Blueprint graph(s) for {target}.",
                }
            ],
            "structuredContent": {
                "graph_schema_version": "inventory_blueprint_graph_snapshot_v2",
                "blueprint_path": blueprint.get("asset_path") or blueprint_query,
                "blueprint_name": blueprint.get("asset_name") or "",
                "parent_class": blueprint.get("parent_class") or "",
                "graph_metrics": graph_metrics,
                "graphs": graphs,
                "variables": list(blueprint.get("variables") or [])[:64],
                "components": list(blueprint.get("components") or [])[:64],
                "functions": list(blueprint.get("functions") or [])[:64],
                "summary": summary,
                "empty_reason": "" if graphs else self._empty_inventory_reason(summary, "no_matching_blueprint_graphs"),
            },
        }

    def _call_inspect_blueprint_node_detail(self, spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
        del spec
        project_id = _first_text(args.get("project_id")) or None
        blueprint_query = _first_text(
            args.get("blueprint_path"),
            args.get("asset_path"),
            args.get("blueprint_query"),
            args.get("query"),
        )
        graph_name = _first_text(args.get("graph_name")) or None
        node_query = _first_text(
            args.get("node_id"),
            args.get("node_title"),
            args.get("node_name"),
            args.get("target_node"),
            args.get("node_query"),
        )
        summary = self._summary(project_id)
        graphs = self.inventory.list_blueprint_graphs(
            project_id=project_id,
            blueprint_query=blueprint_query or None,
            graph_name=graph_name,
            include_nodes=True,
            limit=50,
        )
        blueprints = self.inventory.list_blueprints(project_id=project_id, query=blueprint_query or None, limit=1)
        blueprint = blueprints[0] if blueprints else {}
        graph, node = self._find_blueprint_graph_node(graphs, node_query)
        pins = self._blueprint_node_pins(node)
        empty_reason = ""
        if not summary.get("has_snapshot"):
            empty_reason = "no_project_inventory_snapshot"
        elif not graphs:
            empty_reason = "no_matching_blueprint_graphs"
        elif not node:
            empty_reason = "no_matching_blueprint_node"
        node_title = self._blueprint_node_title(node)
        node_id = self._blueprint_node_id(node)
        return {
            "content": [
                {
                    "type": "text",
                    "text": self._blueprint_node_detail_text(
                        blueprint_name=blueprint.get("asset_name") or blueprint_query,
                        graph_name=_first_text(graph.get("graph_name")),
                        node_title=node_title or node_query,
                        node_class=self._blueprint_node_class(node),
                        empty_reason=empty_reason,
                    ),
                }
            ],
            "structuredContent": {
                "schema_version": "inventory_blueprint_node_detail_v1",
                "blueprint_path": blueprint.get("asset_path") or blueprint_query,
                "blueprint_name": blueprint.get("asset_name") or "",
                "parent_class": blueprint.get("parent_class") or "",
                "graph_name": _first_text(graph.get("graph_name")),
                "graph_type": _first_text(graph.get("graph_type")),
                "node_id": node_id,
                "node_title": node_title,
                "node_class": self._blueprint_node_class(node),
                "node": node,
                "pins": pins,
                "linked_pins": self._blueprint_linked_pins(pins),
                "graph_summary": {
                    "node_count": graph.get("node_count"),
                    "pin_count": graph.get("pin_count"),
                    "link_count": graph.get("link_count"),
                },
                "summary": summary,
                "empty_reason": empty_reason,
            },
        }

    @classmethod
    def _find_blueprint_graph_node(
        cls,
        graphs: list[dict[str, Any]],
        node_query: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not graphs:
            return {}, {}
        query = cls._norm(node_query)
        first_graph = graphs[0]
        first_node: dict[str, Any] = {}
        for graph in graphs:
            nodes = [item for item in _as_list(graph.get("nodes")) if isinstance(item, dict)]
            if nodes and not first_node:
                first_graph = graph
                first_node = nodes[0]
            if not query:
                continue
            for node in nodes:
                if any(cls._norm(value) == query for value in cls._blueprint_node_identity_values(node)):
                    return graph, node
            for node in nodes:
                if any(query in cls._norm(value) for value in cls._blueprint_node_identity_values(node)):
                    return graph, node
        return first_graph, first_node if not query else {}

    @staticmethod
    def _blueprint_node_identity_values(node: dict[str, Any]) -> list[str]:
        return [
            _first_text(node.get("node_id")),
            _first_text(node.get("id")),
            _first_text(node.get("guid")),
            _first_text(node.get("title")),
            _first_text(node.get("node_title")),
            _first_text(node.get("name")),
            _first_text(node.get("node_name")),
            _first_text(node.get("template_id")),
        ]

    @staticmethod
    def _blueprint_node_id(node: dict[str, Any]) -> str:
        return _first_text(node.get("node_id"), node.get("id"), node.get("guid"), node.get("name"))

    @staticmethod
    def _blueprint_node_title(node: dict[str, Any]) -> str:
        return _first_text(node.get("title"), node.get("node_title"), node.get("name"), node.get("node_id"))

    @staticmethod
    def _blueprint_node_class(node: dict[str, Any]) -> str:
        return _first_text(node.get("node_class"), node.get("class"), node.get("type"), node.get("node_type"))

    @classmethod
    def _blueprint_node_pins(cls, node: dict[str, Any]) -> list[dict[str, Any]]:
        pins: list[dict[str, Any]] = []
        for key, direction in (("pins", ""), ("input_pins", "input"), ("output_pins", "output")):
            for raw_pin in _as_list(node.get(key)):
                if not isinstance(raw_pin, dict):
                    continue
                pin = dict(raw_pin)
                pin.setdefault("direction", direction or _first_text(raw_pin.get("direction"), raw_pin.get("pin_direction")))
                pin.setdefault("pin_name", cls._blueprint_pin_name(pin))
                pins.append(pin)
        return pins[:128]

    @staticmethod
    def _blueprint_pin_name(pin: dict[str, Any]) -> str:
        return _first_text(pin.get("pin_name"), pin.get("name"), pin.get("display_name"), pin.get("id"))

    @classmethod
    def _blueprint_linked_pins(cls, pins: list[dict[str, Any]]) -> list[dict[str, Any]]:
        linked: list[dict[str, Any]] = []
        for pin in pins:
            links = _as_list(pin.get("linked_to") or pin.get("links") or pin.get("connections"))
            for raw_link in links:
                if isinstance(raw_link, dict):
                    linked.append(
                        {
                            "pin_name": cls._blueprint_pin_name(pin),
                            "direction": _first_text(pin.get("direction"), pin.get("pin_direction")),
                            "target_node_id": _first_text(
                                raw_link.get("node_id"),
                                raw_link.get("target_node_id"),
                                raw_link.get("node"),
                            ),
                            "target_pin_name": _first_text(
                                raw_link.get("pin_name"),
                                raw_link.get("target_pin_name"),
                                raw_link.get("pin"),
                            ),
                        }
                    )
                else:
                    linked.append(
                        {
                            "pin_name": cls._blueprint_pin_name(pin),
                            "direction": _first_text(pin.get("direction"), pin.get("pin_direction")),
                            "target": str(raw_link),
                        }
                    )
        return linked[:128]

    @staticmethod
    def _blueprint_node_detail_text(
        *,
        blueprint_name: Any,
        graph_name: str,
        node_title: str,
        node_class: str,
        empty_reason: str,
    ) -> str:
        if empty_reason:
            return f"Blueprint node detail unavailable: {empty_reason}."
        parts = [f"Found {node_title or 'node'}"]
        if node_class:
            parts.append(f"class={node_class}")
        if graph_name:
            parts.append(f"graph={graph_name}")
        if blueprint_name:
            parts.append(f"in {blueprint_name}")
        return "; ".join(parts) + "."

    def _call_widget_tree(self, spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
        del spec
        project_id = _first_text(args.get("project_id")) or None
        widget_query = _first_text(
            args.get("widget_blueprint_path"),
            args.get("blueprint_path"),
            args.get("asset_path"),
            args.get("query"),
        )
        summary = self._summary(project_id)
        asset = self._find_widget_blueprint(project_id=project_id, widget_query=widget_query)
        blueprint = _as_dict(asset.get("blueprint") if asset else {})
        properties = _as_dict(asset.get("properties") if asset else {})
        metadata = _as_dict(asset.get("metadata") if asset else {})
        widget_tree = self._extract_widget_tree(blueprint=blueprint, properties=properties, metadata=metadata)
        widgets = _as_list(widget_tree.get("widgets") or widget_tree.get("children") or widget_tree.get("nodes"))
        empty_reason = ""
        if not summary.get("has_snapshot"):
            empty_reason = "no_project_inventory_snapshot"
        elif not asset:
            empty_reason = "no_matching_widget_blueprint"
        elif not widget_tree:
            empty_reason = "widget_tree_not_in_inventory_snapshot"
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Found Widget Blueprint {asset.get('asset_name') if asset else widget_query or 'n/a'}; widget_count={len(widgets)}.",
                }
            ],
            "structuredContent": {
                "schema_version": "inventory_widget_tree_snapshot_v1",
                "widget_blueprint_path": asset.get("asset_path") if asset else widget_query,
                "widget_blueprint_name": asset.get("asset_name") if asset else "",
                "parent_class": asset.get("parent_class") or blueprint.get("parent_class") if asset else "",
                "widget_count": len(widgets),
                "widget_tree": widget_tree,
                "graph_summaries": list(asset.get("graph_summaries") or blueprint.get("graph_summaries") or [])[:8]
                if asset
                else [],
                "summary": summary,
                "empty_reason": empty_reason,
            },
        }

    def _call_inspect_umg_widget_detail(self, spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
        del spec
        project_id = _first_text(args.get("project_id")) or None
        widget_query = _first_text(
            args.get("widget_blueprint_path"),
            args.get("blueprint_path"),
            args.get("asset_path"),
            args.get("widget_blueprint_query"),
            args.get("query"),
        )
        widget_name = _first_text(args.get("widget_name"), args.get("target_widget"), args.get("cursor_widget"))
        summary = self._summary(project_id)
        asset = self._find_widget_blueprint(project_id=project_id, widget_query=widget_query)
        blueprint = _as_dict(asset.get("blueprint") if asset else {})
        properties = _as_dict(asset.get("properties") if asset else {})
        metadata = _as_dict(asset.get("metadata") if asset else {})
        widget_tree = self._extract_widget_tree(blueprint=blueprint, properties=properties, metadata=metadata)
        widgets = self._flatten_widgets(widget_tree)
        widget = self._find_widget(widgets, widget_name)
        children = self._widget_children(widgets, widget)
        empty_reason = ""
        if not summary.get("has_snapshot"):
            empty_reason = "no_project_inventory_snapshot"
        elif not asset:
            empty_reason = "no_matching_widget_blueprint"
        elif not widget_tree:
            empty_reason = "widget_tree_not_in_inventory_snapshot"
        elif not widget:
            empty_reason = "no_matching_widget"
        resolved_widget_name = self._widget_name(widget)
        resolved_widget_class = self._widget_class(widget)
        parent_widget_name = self._widget_parent(widget)
        return {
            "content": [
                {
                    "type": "text",
                    "text": self._widget_detail_text(
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
                "slot": self._widget_slot(widget),
                "layout": self._widget_layout(widget),
                "properties": self._widget_properties(widget),
                "style": self._widget_style(widget),
                "children": children[:64],
                "widget_tree_summary": {
                    "widget_count": len(widgets),
                    "root_widget_name": _first_text(widget_tree.get("root"), widget_tree.get("root_widget")),
                },
                "summary": summary,
                "empty_reason": empty_reason,
            },
        }

    def _find_widget_blueprint(self, *, project_id: str | None, widget_query: str) -> dict[str, Any] | None:
        asset = self.inventory.get_asset(widget_query, project_id) if widget_query else None
        if asset:
            return asset
        matches = self.inventory.list_assets(
            project_id=project_id,
            query=widget_query or None,
            asset_type="WidgetBlueprint",
            limit=1,
        )
        return matches[0] if matches else None

    @staticmethod
    def _extract_widget_tree(
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

    @classmethod
    def _flatten_widgets(cls, widget_tree: dict[str, Any]) -> list[dict[str, Any]]:
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
                if parent_name and not cls._widget_parent(item):
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

    @classmethod
    def _find_widget(cls, widgets: list[dict[str, Any]], widget_name: str) -> dict[str, Any]:
        query = cls._norm(widget_name)
        if not query:
            return widgets[0] if widgets else {}
        for widget in widgets:
            if any(cls._norm(value) == query for value in cls._widget_identity_values(widget)):
                return widget
        for widget in widgets:
            if any(query in cls._norm(value) for value in cls._widget_identity_values(widget)):
                return widget
        return {}

    @staticmethod
    def _widget_identity_values(widget: dict[str, Any]) -> list[str]:
        return [
            _first_text(widget.get("name")),
            _first_text(widget.get("widget_name")),
            _first_text(widget.get("id")),
            _first_text(widget.get("display_name")),
            _first_text(widget.get("object_name")),
        ]

    @staticmethod
    def _norm(value: Any) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _widget_name(widget: dict[str, Any]) -> str:
        return _first_text(
            widget.get("name"),
            widget.get("widget_name"),
            widget.get("id"),
            widget.get("display_name"),
            widget.get("object_name"),
        )

    @staticmethod
    def _widget_class(widget: dict[str, Any]) -> str:
        return _first_text(widget.get("class"), widget.get("widget_class"), widget.get("type"))

    @staticmethod
    def _widget_parent(widget: dict[str, Any]) -> str:
        return _first_text(
            widget.get("parent"),
            widget.get("parent_name"),
            widget.get("parent_widget"),
            widget.get("parent_widget_name"),
            _as_dict(widget.get("slot")).get("parent"),
            _as_dict(widget.get("slot")).get("parent_widget_name"),
        )

    @classmethod
    def _widget_children(cls, widgets: list[dict[str, Any]], widget: dict[str, Any]) -> list[dict[str, Any]]:
        widget_name = cls._norm(cls._widget_name(widget))
        if not widget_name:
            return []
        children: list[dict[str, Any]] = []
        for item in widgets:
            parent_name = cls._norm(cls._widget_parent(item))
            if parent_name == widget_name:
                children.append(
                    {
                        "widget_name": cls._widget_name(item),
                        "widget_class": cls._widget_class(item),
                    }
                )
        return children

    @staticmethod
    def _widget_slot(widget: dict[str, Any]) -> dict[str, Any]:
        return dict(_as_dict(widget.get("slot") or widget.get("slot_data") or widget.get("layout_slot")))

    @staticmethod
    def _widget_layout(widget: dict[str, Any]) -> dict[str, Any]:
        layout = dict(_as_dict(widget.get("layout") or widget.get("layout_data")))
        for key in ("position", "size", "anchors", "alignment", "padding", "offsets"):
            if key in widget and key not in layout:
                layout[key] = widget[key]
        return layout

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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

    def _call_inspect_assets(self, spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
        del spec
        project_id = _first_text(args.get("project_id")) or None
        items = self.inventory.list_assets(
            project_id=project_id,
            query=_first_text(args.get("query")) or None,
            asset_type=_first_text(args.get("asset_type")) or None,
            limit=_bounded_int(args.get("limit"), default=100, minimum=1, maximum=500),
        )
        summary = self._summary(project_id)
        return self._inspection_result(
            operation_type="inspect_assets",
            summary=summary,
            items=items,
            empty_reason="no_matching_assets",
            extra={"asset_type": _first_text(args.get("asset_type")), "query": _first_text(args.get("query"))},
        )

    def _call_inspect_asset_detail(self, spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
        del spec
        project_id = _first_text(args.get("project_id")) or None
        lookup = _first_text(args.get("asset_id"), args.get("asset_path"), args.get("query"))
        item = self.inventory.get_asset(lookup, project_id) if lookup else None
        if not item and args.get("query"):
            matches = self.inventory.list_assets(project_id=project_id, query=_first_text(args.get("query")), limit=1)
            item = matches[0] if matches else None
        return self._detail_result(
            operation_type="inspect_asset_detail",
            summary=self._summary(project_id),
            item=item,
            empty_reason="no_matching_asset",
            extra={"asset_id": _first_text(args.get("asset_id")), "asset_path": _first_text(args.get("asset_path"))},
        )

    def _call_inspect_level_actors(self, spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
        del spec
        project_id = _first_text(args.get("project_id")) or None
        items = self.inventory.list_level_actors(
            project_id=project_id,
            query=_first_text(args.get("query")) or None,
            level_name=_first_text(args.get("level_name")) or None,
            limit=_bounded_int(args.get("limit"), default=100, minimum=1, maximum=500),
        )
        return self._inspection_result(
            operation_type="inspect_level_actors",
            summary=self._summary(project_id),
            items=items,
            empty_reason="no_matching_level_actors",
            extra={"level_name": _first_text(args.get("level_name")), "query": _first_text(args.get("query"))},
        )

    def _call_inspect_level_actor_detail(self, spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
        del spec
        project_id = _first_text(args.get("project_id")) or None
        lookup = _first_text(args.get("actor_reference"), args.get("query"))
        item = self.inventory.get_level_actor(lookup, project_id) if lookup else None
        if not item and args.get("query"):
            matches = self.inventory.list_level_actors(project_id=project_id, query=_first_text(args.get("query")), limit=1)
            item = matches[0] if matches else None
        return self._detail_result(
            operation_type="inspect_level_actor_detail",
            summary=self._summary(project_id),
            item=item,
            empty_reason="no_matching_level_actor",
            extra={"actor_reference": _first_text(args.get("actor_reference")), "query": _first_text(args.get("query"))},
        )

    def _call_inspect_material_instance_parameters(self, spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
        del spec
        project_id = _first_text(args.get("project_id")) or None
        query = _first_text(args.get("material_instance_path"), args.get("query"))
        items = self.inventory.list_material_instances(
            project_id=project_id,
            query=query or None,
            parent_material=_first_text(args.get("parent_material")) or None,
            limit=_bounded_int(args.get("limit"), default=100, minimum=1, maximum=500),
        )
        return self._inspection_result(
            operation_type="inspect_material_instance_parameters",
            summary=self._summary(project_id),
            items=items,
            empty_reason="no_matching_material_instances",
            extra={
                "material_instance_path": _first_text(args.get("material_instance_path")),
                "parent_material": _first_text(args.get("parent_material")),
                "query": _first_text(args.get("query")),
            },
        )

    def _call_inspect_material_instance_detail(self, spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
        del spec
        project_id = _first_text(args.get("project_id")) or None
        lookup = _first_text(args.get("material_instance_path"), args.get("query"))
        item = self.inventory.get_material_instance(lookup, project_id) if lookup else None
        if not item and args.get("query"):
            matches = self.inventory.list_material_instances(
                project_id=project_id,
                query=_first_text(args.get("query")),
                limit=1,
            )
            item = matches[0] if matches else None
        return self._detail_result(
            operation_type="inspect_material_instance_detail",
            summary=self._summary(project_id),
            item=item,
            empty_reason="no_matching_material_instance",
            extra={
                "material_instance_path": _first_text(args.get("material_instance_path")),
                "query": _first_text(args.get("query")),
            },
        )

    @staticmethod
    def _empty_inventory_reason(summary: dict[str, Any], fallback: str) -> str:
        return "no_project_inventory_snapshot" if not summary.get("has_snapshot") else fallback

    def _inspection_result(
        self,
        *,
        operation_type: str,
        summary: dict[str, Any],
        items: list[dict[str, Any]],
        empty_reason: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reason = "" if items else self._empty_inventory_reason(summary, empty_reason)
        return {
            "inspection": {
                "operation_type": operation_type,
                "side_effect_level": "read_only",
                "source": "project_inventory",
                "match_count": len(items),
                "empty_reason": reason,
                **(extra or {}),
            },
            "summary": summary,
            "items": items,
        }

    def _detail_result(
        self,
        *,
        operation_type: str,
        summary: dict[str, Any],
        item: dict[str, Any] | None,
        empty_reason: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reason = "" if item else self._empty_inventory_reason(summary, empty_reason)
        return {
            "inspection": {
                "operation_type": operation_type,
                "side_effect_level": "read_only",
                "source": "project_inventory",
                "match_count": 1 if item else 0,
                "empty_reason": reason,
                **(extra or {}),
            },
            "summary": summary,
            "item": item or {},
        }

    @staticmethod
    def _blocked(
        *,
        tool_id: str | None = None,
        spec: ToolSpec | None = None,
        reason: str,
        message: str,
    ) -> dict[str, Any]:
        resolved_tool_id = spec.tool_id if spec else str(tool_id or "").strip()
        return {
            "ok": False,
            "status": "blocked",
            "reason": reason,
            "message": message,
            "protocol_version": TOOL_REGISTRY_READONLY_CALL_VERSION,
            "tool_id": resolved_tool_id,
            "tool_name": _stable_tool_name(spec) if spec else resolved_tool_id,
            "side_effect_level": spec.side_effect_level if spec else "",
            "transport": "local_tool_registry",
            "result": {},
            "errors": [
                {
                    "code": reason,
                    "message": message,
                    "details": {
                        "tool_id": resolved_tool_id,
                        "side_effect_level": spec.side_effect_level if spec else "",
                    },
                }
            ],
        }
