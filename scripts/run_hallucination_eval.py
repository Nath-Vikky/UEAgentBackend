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
from app.evaluation.hallucination_metrics import (
    build_hallucination_markdown,
    evaluate_hallucination_case,
    summarize_hallucination_cases,
)
from app.main import create_app


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run hallucination guard evaluation.")
    parser.add_argument(
        "--dataset",
        default="tests/eval/hallucination_guard_dataset.jsonl",
        help="Path to the JSONL hallucination guard dataset.",
    )
    parser.add_argument("--source-path", action="append", dest="source_paths")
    parser.add_argument("--output", help="Optional JSON output path.")
    parser.add_argument("--markdown-output", help="Optional Markdown output path.")
    parser.add_argument(
        "--min-grounding-accuracy",
        type=float,
        default=0.0,
        help="Fail if grounding accuracy is below this threshold.",
    )
    parser.add_argument(
        "--max-unsupported-answer-rate",
        type=float,
        default=1.0,
        help="Fail if unsupported answer rate is above this threshold.",
    )
    parser.add_argument(
        "--use-live-llm",
        action="store_true",
        help="Use local .env LLM settings. Default disables live LLM calls for reproducibility.",
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
def _isolated_runtime(*, source_paths: list[str], use_live_llm: bool) -> Iterator[None]:
    runtime_path = Path(".eval-runtime") / f"hallucination-eval-{uuid.uuid4().hex}"
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


def _build_request(case: dict[str, Any]) -> dict[str, Any]:
    query = str(case["query"])
    domain_filters = list(case.get("domain_filters") or [])
    return {
        "task_type": "project_qa",
        "session": {
            "session_id": f"hallucination_{case['case_id']}_{uuid.uuid4().hex[:8]}",
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
    return Path("storage/artifacts/evals") / f"hallucination-guard-{stamp}.json"


def main() -> int:
    args = _parse_args()
    dataset_path = Path(args.dataset).resolve()
    if not dataset_path.exists():
        raise SystemExit(f"Dataset not found: {dataset_path}")
    source_paths = args.source_paths or ["./README.md", "./docs", "./knowledge"]
    cases = _load_jsonl(dataset_path)

    with _isolated_runtime(source_paths=source_paths, use_live_llm=args.use_live_llm):
        with TestClient(create_app()) as client:
            refresh = client.post(
                "/api/v1/knowledge-base/refresh",
                json={"source_paths": source_paths, "force_rebuild": True},
            )
            if refresh.status_code != 200:
                raise SystemExit(f"KB refresh failed with {refresh.status_code}: {refresh.text}")

            results: list[dict[str, Any]] = []
            for case in cases:
                response = client.post("/api/v1/tasks/project-qa", json=_build_request(case))
                if response.status_code != 200:
                    raise SystemExit(
                        f"Case {case['case_id']} failed with {response.status_code}: {response.text}"
                    )
                results.append(evaluate_hallucination_case(case, response.json()))

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_path": str(dataset_path),
        "source_paths": source_paths,
        "llm_mode": "live" if args.use_live_llm else "offline_fallback",
        "summary": summarize_hallucination_cases(results),
        "cases": results,
    }
    output_path = Path(args.output).resolve() if args.output else _default_output_path().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_output_path = Path(args.markdown_output).resolve() if args.markdown_output else None
    if markdown_output_path:
        markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_output_path.write_text(build_hallucination_markdown(report), encoding="utf-8")

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Saved hallucination guard report to: {output_path}")
    if markdown_output_path:
        print(f"Saved Markdown report to: {markdown_output_path}")

    if report["summary"]["grounding_accuracy"] < args.min_grounding_accuracy:
        raise SystemExit("Hallucination guard grounding_accuracy is below threshold.")
    if report["summary"]["unsupported_answer_rate"] > args.max_unsupported_answer_rate:
        raise SystemExit("Hallucination guard unsupported_answer_rate is above threshold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
