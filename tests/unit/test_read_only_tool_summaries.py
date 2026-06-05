from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.core.settings import Settings
from app.schemas.requests import UnifiedTaskRequest
from app.services.llm_service import ChatRuntimeConfig
from app.services.task_handlers.base import TaskExecutionContext
from app.services.task_handlers import read_only_tool_summaries


class _FakeMCPToolExecutor:
    def __init__(self, settings: Settings):
        self.settings = settings

    def call_readonly_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        if tool_name == "get_blueprint_graph":
            return {
                "ok": True,
                "status": "completed",
                "reason": "mcp_tool_call_completed",
                "tool_name": tool_name,
                "transport": "mcp_tcp",
                "result": {
                    "structuredContent": {
                        "blueprint_path": arguments["blueprint_path"],
                        "graphs": [
                            {
                                "graph_name": "EventGraph",
                                "graph_type": "Ubergraph",
                                "node_count": 2,
                                "link_count": 1,
                                "nodes": [
                                    {"node_id": "EventBeginPlay", "title": "Event BeginPlay"},
                                    {"node_id": "PrintString_1", "title": "Print String"},
                                ],
                            }
                        ],
                    },
                    "content": [{"type": "text", "text": "graph"}],
                    "isError": False,
                },
                "errors": [],
            }
        if tool_name == "get_widget_tree":
            return {
                "ok": True,
                "status": "completed",
                "reason": "mcp_tool_call_completed",
                "tool_name": tool_name,
                "transport": "mcp_tcp",
                "result": {
                    "structuredContent": {
                        "widget_blueprint_path": arguments["widget_blueprint_path"],
                        "root": "RootCanvas",
                        "widgets": [{"name": "TitleText", "class": "TextBlock", "parent": "RootCanvas"}],
                    },
                    "content": [{"type": "text", "text": "widget"}],
                    "isError": False,
                },
                "errors": [],
            }
        return {
            "ok": False,
            "status": "blocked",
            "reason": "tool_not_in_mcp_allowed_tools",
            "tool_name": tool_name,
            "transport": "mcp_tcp",
            "result": {},
            "errors": [],
        }


class _FailingMCPToolExecutor:
    def __init__(self, settings: Settings):
        self.settings = settings

    def call_readonly_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "error",
            "reason": "mcp_tcp_connect_failed",
            "tool_name": tool_name,
            "transport": "mcp_tcp",
            "result": {},
            "errors": [{"reason": "mcp_tcp_connect_failed"}],
        }


def _context(*, selected_tool_id: str, request: UnifiedTaskRequest) -> TaskExecutionContext:
    return TaskExecutionContext(
        request=request,
        routing={
            "intent": {"reason": "test route"},
            "route": {"selected_tool_id": selected_tool_id, "candidate_tool_ids": [selected_tool_id]},
        },
        task_id="task_test",
        run_id="run_test",
        trace_id="trace_test",
        actual_task_type="agent_chat",
        output_language="en",
        chat_config=ChatRuntimeConfig(
            profile_id="default",
            profile_name="Default",
            model="test",
            temperature=0.0,
            max_tokens=128,
            timeout_ms=1000,
        ),
        context_bundle={
            "project_inventory_context": {
                "current_blueprint": {
                    "asset_name": "BP_PlayerCharacter",
                    "asset_path": "/Game/Blueprints/BP_PlayerCharacter",
                },
                "current_blueprint_graph": {"graph_name": "EventGraph"},
                "selected_assets": [
                    {
                        "asset_name": "WBP_MainHUD",
                        "asset_type": "WidgetBlueprint",
                        "asset_path": "/Game/UI/WBP_MainHUD",
                    }
                ],
            }
        },
        dependencies=SimpleNamespace(settings=Settings()),
    )


def test_live_mcp_readonly_result_uses_tcp_blueprint_graph(monkeypatch) -> None:
    monkeypatch.setattr(read_only_tool_summaries, "MCPToolExecutor", _FakeMCPToolExecutor)
    request = UnifiedTaskRequest(
        session={"session_id": "s1", "messages": [{"role": "user", "content": "read current graph"}]},
        context={"editor_state": {"current_blueprint_path": "/Game/Blueprints/BP_PlayerCharacter"}},
        payload={},
    )
    base_debug: dict[str, Any] = {}

    result = read_only_tool_summaries.live_mcp_readonly_result(
        context=_context(selected_tool_id="mcp_get_blueprint_graph", request=request),
        base_debug=base_debug,
        output_language="en",
        selected_tool_id="mcp_get_blueprint_graph",
    )

    assert result is not None
    assert result["retrieval_trace"]["mode"] == "mcp_tcp_readonly"
    assert result["data"]["mcp_tool"]["transport"] == "mcp_tcp"
    assert "EventGraph" in result["assistant_message"]
    assert "Print String" in result["assistant_message"]
    assert base_debug["mcp_live_attempt"]["tool_name"] == "get_blueprint_graph"


def test_live_mcp_readonly_result_uses_selected_widget_path(monkeypatch) -> None:
    monkeypatch.setattr(read_only_tool_summaries, "MCPToolExecutor", _FakeMCPToolExecutor)
    request = UnifiedTaskRequest(
        session={"session_id": "s1", "messages": [{"role": "user", "content": "read widget tree"}]},
        context={"selected_assets": ["/Game/UI/WBP_MainHUD"]},
        payload={},
    )
    base_debug: dict[str, Any] = {}

    result = read_only_tool_summaries.live_mcp_readonly_result(
        context=_context(selected_tool_id="mcp_get_widget_tree", request=request),
        base_debug=base_debug,
        output_language="en",
        selected_tool_id="mcp_get_widget_tree",
    )

    assert result is not None
    assert result["data"]["mcp_tool"]["arguments"]["widget_blueprint_path"] == "/Game/UI/WBP_MainHUD"
    assert "RootCanvas" in result["assistant_message"]
    assert "TitleText" in result["assistant_message"]


def test_live_mcp_readonly_result_returns_none_when_tcp_fails(monkeypatch) -> None:
    monkeypatch.setattr(read_only_tool_summaries, "MCPToolExecutor", _FailingMCPToolExecutor)
    request = UnifiedTaskRequest(
        session={"session_id": "s1", "messages": [{"role": "user", "content": "read current graph"}]},
        context={"editor_state": {"current_blueprint_path": "/Game/Blueprints/BP_PlayerCharacter"}},
        payload={},
    )
    base_debug: dict[str, Any] = {}

    result = read_only_tool_summaries.live_mcp_readonly_result(
        context=_context(selected_tool_id="mcp_get_blueprint_graph", request=request),
        base_debug=base_debug,
        output_language="en",
        selected_tool_id="mcp_get_blueprint_graph",
    )

    assert result is None
    assert base_debug["mcp_live_attempt"]["reason"] == "mcp_tcp_connect_failed"
