from __future__ import annotations

from app.agent.active_context import build_active_context
from app.schemas.requests import UnifiedTaskRequest


def test_active_context_summarizes_project_asset_code_and_log_inputs() -> None:
    request = UnifiedTaskRequest.model_validate(
        {
            "task_type": "agent_chat",
            "session": {"session_id": "active_context_test", "messages": []},
            "context": {
                "project_name": "RushBa",
                "project_root": "D:/Project/RushBa",
                "active_panel": "AgentChat",
                "current_file": "Source/RushBa/Private/Hero.cpp",
                "current_module": "RushBa",
                "selected_assets": ["/Game/BP_Hero"],
                "editor_state": {
                    "ue_version": "5.4",
                    "plugin_version": "0.1",
                    "current_graph_name": "EventGraph",
                    "selected_node_id": "EventBeginPlay",
                },
            },
            "payload": {
                "user_query": "当前项目有哪些蓝图资产？",
                "log_file_path": "Saved/Logs/RushBa.log",
                "selected_log_text": "LogTemp: Error: Something failed",
            },
        }
    )
    active_context = build_active_context(
        request=request,
        routing={
            "intent": {"requires_rag": True},
            "route": {"selected_tool_id": "query_project_inventory"},
        },
    )

    assert active_context["version"] == "active_context_v1"
    assert active_context["project"]["project_name"] == "RushBa"
    assert active_context["asset"]["selected_assets"] == ["/Game/BP_Hero"]
    assert active_context["blueprint"]["current_blueprint_path"] == "/Game/BP_Hero"
    assert active_context["blueprint"]["current_graph_name"] == "EventGraph"
    assert active_context["blueprint"]["selected_node_id"] == "EventBeginPlay"
    assert active_context["blueprint"]["has_blueprint_focus"] is True
    assert active_context["editor_focus"]["current_blueprint_path"] == "/Game/BP_Hero"
    assert active_context["code"]["current_file"] == "Source/RushBa/Private/Hero.cpp"
    assert active_context["log"]["has_log_text"] is True
    assert active_context["kb"]["selected_tool_id"] == "query_project_inventory"
    assert active_context["mcp"]["status"] == "disabled"
