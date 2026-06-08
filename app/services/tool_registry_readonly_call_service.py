from __future__ import annotations

from typing import Any

from app.core.settings import Settings
from app.services.project_inventory_service import ProjectInventoryService
from app.services.tool_registry_readonly.blueprint import build_blueprint_node_detail_result
from app.services.tool_registry_readonly.umg import (
    build_umg_widget_detail_result,
    extract_widget_tree,
    find_widget_blueprint,
)
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
            "mcp_get_blueprint_node_details": self._call_inspect_blueprint_node_detail,
            "editor_inspect_blueprint_node_detail": self._call_inspect_blueprint_node_detail,
            "mcp_get_widget_tree": self._call_widget_tree,
            "mcp_get_umg_widget_details": self._call_inspect_umg_widget_detail,
            "mcp_get_material_instance_parameters": self._call_inspect_material_instance_parameters,
            "mcp_get_material_parameter_details": self._call_inspect_material_parameter_detail,
            "mcp_get_level_actors": self._call_inspect_level_actors,
            "mcp_get_level_actor_details": self._call_inspect_level_actor_detail,
            "mcp_get_asset_details": self._call_inspect_asset_detail,
            "mcp_get_static_mesh_details": self._call_static_mesh_details,
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
        return build_blueprint_node_detail_result(
            inventory=self.inventory,
            summary=self._summary(project_id),
            project_id=project_id,
            args=args,
        )

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
        asset = find_widget_blueprint(inventory=self.inventory, project_id=project_id, widget_query=widget_query)
        blueprint = _as_dict(asset.get("blueprint") if asset else {})
        properties = _as_dict(asset.get("properties") if asset else {})
        metadata = _as_dict(asset.get("metadata") if asset else {})
        widget_tree = extract_widget_tree(blueprint=blueprint, properties=properties, metadata=metadata)
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
        return build_umg_widget_detail_result(
            inventory=self.inventory,
            summary=self._summary(project_id),
            project_id=project_id,
            args=args,
        )

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

    def _call_static_mesh_details(self, spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
        del spec
        project_id = _first_text(args.get("project_id")) or None
        lookup = _first_text(args.get("static_mesh_path"), args.get("asset_path"), args.get("query"))
        item = self.inventory.get_asset(lookup, project_id) if lookup else None
        if item and str(item.get("asset_type") or "").lower() != "staticmesh":
            item = None
        if not item and lookup:
            matches = self.inventory.list_assets(project_id=project_id, query=lookup, asset_type="StaticMesh", limit=1)
            item = matches[0] if matches else None
        return self._detail_result(
            operation_type="inspect_static_mesh_details",
            summary=self._summary(project_id),
            item=item,
            empty_reason="no_matching_static_mesh",
            extra={"static_mesh_path": _first_text(args.get("static_mesh_path")), "query": lookup},
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

    def _call_inspect_material_parameter_detail(self, spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
        del spec
        project_id = _first_text(args.get("project_id")) or None
        material_query = _first_text(args.get("material_instance_path"), args.get("asset_path"))
        parameter_query = _first_text(args.get("parameter_name"), args.get("target_parameter"), args.get("query"))
        parameter_type = _first_text(args.get("parameter_type"))
        material = self.inventory.get_material_instance(material_query, project_id) if material_query else None
        if not material and material_query:
            matches = self.inventory.list_material_instances(project_id=project_id, query=material_query, limit=1)
            material = matches[0] if matches else None
        parameter = self._find_material_parameter(material or {}, parameter_query, parameter_type)
        summary = self._summary(project_id)
        reason = "" if parameter else self._empty_inventory_reason(summary, "no_matching_material_parameter")
        return {
            "inspection": {
                "operation_type": "inspect_material_parameter_detail",
                "side_effect_level": "read_only",
                "source": "project_inventory",
                "match_count": 1 if parameter else 0,
                "empty_reason": reason,
                "material_instance_path": material_query,
                "parameter_name": parameter_query,
                "parameter_type": parameter_type,
            },
            "summary": summary,
            "material_instance": material or {},
            "parameter": parameter,
            "item": parameter or {},
        }

    @staticmethod
    def _material_parameters(material: dict[str, Any]) -> list[dict[str, Any]]:
        parameters: list[dict[str, Any]] = []
        for key in (
            "parameters",
            "scalar_parameters",
            "vector_parameters",
            "texture_parameters",
            "static_switch_parameters",
        ):
            for item in _as_list(material.get(key)):
                if isinstance(item, dict) and item not in parameters:
                    parameters.append(item)
        return parameters

    @classmethod
    def _find_material_parameter(
        cls,
        material: dict[str, Any],
        parameter_query: str,
        parameter_type: str,
    ) -> dict[str, Any] | None:
        needle = str(parameter_query or "").strip().lower()
        requested_type = str(parameter_type or "").strip().lower()
        if not needle:
            return None
        for parameter in cls._material_parameters(material):
            name = _first_text(parameter.get("parameter_name"), parameter.get("name")).lower()
            kind = _first_text(parameter.get("parameter_type"), parameter.get("type")).lower()
            if requested_type and kind != requested_type:
                continue
            if name == needle or needle in name:
                return parameter
        return None

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
