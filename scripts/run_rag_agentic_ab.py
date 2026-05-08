from __future__ import annotations

import argparse
import json
import os
import shutil
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.core.settings import get_settings
from app.db.session import get_engine, get_session_factory
from app.main import create_app
from app.rag.evaluation.metrics import evaluate_case, summarize_cases


NUMERIC_SUMMARY_KEYS = (
    "recall_at_k",
    "precision_at_k",
    "precision_at_retrieved",
    "labeled_precision_ceiling",
    "normalized_precision_at_k",
    "hit_at_k",
    "top1_accuracy",
    "mrr",
    "ndcg_at_k",
    "route_accuracy",
    "language_accuracy",
    "citation_coverage",
    "low_confidence_ratio",
    "no_result_ratio",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare baseline RAG with Agentic RAG query refinement."
    )
    parser.add_argument(
        "--dataset",
        action="append",
        dest="datasets",
        help="JSONL RAG dataset path. Can be passed multiple times.",
    )
    parser.add_argument(
        "--source-path",
        action="append",
        dest="source_paths",
        help="Optional KB source path override. Can be passed multiple times.",
    )
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument(
        "--output",
        default="storage/artifacts/evals/rag-agentic-ab-latest.json",
        help="Path for the JSON report.",
    )
    parser.add_argument(
        "--markdown-output",
        default="docs/rag-agentic-ab-report.md",
        help="Path for the Markdown report.",
    )
    parser.add_argument(
        "--max-hit-drop",
        type=float,
        default=0.0,
        help="Fail if Agentic RAG hit@k drops below baseline by more than this value.",
    )
    return parser.parse_args()


def _default_datasets() -> list[Path]:
    return [
        Path("tests/eval/rag_project_qa_dataset.jsonl"),
        Path("tests/eval/rag_ue_knowledge_dataset.jsonl"),
        Path("tests/eval/rag_agentic_ab_dataset.jsonl"),
    ]


def _resolve_dataset_paths(items: list[str] | None) -> list[Path]:
    return [Path(item).resolve() for item in items] if items else [item.resolve() for item in _default_datasets()]


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


@contextmanager
def _isolated_runtime(source_paths: list[str]) -> Iterator[None]:
    runtime_path = Path(".eval-runtime") / f"rag-agentic-ab-{uuid.uuid4().hex}"
    storage_dir = runtime_path / "storage"
    shutil.rmtree(runtime_path, ignore_errors=True)
    storage_dir.mkdir(parents=True, exist_ok=True)
    overrides = {
        "DATABASE_URL": "sqlite+pysqlite:///:memory:",
        "STORAGE_DIR": str(storage_dir.resolve()),
        "UPLOAD_DIR": str((storage_dir / "uploads").resolve()),
        "ARTIFACT_DIR": str((storage_dir / "artifacts").resolve()),
        "KB_DIR": str((storage_dir / "kb").resolve()),
        "KB_SOURCE_PATHS": ",".join(source_paths),
        "EMBEDDING_ENABLED": "false",
        "RAG_MODE": "lexical",
        "RAG_FALLBACK_MODE": "lexical_only",
        "OPENAI_API_KEY": "",
        "OPENAI_BASE_URL": "",
    }
    previous = {key: os.environ.get(key) for key in overrides}
    for key, value in overrides.items():
        os.environ[key] = value
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()
        get_engine.cache_clear()
        get_session_factory.cache_clear()
        shutil.rmtree(runtime_path, ignore_errors=True)


def _build_request(case: dict[str, Any], *, disable_agentic_rag: bool) -> dict[str, Any]:
    query = case["query"]
    domain_filters = case.get("domain_filters", ["project_docs"])
    return {
        "task_type": "project_qa",
        "session": {
            "session_id": f"ab_{case['case_id']}_{uuid.uuid4().hex[:8]}",
            "messages": [{"role": "user", "content": query, "language": "auto"}],
        },
        "context": {
            "project_name": "UEAgentBackend",
            "active_panel": "AgentChat",
            "current_file": case.get("current_file"),
            "kb_domains_hint": domain_filters,
        },
        "payload": {
            "user_query": query,
            "domain_filters": domain_filters,
            "disable_agentic_rag": disable_agentic_rag,
        },
        "ui_state": {"active_view": "user", "selected_panel": "ProjectQA"},
        "runtime_options": {
            "profile_id": "default",
            "stream": False,
            "debug": True,
            "preferred_output_language": "auto",
            "return_debug_projection": True,
        },
    }


