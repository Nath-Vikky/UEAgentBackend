from __future__ import annotations

from app.agent.context_budget import build_context_budget_report
from app.agent.turn_context import build_agent_turn_context
from app.schemas.requests import UnifiedTaskRequest


def _request() -> UnifiedTaskRequest:
    return UnifiedTaskRequest(
        task_type="agent_chat",
        session={
            "session_id": "agent_turn_context_session",
            "messages": [{"role": "user", "content": "Analyze this asset"}],
        },
        context={
            "project_name": "DemoProject",
            "active_panel": "AgentChat",
            "selected_assets": ["/Game/Characters/BP_Player.BP_Player"],
            "editor_state": {
                "current_blueprint_path": "/Game/Characters/BP_Player.BP_Player",
                "current_graph_name": "EventGraph",
            },
        },
        payload={"user_query": "Analyze this asset"},
    )


def test_build_agent_turn_context_prioritizes_active_targets() -> None:
    request = _request()
    routing = {
        "locale": {"final_output_language": "en-US"},
        "intent": {"route_type": "project_qa", "intent_type": "project_qa"},
        "route": {
            "selected_tool_id": "query_project_inventory",
            "candidate_tool_ids": ["query_project_inventory"],
            "planner_confidence": 0.9,
            "decision_source": "unit_test",
        },
    }
    bundle = {
        "active_context": {
            "asset": {"selected_assets": ["/Game/Characters/BP_Player.BP_Player"]},
            "blueprint": {
                "current_blueprint_path": "/Game/Characters/BP_Player.BP_Player",
                "current_graph_name": "EventGraph",
            },
            "level_actor": {},
            "material": {},
            "code": {},
            "log": {},
            "mcp": {"enabled": True, "status": "available"},
        },
        "project_inventory_context": {"status": "available", "has_snapshot": True},
        "retrieval_context": {"status": "pending_execution"},
        "tool_context": [{"task_id": "task_1", "task_type": "project_qa", "summary": "Matched asset."}],
        "recent_editor_operations": [{"operation_type": "add_blueprint_node_template"}],
        "context_budget_report": {"version": "context_budget_v1", "estimated_chars": 100},
    }

    turn = build_agent_turn_context(request=request, routing=routing, context_bundle=bundle)

    assert turn["version"] == "agent_turn_context_v1"
    assert turn["user_message"] == "Analyze this asset"
    assert turn["active_targets"]["has_any_active_target"] is True
    assert turn["active_targets"]["asset"]["available"] is True
    assert turn["active_targets"]["blueprint"]["current_graph_name"] == "EventGraph"
    assert turn["context_sources"]["active_ue_context"] is True
    assert turn["context_sources"]["project_inventory"] is True
    assert turn["mcp_provider_status"]["status"] == "available"
    assert turn["previous_tool_summaries"][0]["task_id"] == "task_1"


def test_build_context_budget_report_breaks_down_context_sources() -> None:
    bundle = {
        "recent_messages": [{"content": "hello"}],
        "active_context": {"asset": {"selected_assets": ["/Game/A"]}},
        "project_inventory_context": {"summary": {"asset_count": 1}},
        "retrieval_context": {"retrieved_docs": [{"title": "doc"}]},
        "session_summary": {"summary_text": "short summary"},
        "tool_context": [{"summary": "tool summary"}],
        "recent_editor_operations": [{"operation_type": "rename_selected_asset"}],
        "source_policy": {"policy": "test"},
        "budget": {"char_budget": 1000, "warnings": []},
    }

    report = build_context_budget_report(bundle)

    assert report["version"] == "context_budget_v1"
    assert report["estimated_chars"] > 0
    assert report["section_char_counts"]["active_ue_context"] > 0
    assert report["section_char_counts"]["tool_results"] > 0
    assert report["top_sources"]
    assert report["within_budget"] is True
