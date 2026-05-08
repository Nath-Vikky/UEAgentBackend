from __future__ import annotations

import argparse
import json
import os
import shutil
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
from app.evaluation.task_metrics import evaluate_task_case, summarize_task_cases
from app.main import create_app


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local Phase 5 task evaluation datasets.")
    parser.add_argument(
        "--dataset",
        action="append",
        dest="datasets",
        help="Path to a JSONL evaluation dataset. Can be passed multiple times.",
    )
    parser.add_argument(
        "--source-path",
        action="append",
        dest="source_paths",
        help="Optional KB source path override. Can be passed multiple times.",
    )
    parser.add_argument(
        "--output",
        help="Optional path for the JSON report. Defaults to storage/artifacts/evals/.",
    )
    return parser.parse_args()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


@contextmanager
def _isolated_runtime(*, source_paths: list[str]) -> Iterator[None]:
    runtime_path = Path(".eval-runtime") / f"task-eval-{uuid.uuid4().hex}"
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


def _default_datasets() -> list[Path]:
    return [
        Path("tests/eval/intent_language_dataset.jsonl"),
        Path("tests/eval/code_generate_dataset.jsonl"),
        Path("tests/eval/logs_analyze_dataset.jsonl"),
        Path("tests/eval/code_review_dataset.jsonl"),
        Path("tests/eval/config_task_dataset.jsonl"),
    ]


def _default_output_path() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("storage/artifacts/evals") / f"task-eval-{stamp}.json"


def main() -> int:
    args = _parse_args()
    dataset_paths = [Path(item).resolve() for item in (args.datasets or _default_datasets())]
    for dataset_path in dataset_paths:
        if not dataset_path.exists():
            raise SystemExit(f"Dataset not found: {dataset_path}")

    source_paths = args.source_paths or ["./README.md", "./docs", "./knowledge"]

    with _isolated_runtime(source_paths=source_paths):
        with TestClient(create_app()) as client:
            refresh = client.post(
                "/api/v1/knowledge-base/refresh",
                json={"source_paths": source_paths, "force_rebuild": True},
            )
            if refresh.status_code != 200:
                raise SystemExit(f"KB refresh failed with {refresh.status_code}: {refresh.text}")

            all_results: list[dict[str, Any]] = []
            dataset_results: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for dataset_path in dataset_paths:
                for case in _load_jsonl(dataset_path):
                    response = client.post(case["endpoint"], json=case["request"])
                    if response.status_code != 200:
                        raise SystemExit(
                            f"Case {case['case_id']} failed with {response.status_code}: {response.text}"
                        )
                    result = evaluate_task_case(
                        {**case, "dataset": dataset_path.name},
                        response.json(),
                    )
                    dataset_results[dataset_path.name].append(result)
                    all_results.append(result)

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "datasets": [str(path) for path in dataset_paths],
        "source_paths": source_paths,
        "summary": summarize_task_cases(all_results),
        "datasets_summary": {
            dataset_name: summarize_task_cases(results)
            for dataset_name, results in dataset_results.items()
        },
        "cases": all_results,
    }

    output_path = Path(args.output).resolve() if args.output else _default_output_path().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Saved report to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