def _timed_eval(
    *,
    client: TestClient,
    case: dict[str, Any],
    top_k: int,
    disable_agentic_rag: bool,
) -> dict[str, Any]:
    start = time.perf_counter()
    response = client.post(
        "/api/v1/tasks/project-qa",
        json=_build_request(case, disable_agentic_rag=disable_agentic_rag),
    )
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    if response.status_code != 200:
        raise SystemExit(
            f"Case {case['case_id']} failed with {response.status_code}: {response.text}"
        )
    body = response.json()
    result = evaluate_case(case, body, top_k=top_k)
    retrieval_trace = dict(body.get("retrieval_trace") or {})
    agentic_rag = dict(retrieval_trace.get("agentic_rag") or {})
    result["latency_ms"] = latency_ms
    result["agentic_rag"] = {
        "enabled": agentic_rag.get("enabled", False),
        "selected_round": agentic_rag.get("selected_round"),
        "selected_query": agentic_rag.get("selected_query"),
        "evidence_sufficient": agentic_rag.get("evidence_sufficient"),
        "final_reason": agentic_rag.get("final_reason"),
        "rewrite_used": any(
            bool(item.get("rewrite_applied")) for item in agentic_rag.get("attempts", [])
        ),
    }
    result["retrieval_quality_gate"] = (
        body.get("data", {}).get("retrieval_quality_gate")
        or retrieval_trace.get("retrieval_quality_gate")
        or {}
    )
    return result


