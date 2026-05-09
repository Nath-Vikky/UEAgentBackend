from __future__ import annotations

import argparse
import json
import os
import shutil
import time
import uuid
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.core.settings import get_settings
from app.db.session import get_engine, get_session_factory
from app.evaluation.benchmark_report import build_benchmark_markdown, summarize_latency
from app.evaluation.hallucination_metrics import (
    evaluate_hallucination_case,
    summarize_hallucination_cases,
)
from app.evaluation.task_metrics import evaluate_task_case, summarize_task_cases
from app.main import create_app
from app.rag.evaluation.metrics import evaluate_case, summarize_cases


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run UE Agent local benchmark suite.")
    parser.add_argument("--rag-dataset", action="append", dest="rag_datasets")
    parser.add_argument("--task-dataset", action="append", dest="task_datasets")
    parser.add_argument("--hallucination-dataset", dest="hallucination_dataset")
    parser.add_argument("--source-path", action="append", dest="source_paths")
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--output", help="Optional JSON output path.")
    parser.add_argument("--markdown-output", help="Optional Markdown output path.")
    parser.add_argument("--min-recall-at-k", type=float, default=0.0)
    parser.add_argument("--min-precision-at-k", type=float, default=0.0)
    parser.add_argument("--min-route-accuracy", type=float, default=0.0)
    parser.add_argument("--min-task-success-rate", type=float, default=0.0)
    parser.add_argument(
        "--use-live-llm",
        action="store_true",
        help="Use local .env LLM settings. Default benchmark disables live LLM calls for reproducibility.",
    )
    return parser.parse_args()


def _default_rag_datasets() -> list[Path]:
    return [
        Path("tests/eval/rag_project_qa_dataset.jsonl"),
        Path("tests/eval/rag_ue_knowledge_dataset.jsonl"),
    ]


def _default_task_datasets() -> list[Path]:
    return [
        Path("tests/eval/intent_language_dataset.jsonl"),
        Path("tests/eval/code_generate_dataset.jsonl"),
        Path("tests/eval/code_review_dataset.jsonl"),
        Path("tests/eval/logs_analyze_dataset.jsonl"),
        Path("tests/eval/config_task_dataset.jsonl"),
    ]


def _default_hallucination_dataset() -> Path:
    return Path("tests/eval/hallucination_guard_dataset.jsonl")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        text = line.strip()
        if text:
            rows.append(json.loads(text))
    return rows


@contextmanager
def _isolated_runtime(*, source_paths: list[str], use_live_llm: bool) -> Iterator[None]:
    runtime_path = Path(".eval-runtime") / f"project-benchmark-{uuid.uuid4().hex}"
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
    }
    if not use_live_llm:
        overrides["OPENAI_API_KEY"] = ""
        overrides["OPENAI_BASE_URL"] = ""
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


def _rag_request(case: dict[str, Any]) -> dict[str, Any]:
    query = case["query"]
    domain_filters = case.get("domain_filters", ["project_docs"])
    return {
        "task_type": "project_qa",
        "session": {
            "session_id": f"benchmark_rag_{case['case_id']}_{uuid.uuid4().hex[:8]}",
            "messages": [{"role": "user", "content": query, "language": "auto"}],
        },
        "context": {
            "project_name": "UEAgentBackend",
            "active_panel": "AgentChat",
            "current_file": case.get("current_file"),
            "kb_domains_hint": domain_filters,
        },
        "payload": {"user_query": query, "domain_filters": domain_filters},
        "ui_state": {"active_view": "user", "selected_panel": "ProjectQA"},
        "runtime_options": {
            "profile_id": "default",
            "stream": False,
            "debug": True,
            "preferred_output_language": "auto",
            "return_debug_projection": True,
        },
    }


