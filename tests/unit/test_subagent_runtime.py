from __future__ import annotations

from app.agent.subagent_runtime import build_subagent_runtime


def test_subagent_runtime_projects_completed_dag_nodes() -> None:
    runtime = build_subagent_runtime(
        {
            "framework": "custom_lightweight",
            "nodes": [
                {
                    "node_id": "input",
                    "role": "InputNormalizer",
                    "status": "completed",
                    "responsibility": "Normalize request.",
                    "evidence": {"task_type": "agent_chat", "active_panel": "AgentChat"},
                },
                {
                    "node_id": "tool_plan",
                    "role": "ToolPlanner",
                    "status": "completed",
                    "responsibility": "Plan read-only tool.",
                    "evidence": {"tool_id": "mcp_get_asset_details", "mode": "read_only"},
                },
                {
                    "node_id": "finalize",
                    "role": "ResponseComposer",
                    "status": "completed",
                    "responsibility": "Build response.",
                    "evidence": {"task_status": "completed", "finish_reason": "completed"},
                },
            ],
            "edges": [{"from": "input", "to": "tool_plan"}, {"from": "tool_plan", "to": "finalize"}],
        }
    )

    assert runtime["version"] == "subagent_runtime_v1"
    assert runtime["summary"]["state_count"] == 3
    assert runtime["summary"]["completed_count"] == 3
    assert runtime["summary"]["current_focus"] == "finalize"
    assert runtime["states"][1]["output_summary"] == "mode=read_only, proposal=False"
    assert runtime["boundary"]["no_extra_llm_calls"] is True


def test_subagent_runtime_focuses_waiting_confirmation_node() -> None:
    runtime = build_subagent_runtime(
        {
            "nodes": [
                {
                    "node_id": "tool_plan",
                    "role": "ToolPlanner",
                    "status": "completed",
                    "responsibility": "Plan write Proposal.",
                    "evidence": {"tool_id": "editor_rename_asset", "requires_proposal": True},
                },
                {
                    "node_id": "evidence_or_tool",
                    "role": "EvidenceAndToolExecutor",
                    "status": "waiting_confirmation",
                    "responsibility": "Create pending Proposal.",
                    "evidence": {"selected_tool_id": "editor_rename_asset", "proposal_count": 1},
                },
                {
                    "node_id": "finalize",
                    "role": "ResponseComposer",
                    "status": "completed",
                    "responsibility": "Build response.",
                    "evidence": {"task_status": "waiting_confirmation"},
                },
            ]
        }
    )

    assert runtime["summary"]["waiting_count"] == 1
    assert runtime["summary"]["current_focus"] == "evidence_or_tool"
    waiting = next(state for state in runtime["states"] if state["status"] == "waiting_confirmation")
    assert waiting["error"] is None
    assert "proposal_count=1" in waiting["recent_activities"]
