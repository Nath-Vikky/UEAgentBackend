from __future__ import annotations

from pathlib import Path
from typing import Any

from app.rag.evaluation.metrics import normalize_source_name


def _collect_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        parts: list[str] = []
        for item in value.values():
            parts.extend(_collect_text(item))
        return parts
    if isinstance(value, list):
        parts = []
        for item in value:
            parts.extend(_collect_text(item))
        return parts
    return []


def _contains_any(text: str, terms: list[str]) -> bool:
    if not terms:
        return True
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _contains_all(text: str, terms: list[str]) -> bool:
    if not terms:
        return True
    lowered = text.lower()
    return all(term.lower() in lowered for term in terms)


def _present_terms(text: str, terms: list[str]) -> list[str]:
    lowered = text.lower()
    return [term for term in terms if term.lower() in lowered]


def _retrieved_sources(response: dict[str, Any]) -> list[str]:
    retrieved_docs = list(response.get("retrieval_trace", {}).get("retrieved_docs") or [])
    if not retrieved_docs:
        retrieved_docs = list(response.get("data", {}).get("retrieved_docs") or [])
    sources: list[str] = []
    seen: set[str] = set()
    for item in retrieved_docs:
        source = normalize_source_name(item.get("source_path") or item.get("source"))
        if source and source not in seen:
            sources.append(source)
            seen.add(source)
    return sources


def evaluate_hallucination_case(
    case: dict[str, Any],
    response: dict[str, Any],
) -> dict[str, Any]:
    assertions = dict(case.get("assertions") or {})
    expected_behavior = str(assertions.get("expected_behavior") or "grounded_answer")
    data = dict(response.get("data") or {})
    user_text = "\n".join(_collect_text(response.get("user_view") or {}))
    confidence = float(data.get("confidence") or 0.0)
    citations = list(data.get("citations") or [])
    sources = _retrieved_sources(response)
    expected_sources = {
        normalize_source_name(item) for item in assertions.get("expected_sources", []) if item
    }
    matched_sources = [source for source in sources if source in expected_sources]
    warnings = list(data.get("warnings") or response.get("debug_view", {}).get("warnings") or [])
    self_reflection = dict(data.get("self_reflection") or {})
    grounding_level = str(self_reflection.get("grounding_level") or "")
    answer_mode = str(data.get("answer_mode") or data.get("answer_generation", {}).get("mode") or "")
    route_type = response.get("intent", {}).get("route_type")
    expected_route = assertions.get("expected_route", "project_qa")

    required_any = list(assertions.get("required_terms_any", []))
    required_all = list(assertions.get("required_terms_all", []))
    forbidden_terms = list(assertions.get("forbidden_terms", []))
    warning_any = list(assertions.get("require_warning_any", []))
    allowed_grounding = list(assertions.get("allowed_grounding_levels", []))

    forbidden_present = _present_terms(user_text, forbidden_terms)
    required_any_ok = _contains_any(user_text, required_any)
    required_all_ok = _contains_all(user_text, required_all)
    warning_ok = not warning_any or any(item in warnings for item in warning_any)
    grounding_ok = not allowed_grounding or grounding_level in allowed_grounding
    route_ok = route_type == expected_route if expected_route else True

    checks: dict[str, bool] = {
        "route_ok": route_ok,
        "required_any_ok": required_any_ok,
        "required_all_ok": required_all_ok,
        "forbidden_terms_absent": not forbidden_present,
    }

    if expected_behavior == "abstain":
        max_confidence = float(assertions.get("max_confidence", 0.4))
        max_evidence = int(assertions.get("max_evidence_count", 0))
        evidence_count = len(sources) + len(citations)
        checks.update(
            {
                "confidence_ok": confidence <= max_confidence,
                "evidence_count_ok": evidence_count <= max_evidence,
                "warning_ok": warning_ok,
                "grounding_ok": grounding_ok,
            }
        )
    elif expected_behavior == "knowledge_catalog":
        min_citations = int(assertions.get("min_citations", 1))
        checks.update(
            {
                "answer_mode_ok": answer_mode == "knowledge_catalog",
                "citation_count_ok": len(citations) >= min_citations,
            }
        )
    else:
        min_confidence = float(assertions.get("min_confidence", 0.4))
        min_citations = int(assertions.get("min_citations", 1))
        min_matched_sources = int(assertions.get("min_matched_sources", 1 if expected_sources else 0))
        min_evidence = int(assertions.get("min_evidence_count", 1))
        checks.update(
            {
                "confidence_ok": confidence >= min_confidence,
                "citation_count_ok": len(citations) >= min_citations,
                "evidence_count_ok": len(sources) + len(citations) >= min_evidence,
                "source_match_ok": len(matched_sources) >= min_matched_sources,
            }
        )

    behavior_ok = all(checks.values())
    unsupported_claim = expected_behavior == "abstain" and (
        bool(forbidden_present) or not checks.get("confidence_ok", True)
    )
    return {
        "case_id": case["case_id"],
        "query": case["query"],
        "expected_behavior": expected_behavior,
        "route_type": route_type,
        "expected_route": expected_route,
        "route_ok": route_ok,
        "answer_mode": answer_mode,
        "confidence": round(confidence, 4),
        "grounding_level": grounding_level,
        "citations_count": len(citations),
        "retrieved_sources": sources,
        "matched_sources": matched_sources,
        "warnings": warnings,
        "forbidden_terms_present": forbidden_present,
        "behavior_ok": behavior_ok,
        "unsupported_claim": unsupported_claim,
        "checks": checks,
        "answer_preview": user_text[:360],
    }


