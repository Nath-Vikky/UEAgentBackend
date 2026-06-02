from __future__ import annotations

import re
from typing import Any

BLUEPRINT_GRAPH_POLICY_SCHEMA_VERSION = "blueprint_graph_policy_v1"

_DEFAULT_GRAPH_NAME = "EventGraph"
_CONSTRUCTION_GRAPH_NAME = "ConstructionScript"

_TEMPLATE_CAPABILITIES: dict[str, dict[str, Any]] = {
    "branch_print_string": {
        "connects_exec_pins": True,
        "default_entry_event": "BeginPlay",
        "needs_entry_event_on_event_graph": True,
        "creates_multiple_nodes": True,
    },
    "call_function": {
        "connects_exec_pins": True,
        "default_entry_event": "BeginPlay",
        "needs_entry_event_on_event_graph": True,
        "creates_multiple_nodes": False,
    },
    "custom_event_print_string": {
        "connects_exec_pins": True,
        "default_entry_event": "",
        "needs_entry_event_on_event_graph": False,
        "creates_multiple_nodes": True,
    },
    "delay_print_string": {
        "connects_exec_pins": True,
        "default_entry_event": "BeginPlay",
        "needs_entry_event_on_event_graph": True,
        "creates_multiple_nodes": True,
    },
    "enhanced_input_action_event": {
        "connects_exec_pins": False,
        "default_entry_event": "",
        "needs_entry_event_on_event_graph": False,
        "creates_multiple_nodes": False,
    },
    "enhanced_input_print_string": {
        "connects_exec_pins": True,
        "default_entry_event": "",
        "needs_entry_event_on_event_graph": False,
        "creates_multiple_nodes": True,
    },
    "get_variable": {
        "connects_exec_pins": False,
        "default_entry_event": "",
        "needs_entry_event_on_event_graph": False,
        "creates_multiple_nodes": False,
    },
    "print_string": {
        "connects_exec_pins": True,
        "default_entry_event": "BeginPlay",
        "needs_entry_event_on_event_graph": True,
        "creates_multiple_nodes": False,
    },
    "sequence_print_strings": {
        "connects_exec_pins": True,
        "default_entry_event": "BeginPlay",
        "needs_entry_event_on_event_graph": True,
        "creates_multiple_nodes": True,
    },
    "set_variable": {
        "connects_exec_pins": True,
        "default_entry_event": "BeginPlay",
        "needs_entry_event_on_event_graph": True,
        "creates_multiple_nodes": False,
    },
}


def _query_parts(query_text: str) -> tuple[str, str]:
    query_lower = str(query_text or "").lower()
    compact = query_lower.replace("_", "").replace("-", "").replace(" ", "")
    return query_lower, compact


def _contains_any(query_text: str, query_lower: str, compact: str, tokens: tuple[str, ...]) -> bool:
    return any(token in query_text or token in query_lower or token in compact for token in tokens)


def blueprint_template_capability(template_id: Any) -> dict[str, Any]:
    """Return display-safe execution expectations for a Blueprint node template."""

    normalized = str(template_id or "").strip().replace("-", "_").replace(" ", "_").lower()
    capability = dict(_TEMPLATE_CAPABILITIES.get(normalized) or {})
    if not capability:
        capability = {
            "connects_exec_pins": False,
            "default_entry_event": "",
            "needs_entry_event_on_event_graph": False,
            "creates_multiple_nodes": False,
        }
    capability["template_id"] = normalized
    return capability


def detect_unconnected_blueprint_node_intent(query_text: str) -> bool:
    query_lower, compact = _query_parts(query_text)
    return _contains_any(
        query_text,
        query_lower,
        compact,
        (
            "unconnected",
            "unlinked",
            "standalone",
            "withoutconnection",
            "donotconnect",
            "dontconnect",
            "nolink",
            "noconnection",
            "\u4e0d\u8fde\u63a5",
            "\u4e0d\u8fde\u7ebf",
            "\u4e0d\u8981\u8fde",
            "\u53ea\u521b\u5efa",
            "\u4ec5\u521b\u5efa",
            "\u5b64\u7acb",
        ),
    )


def detect_blueprint_graph_name(payload: dict[str, Any] | None, query_text: str) -> tuple[str, str, float]:
    payload = payload or {}
    explicit_graph = str(payload.get("graph_name") or "").strip()
    if explicit_graph:
        return explicit_graph, "payload.graph_name", 1.0

    query_lower, compact = _query_parts(query_text)
    if _contains_any(
        query_text,
        query_lower,
        compact,
        (
            "constructionscript",
            "userconstructionscript",
            "construction script",
            "\u6784\u9020\u811a\u672c",
            "\u6784\u5efa\u811a\u672c",
        ),
    ):
        return _CONSTRUCTION_GRAPH_NAME, "query_mentions_construction_script", 0.96
    if _contains_any(
        query_text,
        query_lower,
        compact,
        (
            "eventgraph",
            "event graph",
            "\u4e8b\u4ef6\u56fe\u8868",
            "\u4e8b\u4ef6\u56fe",
            "\u84dd\u56fe\u4e8b\u4ef6\u56fe",
        ),
    ):
        return _DEFAULT_GRAPH_NAME, "query_mentions_event_graph", 0.94

    for pattern in (
        r"(?:graph)\s*[:=]?\s*([A-Za-z][A-Za-z0-9_]{1,63})",
        r"\b([A-Za-z][A-Za-z0-9_]{1,63})\s+(?:graph)\b",
    ):
        match = re.search(pattern, query_text, flags=re.IGNORECASE)
        if match:
            graph_name = match.group(1)
            if graph_name.lower() not in {"blueprint", "event", "node"}:
                return graph_name, "query_graph_name_pattern", 0.84

    return _DEFAULT_GRAPH_NAME, "default_event_graph", 0.55


