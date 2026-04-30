from __future__ import annotations

from math import ceil
from statistics import median
from pathlib import Path
from typing import Any


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, ceil((percentile_value / 100.0) * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def summarize_latency(samples: list[dict[str, Any]]) -> dict[str, Any]:
    durations = [float(item.get("duration_ms") or 0.0) for item in samples]
    by_endpoint: dict[str, list[float]] = {}
    for item in samples:
        endpoint = str(item.get("endpoint") or "unknown")
        by_endpoint.setdefault(endpoint, []).append(float(item.get("duration_ms") or 0.0))

    return {
        "requests": len(durations),
        "p50_ms": round(median(durations), 2) if durations else 0.0,
        "p95_ms": round(percentile(durations, 95), 2),
        "max_ms": round(max(durations), 2) if durations else 0.0,
        "by_endpoint": {
            endpoint: {
                "requests": len(endpoint_durations),
                "p50_ms": round(median(endpoint_durations), 2),
                "p95_ms": round(percentile(endpoint_durations, 95), 2),
                "max_ms": round(max(endpoint_durations), 2),
            }
            for endpoint, endpoint_durations in sorted(by_endpoint.items())
        },
    }


def build_benchmark_markdown(report: dict[str, Any]) -> str:
    rag_summary = dict(report.get("rag_summary") or {})
    task_summary = dict(report.get("task_summary") or {})
    performance = dict(report.get("performance") or {})
    knowledge = dict(report.get("knowledge_base") or {})

    lines = [
        "# UE Agent Backend Benchmark Report",
        "",
        "## Summary",
        "",
        f"- Generated at: `{report.get('generated_at')}`",
        f"- Source paths: `{', '.join(report.get('source_paths') or [])}`",
        f"- RAG datasets: `{', '.join(_fmt_paths(report.get('rag_datasets') or []))}`",
        f"- Task datasets: `{', '.join(_fmt_paths(report.get('task_datasets') or []))}`",
        f"- LLM mode: `{report.get('llm_mode', 'offline_fallback')}`",
        "",
        "## RAG Retrieval Quality",
        "",
        "| Metric | Value | Meaning |",
        "| --- | ---: | --- |",
    ]
    metric_notes = {
        "cases": "Evaluation case count.",
        "recall_at_k": "How many expected sources were recovered in top-k.",
        "precision_at_k": "How many top-k results were relevant.",
        "hit_at_k": "Whether each case hit at least one expected source.",
        "mrr": "How early the first relevant source appeared.",
        "ndcg_at_k": "Ranking quality with position discount.",
        "route_accuracy": "Whether route_type matched expectation.",
        "language_accuracy": "Whether output language matched expectation.",
        "citation_coverage": "Whether responses included citations.",
        "no_result_ratio": "Share of cases without a relevant hit.",
    }
    for key, note in metric_notes.items():
        if key in rag_summary:
            lines.append(f"| `{key}` | {_fmt(rag_summary[key])} | {note} |")

    lines.extend(
        [
            "",
            "## Task Workflow Quality",
            "",
            "| Metric | Value | Meaning |",
            "| --- | ---: | --- |",
        ]
    )
    task_notes = {
        "cases": "Task evaluation case count.",
        "success_rate": "Responses with success=true.",
        "route_accuracy": "Route matched expected workflow/single_tool/direct route.",
        "language_accuracy": "Output language matched expected locale.",
        "field_coverage": "Required response fields were present.",
        "semantic_accuracy": "Rule/issue/value checks matched expectations.",
        "error_rate": "Responses containing errors.",
    }
    for key, note in task_notes.items():
        if key in task_summary:
            lines.append(f"| `{key}` | {_fmt(task_summary[key])} | {note} |")

    lines.extend(
        [
            "",
            "## Runtime Performance",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| `requests` | {_fmt(performance.get('requests', 0))} |",
            f"| `p50_ms` | {_fmt(performance.get('p50_ms', 0.0))} |",
            f"| `p95_ms` | {_fmt(performance.get('p95_ms', 0.0))} |",
            f"| `max_ms` | {_fmt(performance.get('max_ms', 0.0))} |",
            f"| `kb_refresh_ms` | {_fmt(report.get('kb_refresh_ms', 0.0))} |",
            "",
            "## Endpoint Latency",
            "",
            "| Endpoint | Requests | P50 ms | P95 ms | Max ms |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for endpoint, item in (performance.get("by_endpoint") or {}).items():
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{endpoint}`",
                    _fmt(item.get("requests", 0)),
                    _fmt(item.get("p50_ms", 0.0)),
                    _fmt(item.get("p95_ms", 0.0)),
                    _fmt(item.get("max_ms", 0.0)),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Knowledge Base Snapshot",
            "",
            f"- Documents: `{knowledge.get('documents', 0)}`",
            f"- Chunks: `{knowledge.get('chunks', 0)}`",
            f"- Effective mode: `{knowledge.get('effective_mode')}`",
            f"- Searchable local files: `{knowledge.get('local_search_readiness', {}).get('searchable_files', 0)}`",
            "",
            "## Notes",
            "",
            "- Recall and precision are computed from expected source files in eval datasets.",
            "- This report is a local benchmark for portfolio/interview demonstration, not a production SLA.",
            "- Use it as a baseline before and after RAG, routing, context, or performance optimizations.",
        ]
    )
    return "\n".join(lines) + "\n"


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _fmt_paths(paths: list[Any]) -> list[str]:
    formatted: list[str] = []
    cwd = Path.cwd().resolve()
    for item in paths:
        text = str(item)
        try:
            path = Path(text)
            formatted.append(path.resolve().relative_to(cwd).as_posix() if path.is_absolute() else text)
        except (OSError, ValueError):
            formatted.append(text)
    return formatted
