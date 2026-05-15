from __future__ import annotations

from typing import Any


def evaluate_web_search_case(
    case: dict[str, Any],
    *,
    triggered: bool,
    trigger_reason: str,
    response: dict[str, Any],
) -> dict[str, Any]:
    expected = case.get("expected", {})
    items = [item for item in response.get("items", []) if isinstance(item, dict)]
    domains = [str(item.get("domain") or "") for item in items]
    warnings = [str(item) for item in response.get("warnings", [])]

    expected_trigger = expected.get("should_trigger")
    expected_reason = expected.get("reason")
    expected_status = expected.get("status")
    expected_domains = [str(item) for item in expected.get("domains", [])]
    forbidden_domains = [str(item) for item in expected.get("forbidden_domains_absent", [])]
    min_items = int(expected.get("min_items", 0))
    warning_contains = [str(item) for item in expected.get("warnings_contains", [])]
    allowed_domains_only = bool(expected.get("allowed_domains_only", False))
    allowed_domains = [str(item) for item in case.get("settings", {}).get("web_search_allowed_domains", [])]

    trigger_ok = triggered == expected_trigger if expected_trigger is not None else True
    reason_ok = trigger_reason == expected_reason if expected_reason else True
    status_ok = response.get("status") == expected_status if expected_status else True
    min_items_ok = len(items) >= min_items
    expected_domains_ok = all(domain in domains for domain in expected_domains)
    forbidden_domains_ok = all(domain not in domains for domain in forbidden_domains)
    allowed_domains_ok = True
    if allowed_domains_only and allowed_domains:
        allowed_domains_ok = all(_domain_allowed(domain, allowed_domains) for domain in domains)
    warnings_ok = all(any(needle in warning for warning in warnings) for needle in warning_contains)

    return {
        "case_id": case["case_id"],
        "query": case["query"],
        "triggered": triggered,
        "expected_triggered": expected_trigger,
        "trigger_reason": trigger_reason,
        "expected_reason": expected_reason,
        "status": response.get("status"),
        "expected_status": expected_status,
        "domains": domains,
        "warnings": warnings,
        "metrics": {
            "trigger_ok": trigger_ok,
            "reason_ok": reason_ok,
            "status_ok": status_ok,
            "min_items_ok": min_items_ok,
            "expected_domains_ok": expected_domains_ok,
            "forbidden_domains_ok": forbidden_domains_ok,
            "allowed_domains_ok": allowed_domains_ok,
            "warnings_ok": warnings_ok,
        },
        "success": all(
            [
                trigger_ok,
                reason_ok,
                status_ok,
                min_items_ok,
                expected_domains_ok,
                forbidden_domains_ok,
                allowed_domains_ok,
                warnings_ok,
            ]
        ),
    }


def summarize_web_search_cases(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "cases": 0,
            "success_rate": 0.0,
            "trigger_accuracy": 0.0,
            "reason_accuracy": 0.0,
            "status_accuracy": 0.0,
            "result_count_accuracy": 0.0,
            "safety_pass_rate": 0.0,
            "warning_accuracy": 0.0,
        }
    count = len(results)
    metrics = [item["metrics"] for item in results]
    return {
        "cases": count,
        "success_rate": _mean([item["success"] for item in results]),
        "trigger_accuracy": _mean([item["trigger_ok"] for item in metrics]),
        "reason_accuracy": _mean([item["reason_ok"] for item in metrics]),
        "status_accuracy": _mean([item["status_ok"] for item in metrics]),
        "result_count_accuracy": _mean([item["min_items_ok"] for item in metrics]),
        "safety_pass_rate": _mean(
            [
                item["forbidden_domains_ok"] and item["allowed_domains_ok"]
                for item in metrics
            ]
        ),
        "warning_accuracy": _mean([item["warnings_ok"] for item in metrics]),
    }


def _mean(values: list[bool]) -> float:
    return round(sum(1 for item in values if item) / len(values), 4) if values else 0.0


def _domain_allowed(domain: str, allowed_domains: list[str]) -> bool:
    clean_domain = domain.lower().split(":")[0]
    normalized_allowed = [item.lower().split(":")[0] for item in allowed_domains]
    return any(clean_domain == allowed or clean_domain.endswith(f".{allowed}") for allowed in normalized_allowed)
