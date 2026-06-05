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
        data={
            "self_reflection": {"status": "passed", "grounding_level": "tool_grounded"},
            "tool_contracts": {
                "input_contracts": [{"tool_id": "editor.add_blueprint_node_template", "ok": True}],
                "result_contracts": [{"tool_id": "editor.add_blueprint_node_template", "ok": True}],
            },
            "warnings": [],
        },
        debug_view={},
        action_proposals=[{"proposal_id": "proposal_1"}],
        task_status="waiting_confirmation",
        finish_reason="waiting_confirmation",
        output_complete=True,
    )

    assert trace["version"] == "react_v2_trace_v1"
    assert trace["boundary"]["raw_chain_of_thought_exposed"] is False
    assert trace["boundary"]["confirmed_write_required"] is True
    assert trace["boundary"]["display_safe_summary_only"] is True
    assert trace["summary"]["proposal_count"] == 1
    assert trace["summary"]["validation_passed"] is True
    assert [step["phase"] for step in trace["steps"]] == [
        "input",
        "thought_summary",
        "plan",
        "observation",
        "reflection",
        "validation",
        "final",
    ]
    validation_step = next(step for step in trace["steps"] if step["phase"] == "validation")
    assert validation_step["details"]["input_contract_count"] == 1
    assert validation_step["details"]["result_contract_count"] == 1
    assert validation_step["details"]["output_complete"] is True
    assert validation_step["details"]["confirmed_write_required"] is True


def test_react_v2_trace_validation_reports_failed_contracts() -> None:
    request = UnifiedTaskRequest.model_validate(
        {
            "task_type": "agent_chat",
            "session": {"session_id": "s1", "messages": [{"role": "user", "content": "move actor"}]},
        }
    )

    trace = build_react_v2_trace(
        request=request,
        routing={
            "intent": {"route_type": "single_tool", "reason": "editor operation request"},
            "route": {"selected_tool_id": "editor.move_actor"},
        },
        context_pack={"debug_summary": {}, "memory_layer": {}, "tool_layer": {}},
        skill_runtime={"skill_id": "EditorOperationSkill"},
        retrieval_trace={"mode": "not_used", "retrieved_docs": []},
        data={
            "tool_contracts": {
                "input_contracts": [{"tool_id": "editor.move_actor", "ok": False}],
                "result_contracts": [],
            },
            "warnings": ["contract_validation_failed"],
        },
        debug_view={},
        action_proposals=[],
        task_status="failed",
        finish_reason="tool_validation_failed",
        output_complete=False,
    )

    validation_step = next(step for step in trace["steps"] if step["phase"] == "validation")
    assert trace["summary"]["validation_passed"] is False
    assert validation_step["details"]["failed_input_contract_count"] == 1
    assert validation_step["details"]["warning_count"] == 1
    assert validation_step["details"]["output_complete"] is False
