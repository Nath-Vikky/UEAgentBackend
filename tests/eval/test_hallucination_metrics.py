from __future__ import annotations

from app.evaluation.hallucination_metrics import (
    build_hallucination_markdown,
    evaluate_hallucination_case,
    summarize_hallucination_cases,
)


def test_abstention_case_passes_when_evidence_is_missing() -> None:
    case = {
        "case_id": "missing-blueprint",
        "query": "Does BP_ImpossibleDragon exist?",
        "assertions": {
            "expected_behavior": "abstain",
            "max_confidence": 0.4,
            "max_evidence_count": 0,
            "allowed_grounding_levels": ["insufficient_evidence"],
            "required_terms_any": ["no available Project Inventory", "not enough evidence"],
            "forbidden_terms": ["Health", "AttackDamage"],
        },
    }
    response = {
        "intent": {"route_type": "project_qa"},
        "user_view": {
            "text": "There is no available Project Inventory, so I do not have enough evidence."
        },
        "data": {
            "confidence": 0.12,
            "citations": [],
            "self_reflection": {"grounding_level": "insufficient_evidence"},
        },
        "retrieval_trace": {"retrieved_docs": []},
    }

    result = evaluate_hallucination_case(case, response)

    assert result["behavior_ok"] is True
    assert result["unsupported_claim"] is False
    assert result["checks"]["confidence_ok"] is True


def test_abstention_case_flags_unsupported_claims() -> None:
    case = {
        "case_id": "bad-claim",
        "query": "Does BP_ImpossibleDragon exist?",
        "assertions": {
            "expected_behavior": "abstain",
            "max_confidence": 0.4,
            "forbidden_terms": ["AttackDamage"],
        },
    }
    response = {
        "intent": {"route_type": "project_qa"},
        "user_view": {"text": "BP_ImpossibleDragon has an AttackDamage variable."},
        "data": {
            "confidence": 0.77,
            "citations": [],
            "self_reflection": {"grounding_level": "project_grounded"},
        },
        "retrieval_trace": {"retrieved_docs": []},
    }

    result = evaluate_hallucination_case(case, response)

    assert result["behavior_ok"] is False
    assert result["unsupported_claim"] is True
    assert "AttackDamage" in result["forbidden_terms_present"]


def test_grounded_case_requires_expected_source_and_citation() -> None:
    case = {
        "case_id": "actor-lifecycle",
        "query": "actor lifecycle",
        "assertions": {
            "expected_behavior": "grounded_answer",
            "expected_sources": ["ue-actor-lifecycle.md"],
            "required_terms_any": ["BeginPlay"],
        },
    }
    response = {
        "intent": {"route_type": "project_qa"},
        "user_view": {"text": "Actor lifecycle includes BeginPlay and Tick."},
        "data": {
            "confidence": 0.72,
            "citations": [{"source": "knowledge/engine-notes/ue-actor-lifecycle.md"}],
            "self_reflection": {"grounding_level": "project_grounded"},
        },
        "retrieval_trace": {
            "retrieved_docs": [
                {"source_path": "knowledge/engine-notes/ue-actor-lifecycle.md"}
            ]
        },
    }

    result = evaluate_hallucination_case(case, response)

    assert result["behavior_ok"] is True
    assert result["matched_sources"] == ["ue-actor-lifecycle.md"]


def test_summary_tracks_unsupported_answer_rate() -> None:
    results = [
        {"expected_behavior": "abstain", "behavior_ok": True, "route_ok": True, "unsupported_claim": False, "citations_count": 0},
        {"expected_behavior": "abstain", "behavior_ok": False, "route_ok": True, "unsupported_claim": True, "citations_count": 0},
        {"expected_behavior": "grounded_answer", "behavior_ok": True, "route_ok": True, "unsupported_claim": False, "citations_count": 1},
    ]

    summary = summarize_hallucination_cases(results)

    assert summary["cases"] == 3
    assert summary["grounding_accuracy"] == 0.6667
    assert summary["unsupported_answer_rate"] == 0.5
    assert summary["abstention_accuracy"] == 0.5


def test_markdown_report_includes_core_metrics() -> None:
    report = {
        "generated_at": "2026-05-09T00:00:00+00:00",
        "dataset_path": "tests/eval/hallucination_guard_dataset.jsonl",
        "source_paths": ["./knowledge"],
        "summary": {
            "cases": 1,
            "grounding_accuracy": 1.0,
            "unsupported_answer_rate": 0.0,
        },
        "cases": [
            {
                "case_id": "missing-blueprint",
                "expected_behavior": "abstain",
                "behavior_ok": True,
                "confidence": 0.12,
                "grounding_level": "insufficient_evidence",
                "matched_sources": [],
                "checks": {"confidence_ok": True},
            }
        ],
    }

    markdown = build_hallucination_markdown(report)

    assert "# Hallucination Guard Eval Report" in markdown
    assert "`unsupported_answer_rate`" in markdown
    assert "`missing-blueprint`" in markdown
