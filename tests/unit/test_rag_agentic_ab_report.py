from __future__ import annotations

from pathlib import Path

from scripts.run_rag_agentic_ab import build_comparison_report, build_markdown_report


def _result(case_id: str, *, hit: float, top1: float, mrr: float) -> dict:
    return {
        "dataset": "rag_demo.jsonl",
        "case_id": case_id,
        "query": "demo query",
        "route_ok": True,
        "language_ok": True,
        "confidence": 0.5,
        "citations_count": 1,
        "warnings": [],
        "metrics": {
            "recall_at_k": hit,
            "precision_at_k": hit / 4,
            "precision_at_retrieved": hit,
            "labeled_precision_ceiling": 0.25,
            "normalized_precision_at_k": hit,
            "hit_at_k": hit,
            "top1_accuracy": top1,
            "mrr": mrr,
            "ndcg_at_k": mrr,
        },
        "agentic_rag": {
            "enabled": True,
            "selected_round": 2,
            "selected_query": "demo query Unreal Engine C++",
            "rewrite_used": True,
        },
    }


def test_agentic_ab_report_includes_delta_and_case_trace() -> None:
    report = build_comparison_report(
        dataset_paths=[Path("tests/eval/rag_demo.jsonl")],
        source_paths=["./knowledge"],
        top_k=4,
        baseline_results=[_result("case-a", hit=0.0, top1=0.0, mrr=0.0)],
        agentic_results=[_result("case-a", hit=1.0, top1=1.0, mrr=1.0)],
    )
    markdown = build_markdown_report(report)

    assert report["delta"]["hit_at_k"] == 1.0
    assert report["cases"][0]["delta"]["mrr"] == 1.0
    assert "Agentic RAG A/B Report" in markdown
    assert "demo query Unreal Engine C++" in markdown
