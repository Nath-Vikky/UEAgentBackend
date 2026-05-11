from __future__ import annotations

from app.skills.executors.logs_analyze import _build_log_workflow_trace


def test_log_workflow_trace_reports_fixed_workflow_without_fake_agent_stop() -> None:
    trace = _build_log_workflow_trace(
        result={
            "summary": "Detected one error.",
            "issue_families": ["access_violation"],
            "log_summary": {"line_count": 3},
            "input_context": {"log_source": "Saved/Logs/Demo.log"},
            "parser_diagnostics": {"modules": ["Demo"]},
            "retrieval_quality_gate": {"status": "skipped"},
        },
        workflow={
            "tools": [
                {
                    "tool_id": "lookup_incident_history",
                    "summary": "No strong prior incident match.",
                }
            ]
        },
        llm_result={"ok": False, "reason": "missing_openai_api_key"},
    )

    assert trace["mode"] == "fixed_log_workflow_v1"
    assert trace["workflow_kind"] == "deterministic_bounded_workflow"
    assert trace["steps_executed"] == 2
    assert trace["stop_reason"] == "workflow_completed"
    assert trace["tool_call_sequence"] == ["analyze_ue_log", "lookup_incident_history"]
    assert trace["compatibility"]["previous_mode"] == "bounded_log_react_v1"

