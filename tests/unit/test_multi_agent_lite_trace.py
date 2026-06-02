from __future__ import annotations

from app.agent.multi_agent.role_trace import build_multi_agent_lite_trace
from app.schemas.requests import UnifiedTaskRequest


def test_multi_agent_lite_trace_explains_role_chain_without_extra_llm() -> None:
    request = UnifiedTaskRequest.model_validate(
        {
            "task_type": "agent_chat",
            "session": {"session_id": "s1", "messages": [{"role": "user", "content": "show assets"}]},
            "payload": {"user_query": "show assets"},
        }
    )
    routing = {
        "intent": {"route_type": "project_inventory", "requires_tool": True},
        "route": {"selected_tool_id": "query_project_inventory"},
    }
    context_pack = {
        "debug_summary": {"actual_task_type": "project_qa"},
        "project_layer": {"inventory": {"query_candidate_count": 3}},
        "memory_layer": {"selected_items": [{"title": "inventory"}]},
        "tool_layer": {"proposal_policy": "confirmed writes only"},
    }

    trace = build_multi_agent_lite_trace(
        request=request,
        routing=routing,
        context_pack=context_pack,
        skill_runtime={"skill_id": "ProjectQASkill"},
        retrieval_trace={"mode": "inventory", "retrieved_docs": []},
        data={"self_reflection": {"status": "completed", "grounding_level": "project_context"}},
        debug_view={},
        action_proposals=[],
    )

    assert trace["version"] == "multi_agent_lite_trace_v1"
    assert trace["summary"]["researcher_active"] is True
    assert trace["summary"]["planner_active"] is True
    assert trace["boundary"]["no_extra_llm_calls"] is True
    assert [role["role_id"] for role in trace["roles"]] == [
        "coordinator",
        "researcher",
        "planner",
        "executor",
        "reviewer",
    ]
