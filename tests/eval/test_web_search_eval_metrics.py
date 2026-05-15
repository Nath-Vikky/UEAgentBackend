from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from app.evaluation.web_search_metrics import (
    evaluate_web_search_case,
    summarize_web_search_cases,
)
from scripts.run_web_search_eval import _load_jsonl, _run_case


def test_evaluate_web_search_case_tracks_trigger_and_safety() -> None:
    case = {
        "case_id": "safe-official-result",
        "query": "Search Unreal docs",
        "settings": {"web_search_allowed_domains": ["dev.epicgames.com"]},
        "expected": {
            "should_trigger": True,
            "reason": "explicit_user_request",
            "status": "completed",
            "domains": ["dev.epicgames.com"],
            "forbidden_domains_absent": ["127.0.0.1"],
            "allowed_domains_only": True,
            "min_items": 1,
        },
    }
    response = {
        "status": "completed",
        "items": [{"domain": "dev.epicgames.com"}],
        "warnings": [],
    }

    result = evaluate_web_search_case(
        case,
        triggered=True,
        trigger_reason="explicit_user_request",
        response=response,
    )

    assert result["success"] is True
    assert result["metrics"]["trigger_ok"] is True
    assert result["metrics"]["allowed_domains_ok"] is True


def test_summarize_web_search_cases_aggregates_policy_metrics() -> None:
    results = [
        {
            "success": True,
            "metrics": {
                "trigger_ok": True,
                "reason_ok": True,
                "status_ok": True,
                "min_items_ok": True,
                "forbidden_domains_ok": True,
                "allowed_domains_ok": True,
                "warnings_ok": True,
            },
        },
        {
            "success": False,
            "metrics": {
                "trigger_ok": False,
                "reason_ok": True,
                "status_ok": False,
                "min_items_ok": True,
                "forbidden_domains_ok": True,
                "allowed_domains_ok": False,
                "warnings_ok": True,
            },
        },
    ]

    summary = summarize_web_search_cases(results)

    assert summary["cases"] == 2
    assert summary["success_rate"] == 0.5
    assert summary["trigger_accuracy"] == 0.5
    assert summary["safety_pass_rate"] == 0.5


def test_offline_web_search_eval_dataset_passes() -> None:
    cases = _load_jsonl(Path("tests/eval/web_search_policy_dataset.jsonl"))
    runtime_root = Path(".test-runtime") / f"web-search-eval-{uuid.uuid4().hex}"
    shutil.rmtree(runtime_root, ignore_errors=True)
    runtime_root.mkdir(parents=True, exist_ok=True)
    try:
        results = [_run_case(case, runtime_root) for case in cases]
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)

    summary = summarize_web_search_cases(results)

    assert summary["cases"] == 8
    assert summary["success_rate"] == 1.0
    assert summary["safety_pass_rate"] == 1.0
