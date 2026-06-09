from __future__ import annotations

from pathlib import Path

from scripts.run_agent_decision_eval import (
    evaluate_agent_decision_case,
    load_jsonl,
    summarize_agent_decision_cases,
)


def _case(case_id: str) -> dict:
    dataset = load_jsonl(Path("tests/eval/agent_decision_dataset.jsonl"))
    cases = {str(item["case_id"]): item for item in dataset}
    return cases[case_id]


def test_agent_decision_eval_v2_tracks_no_tool_and_missing_context_gates() -> None:
    results = [
        evaluate_agent_decision_case(_case("smalltalk_zh")),
        evaluate_agent_decision_case(_case("smalltalk_en")),
        evaluate_agent_decision_case(_case("missing_selected_asset_zh")),
        evaluate_agent_decision_case(_case("missing_blueprint_context_en")),
    ]

    by_id = {str(item["case_id"]): item for item in results}
    assert by_id["smalltalk_zh"]["checks"]["no_tool_selected_ok"] is True
    assert by_id["smalltalk_en"]["checks"]["no_tool_selected_ok"] is True
    assert by_id["missing_selected_asset_zh"]["checks"]["missing_context_gate_ok"] is True
    assert by_id["missing_blueprint_context_en"]["checks"]["missing_context_gate_ok"] is True

    summary = summarize_agent_decision_cases(results)

    assert summary["case_count"] == 4
    assert summary["no_tool_safety_accuracy"] == 1.0
    assert summary["no_tool_safety_case_count"] == 2
    assert summary["missing_context_gate_accuracy"] == 1.0
    assert summary["missing_context_gate_case_count"] == 2
    assert summary["tag_breakdown"]["smalltalk"]["overall_accuracy"] == 1.0
    assert summary["tag_breakdown"]["missing_context"]["overall_accuracy"] == 1.0
