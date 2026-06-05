from __future__ import annotations

from typing import Any


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


def build_blueprint_node_detail_result(
    *,
    inventory: Any,
    summary: dict[str, Any],
    project_id: str | None,
    args: dict[str, Any],
) -> dict[str, Any]:
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
    graphs = inventory.list_blueprint_graphs(
        project_id=project_id,
        blueprint_query=blueprint_query or None,
        graph_name=graph_name,
        include_nodes=True,
        limit=50,
    )
    blueprints = inventory.list_blueprints(project_id=project_id, query=blueprint_query or None, limit=1)
    blueprint = blueprints[0] if blueprints else {}
    graph, node = _find_blueprint_graph_node(graphs, node_query)
    pins = _blueprint_node_pins(node)
    empty_reason = ""
    if not summary.get("has_snapshot"):
        empty_reason = "no_project_inventory_snapshot"
    elif not graphs:
        empty_reason = "no_matching_blueprint_graphs"
    elif not node:
        empty_reason = "no_matching_blueprint_node"
    node_title = _blueprint_node_title(node)
    node_id = _blueprint_node_id(node)
    return {
        "content": [
            {
                "type": "text",
                "text": _blueprint_node_detail_text(
                    blueprint_name=blueprint.get("asset_name") or blueprint_query,
                    graph_name=_first_text(graph.get("graph_name")),
                    node_title=node_title or node_query,
                    node_class=_blueprint_node_class(node),
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
            "node_class": _blueprint_node_class(node),
            "node": node,
            "pins": pins,
            "linked_pins": _blueprint_linked_pins(pins),
            "graph_summary": {
                "node_count": graph.get("node_count"),
                "pin_count": graph.get("pin_count"),
                "link_count": graph.get("link_count"),
            },
            "summary": summary,
            "empty_reason": empty_reason,
        },
    }


def _find_blueprint_graph_node(
    graphs: list[dict[str, Any]],
    node_query: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not graphs:
        return {}, {}
    query = _norm(node_query)
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
            if any(_norm(value) == query for value in _blueprint_node_identity_values(node)):
                return graph, node
        for node in nodes:
            if any(query in _norm(value) for value in _blueprint_node_identity_values(node)):
                return graph, node
    return first_graph, first_node if not query else {}


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


def _blueprint_node_id(node: dict[str, Any]) -> str:
    return _first_text(node.get("node_id"), node.get("id"), node.get("guid"), node.get("name"))


def _blueprint_node_title(node: dict[str, Any]) -> str:
    return _first_text(node.get("title"), node.get("node_title"), node.get("name"), node.get("node_id"))


def _blueprint_node_class(node: dict[str, Any]) -> str:
    return _first_text(node.get("node_class"), node.get("class"), node.get("type"), node.get("node_type"))


def _blueprint_node_pins(node: dict[str, Any]) -> list[dict[str, Any]]:
    pins: list[dict[str, Any]] = []
    for key, direction in (("pins", ""), ("input_pins", "input"), ("output_pins", "output")):
        for raw_pin in _as_list(node.get(key)):
            if not isinstance(raw_pin, dict):
                continue
            pin = dict(raw_pin)
            pin.setdefault("direction", direction or _first_text(raw_pin.get("direction"), raw_pin.get("pin_direction")))
            pin.setdefault("pin_name", _blueprint_pin_name(pin))
            pins.append(pin)
    return pins[:128]


def _blueprint_pin_name(pin: dict[str, Any]) -> str:
    return _first_text(pin.get("pin_name"), pin.get("name"), pin.get("display_name"), pin.get("id"))


def _blueprint_linked_pins(pins: list[dict[str, Any]]) -> list[dict[str, Any]]:
    linked: list[dict[str, Any]] = []
    for pin in pins:
        links = _as_list(pin.get("linked_to") or pin.get("links") or pin.get("connections"))
        for raw_link in links:
            if isinstance(raw_link, dict):
                linked.append(
                    {
                        "pin_name": _blueprint_pin_name(pin),
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
                        "pin_name": _blueprint_pin_name(pin),
                        "direction": _first_text(pin.get("direction"), pin.get("pin_direction")),
                        "target": str(raw_link),
                    }
                )
    return linked[:128]


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

