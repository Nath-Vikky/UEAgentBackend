from __future__ import annotations

from app.agent.tool_permission import annotate_tool_plan_permissions, decide_tool_permission


def test_read_only_free_chat_tool_is_allowed() -> None:
    decision = decide_tool_permission("query_project_inventory", free_chat=True)

    assert decision["version"] == "tool_permission_v1"
    assert decision["status"] == "allow"
    assert decision["side_effect_level"] == "read_only"
    assert decision["safe_to_run_automatically"] is True
    assert decision["requires_user_confirmation"] is False


def test_write_tool_maps_to_proposal() -> None:
    decision = decide_tool_permission("editor_rename_asset", free_chat=False)

    assert decision["status"] == "proposal"
    assert decision["requires_user_confirmation"] is True
    assert decision["safe_to_run_automatically"] is False


def test_mcp_write_tool_still_maps_to_proposal() -> None:
    decision = decide_tool_permission(
        "editor_rename_asset",
        provider="mcp_tcp",
    )

    assert decision["status"] == "proposal"
    assert decision["reason"] == "mcp_write_tool_must_map_to_proposal"


def test_unregistered_tool_is_denied() -> None:
    decision = decide_tool_permission("unknown_tool")

    assert decision["status"] == "deny"
    assert decision["reason"] == "unregistered_tool"


def test_tool_plan_permission_summary_marks_safe_read_only_plan() -> None:
    plan = {
        "tool_calls": [
            {"tool_id": "query_project_inventory", "input": {"query": "assets"}},
            {"tool_id": "retrieve_project_knowledge", "input": {"query": "Actor lifecycle"}},
        ]
    }

    annotated = annotate_tool_plan_permissions(plan, free_chat=True)

    assert annotated["permission_summary"]["decision_count"] == 2
    assert annotated["permission_summary"]["all_safe_to_run"] is True
    assert {item["status"] for item in annotated["permission_decisions"]} == {"allow"}
