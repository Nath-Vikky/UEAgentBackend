from __future__ import annotations

from app.agent.agent_dag import build_agent_dag_projection
from app.schemas.requests import UnifiedTaskRequest


def test_agent_dag_projects_decision_chain_for_readonly_tool() -> None:
    request = UnifiedTaskRequest.model_validate(
        {
            "task_type": "agent_chat",
            "session": {"session_id": "s1", "messages": [{"role": "user", "content": "Analyze this asset"}]},
            "payload": {"user_query": "Analyze this asset"},
            "context": {"project_name": "DemoProject", "active_panel": "AgentChat"},
        }
    )

    dag = build_agent_dag_projection(
        request=request,
        routing={
            "intent": {"route_type": "single_tool", "intent_type": "selected_context_question"},
            "route": {"selected_tool_id": "mcp_get_asset_details"},
        },
        context_bundle={
            "intent_draft": {"intent_type": "selected_context_question", "target_kind": "selected_asset"},
            "verified_intent": {"corrections": [], "safety_flags": []},
            "context_resolution": {"target_kind": "selected_asset", "status": "resolved", "source": "selected_assets"},
            "tool_plan_v1": {
                "tool_id": "mcp_get_asset_details",
                "mode": "readonly_tool",
                "side_effect_level": "read_only",
                "requires_proposal": False,
            },
        },
        skill_runtime={"skill_id": "ToolRegistryReadOnly"},
        retrieval_trace={"mode": "local_tool_registry_readonly", "retrieved_docs": []},
        data={
            "response_synthesizer": {"user_view_ready": True, "title_source": "handler"},
            "response_critic": {"answer_ok": True, "leaked_internal_tooling": False},
        },
        debug_view={},
        action_proposals=[],
        task_status="completed",
        finish_reason="completed",
    )

    assert dag["version"] == "agent_dag_v1"
    assert dag["mode"] == "single_process_framework_neutral_dag"
    assert dag["summary"]["selected_tool_id"] == "mcp_get_asset_details"
    assert dag["summary"]["completed_count"] >= 7
    assert dag["migration_notes"]["langgraph_ready"] is True
    assert [node["node_id"] for node in dag["nodes"]] == [
        "input",
        "intent_draft",
        "intent_verify",
        "context_resolve",
        "tool_plan",
        "evidence_or_tool",
        "response_synthesize",
        "response_critic",
        "finalize",
    ]
    assert dag["edges"][0] == {"from": "input", "to": "intent_draft"}
    assert dag["edges"][-1] == {"from": "response_critic", "to": "finalize"}


def test_agent_dag_marks_write_tool_as_waiting_confirmation() -> None:
    request = UnifiedTaskRequest.model_validate(
        {
            "task_type": "agent_chat",
            "session": {"session_id": "s1", "messages": [{"role": "user", "content": "Rename this asset"}]},
            "payload": {"user_query": "Rename this asset"},
        }
    )

    dag = build_agent_dag_projection(
        request=request,
        routing={
            "intent": {"route_type": "single_tool", "intent_type": "editor_write_request"},
            "route": {"selected_tool_id": "editor_rename_asset"},
        },
        context_bundle={"tool_plan_v1": {"tool_id": "editor_rename_asset", "requires_proposal": True}},
        skill_runtime={"skill_id": "EditorOperationProposal"},
        retrieval_trace={"mode": "not_used", "retrieved_docs": []},
        data={"response_synthesizer": {"user_view_ready": True}},
        debug_view={"response_critic": {"answer_ok": True}},
        action_proposals=[{"proposal_id": "proposal_1"}],
        task_status="completed",
        finish_reason="completed",
    )

    evidence_node = next(node for node in dag["nodes"] if node["node_id"] == "evidence_or_tool")
    assert evidence_node["status"] == "waiting_confirmation"
    assert dag["summary"]["proposal_count"] == 1
    assert dag["migration_notes"]["side_effects_stay_behind_proposals"] is True