def _hallucination_request(case: dict[str, Any]) -> dict[str, Any]:
    query = case["query"]
    domain_filters = case.get("domain_filters", ["project_docs"])
    return {
        "task_type": "project_qa",
        "session": {
            "session_id": f"benchmark_hallucination_{case['case_id']}_{uuid.uuid4().hex[:8]}",
            "messages": [{"role": "user", "content": query, "language": "auto"}],
        },
        "context": {
            "project_name": "UEAgentBackend",
            "active_panel": "AgentChat",
            "current_file": case.get("current_file"),
            "kb_domains_hint": domain_filters,
        },
        "payload": {"user_query": query, "domain_filters": domain_filters},
        "ui_state": {"active_view": "user", "selected_panel": "ProjectQA"},
        "runtime_options": {
            "profile_id": "default",
            "stream": False,
            "debug": True,
            "preferred_output_language": "auto",
            "return_debug_projection": True,
        },
    }


def _default_output_path() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("storage/artifacts/evals") / f"project-benchmark-{stamp}.json"


def _resolve_paths(items: list[str] | None, defaults: list[Path]) -> list[Path]:
    return [Path(item).resolve() for item in items] if items else [item.resolve() for item in defaults]


def _timed_post(client: TestClient, endpoint: str, payload: dict[str, Any]) -> tuple[Any, float]:
    start = time.perf_counter()
    response = client.post(endpoint, json=payload)
    duration_ms = (time.perf_counter() - start) * 1000
    return response, duration_ms