def detect_blueprint_entry_event(
    payload: dict[str, Any] | None,
    query_text: str,
    *,
    default: str = "",
    graph_name: str = _DEFAULT_GRAPH_NAME,
) -> tuple[str, str, float]:
    payload = payload or {}
    explicit_event = str(payload.get("entry_event") or "").strip()
    if explicit_event:
        return explicit_event, "payload.entry_event", 1.0

    query_lower, compact = _query_parts(query_text)
    if _contains_any(
        query_text,
        query_lower,
        compact,
        (
            "actorbeginoverlap",
            "beginoverlap",
            "begin overlap",
            "overlapbegin",
            "\u5f00\u59cb\u91cd\u53e0",
            "\u8fdb\u5165\u91cd\u53e0",
            "\u5f00\u59cb\u78b0\u649e",
        ),
    ):
        return "ActorBeginOverlap", "query_mentions_begin_overlap", 0.94
    if _contains_any(
        query_text,
        query_lower,
        compact,
        (
            "actorendoverlap",
            "endoverlap",
            "end overlap",
            "overlapend",
            "\u7ed3\u675f\u91cd\u53e0",
            "\u79bb\u5f00\u91cd\u53e0",
            "\u7ed3\u675f\u78b0\u649e",
        ),
    ):
        return "ActorEndOverlap", "query_mentions_end_overlap", 0.94
    if _contains_any(
        query_text,
        query_lower,
        compact,
        (
            "beginplay",
            "eventbeginplay",
            "event begin play",
            "receivebeginplay",
            "\u5f00\u59cb\u64ad\u653e",
            "\u5f00\u59cb\u8fd0\u884c",
        ),
    ):
        return "BeginPlay", "query_mentions_begin_play", 0.96
    if graph_name != _DEFAULT_GRAPH_NAME:
        return "", "non_event_graph_has_no_entry_event", 0.88
    if default:
        return default, "default_entry_event", 0.62
    return "", "no_entry_event_requested", 0.5


def detect_blueprint_graph_target(
    payload: dict[str, Any] | None,
    query_text: str,
    *,
    default_entry_event: str = "",
) -> dict[str, Any]:
    payload = payload or {}
    graph_name, graph_reason, graph_confidence = detect_blueprint_graph_name(payload, query_text)
    entry_event, entry_reason, entry_confidence = detect_blueprint_entry_event(
        payload,
        query_text,
        default=default_entry_event,
        graph_name=graph_name,
    )
    unconnected = detect_unconnected_blueprint_node_intent(query_text)
    if unconnected and not str(payload.get("entry_event") or "").strip():
        entry_event = ""
        entry_reason = "query_requests_unconnected_node"
        entry_confidence = 0.95

    return {
        "schema_version": BLUEPRINT_GRAPH_POLICY_SCHEMA_VERSION,
        "graph_name": graph_name,
        "entry_event": entry_event,
        "unconnected": unconnected,
        "confidence": round(min(graph_confidence, entry_confidence), 3),
        "selection_reasons": {
            "graph_name": graph_reason,
            "entry_event": entry_reason,
        },
    }


def build_blueprint_graph_policy_preview(payload: dict[str, Any], query_text: str = "") -> dict[str, Any]:
    capability = blueprint_template_capability(payload.get("template_id"))
    target = detect_blueprint_graph_target(
        payload,
        query_text,
        default_entry_event=str(capability.get("default_entry_event") or ""),
    )
    graph_name = str(payload.get("graph_name") or target["graph_name"])
    entry_event = str(payload.get("entry_event") or target["entry_event"])
    warnings: list[str] = []
    if graph_name != _DEFAULT_GRAPH_NAME and entry_event:
        warnings.append("entry_event_on_non_event_graph")
    if capability["needs_entry_event_on_event_graph"] and graph_name == _DEFAULT_GRAPH_NAME and not entry_event:
        warnings.append("event_graph_template_without_entry_event")
    if target["unconnected"]:
        warnings.append("query_requested_unconnected_node")

    return {
        "schema_version": BLUEPRINT_GRAPH_POLICY_SCHEMA_VERSION,
        "graph_name": graph_name,
        "entry_event": entry_event,
        "unconnected": target["unconnected"] or not bool(entry_event),
        "selection_reasons": target["selection_reasons"],
        "confidence": target["confidence"],
        "template_capability": capability,
        "expected_behavior": {
            "connects_exec_pins": bool(capability["connects_exec_pins"] and entry_event),
            "creates_multiple_nodes": bool(capability["creates_multiple_nodes"]),
            "compile_after_edit": bool(payload.get("compile_after_edit", True)),
            "requires_frontend_graph_validation": True,
        },
        "warnings": warnings,
    }
