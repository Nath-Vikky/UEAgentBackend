from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agent.router import classify_request
from app.schemas.requests import UnifiedTaskRequest


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run offline router SignalDetector route-diff evaluation.")
    parser.add_argument(
        "--dataset",
        default="tests/eval/router_signal_dataset.jsonl",
        help="Path to the router signal JSONL dataset.",
    )
    parser.add_argument(
        "--output",
        default="storage/artifacts/evals/router-signal-eval-latest.json",
        help="Path for the JSON report.",
    )
    parser.add_argument(
        "--markdown-output",
        default="docs/router-signal-eval-report.md",
        help="Optional Markdown report path.",
    )
    parser.add_argument("--min-route-accuracy", type=float, default=1.0)
    parser.add_argument("--min-shadow-stability", type=float, default=1.0)
    parser.add_argument("--min-recommendation-accuracy", type=float, default=0.8)
    return parser.parse_args()


def load_jsonl(path: Path | str) -> list[dict[str, Any]]:
    path = Path(path)
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def evaluate_router_signal_case(case: dict[str, Any]) -> dict[str, Any]:
    request = UnifiedTaskRequest(**case["request"])
    baseline = classify_request(request, signal_mode="compatibility_observer")
    shadow = classify_request(request, signal_mode="scoring_shadow")
    baseline_route = dict(baseline.get("route") or {})
    shadow_route = dict(shadow.get("route") or {})
    recommendation = dict(shadow_route.get("signal_router_recommendation") or {})

    expected_route_type = case.get("expected_route_type")
    expected_tool_id = case.get("expected_selected_tool_id")
    expected_signal_route_hint = case.get("expected_signal_route_hint")
    expected_signal_tool_id = case.get("expected_signal_tool_id")

    baseline_route_type = baseline_route.get("route_type")
    shadow_route_type = shadow_route.get("route_type")
    baseline_tool_id = baseline_route.get("selected_tool_id")
    shadow_tool_id = shadow_route.get("selected_tool_id")
    recommendation_route_hint = recommendation.get("route_hint")
    recommendation_tool_id = recommendation.get("selected_tool_id")

    recommendation_route_ok = (
        True
        if expected_signal_route_hint is None
        else recommendation_route_hint == expected_signal_route_hint
    )
    recommendation_tool_ok = (
        True
        if expected_signal_tool_id is None
        else recommendation_tool_id == expected_signal_tool_id
    )
    return {
        "case_id": case["case_id"],
        "baseline_route_type": baseline_route_type,
        "shadow_route_type": shadow_route_type,
        "baseline_selected_tool_id": baseline_tool_id,
        "shadow_selected_tool_id": shadow_tool_id,
        "expected_route_type": expected_route_type,
        "expected_selected_tool_id": expected_tool_id,
        "route_ok": baseline_route_type == expected_route_type,
        "tool_ok": baseline_tool_id == expected_tool_id,
        "shadow_stable": baseline_route_type == shadow_route_type and baseline_tool_id == shadow_tool_id,
        "recommendation_status": recommendation.get("status"),
        "recommendation_route_hint": recommendation_route_hint,
        "recommendation_selected_tool_id": recommendation_tool_id,
        "expected_signal_route_hint": expected_signal_route_hint,
        "expected_signal_tool_id": expected_signal_tool_id,
        "recommendation_ok": recommendation_route_ok and recommendation_tool_ok,
        "override_applied": bool(shadow_route.get("signal_router_override_applied")),
        "score_margin": recommendation.get("score_margin"),
        "top_signal_detector": shadow_route.get("top_signal_detector"),
    }


def summarize_router_signal_cases(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    if total == 0:
        return {
            "case_count": 0,
            "route_accuracy": 0.0,
            "tool_accuracy": 0.0,
            "shadow_stability": 0.0,
            "recommendation_accuracy": 0.0,
            "override_applied_count": 0,
            "eligible_count": 0,
        }
    return {
        "case_count": total,
        "route_accuracy": _ratio(results, "route_ok"),
        "tool_accuracy": _ratio(results, "tool_ok"),
        "shadow_stability": _ratio(results, "shadow_stable"),
        "recommendation_accuracy": _ratio(results, "recommendation_ok"),
        "override_applied_count": sum(1 for item in results if item["override_applied"]),
        "eligible_count": sum(1 for item in results if item["recommendation_status"] == "eligible"),
    }


def build_markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Router Signal Eval Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Dataset: `{report['dataset']}`",
        f"- Cases: `{summary['case_count']}`",
        f"- Route accuracy: `{summary['route_accuracy']:.4f}`",
        f"- Tool accuracy: `{summary['tool_accuracy']:.4f}`",
        f"- Shadow stability: `{summary['shadow_stability']:.4f}`",
        f"- Recommendation accuracy: `{summary['recommendation_accuracy']:.4f}`",
        f"- Override applied count: `{summary['override_applied_count']}`",
        "",
        "## Cases",
        "",
    ]
    for item in report["cases"]:
        lines.extend(
            [
                f"### {item['case_id']}",
                "",
                f"- Baseline route: `{item['baseline_route_type']}` / `{item['baseline_selected_tool_id']}`",
                f"- Shadow route: `{item['shadow_route_type']}` / `{item['shadow_selected_tool_id']}`",
                (
                    f"- Recommendation: `{item['recommendation_status']}` "
                    f"`{item['recommendation_route_hint']}` / `{item['recommendation_selected_tool_id']}`"
                ),
                (
                    f"- Checks: route=`{item['route_ok']}`, tool=`{item['tool_ok']}`, "
                    f"stable=`{item['shadow_stable']}`, recommendation=`{item['recommendation_ok']}`"
                ),
                "",
            ]
        )
    return "\n".join(lines)


def _ratio(results: list[dict[str, Any]], key: str) -> float:
    return round(sum(1 for item in results if item.get(key)) / len(results), 4)


def main() -> int:
    args = _parse_args()
    dataset_path = Path(args.dataset).resolve()
    if not dataset_path.exists():
        raise SystemExit(f"Dataset not found: {dataset_path}")

    cases = load_jsonl(dataset_path)
    results = [evaluate_router_signal_case(case) for case in cases]
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": str(dataset_path),
        "summary": summarize_router_signal_cases(results),
        "cases": results,
    }

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown_output = Path(args.markdown_output).resolve() if args.markdown_output else None
    if markdown_output:
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.write_text(build_markdown_report(report), encoding="utf-8")

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Saved report to: {output_path}")
    if markdown_output:
        print(f"Saved Markdown report to: {markdown_output}")

    summary = report["summary"]
    if summary["route_accuracy"] < args.min_route_accuracy:
        raise SystemExit("Router signal eval route_accuracy is below threshold.")
    if summary["shadow_stability"] < args.min_shadow_stability:
        raise SystemExit("Router signal eval shadow_stability is below threshold.")
    if summary["recommendation_accuracy"] < args.min_recommendation_accuracy:
        raise SystemExit("Router signal eval recommendation_accuracy is below threshold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
