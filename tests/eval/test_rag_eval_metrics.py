from __future__ import annotations

from app.rag.evaluation.metrics import evaluate_case, summarize_cases
from app.rag.evaluation.reporting import build_markdown_report


def test_evaluate_case_tracks_rank_and_language() -> None:
    case = {
        "case_id": "ranked-hit",
        "query": "Explain locale fields",
        "expected_route": "project_qa",
        "expected_language": "en-US",
        "expected_sources": ["backend.md"],
    }
    response = {
        "intent": {"route_type": "project_qa"},
        "locale": {"final_output_language": "en-US"},
        "data": {"confidence": 0.82, "citations": [{"source": "/tmp/backend.md"}]},
        "retrieval_trace": {
            "retrieved_docs": [
                {"source_path": "/tmp/other.md"},
                {"source_path": "/tmp/backend.md"},
            ]
        },
    }

    result = evaluate_case(case, response, top_k=3)

    assert result["route_ok"] is True
    assert result["language_ok"] is True
    assert result["matched_sources"] == ["backend.md"]
    assert result["metrics"]["hit_at_k"] == 1.0
    assert result["metrics"]["top1_accuracy"] == 0.0
    assert result["metrics"]["mrr"] == 0.5
    assert result["metrics"]["precision_at_k"] == 0.3333
    assert result["metrics"]["precision_at_retrieved"] == 0.5
    assert result["metrics"]["labeled_precision_ceiling"] == 0.3333
    assert result["metrics"]["normalized_precision_at_k"] == 1.0


def test_summarize_cases_aggregates_metrics() -> None:
    results = [
        {
            "route_ok": True,
            "language_ok": True,
            "citations_count": 1,
            "confidence": 0.8,
            "metrics": {
                "recall_at_k": 1.0,
                "precision_at_k": 0.5,
                "precision_at_retrieved": 1.0,
                "labeled_precision_ceiling": 0.5,
                "normalized_precision_at_k": 1.0,
                "hit_at_k": 1.0,
                "top1_accuracy": 1.0,
                "mrr": 1.0,
                "ndcg_at_k": 1.0,
            },
        },
        {
            "route_ok": False,
            "language_ok": True,
            "citations_count": 0,
            "confidence": 0.2,
            "metrics": {
                "recall_at_k": 0.0,
                "precision_at_k": 0.0,
                "precision_at_retrieved": 0.0,
                "labeled_precision_ceiling": 0.5,
                "normalized_precision_at_k": 0.0,
                "hit_at_k": 0.0,
                "top1_accuracy": 0.0,
                "mrr": 0.0,
                "ndcg_at_k": 0.0,
            },
        },
    ]

    summary = summarize_cases(results)

    assert summary["cases"] == 2
    assert summary["recall_at_k"] == 0.5
    assert summary["precision_at_k"] == 0.25
    assert summary["precision_at_retrieved"] == 0.5
    assert summary["labeled_precision_ceiling"] == 0.5
    assert summary["normalized_precision_at_k"] == 0.5
    assert summary["top1_accuracy"] == 0.5
    assert summary["route_accuracy"] == 0.5
    assert summary["citation_coverage"] == 0.5
    assert summary["low_confidence_ratio"] == 0.5
    assert summary["no_result_ratio"] == 0.5


def test_evaluate_case_deduplicates_same_source_hits() -> None:
    case = {
        "case_id": "dedupe-hit",
        "query": "Explain RAG refresh",
        "expected_route": "project_qa",
        "expected_sources": ["backend.md"],
    }
    response = {
        "intent": {"route_type": "project_qa"},
        "locale": {"final_output_language": "en-US"},
        "data": {"confidence": 0.9, "citations": [{"source": "/tmp/backend.md"}]},
        "retrieval_trace": {
            "retrieved_docs": [
                {"source_path": "/tmp/backend.md"},
                {"source_path": "/tmp/backend.md"},
                {"source_path": "/tmp/backend.md"},
            ]
        },
    }

    result = evaluate_case(case, response, top_k=4)

    assert result["retrieved_sources"] == ["backend.md"]
    assert result["metrics"]["recall_at_k"] == 1.0
    assert result["metrics"]["precision_at_k"] == 0.25
    assert result["metrics"]["precision_at_retrieved"] == 1.0
    assert result["metrics"]["normalized_precision_at_k"] == 1.0
    assert result["metrics"]["top1_accuracy"] == 1.0
    assert result["metrics"]["ndcg_at_k"] == 1.0


def test_build_markdown_report_includes_summary_and_cases() -> None:
    report = {
        "generated_at": "2026-04-27T00:00:00+00:00",
        "dataset_path": "tests/eval/rag_project_qa_dataset.jsonl",
        "source_paths": ["./knowledge", "./docs"],
        "top_k": 4,
        "summary": {
            "cases": 1,
            "hit_at_k": 1.0,
            "top1_accuracy": 1.0,
            "route_accuracy": 1.0,
            "citation_coverage": 1.0,
        },
        "cases": [
            {
                "case_id": "ue-enhanced-input",
                "route_ok": True,
                "language_ok": True,
                "confidence": 0.9,
                "matched_sources": ["enhanced-input-character.md"],
                "metrics": {"hit_at_k": 1.0, "top1_accuracy": 1.0, "mrr": 1.0},
            }
        ],
    }

    markdown = build_markdown_report(report)

    assert "# RAG Eval Report" in markdown
    assert "| `hit_at_k` | 1.0000 |" in markdown
    assert "| `top1_accuracy` | 1.0000 |" in markdown
    assert "`ue-enhanced-input`" in markdown
    assert "enhanced-input-character.md" in markdown
