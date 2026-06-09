from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agent.context_manager import apply_active_target_memory
from app.agent.context_route_refiner import refine_route_from_resolved_context
from app.agent.context_resolver import resolve_context
from app.agent.intent_drafter import build_intent_draft
from app.agent.intent_verifier import verify_intent
from app.agent.router import classify_request
from app.agent.tool_decision import build_tool_plan
from app.agent.turn_context import build_agent_turn_context
from app.schemas.requests import UnifiedTaskRequest


_EXPECTED_FIELD_BY_CHECK = {
    "no_tool_selected_ok": "no_tool_selected",
    "missing_context_gate_ok": "must_ask_for_context",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run offline Improv6 Agent decision-chain evaluation.")
    parser.add_argument(
        "--dataset",
        default="tests/eval/agent_decision_dataset.jsonl",
        help="Path to the Agent decision JSONL dataset.",
    )
    parser.add_argument(
        "--output",
        default="storage/artifacts/evals/agent-decision-eval-latest.json",
        help="Path for the JSON report.",
    )
    parser.add_argument("--min-route-accuracy", type=float, default=0.85)
    parser.add_argument("--min-tool-accuracy", type=float, default=0.85)
    parser.add_argument("--min-context-resolution-accuracy", type=float, default=0.85)
    parser.add_argument("--min-tool-plan-accuracy", type=float, default=0.85)
    parser.add_argument("--min-proposal-safety-accuracy", type=float, default=1.0)
    parser.add_argument("--min-no-tool-safety-accuracy", type=float, default=1.0)
    parser.add_argument("--min-missing-context-gate-accuracy", type=float, default=1.0)
    return parser.parse_args()


def load_jsonl(path: Path | str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def evaluate_agent_decision_case(case: dict[str, Any]) -> dict[str, Any]:
    request = UnifiedTaskRequest(**case["request"])
    routing = classify_request(request)
    context_bundle = _context_bundle_for_case(case)
    intent_draft, context_resolution, verified_intent, tool_plan = _run_decision_chain(
        request=request,
        routing=routing,
        context_bundle=context_bundle,
    )
    context_bundle["context_resolution"] = context_resolution
    refined_routing, refinement_report = refine_route_from_resolved_context(
        routing=routing,
        context_bundle=context_bundle,
        free_chat=request.task_type in {"agent_chat", "project_qa"},
    )
    if refinement_report.get("status") == "applied":
        routing = refined_routing
        context_bundle = _context_bundle_for_case(case)
        context_bundle["context_route_refinement"] = refinement_report
        intent_draft, context_resolution, verified_intent, tool_plan = _run_decision_chain(
            request=request,
            routing=routing,
            context_bundle=context_bundle,
        )
    else:
        context_bundle["context_route_refinement"] = refinement_report

    route = dict(routing.get("route") or {})
    intent = dict(routing.get("intent") or {})
    expected = dict(case.get("expected") or {})
    route_ok = _matches(expected.get("route_type"), intent.get("route_type"))
    tool_ok = _matches(expected.get("selected_tool_id"), route.get("selected_tool_id"))
    target_status_ok = _matches(expected.get("target_resolution_status"), context_resolution.get("status"))
    context_source_ok = _matches(expected.get("context_source"), context_resolution.get("source"))
    target_kind_ok = _matches(expected.get("target_kind"), context_resolution.get("target_kind"))
    tool_plan_ok = _matches(expected.get("tool_plan_mode"), tool_plan.get("mode"))
    proposal_required = expected.get("requires_proposal")
    proposal_safety_ok = True if proposal_required is None else bool(tool_plan.get("requires_proposal")) == bool(proposal_required)
    no_tool_selected_ok = _optional_bool_check(
        expected.get("no_tool_selected"),
        not route.get("selected_tool_id") and not tool_plan.get("tool_id"),
    )
    missing_context_gate_ok = _optional_bool_check(
        expected.get("must_ask_for_context"),
        context_resolution.get("status") == "missing_active_context"
        and tool_plan.get("mode") == "ask_for_context"
        and not bool(tool_plan.get("requires_proposal")),
    )

    return {
        "case_id": case["case_id"],
        "tags": list(case.get("tags") or []),
        "query": _query_for_request(request),
        "expected": expected,
        "actual": {
            "route_type": intent.get("route_type"),
            "selected_tool_id": route.get("selected_tool_id"),
            "target_kind": context_resolution.get("target_kind"),
            "target_resolution_status": context_resolution.get("status"),
            "context_source": context_resolution.get("source"),
            "tool_plan_mode": tool_plan.get("mode"),
            "requires_proposal": tool_plan.get("requires_proposal"),
        },
        "checks": {
            "route_ok": route_ok,
            "tool_ok": tool_ok,
            "target_kind_ok": target_kind_ok,
            "context_resolution_ok": target_status_ok and context_source_ok,
            "tool_plan_ok": tool_plan_ok,
            "proposal_safety_ok": proposal_safety_ok,
            "no_tool_selected_ok": no_tool_selected_ok,
            "missing_context_gate_ok": missing_context_gate_ok,
        },
        "debug": {
            "intent_draft": intent_draft,
            "context_resolution": context_resolution,
            "context_route_refinement": refinement_report,
            "verified_intent": verified_intent,
            "tool_plan": tool_plan,
        },
    }


def _run_decision_chain(
    *,
    request: UnifiedTaskRequest,
    routing: dict[str, Any],
    context_bundle: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    context_bundle["agent_turn_context"] = build_agent_turn_context(
        request=request,
        routing=routing,
        context_bundle=context_bundle,
    )
    intent_draft = build_intent_draft(request=request, routing=routing, context_bundle=context_bundle)
    context_resolution = resolve_context(
        request=request,
        routing=routing,
        context_bundle=context_bundle,
        intent_draft=intent_draft,
    )
    verified_intent = verify_intent(
        draft=intent_draft,
        routing=routing,
        context_bundle=context_bundle,
        free_chat=request.task_type in {"agent_chat", "project_qa"},
    )
    tool_plan = build_tool_plan(
        intent_draft=intent_draft,
        verified_intent=verified_intent,
        context_resolution=context_resolution,
        routing=routing,
    )
    return (intent_draft, context_resolution, verified_intent, tool_plan)


def summarize_agent_decision_cases(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    if total == 0:
        return {
            "case_count": 0,
            "route_accuracy": 0.0,
            "tool_accuracy": 0.0,
            "target_kind_accuracy": 0.0,
            "context_resolution_accuracy": 0.0,
            "tool_plan_accuracy": 0.0,
            "proposal_safety_accuracy": 0.0,
            "no_tool_safety_accuracy": 0.0,
            "no_tool_safety_case_count": 0,
            "missing_context_gate_accuracy": 0.0,
            "missing_context_gate_case_count": 0,
            "tag_breakdown": {},
            "overall_accuracy": 0.0,
        }
    summary = {
        "case_count": total,
        "route_accuracy": _ratio(results, "route_ok"),
        "tool_accuracy": _ratio(results, "tool_ok"),
        "target_kind_accuracy": _ratio(results, "target_kind_ok"),
        "context_resolution_accuracy": _ratio(results, "context_resolution_ok"),
        "tool_plan_accuracy": _ratio(results, "tool_plan_ok"),
        "proposal_safety_accuracy": _ratio(results, "proposal_safety_ok"),
        "no_tool_safety_accuracy": _conditional_ratio(results, "no_tool_selected_ok"),
        "no_tool_safety_case_count": _conditional_count(results, "no_tool_selected_ok"),
        "missing_context_gate_accuracy": _conditional_ratio(results, "missing_context_gate_ok"),
        "missing_context_gate_case_count": _conditional_count(results, "missing_context_gate_ok"),
        "tag_breakdown": _tag_breakdown(results),
        "overall_accuracy": round(
            sum(1 for item in results if all(item["checks"].values())) / total,
            4,
        ),
    }
    return summary


def _context_bundle_for_case(case: dict[str, Any]) -> dict[str, Any]:
    context = dict(case.get("context_bundle") or {})
    context.setdefault("active_context", {})
    context["active_context"] = apply_active_target_memory(
        dict(context.get("active_context") or {}),
        dict(context.get("active_target_memory") or {}),
    )
    context.setdefault("project_inventory_context", {})
    context.setdefault("retrieval_context", {})
    context.setdefault("tool_context", [])
    context.setdefault("context_budget_report", {"version": "context_budget_v1", "estimated_chars": 0})
    return context


def _query_for_request(request: UnifiedTaskRequest) -> str:
    text = str(request.payload.get("user_query") or request.payload.get("requirement_description") or "").strip()
    if text:
        return text
    for message in reversed(request.session.messages):
        if message.role == "user" and message.content.strip():
            return message.content.strip()
    return ""


def _matches(expected: Any, actual: Any) -> bool:
    if expected is None:
        return True
    if isinstance(expected, list):
        return actual in expected
    return actual == expected


def _optional_bool_check(expected: Any, actual: bool) -> bool:
    if expected is None:
        return True
    return bool(expected) == bool(actual)


def _ratio(results: list[dict[str, Any]], check_name: str) -> float:
    return round(sum(1 for item in results if item["checks"].get(check_name)) / len(results), 4)


def _conditional_ratio(results: list[dict[str, Any]], check_name: str) -> float:
    scoped = _conditional_scope(results, check_name)
    if not scoped:
        return 1.0
    return round(sum(1 for item in scoped if item["checks"].get(check_name)) / len(scoped), 4)


def _conditional_count(results: list[dict[str, Any]], check_name: str) -> int:
    return len(_conditional_scope(results, check_name))


def _conditional_scope(results: list[dict[str, Any]], check_name: str) -> list[dict[str, Any]]:
    expected_field = _EXPECTED_FIELD_BY_CHECK.get(check_name)
    if not expected_field:
        return [item for item in results if check_name in item.get("checks", {})]
    return [
        item
        for item in results
        if (dict(item.get("expected") or {}).get(expected_field) is not None)
    ]


def _tag_breakdown(results: list[dict[str, Any]]) -> dict[str, Any]:
    tags = sorted({tag for item in results for tag in list(item.get("tags") or [])})
    breakdown: dict[str, Any] = {}
    for tag in tags:
        scoped = [item for item in results if tag in list(item.get("tags") or [])]
        if not scoped:
            continue
        breakdown[tag] = {
            "case_count": len(scoped),
            "overall_accuracy": round(
                sum(1 for item in scoped if all(item["checks"].values())) / len(scoped),
                4,
            ),
            "route_accuracy": _ratio(scoped, "route_ok"),
            "tool_plan_accuracy": _ratio(scoped, "tool_plan_ok"),
            "proposal_safety_accuracy": _ratio(scoped, "proposal_safety_ok"),
        }
    return breakdown


def main() -> int:
    args = _parse_args()
    dataset_path = Path(args.dataset).resolve()
    if not dataset_path.exists():
        raise SystemExit(f"Dataset not found: {dataset_path}")
    results = [evaluate_agent_decision_case(case) for case in load_jsonl(dataset_path)]
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": str(dataset_path),
        "summary": summarize_agent_decision_cases(results),
        "cases": results,
    }
    output_text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output == "-":
        output_path = None
    else:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_text, encoding="utf-8")

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    if output_path is None:
        print(output_text)
    else:
        print(f"Saved report to: {output_path}")
    summary = report["summary"]
    if summary["route_accuracy"] < args.min_route_accuracy:
        raise SystemExit("Agent decision eval route_accuracy is below threshold.")
    if summary["tool_accuracy"] < args.min_tool_accuracy:
        raise SystemExit("Agent decision eval tool_accuracy is below threshold.")
    if summary["context_resolution_accuracy"] < args.min_context_resolution_accuracy:
        raise SystemExit("Agent decision eval context_resolution_accuracy is below threshold.")
    if summary["tool_plan_accuracy"] < args.min_tool_plan_accuracy:
        raise SystemExit("Agent decision eval tool_plan_accuracy is below threshold.")
    if summary["proposal_safety_accuracy"] < args.min_proposal_safety_accuracy:
        raise SystemExit("Agent decision eval proposal_safety_accuracy is below threshold.")
    if summary["no_tool_safety_accuracy"] < args.min_no_tool_safety_accuracy:
        raise SystemExit("Agent decision eval no_tool_safety_accuracy is below threshold.")
    if summary["missing_context_gate_accuracy"] < args.min_missing_context_gate_accuracy:
        raise SystemExit("Agent decision eval missing_context_gate_accuracy is below threshold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
