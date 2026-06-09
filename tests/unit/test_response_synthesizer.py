from __future__ import annotations

from app.agent.response_synthesizer import synthesize_execution_response


def test_response_synthesizer_preserves_handler_answer() -> None:
    execution = {
        "assistant_message": "Readable answer",
        "user_view": {"title": "Answer", "text": "Readable answer", "blocks": [{"text": "Detail"}]},
        "data": {"answer": "Readable answer"},
        "debug_view": {},
    }

    result = synthesize_execution_response(
        execution,
        output_language="en-US",
        route_type="project_qa",
        selected_tool_id="retrieve_project_knowledge",
    )

    assert result["assistant_message"] == "Readable answer"
    assert result["user_view"]["title"] == "Answer"
    assert result["user_view"]["text"] == "Readable answer"
    report = result["debug_view"]["response_synthesizer"]
    assert report["version"] == "response_synthesizer_v1"
    assert report["title_source"] == "handler"
    assert report["text_source"] == "handler"
    assert report["assistant_message_source"] == "handler"
    assert report["user_view_ready"] is True


def test_response_synthesizer_fills_missing_user_view_from_data_answer() -> None:
    execution = {
        "assistant_message": "",
        "user_view": {"blocks": []},
        "data": {"answer": "Inventory says BP_PlayerCharacter has EventGraph."},
        "debug_view": {},
    }

    result = synthesize_execution_response(
        execution,
        output_language="en-US",
        route_type="project_qa",
        selected_tool_id="query_project_inventory",
    )

    assert result["assistant_message"] == "Inventory says BP_PlayerCharacter has EventGraph."
    assert result["user_view"]["title"] == "Project Answer"
    assert result["user_view"]["text"] == "Inventory says BP_PlayerCharacter has EventGraph."
    report = result["data"]["response_synthesizer"]
    assert report["title_source"] == "default_title"
    assert report["text_source"] == "data.answer"
    assert report["assistant_message_source"] == "user_view_text"


def test_response_synthesizer_fills_missing_blocks_and_chinese_default() -> None:
    execution = {
        "assistant_message": "",
        "user_view": {"title": "", "text": "", "blocks": None},
        "data": {},
        "debug_view": {},
    }

    result = synthesize_execution_response(
        execution,
        output_language="zh-CN",
        route_type="single_tool",
        selected_tool_id="mcp_get_selected_assets",
    )

    assert result["user_view"]["title"] == "工具结果"
    assert result["user_view"]["blocks"] == []
    assert "还没有拿到足够的可展示结果" in result["assistant_message"]
    assert result["debug_view"]["response_synthesizer"]["text_source"] == "default_empty_answer"


def test_response_synthesizer_uses_chinese_proposal_title() -> None:
    result = synthesize_execution_response(
        {"assistant_message": "已创建提案，请确认。", "user_view": {}, "data": {}, "debug_view": {}},
        output_language="zh-CN",
        route_type="proposal_wait",
        selected_tool_id="editor_rename_asset",
    )

    assert result["user_view"]["title"] == "待确认提案"
