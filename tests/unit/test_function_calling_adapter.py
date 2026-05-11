from __future__ import annotations

from app.agent.function_calling_adapter import (
    build_function_calling_tools,
    normalize_function_tool_calls,
)


def test_function_calling_tools_expose_only_read_only_free_chat_tools_by_default() -> None:
    tools = build_function_calling_tools()

    names = {tool["function"]["name"] for tool in tools}
    assert "retrieve_project_knowledge" in names
    assert "query_project_inventory" in names
    assert "read_project_file" in names
    assert "editor_rename_asset" not in names
    assert "write_code_files" not in names

    inventory_tool = next(tool for tool in tools if tool["function"]["name"] == "query_project_inventory")
    assert inventory_tool["type"] == "function"
    assert inventory_tool["function"]["parameters"]["type"] == "object"
    assert inventory_tool["function"]["parameters"]["additionalProperties"] is False


def test_normalize_function_tool_calls_matches_existing_planner_contract() -> None:
    normalized = normalize_function_tool_calls(
        [
            {
                "function": {
                    "name": "query_project_inventory",
                    "arguments": '{"query":"当前项目有哪些蓝图资产","limit":20,"unsafe":"ignored"}',
                }
            },
            {
                "function": {
                    "name": "retrieve_project_knowledge",
                    "arguments": {"query": "Enhanced Input", "top_k": 4},
                }
            },
        ],
        allowed_tool_ids={"query_project_inventory", "retrieve_project_knowledge"},
    )

    assert normalized["adapter"] == "function_calling"
    assert normalized["requested_tool_ids"] == [
        "query_project_inventory",
        "retrieve_project_knowledge",
    ]
    assert normalized["tool_inputs_by_id"]["query_project_inventory"] == {
        "query": "当前项目有哪些蓝图资产",
        "limit": 20,
    }
    assert normalized["tool_inputs_by_id"]["retrieve_project_knowledge"] == {
        "query": "Enhanced Input",
        "top_k": 4,
    }


def test_normalize_function_tool_calls_blocks_write_tools_even_if_allowed() -> None:
    normalized = normalize_function_tool_calls(
        [
            {
                "function": {
                    "name": "editor_rename_asset",
                    "arguments": '{"asset_path":"/Game/Hero","new_name":"Hero_BP"}',
                }
            }
        ],
        allowed_tool_ids={"editor_rename_asset"},
    )

    assert normalized["requested_tool_ids"] == []
    assert normalized["tool_inputs_by_id"] == {}