def main() -> int:
    args = _parse_args()
    rag_dataset_paths = _resolve_paths(args.rag_datasets, _default_rag_datasets())
    task_dataset_paths = _resolve_paths(args.task_datasets, _default_task_datasets())
    hallucination_dataset_path = (
        Path(args.hallucination_dataset).resolve()
        if args.hallucination_dataset
        else _default_hallucination_dataset().resolve()
    )
    for dataset_path in [*rag_dataset_paths, *task_dataset_paths, hallucination_dataset_path]:
        if not dataset_path.exists():
            raise SystemExit(f"Dataset not found: {dataset_path}")

    source_paths = args.source_paths or ["./README.md", "./docs", "./knowledge"]

    with _isolated_runtime(source_paths=source_paths, use_live_llm=args.use_live_llm):
        with TestClient(create_app()) as client:
            refresh_start = time.perf_counter()
            refresh = client.post(
                "/api/v1/knowledge-base/refresh",
                json={"source_paths": source_paths, "force_rebuild": True},
            )
            kb_refresh_ms = (time.perf_counter() - refresh_start) * 1000
            if refresh.status_code != 200:
                raise SystemExit(f"KB refresh failed with {refresh.status_code}: {refresh.text}")

            latency_samples: list[dict[str, Any]] = []
            rag_results: list[dict[str, Any]] = []
            rag_dataset_results: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for dataset_path in rag_dataset_paths:
                for case in _load_jsonl(dataset_path):
                    response, duration_ms = _timed_post(
                        client, "/api/v1/tasks/project-qa", _rag_request(case)
                    )
                    latency_samples.append(
                        {
                            "case_id": case["case_id"],
                            "endpoint": "/api/v1/tasks/project-qa",
                            "duration_ms": duration_ms,
                        }
                    )
                    if response.status_code != 200:
                        raise SystemExit(
                            f"RAG case {case['case_id']} failed with {response.status_code}: {response.text}"
                        )
                    result = evaluate_case(
                        {**case, "dataset": dataset_path.name},
                        response.json(),
                        top_k=args.top_k,
                    )
                    rag_results.append(result)
                    rag_dataset_results[dataset_path.name].append(result)

            task_results: list[dict[str, Any]] = []
            task_dataset_results: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for dataset_path in task_dataset_paths:
                for case in _load_jsonl(dataset_path):
                    response, duration_ms = _timed_post(client, case["endpoint"], case["request"])
                    latency_samples.append(
                        {
                            "case_id": case["case_id"],
                            "endpoint": case["endpoint"],
                            "duration_ms": duration_ms,
                        }
                    )
                    if response.status_code != 200:
                        raise SystemExit(
                            f"Task case {case['case_id']} failed with {response.status_code}: {response.text}"
                        )
                    result = evaluate_task_case(
                        {**case, "dataset": dataset_path.name},
                        response.json(),
                    )
                    task_results.append(result)
                    task_dataset_results[dataset_path.name].append(result)

            hallucination_results: list[dict[str, Any]] = []
            for case in _load_jsonl(hallucination_dataset_path):
                response, duration_ms = _timed_post(
                    client, "/api/v1/tasks/project-qa", _hallucination_request(case)
                )
                latency_samples.append(
                    {
                        "case_id": case["case_id"],
                        "endpoint": "/api/v1/tasks/project-qa",
                        "duration_ms": duration_ms,
                    }
                )
                if response.status_code != 200:
                    raise SystemExit(
                        f"Hallucination case {case['case_id']} failed with {response.status_code}: {response.text}"
                    )
                hallucination_results.append(evaluate_hallucination_case(case, response.json()))

            status_response = client.get("/api/v1/knowledge-base/status")
            knowledge_base = status_response.json().get("summary", {}) if status_response.status_code == 200 else {}

    rag_summary = summarize_cases(rag_results)
    task_summary = summarize_task_cases(task_results)
    hallucination_summary = summarize_hallucination_cases(hallucination_results)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_paths": source_paths,
        "top_k": args.top_k,
        "rag_datasets": [str(path) for path in rag_dataset_paths],
        "task_datasets": [str(path) for path in task_dataset_paths],
        "hallucination_dataset": str(hallucination_dataset_path),
        "rag_summary": rag_summary,
        "rag_datasets_summary": {
            name: summarize_cases(results) for name, results in rag_dataset_results.items()
        },
        "task_summary": task_summary,
        "hallucination_summary": hallucination_summary,
        "task_datasets_summary": {
            name: summarize_task_cases(results) for name, results in task_dataset_results.items()
        },
        "performance": summarize_latency(latency_samples),
        "kb_refresh_ms": round(kb_refresh_ms, 2),
        "llm_mode": "live" if args.use_live_llm else "offline_fallback",
        "knowledge_base": knowledge_base,
        "rag_cases": rag_results,
        "task_cases": task_results,
        "hallucination_cases": hallucination_results,
        "latency_samples": [
            {**item, "duration_ms": round(float(item["duration_ms"]), 2)}
            for item in latency_samples
        ],
    }

    output_path = Path(args.output).resolve() if args.output else _default_output_path().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_output_path = Path(args.markdown_output).resolve() if args.markdown_output else None
    if markdown_output_path:
        markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_output_path.write_text(build_benchmark_markdown(report), encoding="utf-8")

    print(
        json.dumps(
            {
                **rag_summary,
                **{
                    "task_success_rate": task_summary["success_rate"],
                    "hallucination_guard_accuracy": hallucination_summary[
                        "grounding_accuracy"
                    ],
                    "unsupported_answer_rate": hallucination_summary[
                        "unsupported_answer_rate"
                    ],
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"Saved benchmark report to: {output_path}")
    if markdown_output_path:
        print(f"Saved Markdown benchmark to: {markdown_output_path}")

    if rag_summary["recall_at_k"] < args.min_recall_at_k:
        raise SystemExit("Benchmark recall_at_k is below threshold.")
    if rag_summary["precision_at_k"] < args.min_precision_at_k:
        raise SystemExit("Benchmark precision_at_k is below threshold.")
    if rag_summary["route_accuracy"] < args.min_route_accuracy:
        raise SystemExit("Benchmark route_accuracy is below threshold.")
    if task_summary["success_rate"] < args.min_task_success_rate:
        raise SystemExit("Benchmark task success_rate is below threshold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
