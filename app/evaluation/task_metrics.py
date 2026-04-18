from __future__ import annotations

from typing import Any


def _get_path_value(payload: Any, path: str) -> tuple[bool, Any]:
    current = payload
    for segment in path.split("."):
        if isinstance(current, list):
            if not segment.isdigit():
                return (False, None)
            index = int(segment)
            if index < 0 or index >= len(current):
                return (False, None)
            current = current[index]
            continue
        if not isinstance(current, dict) or segment not in current:
            return (False, None)
        current = current[segment]
    return (True, current)


def _subset(expected: list[str], actual: list[str]) -> bool:
    if not expected:
        return True
    actual_set = {str(item) for item in actual}
    return all(str(item) in actual_set for item in expected)


def evaluate_task_case(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    assertions = case.get("assertions", {})
    route_type = response.get("intent", {}).get("route_type")
    final_language = response.get("locale", {}).get("final_output_language")
    task_status = response.get("task", {}).get("status")
    finish_reason = response.get("task", {}).get("finish_reason")

    expected_route = assertions.get("expected_route")
    expected_language = assertions.get("expected_language")
    expected_status = assertions.get("expected_status")
    expected_finish_reason = assertions.get("expected_finish_reason")

    required_fields = list(assertions.get("required_fields", []))
    field_hits = 0
    missing_fields: list[str] = []
    for path in required_fields:
        exists, _ = _get_path_value(response, path)
        if exists:
            field_hits += 1
        else:
            missing_fields.append(path)
    field_coverage = field_hits / len(required_fields) if required_fields else 1.0

    semantic_checks: list[bool] = []

    issue_families = list(response.get("data", {}).get("issue_families", []))
    expected_issue_families = list(assertions.get("expected_issue_families", []))
    if expected_issue_families:
        semantic_checks.append(_subset(expected_issue_families, issue_families))

    rule_hits = list(response.get("data", {}).get("rule_hits", []))
    expected_rule_hits = list(assertions.get("expected_rule_hits", []))
    if expected_rule_hits:
        semantic_checks.append(_subset(expected_rule_hits, rule_hits))

    suspicious_metrics = [
        str(item.get("metric"))
        for item in response.get("data", {}).get("suspicious_points", [])
        if isinstance(item, dict) and item.get("metric")
    ]
    expected_suspicious_metrics = list(assertions.get("expected_suspicious_metrics", []))
    if expected_suspicious_metrics:
        semantic_checks.append(_subset(expected_suspicious_metrics, suspicious_metrics))

    if "expected_validation_valid" in assertions:
        is_valid = response.get("data", {}).get("validation_summary", {}).get("is_valid")
        semantic_checks.append(is_valid == assertions["expected_validation_valid"])

    if "expected_proposal_state" in assertions:
        proposal_state = (
            response.get("action_proposals", [{}])[0].get("confirmation", {}).get("state")
            if response.get("action_proposals")
            else None
        )
        semantic_checks.append(proposal_state == assertions["expected_proposal_state"])

    expected_values = assertions.get("expected_values", {})
    for path, expected_value in expected_values.items():
        exists, actual_value = _get_path_value(response, path)
        semantic_checks.append(exists and actual_value == expected_value)

    semantic_accuracy = (
        sum(1 for item in semantic_checks if item) / len(semantic_checks)
        if semantic_checks
        else 1.0
    )

    route_ok = route_type == expected_route if expected_route else True
    language_ok = final_language == expected_language if expected_language else True
    status_ok = task_status == expected_status if expected_status else True
    finish_reason_ok = finish_reason == expected_finish_reason if expected_finish_reason else True

    return {
        "case_id": case["case_id"],
        "dataset": case.get("dataset"),
        "endpoint": case["endpoint"],
        "route_type": route_type,
        "expected_route": expected_route,
        "route_ok": route_ok,
        "final_output_language": final_language,
        "expected_language": expected_language,
        "language_ok": language_ok,
        "task_status": task_status,
        "expected_status": expected_status,
        "status_ok": status_ok,
        "finish_reason": finish_reason,
        "expected_finish_reason": expected_finish_reason,
        "finish_reason_ok": finish_reason_ok,
        "field_coverage": round(field_coverage, 4),
        "missing_fields": missing_fields,
        "semantic_accuracy": round(semantic_accuracy, 4),
        "semantic_checks": semantic_checks,
        "success": bool(response.get("success", False)),
        "errors_count": len(response.get("errors", [])),
    }


def summarize_task_cases(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "cases": 0,
            "success_rate": 0.0,
            "route_accuracy": 0.0,
            "language_accuracy": 0.0,
            "status_accuracy": 0.0,
            "finish_reason_accuracy": 0.0,
            "field_coverage": 0.0,
            "semantic_accuracy": 0.0,
            "error_rate": 0.0,
        }

    count = len(results)
    return {
        "cases": count,
        "success_rate": round(sum(1 for item in results if item["success"]) / count, 4),
        "route_accuracy": round(sum(1 for item in results if item["route_ok"]) / count, 4),
        "language_accuracy": round(sum(1 for item in results if item["language_ok"]) / count, 4),
        "status_accuracy": round(sum(1 for item in results if item["status_ok"]) / count, 4),
        "finish_reason_accuracy": round(
            sum(1 for item in results if item["finish_reason_ok"]) / count,
            4,
        ),
        "field_coverage": round(sum(item["field_coverage"] for item in results) / count, 4),
        "semantic_accuracy": round(sum(item["semantic_accuracy"] for item in results) / count, 4),
        "error_rate": round(sum(1 for item in results if item["errors_count"] > 0) / count, 4),
    }
