from __future__ import annotations

from app.agent.multi_agent.review_fix_validate import should_generate_fix_draft
from app.tools.registry import get_tool_spec


def test_review_fix_gate_passes_on_high_findings() -> None:
    gate = should_generate_fix_draft({"high": 1, "medium": 0, "low": 0})

    assert gate.status == "passed"
    assert gate.reason == "high_severity_findings"


def test_review_fix_gate_passes_on_multiple_medium_findings() -> None:
    gate = should_generate_fix_draft({"high": 0, "medium": 3, "low": 1})

    assert gate.status == "passed"
    assert gate.reason == "multiple_medium_findings"


def test_review_fix_gate_skips_low_risk_review() -> None:
    gate = should_generate_fix_draft({"high": 0, "medium": 1, "low": 2})

    assert gate.status == "skipped"
    assert gate.reason == "below_fix_generation_threshold"


def test_multi_agent_tool_is_plan_only_and_not_free_chat_auto_execute() -> None:
    spec = get_tool_spec("multi_agent_code_review_and_fix")

    assert spec is not None
    assert spec.task_type == "code_review"
    assert spec.side_effect_level == "plan_only"
    assert spec.route_preference == "workflow"
    assert spec.allowed_in_free_chat is False
