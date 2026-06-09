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
    assert runtime["mode"] == "dag_runtime_state"
    assert runtime["summary"]["state_count"] == 3
    assert runtime["summary"]["completed_count"] == 3
    assert runtime["summary"]["quality_blocked_count"] == 0
    assert runtime["summary"]["current_focus"] == "finalize"
    assert runtime["states"][1]["output_summary"] == "mode=read_only, proposal=False"
    assert runtime["states"][1]["quality_gate"]["status"] == "pass"
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


def test_subagent_runtime_focuses_quality_blocked_node() -> None:
    runtime = build_subagent_runtime(
        {
            "nodes": [
                {
                    "node_id": "response_synthesize",
                    "role": "ResponseSynthesizer",
                    "status": "completed",
                    "responsibility": "Build user view.",
                    "evidence": {"user_view_ready": True},
                    "quality_gate": {"status": "pass", "checks": []},
                },
                {
                    "node_id": "response_critic",
                    "role": "ResponseCritic",
                    "status": "completed",
                    "responsibility": "Guard user view.",
                    "evidence": {"remaining_internal_tooling": True},
                    "quality_gate": {
                        "status": "block",
                        "checks": [],
                        "blocking_flags": ["remaining_internal_tooling_detected"],
                    },
                    "blocking_flags": ["remaining_internal_tooling_detected"],
                },
            ]
        }
    )

    assert runtime["summary"]["quality_blocked_count"] == 1
    assert runtime["summary"]["blocking_flags"] == ["remaining_internal_tooling_detected"]
    assert runtime["summary"]["current_focus"] == "response_critic"
