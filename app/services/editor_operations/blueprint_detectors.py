from __future__ import annotations

from typing import Any

from app.services.editor_operations.blueprint_graph_policy import (
    detect_blueprint_graph_target,
    detect_unconnected_blueprint_node_intent,
)


def query_mentions_blueprint_graph_target(query_text: str) -> bool:
    """Return whether the user explicitly named a Blueprint graph target."""

    query_lower = str(query_text or "").lower()
    compact = query_lower.replace("_", "").replace("-", "").replace(" ", "")
    return any(
        token in query_lower or token in compact
        for token in (
            "eventgraph",
            "event graph",
            "constructionscript",
            "construction script",
            "userconstructionscript",
        )
    )


def active_graph_name_from_payload_context(
    payload: dict[str, Any] | None,
    editor_state: dict[str, Any] | None,
) -> str:
    """Read the current editor graph focus from request payload/context."""

    payload = payload or {}
    editor_state = editor_state or {}
    payload_graph = str(payload.get("current_graph_name") or payload.get("active_graph_name") or "").strip()
    if payload_graph:
        return payload_graph
    return str(
        editor_state.get("current_graph_name")
        or editor_state.get("graph_name")
        or editor_state.get("active_graph_name")
        or ""
    ).strip()


def detect_blueprint_graph_name_for_request(
    payload: dict[str, Any] | None,
    editor_state: dict[str, Any] | None,
    query_text: str,
) -> str:
    """Resolve graph name while preserving explicit user intent over editor focus."""

    payload = payload or {}
    target = detect_blueprint_graph_target(payload, query_text)
    detected_graph = str(target["graph_name"])
    explicit_graph = str(payload.get("graph_name") or "").strip()
    active_graph = active_graph_name_from_payload_context(payload, editor_state)
    if explicit_graph:
        return detected_graph
    if active_graph and detected_graph == "EventGraph" and not query_mentions_blueprint_graph_target(query_text):
        return active_graph
    return detected_graph


def detect_blueprint_entry_event_for_request(
    payload: dict[str, Any] | None,
    editor_state: dict[str, Any] | None,
    query_text: str,
    *,
    default: str = "",
) -> str:
    """Resolve the entry event and clear default events for non-EventGraph targets."""

    payload = payload or {}
    explicit_event = str(payload.get("entry_event") or "").strip()
    target = detect_blueprint_graph_target(
        payload,
        query_text,
        default_entry_event=default,
    )
    entry_event = str(target["entry_event"])
    graph_name = detect_blueprint_graph_name_for_request(payload, editor_state, query_text)
    if graph_name != "EventGraph" and not explicit_event:
        return ""
    return entry_event


__all__ = [
    "active_graph_name_from_payload_context",
    "detect_blueprint_entry_event_for_request",
    "detect_blueprint_graph_name_for_request",
    "detect_unconnected_blueprint_node_intent",
    "query_mentions_blueprint_graph_target",
]
