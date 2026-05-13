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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the offline UE C++ code-review benchmark.")
    parser.add_argument(
        "--dataset",
        default="tests/eval/code_review_benchmark_dataset.jsonl",
        help="JSONL benchmark dataset path.",
    )
    parser.add_argument(
        "--output",
        default="storage/artifacts/evals/code-review-benchmark-latest.json",
        help="JSON output path.",
    )
    parser.add_argument(
        "--markdown-output",
        default="docs/code-review-benchmark-report.md",
        help="Markdown report output path.",
    )
    parser.add_argument(
        "--min-recall",
        type=float,
        default=0.0,
        help="Optional failure threshold for aggregate single-review recall.",
    )
    parser.add_argument(
        "--min-precision",
        type=float,
        default=0.0,
        help="Optional failure threshold for aggregate single-review precision.",
    )
    return parser.parse_args()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        text = line.strip()
        if text:
            rows.append(json.loads(text))
    return rows


@contextmanager
def _isolated_runtime() -> Iterator[None]:
    runtime_path = Path(".eval-runtime") / f"code-review-benchmark-{uuid.uuid4().hex}"
    storage_dir = runtime_path / "storage"
    shutil.rmtree(runtime_path, ignore_errors=True)
    storage_dir.mkdir(parents=True, exist_ok=True)
    overrides = {
        "DATABASE_URL": "sqlite+pysqlite:///:memory:",
        "STORAGE_DIR": str(storage_dir.resolve()),
        "UPLOAD_DIR": str((storage_dir / "uploads").resolve()),
        "ARTIFACT_DIR": str((storage_dir / "artifacts").resolve()),
        "KB_DIR": str((storage_dir / "kb").resolve()),
        "KB_SOURCE_PATHS": "./knowledge",
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


def _request_payload(case: dict[str, Any], *, multi_agent: bool) -> dict[str, Any]:
    return {
        "task_type": "code_review",
        "session": {
            "session_id": f"benchmark_{case['case_id']}_{'chain' if multi_agent else 'single'}",
            "messages": [
                {
                    "role": "user",
                    "content": "Review this Unreal Engine C++ snippet.",
                    "language": "auto",
                }
            ],
        },
        "context": {
            "project_name": "BenchmarkProject",
            "active_panel": "CodeReview",
            "current_file": f"Source/Benchmark/{case['case_id']}.cpp",
            "current_module": "Benchmark",
        },
        "payload": {
            "user_query": "Review this Unreal Engine C++ snippet.",
            "code": case["code"],
            "focus": case.get("description") or "General UE C++ review",
            "enable_multi_agent": multi_agent,
        },
        "ui_state": {"active_view": "user", "selected_panel": "CodeReview"},
        "runtime_options": {
            "profile_id": "default",
            "stream": False,
            "debug": True,
            "preferred_output_language": "en",
            "return_debug_projection": True,
        },
    }


def _timed_post(client: TestClient, payload: dict[str, Any]) -> tuple[dict[str, Any], float]:
    start = time.perf_counter()
    response = client.post("/api/v1/tasks/code-review", json=payload)
    duration_ms = (time.perf_counter() - start) * 1000
    if response.status_code != 200:
        raise SystemExit(f"Code-review benchmark failed with {response.status_code}: {response.text}")
    return response.json(), duration_ms


def _rule_hits(response: dict[str, Any], *, multi_agent: bool) -> set[str]:
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    if multi_agent:
        review_phase = data.get("review_phase") if isinstance(data.get("review_phase"), dict) else {}
        return {str(item) for item in review_phase.get("rule_hits", [])}
    return {str(item) for item in data.get("rule_hits", [])}


def _metric_counts(expected: set[str], actual: set[str]) -> dict[str, int]:
    return {
        "tp": len(expected & actual),
        "fp": len(actual - expected),
        "fn": len(expected - actual),
    }


def _safe_ratio(numerator: int | float, denominator: int | float, *, empty_value: float = 1.0) -> float:
    if denominator == 0:
        return empty_value
    return round(float(numerator) / float(denominator), 4)


def _case_metrics(expected: set[str], actual: set[str]) -> dict[str, Any]:
    counts = _metric_counts(expected, actual)
    return {
        **counts,
        "expected": sorted(expected),
        "actual": sorted(actual),
        "missing": sorted(expected - actual),
        "extra": sorted(actual - expected),
        "recall": _safe_ratio(counts["tp"], len(expected), empty_value=1.0 if not actual else 0.0),
        "precision": _safe_ratio(counts["tp"], len(actual), empty_value=1.0 if not expected else 0.0),
    }


def _aggregate_counts(results: list[dict[str, Any]], key: str) -> dict[str, Any]:
    tp = sum(int(item[key]["tp"]) for item in results)
    fp = sum(int(item[key]["fp"]) for item in results)
    fn = sum(int(item[key]["fn"]) for item in results)
    clean_cases = [item for item in results if not item[key]["expected"]]
    clean_pass = sum(1 for item in clean_cases if not item[key]["actual"])
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "recall": _safe_ratio(tp, tp + fn, empty_value=1.0),
        "precision": _safe_ratio(tp, tp + fp, empty_value=1.0),
        "false_positive_rate": _safe_ratio(fp, tp + fp, empty_value=0.0),
        "clean_case_accuracy": _safe_ratio(clean_pass, len(clean_cases), empty_value=1.0),
    }


