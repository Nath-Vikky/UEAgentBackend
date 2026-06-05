from __future__ import annotations

from typing import Any

from app.core.settings import Settings
from app.services.project_inventory_service import ProjectInventoryService
from app.tools.registry import ToolSpec, get_tool_spec, iter_tool_specs

TOOL_REGISTRY_PLAN_CALL_VERSION = "tool_registry_plan_call_v1"
LOCAL_PLAN_CALL_PATH = "POST /api/v1/mcp/tool-registry/plans/{tool}/call"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _stable_tool_name(spec: ToolSpec) -> str:
    return spec.mcp_tool_name if spec.transport.startswith("mcp") and spec.mcp_tool_name else spec.tool_id


class ToolRegistryPlanCallService:
    """Resolve plan-only ToolSpec calls into reusable planning context.

    Plan-only tools never write Unreal Editor state and never create proposals by
    themselves. They return a compact context patch that can be passed to later
    confirmed-write Proposal tools such as add_step, connect pins, or compile.
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
        if spec.side_effect_level != "plan_only":
            return self._blocked(
                spec=spec,
                reason="tool_is_not_plan_only",
                message="This endpoint only evaluates plan-only tools. Read-only tools use the local call endpoint; write tools create Proposals.",
            )

        handlers = {
            "editor_blueprint_set_edit_function": self._call_blueprint_set_edit_function,
            "editor_blueprint_set_cursor_node": self._call_blueprint_set_cursor_node,
            "editor_umg_set_widget_blueprint_context": self._call_umg_set_widget_blueprint_context,
            "editor_umg_set_cursor_widget": self._call_umg_set_cursor_widget,
        }
        handler = handlers.get(spec.tool_id)
        if not handler:
            return self._blocked(
                spec=spec,
                reason="local_plan_executor_missing",
                message="This plan-only tool is registered, but no local plan executor is available yet.",
            )

        result = handler(spec, args)
        return {
            "ok": True,
            "status": "completed",
            "reason": "local_plan_tool_completed",
            "protocol_version": TOOL_REGISTRY_PLAN_CALL_VERSION,
            "tool_id": spec.tool_id,
            "tool_name": _stable_tool_name(spec),
            "side_effect_level": spec.side_effect_level,
            "transport": "local_tool_registry",
            "source": "plan_only_context",
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

    def _call_blueprint_set_edit_function(self, spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
        del spec
        project_id = _first_text(args.get("project_id")) or None
        blueprint_path = _first_text(
            args.get("blueprint_path"),
            args.get("asset_path"),
            args.get("blueprint_query"),
        )
        graph_name = _first_text(
            args.get("graph_name"),
            args.get("function_name"),
            args.get("edit_function"),
        ) or "EventGraph"
        graph_type = _first_text(args.get("graph_type")) or "unknown"
        graph_match = self._first_graph(project_id=project_id, blueprint_query=blueprint_path, graph_name=graph_name)
        resolved_graph_name = _first_text(graph_match.get("graph_name"), graph_name)
        context_patch = {
            "blueprint_edit_context": {
                "blueprint_path": blueprint_path,
                "graph_name": resolved_graph_name,
                "edit_function": resolved_graph_name,
                "graph_type": _first_text(graph_match.get("graph_type"), graph_type),
                "source_tool_id": "editor_blueprint_set_edit_function",
                "matched_inventory_graph": bool(graph_match),
            }
        }
        return {
            "plan": {
                "status": "ready",
                "intent": "set_blueprint_edit_function",
                "side_effect_level": "plan_only",
                "message": f"Blueprint edit context set to {blueprint_path or 'current Blueprint'}::{resolved_graph_name}.",
            },
            "context_patch": context_patch,
            "normalized_arguments": {
                "project_id": project_id or "",
                "blueprint_path": blueprint_path,
                "graph_name": resolved_graph_name,
                "graph_type": graph_type,
            },
            "inventory_match": graph_match,
            "next_tool_hints": [
                {
                    "tool_id": "editor_blueprint_add_step",
                    "arguments": {
                        "blueprint_path": blueprint_path,
                        "graph_name": resolved_graph_name,
                    },
                },
                {
                    "tool_id": "editor_compile_blueprint",
                    "arguments": {"blueprint_path": blueprint_path},
                },
            ],
            "prompt_excerpt": (
                "Use blueprint_edit_context.blueprint_path and graph_name as defaults for subsequent "
                "Blueprint add/connect/compile Proposal tools."
            ),
        }

    def _call_blueprint_set_cursor_node(self, spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
        del spec
        project_id = _first_text(args.get("project_id")) or None
        blueprint_path = _first_text(
            args.get("blueprint_path"),
            args.get("asset_path"),
            args.get("blueprint_query"),
        )
        graph_name = _first_text(args.get("graph_name"), args.get("function_name")) or "EventGraph"
        node_query = _first_text(
            args.get("node_id"),
            args.get("node_name"),
            args.get("node_title"),
            args.get("cursor_node"),
        )
        graph_match = self._first_graph(project_id=project_id, blueprint_query=blueprint_path, graph_name=graph_name)
        node_match = self._find_node(graph_match, node_query)
        resolved_node_id = _first_text(node_match.get("node_id"), args.get("node_id"), node_query)
        resolved_node_title = _first_text(node_match.get("title"), node_match.get("node_title"), node_query)
        resolved_graph_name = _first_text(graph_match.get("graph_name"), graph_name)
        context_patch = {
            "blueprint_edit_context": {
                "blueprint_path": blueprint_path,
                "graph_name": resolved_graph_name,
                "cursor_node": {
                    "node_id": resolved_node_id,
                    "title": resolved_node_title,
                    "pins": _as_list(node_match.get("pins"))[:24],
                    "source_tool_id": "editor_blueprint_set_cursor_node",
                    "matched_inventory_node": bool(node_match),
                },
            }
        }
        return {
            "plan": {
                "status": "ready" if resolved_node_id else "needs_node_identifier",
                "intent": "set_blueprint_cursor_node",
                "side_effect_level": "plan_only",
                "message": (
                    f"Blueprint cursor node set to {resolved_node_title or resolved_node_id} "
                    f"in {blueprint_path or 'current Blueprint'}::{resolved_graph_name}."
                    if resolved_node_id
                    else "No cursor node identifier was provided or found in inventory."
                ),
            },
            "context_patch": context_patch,
            "normalized_arguments": {
                "project_id": project_id or "",
                "blueprint_path": blueprint_path,
                "graph_name": resolved_graph_name,
                "node_query": node_query,
                "node_id": resolved_node_id,
            },
            "inventory_match": {
                "graph": graph_match,
                "node": node_match,
            },
            "next_tool_hints": [
                {
                    "tool_id": "editor_connect_blueprint_nodes",
                    "arguments": {
                        "blueprint_path": blueprint_path,
                        "graph_name": resolved_graph_name,
                        "source_node_id": resolved_node_id,
                        "source_pin_name": "then",
                    },
                },
                {
                    "tool_id": "editor_blueprint_add_step",
                    "arguments": {
                        "blueprint_path": blueprint_path,
                        "graph_name": resolved_graph_name,
                    },
                },
            ],
            "prompt_excerpt": (
                "Use blueprint_edit_context.cursor_node as the default source/target node when building "
                "a connect_blueprint_nodes Proposal."
            ),
        }

    def _first_graph(self, *, project_id: str | None, blueprint_query: str, graph_name: str) -> dict[str, Any]:
        graphs = self.inventory.list_blueprint_graphs(
            project_id=project_id,
            blueprint_query=blueprint_query or None,
            graph_name=graph_name or None,
            include_nodes=True,
            limit=1,
        )
        return graphs[0] if graphs else {}

    def _call_umg_set_widget_blueprint_context(self, spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
        del spec
        project_id = _first_text(args.get("project_id")) or None
        widget_query = _first_text(
            args.get("widget_blueprint_path"),
            args.get("blueprint_path"),
            args.get("asset_path"),
            args.get("query"),
        )
        asset = self._find_widget_blueprint(project_id=project_id, widget_query=widget_query)
        widget_tree = self._widget_tree_for_asset(asset)
        widgets = self._widgets_from_tree(widget_tree)
        root_widget_name = _first_text(
            args.get("root_widget_name"),
            widget_tree.get("root"),
            widget_tree.get("root_widget_name"),
            self._first_widget_name(widgets),
        )
        resolved_path = _first_text(widget_query, asset.get("asset_path") if asset else "")
        context_patch = {
            "umg_edit_context": {
                "widget_blueprint_path": resolved_path,
                "widget_blueprint_name": _first_text(asset.get("asset_name") if asset else "", resolved_path),
                "root_widget_name": root_widget_name,
                "widget_count": len(widgets),
                "source_tool_id": "editor_umg_set_widget_blueprint_context",
                "matched_inventory_widget_tree": bool(asset and widget_tree),
            }
        }
        return {
            "plan": {
                "status": "ready" if resolved_path else "needs_widget_blueprint_path",
                "intent": "set_umg_widget_blueprint_context",
                "side_effect_level": "plan_only",
                "message": (
                    f"UMG edit context set to {resolved_path}; root={root_widget_name or 'unknown'}."
                    if resolved_path
                    else "No Widget Blueprint path was provided or found in inventory."
                ),
            },
            "context_patch": context_patch,
            "normalized_arguments": {
                "project_id": project_id or "",
                "widget_blueprint_path": resolved_path,
                "root_widget_name": root_widget_name,
            },
            "inventory_match": {
                "asset": self._asset_preview(asset),
                "widget_tree": widget_tree,
            },
            "next_tool_hints": [
                {
                    "tool_id": "editor_add_umg_widget",
                    "arguments": {
                        "widget_blueprint_path": resolved_path,
                        "parent_widget_name": root_widget_name,
                    },
                },
                {
                    "tool_id": "editor_set_umg_widget_text",
                    "arguments": {"widget_blueprint_path": resolved_path},
                },
            ],
            "prompt_excerpt": (
                "Use umg_edit_context.widget_blueprint_path and root_widget_name as defaults for subsequent "
                "UMG add/set/reparent/duplicate/delete Proposal tools."
            ),
        }

    def _call_umg_set_cursor_widget(self, spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
        del spec
        project_id = _first_text(args.get("project_id")) or None
        widget_query = _first_text(
            args.get("widget_blueprint_path"),
            args.get("blueprint_path"),
            args.get("asset_path"),
            args.get("query"),
        )
        cursor_query = _first_text(
            args.get("widget_name"),
            args.get("cursor_widget"),
            args.get("target_widget"),
        )
        asset = self._find_widget_blueprint(project_id=project_id, widget_query=widget_query)
        widget_tree = self._widget_tree_for_asset(asset)
        widgets = self._widgets_from_tree(widget_tree)
        widget_match = self._find_widget(widgets, cursor_query)
        root_widget_name = _first_text(widget_tree.get("root"), widget_tree.get("root_widget_name"), self._first_widget_name(widgets))
        resolved_path = _first_text(widget_query, asset.get("asset_path") if asset else "")
        cursor_widget = self._widget_projection(widget_match)
        if cursor_widget:
            cursor_widget["source_tool_id"] = "editor_umg_set_cursor_widget"
            cursor_widget["matched_inventory_widget"] = True
        elif cursor_query:
            cursor_widget = {
                "widget_name": cursor_query,
                "widget_class": "",
                "parent_widget_name": "",
                "source_tool_id": "editor_umg_set_cursor_widget",
                "matched_inventory_widget": False,
            }
        context_patch = {
            "umg_edit_context": {
                "widget_blueprint_path": resolved_path,
                "widget_blueprint_name": _first_text(asset.get("asset_name") if asset else "", resolved_path),
                "root_widget_name": root_widget_name,
                "cursor_widget": cursor_widget,
                "widget_count": len(widgets),
                "source_tool_id": "editor_umg_set_cursor_widget",
                "matched_inventory_widget_tree": bool(asset and widget_tree),
            }
        }
        resolved_widget_name = _first_text(cursor_widget.get("widget_name") if cursor_widget else "", cursor_query)
        return {
            "plan": {
                "status": "ready" if resolved_path and resolved_widget_name else "needs_widget_identifier",
                "intent": "set_umg_cursor_widget",
                "side_effect_level": "plan_only",
                "message": (
                    f"UMG cursor widget set to {resolved_widget_name} in {resolved_path}."
                    if resolved_widget_name
                    else "No widget identifier was provided or found in inventory."
                ),
            },
            "context_patch": context_patch,
            "normalized_arguments": {
                "project_id": project_id or "",
                "widget_blueprint_path": resolved_path,
                "widget_query": cursor_query,
                "widget_name": resolved_widget_name,
            },
            "inventory_match": {
                "asset": self._asset_preview(asset),
                "widget": widget_match,
            },
            "next_tool_hints": [
                {
                    "tool_id": "editor_set_umg_widget_text",
                    "arguments": {
                        "widget_blueprint_path": resolved_path,
                        "widget_name": resolved_widget_name,
                    },
                },
                {
                    "tool_id": "editor_set_umg_widget_layout",
                    "arguments": {
                        "widget_blueprint_path": resolved_path,
                        "widget_name": resolved_widget_name,
                    },
                },
                {
                    "tool_id": "editor_add_umg_widget",
                    "arguments": {
                        "widget_blueprint_path": resolved_path,
                        "parent_widget_name": resolved_widget_name,
                    },
                },
            ],
            "prompt_excerpt": (
                "Use umg_edit_context.cursor_widget as the default widget target for UMG set/layout/visibility "
                "Proposal tools, or as the parent for adding a child widget."
            ),
        }

    def _find_widget_blueprint(self, *, project_id: str | None, widget_query: str) -> dict[str, Any]:
        asset = self.inventory.get_asset(widget_query, project_id) if widget_query else None
        if asset:
            return asset
        matches = self.inventory.list_assets(
            project_id=project_id,
            query=widget_query or None,
            asset_type="WidgetBlueprint",
            limit=1,
        )
        return matches[0] if matches else {}

    @staticmethod
    def _widget_tree_for_asset(asset: dict[str, Any]) -> dict[str, Any]:
        if not asset:
            return {}
        blueprint = _as_dict(asset.get("blueprint"))
        properties = _as_dict(asset.get("properties"))
        metadata = _as_dict(asset.get("metadata"))
        for source in (blueprint, properties, metadata, asset):
            for key in ("widget_tree", "widgets", "designer_tree", "hierarchy"):
                value = source.get(key)
                if isinstance(value, dict):
                    return value
                if isinstance(value, list):
                    return {"widgets": value}
        return {}

    @staticmethod
    def _widgets_from_tree(widget_tree: dict[str, Any]) -> list[Any]:
        return _as_list(widget_tree.get("widgets") or widget_tree.get("children") or widget_tree.get("nodes"))

    @staticmethod
    def _first_widget_name(widgets: list[Any]) -> str:
        for widget in widgets:
            if not isinstance(widget, dict):
                continue
            name = _first_text(widget.get("name"), widget.get("widget_name"), widget.get("id"))
            if name:
                return name
        return ""

    @staticmethod
    def _find_widget(widgets: list[Any], widget_query: str) -> dict[str, Any]:
        if not widget_query:
            return {}
        normalized_query = _normalize_lookup(widget_query)
        for widget in widgets:
            if not isinstance(widget, dict):
                continue
            candidates = (
                widget.get("name"),
                widget.get("widget_name"),
                widget.get("id"),
                widget.get("display_name"),
            )
            if any(_normalize_lookup(value) == normalized_query for value in candidates):
                return dict(widget)
        for widget in widgets:
            if not isinstance(widget, dict):
                continue
            label = _normalize_lookup(_first_text(widget.get("name"), widget.get("widget_name"), widget.get("display_name")))
            if normalized_query and normalized_query in label:
                return dict(widget)
        return {}

    @staticmethod
    def _widget_projection(widget: dict[str, Any]) -> dict[str, Any]:
        if not widget:
            return {}
        return {
            "widget_name": _first_text(widget.get("name"), widget.get("widget_name"), widget.get("id")),
            "widget_class": _first_text(widget.get("class"), widget.get("widget_class"), widget.get("type")),
            "parent_widget_name": _first_text(widget.get("parent"), widget.get("parent_name"), widget.get("parent_widget_name")),
            "is_variable": widget.get("is_variable"),
            "slot": _as_dict(widget.get("slot")),
            "layout": _as_dict(widget.get("layout")),
        }

    @staticmethod
    def _asset_preview(asset: dict[str, Any]) -> dict[str, Any]:
        if not asset:
            return {}
        return {
            "asset_path": asset.get("asset_path"),
            "asset_name": asset.get("asset_name"),
            "asset_type": asset.get("asset_type"),
            "package_path": asset.get("package_path"),
        }

    @staticmethod
    def _find_node(graph: dict[str, Any], node_query: str) -> dict[str, Any]:
        if not graph or not node_query:
            return {}
        normalized_query = _normalize_lookup(node_query)
        for node in _as_list(graph.get("nodes")):
            if not isinstance(node, dict):
                continue
            candidates = (
                node.get("node_id"),
                node.get("id"),
                node.get("name"),
                node.get("title"),
                node.get("node_title"),
            )
            if any(_normalize_lookup(value) == normalized_query for value in candidates):
                return dict(node)
        for node in _as_list(graph.get("nodes")):
            if not isinstance(node, dict):
                continue
            title = _normalize_lookup(_first_text(node.get("title"), node.get("node_title"), node.get("name")))
            if normalized_query and normalized_query in title:
                return dict(node)
        return {}

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
            "protocol_version": TOOL_REGISTRY_PLAN_CALL_VERSION,
            "tool_id": resolved_tool_id,
            "tool_name": _stable_tool_name(spec) if spec else resolved_tool_id,
            "side_effect_level": spec.side_effect_level if spec else "",
            "transport": "local_tool_registry",
            "source": "plan_only_context",
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


def _normalize_lookup(value: Any) -> str:
    return " ".join(str(value or "").replace("_", " ").replace("-", " ").strip().lower().split())
