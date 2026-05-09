from __future__ import annotations

from app.evaluation.benchmark_report import (
    build_benchmark_markdown,
    percentile,
    summarize_latency,
)


def test_percentile_uses_nearest_rank() -> None:
    assert percentile([10, 20, 30, 40], 50) == 20
    assert percentile([10, 20, 30, 40], 95) == 40
    assert percentile([], 95) == 0.0


def test_summarize_latency_groups_by_endpoint() -> None:
    summary = summarize_latency(
        [
            {"endpoint": "/a", "duration_ms": 10},
            {"endpoint": "/a", "duration_ms": 30},
            {"endpoint": "/b", "duration_ms": 50},
        ]
    )

    assert summary["requests"] == 3
    assert summary["p50_ms"] == 30
    assert summary["p95_ms"] == 50
    assert summary["by_endpoint"]["/a"]["requests"] == 2
    assert summary["by_endpoint"]["/a"]["p50_ms"] == 20


def test_build_benchmark_markdown_includes_core_metrics() -> None:
    report = {
        "generated_at": "2026-04-30T00:00:00+00:00",
        "source_paths": ["./knowledge"],
        "rag_datasets": ["tests/eval/rag_ue_knowledge_dataset.jsonl"],
        "task_datasets": ["tests/eval/code_generate_dataset.jsonl"],
        "hallucination_dataset": "tests/eval/hallucination_guard_dataset.jsonl",
        "rag_summary": {
            "cases": 1,
            "recall_at_k": 1.0,
            "precision_at_k": 0.25,
            "normalized_precision_at_k": 1.0,
            "top1_accuracy": 1.0,
            "route_accuracy": 1.0,
        },
        "task_summary": {
            "cases": 1,
            "success_rate": 1.0,
            "field_coverage": 1.0,
            "semantic_accuracy": 1.0,
        },
        "hallucination_summary": {
            "cases": 1,
            "grounding_accuracy": 1.0,
            "unsupported_answer_rate": 0.0,
        },
        "performance": {
            "requests": 2,
            "p50_ms": 12.5,
            "p95_ms": 20.0,
            "max_ms": 20.0,
            "by_endpoint": {"/api/v1/tasks/project-qa": {"requests": 1, "p50_ms": 20.0, "p95_ms": 20.0, "max_ms": 20.0}},
        },
        "kb_refresh_ms": 100.0,
        "knowledge_base": {
            "documents": 10,
            "chunks": 20,
            "effective_mode": "lexical",
            "local_search_readiness": {"searchable_files": 10},
        },
    }

    markdown = build_benchmark_markdown(report)

    assert "# UE Agent Backend Benchmark Report" in markdown
    assert "`recall_at_k`" in markdown
    assert "`precision_at_k`" in markdown
    assert "`normalized_precision_at_k`" in markdown
    assert "`top1_accuracy`" in markdown
    assert "`unsupported_answer_rate`" in markdown
    assert "`p95_ms`" in markdown
