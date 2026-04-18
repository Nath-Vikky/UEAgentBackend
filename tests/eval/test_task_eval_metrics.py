from __future__ import annotations

from app.evaluation.task_metrics import evaluate_task_case, summarize_task_cases


def test_evaluate_task_case_tracks_route_fields_and_semantics() -> None:
    case = {
        "case_id": "task-eval-1",
        "endpoint": "/api/v1/tasks/code-review",
        "assertions": {
            "expected_route": "workflow",
            "expected_language": "en-US",
            "expected_status": "completed",
            "expected_finish_reason": "completed",
            "required_fields": ["data.issue_list", "debug_view.tools.0.tool_id"],
            "expected_rule_hits": ["raw_pointer_ownership", "sync_load_usage"],
        },
    }
    response = {
        "success": True,
        "intent": {"route_type": "workflow"},
        "locale": {"final_output_language": "en-US"},
        "task": {"status": "completed", "finish_reason": "completed"},
        "data": {
            "issue_list": [{"title": "Potential raw pointer ownership risk"}],
            "rule_hits": ["raw_pointer_ownership", "sync_load_usage"],
        },
        "debug_view": {"tools": [{"tool_id": "review_ue_cpp_files"}]},
        "errors": [],
    }

    result = evaluate_task_case(case, response)

    assert result["route_ok"] is True
    assert result["language_ok"] is True
    assert result["status_ok"] is True
    assert result["finish_reason_ok"] is True
    assert result["field_coverage"] == 1.0
    assert result["semantic_accuracy"] == 1.0


def test_evaluate_task_case_handles_waiting_confirmation() -> None:
    case = {
        "case_id": "task-eval-2",
        "endpoint": "/api/v1/tasks/config-generate",
        "assertions": {
            "expected_status": "waiting_confirmation",
            "expected_finish_reason": "waiting_confirmation",
            "expected_proposal_state": "pending",
        },
    }
    response = {
        "success": True,
        "task": {"status": "waiting_confirmation", "finish_reason": "waiting_confirmation"},
        "action_proposals": [{"confirmation": {"state": "pending"}}],
        "errors": [],
    }

    result = evaluate_task_case(case, response)

    assert result["status_ok"] is True
    assert result["finish_reason_ok"] is True
    assert result["semantic_accuracy"] == 1.0


def test_summarize_task_cases_aggregates_results() -> None:
    summary = summarize_task_cases(
        [
            {
                "success": True,
                "route_ok": True,
                "language_ok": True,
                "status_ok": True,
                "finish_reason_ok": True,
                "field_coverage": 1.0,
                "semantic_accuracy": 1.0,
                "errors_count": 0,
            },
            {
                "success": True,
                "route_ok": False,
                "language_ok": True,
                "status_ok": False,
                "finish_reason_ok": False,
                "field_coverage": 0.5,
                "semantic_accuracy": 0.5,
                "errors_count": 1,
            },
        ]
    )

    assert summary["cases"] == 2
    assert summary["success_rate"] == 1.0
    assert summary["route_accuracy"] == 0.5
    assert summary["status_accuracy"] == 0.5
    assert summary["field_coverage"] == 0.75
    assert summary["semantic_accuracy"] == 0.75
    assert summary["error_rate"] == 0.5