def _chain_metrics(response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    chain = data.get("multi_agent") if isinstance(data.get("multi_agent"), dict) else {}
    phases = chain.get("phases") if isinstance(chain.get("phases"), list) else []
    validate_phase = data.get("validate_phase") if isinstance(data.get("validate_phase"), dict) else {}
    generated_items = data.get("generated_items") if isinstance(data.get("generated_items"), list) else []
    return {
        "status": chain.get("status"),
        "phase_statuses": {str(item.get("node_id")): item.get("status") for item in phases if isinstance(item, dict)},
        "phase_latency_ms": {
            str(item.get("node_id")): int(item.get("latency_ms") or 0)
            for item in phases
            if isinstance(item, dict)
        },
        "generated_count": len(generated_items),
        "validation_issue_count": len(validate_phase.get("issue_list") or []),
    }


def _summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    single = _aggregate_counts(results, "single_metrics")
    chain = _aggregate_counts(results, "chain_metrics")
    single_detected = sum(len(item["single_metrics"]["actual"]) for item in results)
    chain_detected = sum(len(item["chain_metrics"]["actual"]) for item in results)
    generated_cases = sum(1 for item in results if item["chain_runtime"]["generated_count"] > 0)
    validation_issue_count = sum(item["chain_runtime"]["validation_issue_count"] for item in results)
    generated_count = sum(item["chain_runtime"]["generated_count"] for item in results)
    single_latency = [float(item["latency_ms"]["single"]) for item in results]
    chain_latency = [float(item["latency_ms"]["chain"]) for item in results]
    known_limitation_cases = [item for item in results if item.get("known_limitation")]
    return {
        "cases": len(results),
        "single_review": single,
        "multi_agent_review_phase": chain,
        "known_limitations": {
            "case_count": len(known_limitation_cases),
            "single_missing_rule_count": sum(int(item["single_metrics"]["fn"]) for item in known_limitation_cases),
            "chain_missing_rule_count": sum(int(item["chain_metrics"]["fn"]) for item in known_limitation_cases),
            "note": "Known limitation cases are intentionally included to make the benchmark reflect current lightweight-rule boundaries.",
        },
        "multi_agent_incremental_benefit": {
            "review_detection_ratio": _safe_ratio(chain_detected, single_detected, empty_value=1.0),
            "generated_draft_case_rate": _safe_ratio(generated_cases, len(results), empty_value=0.0),
            "validation_issue_per_generated_file": _safe_ratio(validation_issue_count, generated_count, empty_value=0.0),
            "note": "The chain intentionally reuses the same review detector; extra value is measured by fix-draft and validation coverage.",
        },
        "latency_ms": {
            "single_avg": round(sum(single_latency) / len(single_latency), 2) if single_latency else 0.0,
            "chain_avg": round(sum(chain_latency) / len(chain_latency), 2) if chain_latency else 0.0,
            "single_max": round(max(single_latency), 2) if single_latency else 0.0,
            "chain_max": round(max(chain_latency), 2) if chain_latency else 0.0,
        },
        "llm_hallucination_rate": None,
        "llm_hallucination_note": "Offline benchmark disables LLM calls; use a separate live LLM eval set to measure hallucination.",
    }


def _build_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Code Review Benchmark Report",
        "",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Dataset: `{payload['dataset']}`",
        f"- Cases: `{summary['cases']}`",
        "- LLM mode: `disabled/offline`",
        "",
        "## Aggregate Metrics",
        "",
        "| Metric | Single Review | Multi-Agent Review Phase |",
        "| --- | ---: | ---: |",
        f"| Recall | {summary['single_review']['recall']} | {summary['multi_agent_review_phase']['recall']} |",
        f"| Precision | {summary['single_review']['precision']} | {summary['multi_agent_review_phase']['precision']} |",
        f"| False positive rate | {summary['single_review']['false_positive_rate']} | {summary['multi_agent_review_phase']['false_positive_rate']} |",
        f"| Clean-case accuracy | {summary['single_review']['clean_case_accuracy']} | {summary['multi_agent_review_phase']['clean_case_accuracy']} |",
        "",
        "## Known Limitations Included",
        "",
        f"- Cases: `{summary['known_limitations']['case_count']}`",
        f"- Single-review missing expected rule families in known limitations: `{summary['known_limitations']['single_missing_rule_count']}`",
        f"- Multi-agent missing expected rule families in known limitations: `{summary['known_limitations']['chain_missing_rule_count']}`",
        f"- Note: {summary['known_limitations']['note']}",
        "",
        "## Chain Value",
        "",
        f"- Review detection ratio: `{summary['multi_agent_incremental_benefit']['review_detection_ratio']}`",
        f"- Generated draft case rate: `{summary['multi_agent_incremental_benefit']['generated_draft_case_rate']}`",
        f"- Validation issues per generated file: `{summary['multi_agent_incremental_benefit']['validation_issue_per_generated_file']}`",
        f"- Note: {summary['multi_agent_incremental_benefit']['note']}",
        "",
        "## Latency",
        "",
        "| Metric | Single Review | Multi-Agent Chain |",
        "| --- | ---: | ---: |",
        f"| Average latency ms | {summary['latency_ms']['single_avg']} | {summary['latency_ms']['chain_avg']} |",
        f"| Max latency ms | {summary['latency_ms']['single_max']} | {summary['latency_ms']['chain_max']} |",
        "",
        "## LLM Hallucination",
        "",
        f"- Rate: `{summary['llm_hallucination_rate']}`",
        f"- Note: {summary['llm_hallucination_note']}",
        "",
        "## Per-Case Details",
        "",
        "| Case | Type | Expected | Single actual | Single R/P | Chain actual | Chain R/P | Chain status |",
        "| --- | --- | --- | --- | ---: | --- | ---: | --- |",
    ]
    for item in payload["cases"]:
        expected = ", ".join(item["single_metrics"]["expected"]) or "-"
        single_actual = ", ".join(item["single_metrics"]["actual"]) or "-"
        chain_actual = ", ".join(item["chain_metrics"]["actual"]) or "-"
        single_score = f"{item['single_metrics']['recall']}/{item['single_metrics']['precision']}"
        chain_score = f"{item['chain_metrics']['recall']}/{item['chain_metrics']['precision']}"
        case_type = "known_limitation" if item.get("known_limitation") else str(item.get("case_type") or "regression")
        lines.append(
            "| "
            + " | ".join(
                [
                    item["case_id"],
                    case_type,
                    expected,
                    single_actual,
                    single_score,
                    chain_actual,
                    chain_score,
                    str(item["chain_runtime"]["status"]),
                ]
            )
            + " |"
        )
    known_items = [item for item in payload["cases"] if item.get("known_limitation")]
    if known_items:
        lines.extend(["", "## Known Limitation Case Notes", ""])
        for item in known_items:
            missing = ", ".join(item["single_metrics"]["missing"]) or "-"
            lines.append(
                f"- `{item['case_id']}` missing `{missing}`: {item.get('notes') or item.get('description') or 'Known lightweight-rule boundary.'}"
            )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This benchmark is designed for local, deterministic regression checks and does not require an API key.",
            "- Recall/precision measure rule-family detection against synthetic UE C++ snippets.",
            "- Multi-agent detection is expected to match single review because the chain reuses the same reviewer before fix generation and validation.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = _parse_args()
    dataset_path = Path(args.dataset).resolve()
    if not dataset_path.exists():
        raise SystemExit(f"Dataset not found: {dataset_path}")

    cases = _load_jsonl(dataset_path)
    results: list[dict[str, Any]] = []
    with _isolated_runtime():
        with TestClient(create_app()) as client:
            for case in cases:
                expected = {str(item) for item in case.get("expected_rule_hits", [])}
                single_response, single_ms = _timed_post(client, _request_payload(case, multi_agent=False))
                chain_response, chain_ms = _timed_post(client, _request_payload(case, multi_agent=True))
                single_actual = _rule_hits(single_response, multi_agent=False)
                chain_actual = _rule_hits(chain_response, multi_agent=True)
                results.append(
                    {
                        "case_id": case["case_id"],
                        "description": case.get("description") or "",
                        "case_type": case.get("case_type") or "regression",
                        "known_limitation": bool(case.get("known_limitation")),
                        "notes": case.get("notes") or "",
                        "single_metrics": _case_metrics(expected, single_actual),
                        "chain_metrics": _case_metrics(expected, chain_actual),
                        "chain_runtime": _chain_metrics(chain_response),
                        "latency_ms": {
                            "single": round(single_ms, 2),
                            "chain": round(chain_ms, 2),
                        },
                    }
                )

    output = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": str(Path(args.dataset)),
        "summary": _summarize(results),
        "cases": results,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = Path(args.markdown_output)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_build_markdown(output), encoding="utf-8")

    single_summary = output["summary"]["single_review"]
    if single_summary["recall"] < args.min_recall:
        raise SystemExit(f"Recall below threshold: {single_summary['recall']} < {args.min_recall}")
    if single_summary["precision"] < args.min_precision:
        raise SystemExit(f"Precision below threshold: {single_summary['precision']} < {args.min_precision}")

    print(f"Wrote JSON: {output_path}")
    print(f"Wrote Markdown: {markdown_path}")
    print(
        "single_review recall="
        f"{single_summary['recall']} precision={single_summary['precision']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
