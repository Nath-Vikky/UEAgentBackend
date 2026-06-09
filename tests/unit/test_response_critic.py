from __future__ import annotations

from app.agent.response_critic import apply_response_critic, sanitize_user_visible_text


def test_response_critic_removes_internal_tooling_from_user_view() -> None:
    execution = {
        "assistant_message": (
            "已通过 本地 Project Inventory 只读工具读取资产详情：BP_Player\n\n"
            "tool_id: mcp_get_asset_details\n"
            "selected_asset_count=1"
        ),
        "user_view": {
            "title": "本地只读工具结果",
            "text": (
                "已通过 本地 Project Inventory 只读工具读取资产详情：BP_Player\n\n"
                "tool_name: get_asset_details\n"
                "selected_asset_count=1"
            ),
            "blocks": [
                {
                    "block_type": "summary",
                    "title": "工具结果摘要",
                    "text": "MCP/TCP raw payload: mcp_get_asset_details",
                    "data": {
                        "tool_id": "mcp_get_asset_details",
                        "arguments": {"asset_path": "/Game/BP_Player"},
                        "result": {"raw": True},
                        "asset_count": 1,
                    },
                }
            ],
        },
        "data": {"answer": "old"},
        "debug_view": {},
    }

    cleaned = apply_response_critic(execution, output_language="zh-CN")

    visible = "\n".join(
        [
            cleaned["assistant_message"],
            cleaned["user_view"]["title"],
            cleaned["user_view"]["text"],
            cleaned["user_view"]["blocks"][0]["text"],
        ]
    )
    assert "mcp_get_" not in visible
    assert "MCP/TCP" not in visible
    assert "tool_id" not in visible
    assert "只读工具" not in visible
    assert "选中资产数量：1" in visible
    assert cleaned["user_view"]["blocks"][0]["data"] == {"asset_count": 1}
    assert cleaned["debug_view"]["response_critic"]["leaked_internal_tooling"] is True
    assert cleaned["debug_view"]["response_critic"]["remaining_internal_tooling"] is False
    assert cleaned["debug_view"]["response_critic"]["repair_instruction"].startswith("User View 已转换")


def test_response_critic_keeps_plain_answer_unchanged() -> None:
    text = "这个资产是一个蓝图资产，路径是 /Game/Blueprints/BP_Player。"

    assert sanitize_user_visible_text(text, output_language="zh-CN") == text


def test_response_critic_sanitizes_english_tooling() -> None:
    text = (
        "Read asset details through local Project Inventory read-only tool: BP_Player\n"
        "tool_name: get_asset_details\n"
        "selected_asset_count=2"
    )

    cleaned = sanitize_user_visible_text(text, output_language="en-US")

    assert "read-only tool" not in cleaned
    assert "tool_name" not in cleaned
    assert "Selected asset count: 2" in cleaned
    assert "Read asset details from the current project snapshot" in cleaned
