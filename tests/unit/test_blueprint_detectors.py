from __future__ import annotations

from app.services.editor_operations.blueprint_detectors import (
    active_graph_name_from_payload_context,
    detect_blueprint_entry_event_for_request,
    detect_blueprint_graph_name_for_request,
    query_mentions_blueprint_graph_target,
)


def test_blueprint_detector_uses_active_graph_when_query_is_implicit() -> None:
    graph_name = detect_blueprint_graph_name_for_request(
        {},
        {"current_graph_name": "ConstructionScript"},
        'Add "Ready" Print String node to the current Blueprint',
    )

    assert graph_name == "ConstructionScript"


def test_blueprint_detector_keeps_explicit_eventgraph_over_active_graph() -> None:
    graph_name = detect_blueprint_graph_name_for_request(
        {"graph_name": "EventGraph"},
        {"current_graph_name": "ConstructionScript"},
        'Add "Ready" Print String node in EventGraph',
    )
    entry_event = detect_blueprint_entry_event_for_request(
        {"graph_name": "EventGraph"},
        {"current_graph_name": "ConstructionScript"},
        'Add "Ready" Print String node in EventGraph',
        default="BeginPlay",
    )

    assert graph_name == "EventGraph"
    assert entry_event == "BeginPlay"


def test_blueprint_detector_clears_default_entry_event_for_active_construction_script() -> None:
    entry_event = detect_blueprint_entry_event_for_request(
        {},
        {"current_graph_name": "ConstructionScript"},
        'Add "Ready" Print String node to the current Blueprint',
        default="BeginPlay",
    )

    assert entry_event == ""


def test_blueprint_detector_reads_payload_active_graph_before_editor_state() -> None:
    assert (
        active_graph_name_from_payload_context(
            {"current_graph_name": "EventGraph"},
            {"current_graph_name": "ConstructionScript"},
        )
        == "EventGraph"
    )


def test_blueprint_detector_recognizes_explicit_graph_mentions() -> None:
    assert query_mentions_blueprint_graph_target("Use EventGraph")
    assert query_mentions_blueprint_graph_target("Use Construction Script")
    assert not query_mentions_blueprint_graph_target("Use the current Blueprint")
