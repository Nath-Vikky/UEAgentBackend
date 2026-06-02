from __future__ import annotations

from app.services.editor_operations.blueprint_graph_policy import (
    build_blueprint_graph_policy_preview,
    detect_blueprint_graph_target,
)


def test_detects_event_beginplay_from_chinese_request() -> None:
    target = detect_blueprint_graph_target(
        {},
        "\u7ed9 BP_TestActor \u7684 EventBeginPlay \u6dfb\u52a0\u4e00\u4e2a Print String \u8282\u70b9",
        default_entry_event="BeginPlay",
    )

    assert target["graph_name"] == "EventGraph"
    assert target["entry_event"] == "BeginPlay"
    assert target["selection_reasons"]["entry_event"] == "query_mentions_begin_play"


def test_construction_script_does_not_default_to_beginplay() -> None:
    target = detect_blueprint_graph_target(
        {},
        "Add Print String node to BP_TestActor ConstructionScript",
        default_entry_event="BeginPlay",
    )

    assert target["graph_name"] == "ConstructionScript"
    assert target["entry_event"] == ""
    assert target["selection_reasons"]["entry_event"] == "non_event_graph_has_no_entry_event"


def test_unconnected_request_clears_default_entry_event() -> None:
    target = detect_blueprint_graph_target(
        {},
        "Add an unconnected Print String node to BP_TestActor EventGraph",
        default_entry_event="BeginPlay",
    )

    assert target["graph_name"] == "EventGraph"
    assert target["entry_event"] == ""
    assert target["unconnected"] is True
    assert target["selection_reasons"]["entry_event"] == "query_requests_unconnected_node"


def test_policy_preview_explains_expected_connection_behavior() -> None:
    preview = build_blueprint_graph_policy_preview(
        {
            "template_id": "print_string",
            "graph_name": "EventGraph",
            "entry_event": "BeginPlay",
            "compile_after_edit": True,
        },
        "Add Print String node to BP_TestActor EventGraph",
    )

    assert preview["schema_version"] == "blueprint_graph_policy_v1"
    assert preview["expected_behavior"]["connects_exec_pins"] is True
    assert preview["template_capability"]["needs_entry_event_on_event_graph"] is True
    assert preview["warnings"] == []
