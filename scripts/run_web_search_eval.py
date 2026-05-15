from __future__ import annotations

import argparse
import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.settings import Settings
from app.evaluation.web_search_metrics import (
    evaluate_web_search_case,
    summarize_web_search_cases,
)
from app.services.web_search_service import WebSearchService, should_trigger_web_search


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run offline controlled Web Search policy evaluation.")
    parser.add_argument(
        "--dataset",
        default="tests/eval/web_search_policy_dataset.jsonl",
        help="Path to the JSONL Web Search eval dataset.",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON report path. Defaults to storage/artifacts/evals/.",
    )
    parser.add_argument(
        "--min-success-rate",
        type=float,
        default=0.0,
        help="Fail if success_rate is below this threshold.",
    )
    parser.add_argument(
        "--min-safety-pass-rate",
        type=float,
        default=0.0,
        help="Fail if safety_pass_rate is below this threshold.",
    )
    return parser.parse_args()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _default_output_path() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("storage/artifacts/evals") / f"web-search-eval-{stamp}.json"


def _settings_for_case(case: dict[str, Any], runtime_root: Path) -> Settings:
    settings_kwargs = {
        "web_search_enabled": False,
        "web_search_provider": "disabled",
        "web_search_allowed_domains": [],
        "web_search_domain_boosts": [],
        "web_search_mock_results_path": "",
        "web_search_max_queries": 1,
        "web_search_max_results": 3,
        "web_search_timeout_ms": 1200,
        "web_search_max_content_chars": 1200,
    }
    settings_kwargs.update(case.get("settings") or {})
    mock_results = case.get("mock_results")
    if mock_results is not None:
        mock_path = runtime_root / f"{case['case_id']}.json"
        mock_path.write_text(
            json.dumps({"results": mock_results}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        settings_kwargs["web_search_mock_results_path"] = str(mock_path)
    return Settings(_env_file=None, **settings_kwargs)


def _skipped_result(*, query: str, reason: str, settings: Settings) -> dict[str, Any]:
    return {
        "query": query,
        "provider": settings.web_search_provider,
        "status": "skipped",
        "reason": reason,
        "trigger_reason": reason,
        "items": [],
        "summary": {
            "result_count": 0,
            "candidate_count": 0,
            "raw_result_count": 0,
            "skipped_domain_count": 0,
            "allowed_domains": settings.web_search_allowed_domains,
            "domain_hints": [],
            "terms": [],
            "elapsed_ms": 0.0,
            "queries_used": 0,
        },
        "budget": {
            "max_queries": settings.web_search_max_queries,
            "max_results": settings.web_search_max_results,
            "timeout_ms": settings.web_search_timeout_ms,
            "max_content_chars": settings.web_search_max_content_chars,
        },
        "warnings": [],
    }


def _run_case(case: dict[str, Any], runtime_root: Path) -> dict[str, Any]:
    settings = _settings_for_case(case, runtime_root)
    triggered, reason = should_trigger_web_search(
        query=case["query"],
        evidence_sufficient=bool(case.get("evidence_sufficient", False)),
        settings=settings,
        explicit=case.get("explicit"),
    )
    response = (
        WebSearchService(settings).search(
            query=case["query"],
            domain_hints=case.get("domain_hints") or [],
            language=case.get("language", "auto"),
            trigger_reason=reason,
            max_results=case.get("max_results"),
        )
        if triggered
        else _skipped_result(query=case["query"], reason=reason, settings=settings)
    )
    return evaluate_web_search_case(
        case,
        triggered=triggered,
        trigger_reason=reason,
        response=response,
    )


def main() -> int:
    args = _parse_args()
    dataset_path = Path(args.dataset).resolve()
    if not dataset_path.exists():
        raise SystemExit(f"Dataset not found: {dataset_path}")

    runtime_root = Path(".eval-runtime") / f"web-search-eval-{uuid.uuid4().hex}"
    shutil.rmtree(runtime_root, ignore_errors=True)
    runtime_root.mkdir(parents=True, exist_ok=True)
    try:
        cases = _load_jsonl(dataset_path)
        results = [_run_case(case, runtime_root) for case in cases]
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_path": str(dataset_path),
        "summary": summarize_web_search_cases(results),
        "cases": results,
    }
    output_path = Path(args.output).resolve() if args.output else _default_output_path().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Saved report to: {output_path}")
    if report["summary"]["success_rate"] < args.min_success_rate:
        raise SystemExit(
            f"Web Search eval success_rate {report['summary']['success_rate']} is below {args.min_success_rate}."
        )
    if report["summary"]["safety_pass_rate"] < args.min_safety_pass_rate:
        raise SystemExit(
            f"Web Search eval safety_pass_rate {report['summary']['safety_pass_rate']} is below {args.min_safety_pass_rate}."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
