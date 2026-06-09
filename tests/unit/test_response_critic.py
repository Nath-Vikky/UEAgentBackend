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
    report = cleaned["debug_view"]["response_critic"]

    assert "mcp_get_" not in visible
    assert "MCP/TCP" not in visible
    assert "tool_id" not in visible
    assert "只读工具" not in visible
    assert "选中资产数量：1" in visible
    assert cleaned["user_view"]["blocks"][0]["data"] == {"asset_count": 1}
    assert report["version"] == "response_critic_v2"
    assert report["leaked_internal_tooling"] is True
    assert report["remaining_internal_tooling"] is False
    assert report["quality_ok"] is True
    assert report["repair_instruction"].startswith("User View 已转换")


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


def test_response_critic_flags_missing_context_prompt_without_next_action() -> None:
    cleaned = apply_response_critic(
        {
            "assistant_message": "I cannot answer that yet.",
            "user_view": {"title": "Missing Context", "text": "I cannot answer that yet.", "blocks": []},
            "debug_view": {
                "missing_context_gate": {"status": "blocked"},
                "tool_plan_v1": {"mode": "ask_for_context"},
            },
            "data": {},
        },
        output_language="en-US",
    )

    report = cleaned["debug_view"]["response_critic"]

    assert report["missing_context_prompt_required"] is True
    assert report["missing_context_prompt_ok"] is False
    assert report["quality_ok"] is False
    assert "missing_context_prompt_incomplete" in report["quality_flags"]


def test_response_critic_accepts_missing_context_prompt_with_user_action() -> None:
    cleaned = apply_response_critic(
        {
            "assistant_message": "Select the target in Unreal Editor, then sync inventory and ask again.",
            "user_view": {
                "title": "Select a target first",
                "text": "Select the target in Unreal Editor, then sync inventory and ask again.",
                "blocks": [],
            },
            "debug_view": {"missing_context_gate": {"status": "blocked"}},
            "data": {},
        },
        output_language="en-US",
    )

    report = cleaned["debug_view"]["response_critic"]

    assert report["missing_context_prompt_required"] is True
    assert report["missing_context_prompt_ok"] is True
    assert report["quality_ok"] is True


def test_response_critic_flags_proposal_without_confirmation_guidance() -> None:
    cleaned = apply_response_critic(
        {
            "assistant_message": "I prepared the operation.",
            "user_view": {"title": "Operation", "text": "I prepared the operation.", "blocks": []},
            "debug_view": {"tool_plan_v1": {"requires_proposal": True}},
            "action_proposals": [{"proposal_id": "proposal_1"}],
            "data": {},
        },
        output_language="en-US",
    )

    report = cleaned["debug_view"]["response_critic"]

    assert report["proposal_confirmation_prompt_required"] is True
    assert report["proposal_confirmation_prompt_ok"] is False
    assert "proposal_confirmation_prompt_missing" in report["quality_flags"]


def test_response_critic_accepts_proposal_confirmation_guidance() -> None:
    cleaned = apply_response_critic(
        {
            "assistant_message": "I created a Proposal. Please review and confirm it in the UE panel.",
            "user_view": {
                "title": "Proposal Pending",
                "text": "I created a Proposal. Please review and confirm it in the UE panel.",
                "blocks": [],
            },
            "debug_view": {"tool_plan_v1": {"requires_proposal": True}},
            "action_proposals": [{"proposal_id": "proposal_1"}],
            "data": {},
        },
        output_language="en-US",
    )

    report = cleaned["debug_view"]["response_critic"]

    assert report["proposal_confirmation_prompt_required"] is True
    assert report["proposal_confirmation_prompt_ok"] is True
    assert report["quality_ok"] is True