def _delta_summary(agentic: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    delta: dict[str, float] = {}
    for key in NUMERIC_SUMMARY_KEYS:
        if key in agentic and key in baseline:
            delta[key] = round(float(agentic[key]) - float(baseline[key]), 4)
    return delta


def _metric_delta(agentic: dict[str, Any], baseline: dict[str, Any], key: str) -> float:
    return round(
        float(agentic.get("metrics", {}).get(key, 0.0))
        - float(baseline.get("metrics", {}).get(key, 0.0)),
        4,
    )


def build_comparison_report(
    *,
    dataset_paths: list[Path],
    source_paths: list[str],
    top_k: int,
    baseline_results: list[dict[str, Any]],
    agentic_results: list[dict[str, Any]],
) -> dict[str, Any]:
    baseline_summary = summarize_cases(baseline_results)
    agentic_summary = summarize_cases(agentic_results)
    cases: list[dict[str, Any]] = []
    for baseline, agentic in zip(baseline_results, agentic_results, strict=True):
        cases.append(
            {
                "dataset": agentic.get("dataset"),
                "case_id": agentic["case_id"],
                "query": agentic["query"],
                "baseline": baseline,
                "agentic": agentic,
                "delta": {
                    "hit_at_k": _metric_delta(agentic, baseline, "hit_at_k"),
                    "top1_accuracy": _metric_delta(agentic, baseline, "top1_accuracy"),
                    "mrr": _metric_delta(agentic, baseline, "mrr"),
                    "ndcg_at_k": _metric_delta(agentic, baseline, "ndcg_at_k"),
                },
            }
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "comparison": "baseline_rag_vs_agentic_rag",
        "datasets": [str(path) for path in dataset_paths],
        "source_paths": source_paths,
        "top_k": top_k,
        "baseline": {
            "label": "baseline_rag",
            "payload_overrides": {"disable_agentic_rag": True},
            "summary": baseline_summary,
        },
        "agentic": {
            "label": "agentic_rag",
            "payload_overrides": {"disable_agentic_rag": False},
            "summary": agentic_summary,
        },
        "delta": _delta_summary(agentic_summary, baseline_summary),
        "cases": cases,
        "notes": [
            "This is an offline deterministic A/B evaluation for interview demonstration.",
            "Agentic RAG uses at most one query rewrite round after weak first-round evidence.",
            "No live LLM, embedding model, or Qdrant connection is required for this report.",
        ],
    }


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def build_markdown_report(report: dict[str, Any]) -> str:
    baseline = dict(report["baseline"]["summary"])
    agentic = dict(report["agentic"]["summary"])
    delta = dict(report["delta"])
    lines = [
        "# Agentic RAG A/B Report",
        "",
        "## Summary",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Datasets: `{', '.join(report['datasets'])}`",
        f"- Source paths: `{', '.join(report['source_paths'])}`",
        f"- Top K: `{report['top_k']}`",
        "",
        "| Metric | Baseline RAG | Agentic RAG | Delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for key in NUMERIC_SUMMARY_KEYS:
        if key in baseline and key in agentic:
            lines.append(
                f"| `{key}` | {_fmt(baseline[key])} | {_fmt(agentic[key])} | {_fmt(delta.get(key, 0.0))} |"
            )

    lines.extend(
        [
            "",
            "## Cases",
            "",
            "| Case | Hit Delta | Top1 Delta | MRR Delta | Agentic Round | Rewrite Used | Selected Query |",
            "| --- | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for case in report["cases"]:
        agentic_rag = case["agentic"].get("agentic_rag") or {}
        selected_query = str(agentic_rag.get("selected_query") or "").replace("|", "\\|")
        if len(selected_query) > 120:
            selected_query = selected_query[:117] + "..."
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{case['case_id']}`",
                    _fmt(case["delta"]["hit_at_k"]),
                    _fmt(case["delta"]["top1_accuracy"]),
                    _fmt(case["delta"]["mrr"]),
                    _fmt(agentic_rag.get("selected_round") or 0),
                    str(bool(agentic_rag.get("rewrite_used"))),
                    selected_query or "-",
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Positive deltas mean Agentic RAG improved retrieval for the labeled dataset.",
            "- Zero deltas with stable quality are still useful: the refinement layer did not regress existing retrieval.",
            "- If a case shows `rewrite_used=True`, the second retrieval round was exercised.",
            "- This report is local/offline and is intentionally not a production A/B platform.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = _parse_args()
    dataset_paths = _resolve_dataset_paths(args.datasets)
    for dataset_path in dataset_paths:
        if not dataset_path.exists():
            raise SystemExit(f"Dataset not found: {dataset_path}")

    cases: list[dict[str, Any]] = []
    for dataset_path in dataset_paths:
        for case in _load_jsonl(dataset_path):
            cases.append({**case, "dataset": dataset_path.name})

    source_paths = args.source_paths or ["./README.md", "./docs", "./knowledge"]
    with _isolated_runtime(source_paths):
        with TestClient(create_app()) as client:
            refresh = client.post(
                "/api/v1/knowledge-base/refresh",
                json={"source_paths": source_paths, "force_rebuild": True},
            )
            if refresh.status_code != 200:
                raise SystemExit(
                    f"KB refresh failed with {refresh.status_code}: {refresh.text}"
                )

            baseline_results: list[dict[str, Any]] = []
            agentic_results: list[dict[str, Any]] = []
            for case in cases:
                baseline_results.append(
                    _timed_eval(
                        client=client,
                        case=case,
                        top_k=args.top_k,
                        disable_agentic_rag=True,
                    )
                )
                baseline_results[-1]["dataset"] = case["dataset"]
                agentic_results.append(
                    _timed_eval(
                        client=client,
                        case=case,
                        top_k=args.top_k,
                        disable_agentic_rag=False,
                    )
                )
                agentic_results[-1]["dataset"] = case["dataset"]

    report = build_comparison_report(
        dataset_paths=dataset_paths,
        source_paths=source_paths,
        top_k=args.top_k,
        baseline_results=baseline_results,
        agentic_results=agentic_results,
    )
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_output_path = Path(args.markdown_output).resolve()
    markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_output_path.write_text(build_markdown_report(report), encoding="utf-8")

    print(json.dumps(report["delta"], ensure_ascii=False, indent=2))
    print(f"Saved A/B report to: {output_path}")
    print(f"Saved Markdown report to: {markdown_output_path}")
    if report["delta"].get("hit_at_k", 0.0) < -abs(args.max_hit_drop):
        raise SystemExit(
            "Agentic RAG hit@k regressed by "
            f"{report['delta']['hit_at_k']}, threshold {-abs(args.max_hit_drop)}."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
