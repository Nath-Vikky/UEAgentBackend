from __future__ import annotations

import argparse
import json
import os
import shutil
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
from app.rag.evaluation.reporting import build_markdown_report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local Phase 2 RAG evaluation.")
    parser.add_argument(
        "--dataset",
        default="tests/eval/rag_project_qa_dataset.jsonl",
        help="Path to the JSONL evaluation dataset.",
    )
    parser.add_argument(
        "--source-path",
        action="append",
        dest="source_paths",
        help="Optional KB source path override. Can be passed multiple times.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=4,
        help="Top-k window used for scoring.",
    )
    parser.add_argument(
        "--output",
        help="Optional path for the JSON report. Defaults to storage/artifacts/evals/.",
    )
    parser.add_argument(
        "--markdown-output",
        help="Optional path for a Markdown report.",
    )
    parser.add_argument(
        "--min-hit-at-k",
        type=float,
        default=0.0,
        help="Fail the eval if average hit@k is below this threshold.",
    )
    parser.add_argument(
        "--min-route-accuracy",
        type=float,
        default=0.0,
        help="Fail the eval if route accuracy is below this threshold.",
    )
    return parser.parse_args()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


@contextmanager
def _isolated_runtime() -> Iterator[None]:
    runtime_path = Path(".eval-runtime") / f"rag-eval-{uuid.uuid4().hex}"
    storage_dir = runtime_path / "storage"
    shutil.rmtree(runtime_path, ignore_errors=True)
    storage_dir.mkdir(parents=True, exist_ok=True)
    overrides = {
        "DATABASE_URL": "sqlite+pysqlite:///:memory:",
        "STORAGE_DIR": str(storage_dir.resolve()),
        "UPLOAD_DIR": str((storage_dir / "uploads").resolve()),
        "ARTIFACT_DIR": str((storage_dir / "artifacts").resolve()),
        "KB_DIR": str((storage_dir / "kb").resolve()),
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


def _build_request(case: dict[str, Any]) -> dict[str, Any]:
    query = case["query"]
    domain_filters = case.get("domain_filters", ["project_docs"])
    return {
        "task_type": "project_qa",
        "session": {
            "session_id": f"eval_{case['case_id']}_{uuid.uuid4().hex[:8]}",
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


def _default_output_path() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("storage/artifacts/evals") / f"rag-eval-{stamp}.json"


def main() -> int:
    args = _parse_args()
    dataset_path = Path(args.dataset).resolve()
    if not dataset_path.exists():
        raise SystemExit(f"Dataset not found: {dataset_path}")

    cases = _load_jsonl(dataset_path)
    source_paths = args.source_paths or ["../backend.md", "./docs"]

    with _isolated_runtime():
        with TestClient(create_app()) as client:
            refresh = client.post(
                "/api/v1/knowledge-base/refresh",
                json={"source_paths": source_paths, "force_rebuild": True},
            )
            if refresh.status_code != 200:
                raise SystemExit(
                    f"KB refresh failed with {refresh.status_code}: {refresh.text}"
                )

            case_results: list[dict[str, Any]] = []
            for case in cases:
                response = client.post("/api/v1/tasks/project-qa", json=_build_request(case))
                if response.status_code != 200:
                    raise SystemExit(
                        f"Case {case['case_id']} failed with {response.status_code}: {response.text}"
                    )
                case_results.append(
                    evaluate_case(case, response.json(), top_k=args.top_k)
                )

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_path": str(dataset_path),
        "source_paths": source_paths,
        "top_k": args.top_k,
        "summary": summarize_cases(case_results),
        "cases": case_results,
    }

    output_path = Path(args.output).resolve() if args.output else _default_output_path().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_output_path = Path(args.markdown_output).resolve() if args.markdown_output else None
    if markdown_output_path:
        markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_output_path.write_text(build_markdown_report(report), encoding="utf-8")

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Saved report to: {output_path}")
    if markdown_output_path:
        print(f"Saved Markdown report to: {markdown_output_path}")
    if report["summary"]["hit_at_k"] < args.min_hit_at_k:
        raise SystemExit(
            f"RAG eval hit@k {report['summary']['hit_at_k']} is below threshold {args.min_hit_at_k}."
        )
    if report["summary"]["route_accuracy"] < args.min_route_accuracy:
        raise SystemExit(
            f"RAG eval route accuracy {report['summary']['route_accuracy']} is below threshold {args.min_route_accuracy}."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
