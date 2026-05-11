from __future__ import annotations

from app.skills.executors.code_review import CodeReviewSkillExecutor


def _executor() -> CodeReviewSkillExecutor:
    return CodeReviewSkillExecutor.__new__(CodeReviewSkillExecutor)


def test_code_review_text_fallback_extracts_malformed_json_like_summary() -> None:
    executor = _executor()

    payload = executor._text_fallback_review_payload(
        (
            "{summary: \"The code synchronously loads an asset during Tick.\", "
            "title: \"Synchronous asset load\", "
            "reason: \"Tick should stay cheap.\", "
            "suggestion: \"Move loading to BeginPlay or async loading.\""
        ),
        output_language="en-US",
    )

    assert payload["summary"] == "The code synchronously loads an asset during Tick."
    assert payload["issues"][0]["title"] == "Synchronous asset load"
    assert payload["issues"][0]["reason"] == "Tick should stay cheap."
    assert payload["recommendations"] == ["Move loading to BeginPlay or async loading."]


def test_code_review_text_fallback_hides_unparseable_json_like_raw_text() -> None:
    executor = _executor()
    raw_text = "{issues: [{line: 42, code: TEXT(\"/Game/Hero\")}]}"

    payload = executor._text_fallback_review_payload(raw_text, output_language="en-US")

    assert "structured-looking JSON" in payload["summary"]
    assert raw_text not in payload["summary"]
    assert payload["issues"] == []
    assert payload["recommendations"] == []


def test_code_review_llm_analysis_uses_normalized_summary_not_raw_json() -> None:
    executor = _executor()
    llm_payload = {
        "summary": "The risky load should be moved out of Tick.",
        "issues": [
            {
                "title": "Synchronous load in Tick",
                "reason": "Tick runs every frame.",
                "suggestion": "Cache or async-load the asset.",
            }
        ],
        "recommendations": ["Add a regression test around the loading path."],
    }

    analysis = executor._llm_analysis_from_review(
        result={"severity_summary": {"high": 0, "medium": 1, "low": 0}},
        llm_review={"ok": True, "model": "test-model", "profile_id": "default"},
        llm_payload=llm_payload,
        output_language="en-US",
    )

    assert analysis["status"] == "completed"
    assert analysis["text"] == "The risky load should be moved out of Tick."
    assert analysis["priority"] == "medium"
    assert "Synchronous load in Tick" in analysis["key_points"]
    assert "Add a regression test around the loading path." in analysis["key_points"]
