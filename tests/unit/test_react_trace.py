from __future__ import annotations

from app.agent.react_trace import build_react_v2_trace
from app.schemas.requests import UnifiedTaskRequest


def test_react_v2_trace_is_display_safe_and_bounded() -> None:
    request = UnifiedTaskRequest.model_validate(
        {
            "task_type": "agent_chat",
            "session": {"session_id": "s1", "messages": [{"role": "user", "content": "add print string"}]},
        }
    )

    trace = build_react_v2_trace(
        request=request,
        routing={
            "intent": {"route_type": "single_tool", "reason": "editor operation request"},
            "route": {"selected_tool_id": "editor.add_blueprint_node_template"},
        },
        context_pack={
            "version": "context_pack_v1",
            "debug_summary": {"actual_task_type": "task_request"},
            "memory_layer": {"selected_items": []},
            "tool_layer": {"proposal_policy": "confirmed writes only"},
        },
        skill_runtime={"skill_id": "EditorOperationSkill"},
        retrieval_trace={"mode": "not_used", "retrieved_docs": []},
        data={"self_reflection": {"status": "passed", "grounding_level": "tool_grounded"}},
        debug_view={},
        action_proposals=[{"proposal_id": "proposal_1"}],
        task_status="waiting_confirmation",
        finish_reason="waiting_confirmation",
    )

    assert trace["version"] == "react_v2_trace_v1"
    assert trace["boundary"]["raw_chain_of_thought_exposed"] is False
    assert trace["boundary"]["confirmed_write_required"] is True
    assert trace["summary"]["proposal_count"] == 1
    assert [step["phase"] for step in trace["steps"]] == [
        "input",
        "thought_summary",
        "plan",
        "observation",
        "reflection",
        "final",
    ]
