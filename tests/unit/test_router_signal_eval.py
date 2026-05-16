from __future__ import annotations

from scripts.run_router_signal_eval import (
    build_markdown_report,
    evaluate_router_signal_case,
    load_jsonl,
    summarize_router_signal_cases,
)


def test_router_signal_eval_dataset_has_stable_shadow_recommendations() -> None:
    cases = load_jsonl("tests/eval/router_signal_dataset.jsonl")
    results = [evaluate_router_signal_case(case) for case in cases]
    summary = summarize_router_signal_cases(results)

    assert summary["route_accuracy"] == 1.0
    assert summary["tool_accuracy"] == 1.0
    assert summary["shadow_stability"] == 1.0
    assert summary["recommendation_accuracy"] >= 0.8
    assert summary["override_applied_count"] == 0


def test_router_signal_eval_markdown_report_includes_core_metrics() -> None:
    report = {
        "generated_at": "2026-05-16T00:00:00+00:00",
        "dataset": "tests/eval/router_signal_dataset.jsonl",
        "summary": {
            "case_count": 1,
            "route_accuracy": 1.0,
            "tool_accuracy": 1.0,
            "shadow_stability": 1.0,
            "recommendation_accuracy": 1.0,
            "override_applied_count": 0,
        },
        "cases": [
            {
                "case_id": "demo",
                "baseline_route_type": "project_qa",
                "shadow_route_type": "project_qa",
                "baseline_selected_tool_id": "retrieve_project_knowledge",
                "shadow_selected_tool_id": "retrieve_project_knowledge",
                "recommendation_status": "eligible",
                "recommendation_route_hint": "project_qa",
                "recommendation_selected_tool_id": "retrieve_project_knowledge",
                "route_ok": True,
                "tool_ok": True,
                "shadow_stable": True,
                "recommendation_ok": True,
            }
        ],
    }

    markdown = build_markdown_report(report)

    assert "Router Signal Eval Report" in markdown
    assert "Route accuracy" in markdown
    assert "demo" in markdown
