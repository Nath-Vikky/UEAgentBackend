from __future__ import annotations

from app.agent.tool_use_summary import summarize_tool_use, summarize_tool_uses


def test_summarize_tool_use_hides_raw_payload() -> None:
    summary = summarize_tool_use(
        tool_id="mcp_get_asset_details",
        result={
            "status": "completed",
            "summary": "Read asset details.",
            "output": {
                "items": [{"asset_path": "/Game/A"}],
                "raw_payload": {"large": True},
                "structuredContent": {"hidden": True},
                "warnings": ["partial"],
            },
        },
    )

    assert summary["version"] == "tool_use_summary_v1"
    assert summary["user_summary"] == "Read asset details."
    assert summary["item_count"] == 1
    assert summary["warning_count"] == 1
    assert summary["raw_payload_hidden"] is True
    assert "raw_payload" not in summary["safe_output_keys"]
    assert "structuredContent" not in summary["safe_output_keys"]


def test_summarize_tool_uses_batches_debug_entries() -> None:
    summaries = summarize_tool_uses(
        [
            {"tool_id": "query_project_inventory", "status": "completed", "summary": "Matched 2 items."},
            {"tool_id": "retrieve_project_knowledge", "status": "skipped"},
        ]
    )

    assert [item["tool_id"] for item in summaries] == [
        "query_project_inventory",
        "retrieve_project_knowledge",
    ]
    assert summaries[1]["status"] == "skipped"
