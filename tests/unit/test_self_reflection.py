from __future__ import annotations

from app.agent.self_reflection import build_self_reflection


def test_self_reflection_marks_project_qa_without_evidence_as_needs_context() -> None:
    reflection = build_self_reflection(
        route_type="project_qa",
        output_language="zh-CN",
        answer_text="没有找到相关项目事实。",
        confidence=0.2,
        answer_generation_mode="retrieval_summary_fallback",
        retrieved_docs=[],
        inventory_items=[],
    )

    assert reflection["status"] == "needs_context"
    assert reflection["grounding_level"] in {"insufficient_evidence", "low_confidence"}
    assert reflection["recommendations"]


def test_self_reflection_marks_direct_answer_without_llm_as_degraded() -> None:
    reflection = build_self_reflection(
        route_type="direct_answer",
        output_language="en-US",
        answer_text="Fallback answer.",
        confidence=0.0,
        answer_generation_mode="degraded_fallback",
        live_llm_used=False,
        warnings=["missing_openai_api_key"],
    )

    assert reflection["status"] == "degraded"
    assert reflection["grounding_level"] == "fallback"
