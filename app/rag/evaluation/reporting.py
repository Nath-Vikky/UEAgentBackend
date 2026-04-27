from __future__ import annotations

from pathlib import Path
from typing import Any


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _fmt_path(value: Any) -> str:
    if not value:
        return ""
    path_text = str(value)
    try:
        path = Path(path_text)
        if path.is_absolute():
            return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return path_text
    return path_text


def build_markdown_report(report: dict[str, Any]) -> str:
    summary = dict(report.get("summary") or {})
    cases = list(report.get("cases") or [])
    lines = [
        "# RAG Eval Report",
        "",
        "## Summary",
        "",
        f"- Generated at: `{report.get('generated_at')}`",
        f"- Dataset: `{_fmt_path(report.get('dataset_path'))}`",
        f"- Source paths: `{', '.join(report.get('source_paths') or [])}`",
        f"- Top K: `{report.get('top_k')}`",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key in (
        "cases",
        "recall_at_k",
        "precision_at_k",
        "hit_at_k",
        "mrr",
        "ndcg_at_k",
        "route_accuracy",
        "language_accuracy",
        "citation_coverage",
        "low_confidence_ratio",
        "no_result_ratio",
    ):
        if key in summary:
            lines.append(f"| `{key}` | {_fmt(summary[key])} |")

    lines.extend(
        [
            "",
            "## Cases",
            "",
            "| Case | Route | Language | Confidence | Hit@K | MRR | Matched Sources |",
            "| --- | --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for case in cases:
        metrics = dict(case.get("metrics") or {})
        matched_sources = ", ".join(case.get("matched_sources") or []) or "-"
        route_status = "ok" if case.get("route_ok") else f"expected {case.get('expected_route')}"
        language_status = (
            "ok"
            if case.get("language_ok")
            else f"expected {case.get('expected_language')}"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{case.get('case_id')}`",
                    route_status,
                    language_status,
                    _fmt(case.get("confidence", 0.0)),
                    _fmt(metrics.get("hit_at_k", 0.0)),
                    _fmt(metrics.get("mrr", 0.0)),
                    matched_sources,
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This is an offline local evaluation for portfolio/interview demonstration.",
            "- Metrics focus on retrieval hit quality, routing correctness, citation coverage, and low-confidence detection.",
            "- It is not an online production monitoring or A/B testing system.",
            "",
        ]
    )
    return "\n".join(lines)
