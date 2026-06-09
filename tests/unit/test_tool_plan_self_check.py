from __future__ import annotations

from app.agent.tool_plan_self_check import check_tool_plan_consistency


def test_tool_plan_self_check_accepts_readonly_detail_plan() -> None:
    report = check_tool_plan_consistency(
        intent_draft={"intent_type": "asset_question"},
        verified_intent={"selected_tool_id": "mcp_get_asset_details"},
        context_resolution={"status": "resolved", "target_kind": "selected_asset"},
        tool_plan={
            "mode": "read_only",
            "tool_id": "mcp_get_asset_details",
            "side_effect_level": "read_only",
            "requires_proposal": False,
        },
        routing={"intent": {"route_type": "single_tool"}},
    )

    assert report["version"] == "tool_plan_self_check_v1"
    assert report["status"] == "ok"
    assert report["failed_check_ids"] == []
    assert report["should_block_execution"] is False


def test_tool_plan_self_check_flags_write_tool_without_proposal() -> None:
    report = check_tool_plan_consistency(
        intent_draft={"intent_type": "asset_write"},
        verified_intent={"selected_tool_id": "editor_rename_asset"},
        context_resolution={"status": "resolved", "target_kind": "selected_asset"},
        tool_plan={
            "mode": "read_only",
            "tool_id": "editor_rename_asset",
            "side_effect_level": "confirmed_write",
            "requires_proposal": False,
        },
        routing={"intent": {"route_type": "single_tool"}},
    )

    assert report["status"] == "error"
    assert "write_tool_requires_proposal" in report["failed_check_ids"]
    assert report["should_block_execution"] is False


def test_tool_plan_self_check_flags_missing_context_without_gate() -> None:
    report = check_tool_plan_consistency(
        intent_draft={"intent_type": "asset_question"},
        verified_intent={"selected_tool_id": "mcp_get_asset_details"},
        context_resolution={"status": "missing_active_context", "target_kind": "selected_asset"},
        tool_plan={
            "mode": "read_only",
            "tool_id": "mcp_get_asset_details",
            "side_effect_level": "read_only",
            "requires_proposal": False,
        },
        routing={"intent": {"route_type": "single_tool"}},
    )

    assert report["status"] == "error"
    assert "missing_context_uses_context_gate" in report["failed_check_ids"]