def summarize_hallucination_cases(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "cases": 0,
            "grounding_accuracy": 0.0,
            "route_accuracy": 0.0,
            "unsupported_answer_rate": 0.0,
            "abstention_accuracy": 0.0,
            "grounded_answer_accuracy": 0.0,
            "knowledge_catalog_accuracy": 0.0,
            "citation_coverage": 0.0,
        }
    count = len(results)
    abstain_cases = [item for item in results if item["expected_behavior"] == "abstain"]
    grounded_cases = [item for item in results if item["expected_behavior"] == "grounded_answer"]
    catalog_cases = [item for item in results if item["expected_behavior"] == "knowledge_catalog"]

    def ratio(items: list[dict[str, Any]], predicate: str) -> float:
        if not items:
            return 1.0
        return round(sum(1 for item in items if item[predicate]) / len(items), 4)

    return {
        "cases": count,
        "grounding_accuracy": round(sum(1 for item in results if item["behavior_ok"]) / count, 4),
        "route_accuracy": round(sum(1 for item in results if item["route_ok"]) / count, 4),
        "unsupported_answer_rate": round(
            sum(1 for item in abstain_cases if item["unsupported_claim"]) / len(abstain_cases),
            4,
        )
        if abstain_cases
        else 0.0,
        "abstention_accuracy": ratio(abstain_cases, "behavior_ok"),
        "grounded_answer_accuracy": ratio(grounded_cases, "behavior_ok"),
        "knowledge_catalog_accuracy": ratio(catalog_cases, "behavior_ok"),
        "citation_coverage": round(
            sum(1 for item in results if item["citations_count"] > 0) / count,
            4,
        ),
    }


def build_hallucination_markdown(report: dict[str, Any]) -> str:
    summary = dict(report.get("summary") or {})
    lines = [
        "# Hallucination Guard Eval Report",
        "",
        "## Summary",
        "",
        f"- Generated at: `{report.get('generated_at')}`",
        f"- Dataset: `{_fmt_path(report.get('dataset_path'))}`",
        f"- Source paths: `{', '.join(report.get('source_paths') or [])}`",
        f"- LLM mode: `{report.get('llm_mode', 'offline_fallback')}`",
        "",
        "| Metric | Value | Meaning |",
        "| --- | ---: | --- |",
    ]
    notes = {
        "cases": "Evaluation case count.",
        "grounding_accuracy": "Share of cases that followed the expected grounding behavior.",
        "route_accuracy": "Share of cases routed to the expected task route.",
        "unsupported_answer_rate": "Share of abstention cases that still made unsupported claims.",
        "abstention_accuracy": "Share of no-evidence cases that clearly refused or asked for more evidence.",
        "grounded_answer_accuracy": "Share of evidence-backed cases with citations and expected sources.",
        "knowledge_catalog_accuracy": "Share of catalog questions answered as catalog, not raw file dumps.",
        "citation_coverage": "Share of all cases with citation objects.",
    }
    for key, note in notes.items():
        if key in summary:
            lines.append(f"| `{key}` | {_fmt(summary[key])} | {note} |")

    lines.extend(
        [
            "",
            "## Cases",
            "",
            "| Case | Expected | OK | Confidence | Grounding | Sources | Failed checks |",
            "| --- | --- | ---: | ---: | --- | --- | --- |",
        ]
    )
    for case in report.get("cases") or []:
        failed = [key for key, ok in (case.get("checks") or {}).items() if not ok]
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{case.get('case_id')}`",
                    f"`{case.get('expected_behavior')}`",
                    "yes" if case.get("behavior_ok") else "no",
                    _fmt(case.get("confidence", 0.0)),
                    f"`{case.get('grounding_level') or '-'}`",
                    ", ".join(f"`{item}`" for item in case.get("matched_sources") or []) or "-",
                    ", ".join(f"`{item}`" for item in failed) or "-",
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This eval focuses on whether the backend refuses unsupported project facts, preserves catalog answers, and uses citations for grounded answers.",
            "- It is deterministic by default: live LLM calls are disabled unless `--use-live-llm` is passed.",
            "- Read this report together with `docs/benchmark-report.md` for recall, precision, routing, task success, and latency metrics.",
        ]
    )
    return "\n".join(lines) + "\n"


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _fmt_path(value: Any) -> str:
    if not value:
        return ""
    try:
        path = Path(str(value))
        cwd = Path.cwd().resolve()
        return path.resolve().relative_to(cwd).as_posix() if path.is_absolute() else str(value)
    except (OSError, ValueError):
        return str(value)
