from __future__ import annotations

from math import log2
from pathlib import Path
from typing import Any


def normalize_source_name(value: str | None) -> str:
    if not value:
        return ""
    return Path(value).name.lower()


def _dedupe_preserving_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def evaluate_case(case: dict[str, Any], response: dict[str, Any], *, top_k: int) -> dict[str, Any]:
    retrieved_docs = list(response.get("retrieval_trace", {}).get("retrieved_docs", []))[:top_k]
    retrieved_sources = _dedupe_preserving_order(
        [
            normalize_source_name(item.get("source_path") or item.get("source"))
            for item in retrieved_docs
        ]
    )
    expected_sources = {
        normalize_source_name(item) for item in case.get("expected_sources", []) if item
    }
    relevance_flags = [1 if source in expected_sources else 0 for source in retrieved_sources]
    relevant_hits = len({source for source in retrieved_sources if source in expected_sources})
    expected_total = len(expected_sources)

    precision_at_k = relevant_hits / top_k if top_k else 0.0
    precision_at_retrieved = relevant_hits / len(retrieved_sources) if retrieved_sources else 0.0
    recall_at_k = relevant_hits / expected_total if expected_total else 0.0
    hit_at_k = 1.0 if relevant_hits else 0.0
    top1_accuracy = (
        1.0 if retrieved_sources and retrieved_sources[0] in expected_sources else 0.0
    )
    labeled_precision_ceiling = min(expected_total, top_k) / top_k if top_k else 0.0
    normalized_precision_at_k = (
        precision_at_k / labeled_precision_ceiling if labeled_precision_ceiling else 0.0
    )

    reciprocal_rank = 0.0
    for index, flag in enumerate(relevance_flags, start=1):
        if flag:
            reciprocal_rank = 1.0 / index
            break

    dcg = sum(flag / log2(index + 1) for index, flag in enumerate(relevance_flags, start=1))
    ideal_hits = min(expected_total, top_k)
    idcg = sum(1.0 / log2(index + 1) for index in range(1, ideal_hits + 1))
    ndcg_at_k = dcg / idcg if idcg else 0.0

    route_type = response.get("intent", {}).get("route_type")
    expected_route = case.get("expected_route", "project_qa")
    final_language = response.get("locale", {}).get("final_output_language")
    expected_language = case.get("expected_language")
    citations = list(response.get("data", {}).get("citations", []))

    return {
        "case_id": case["case_id"],
        "query": case["query"],
        "expected_sources": sorted(expected_sources),
        "retrieved_sources": retrieved_sources,
        "matched_sources": [
            source
            for source, flag in zip(retrieved_sources, relevance_flags, strict=False)
            if flag
        ],
        "route_type": route_type,
        "expected_route": expected_route,
        "route_ok": route_type == expected_route,
        "final_output_language": final_language,
        "expected_language": expected_language,
        "language_ok": final_language == expected_language if expected_language else True,
        "confidence": float(response.get("data", {}).get("confidence", 0.0) or 0.0),
        "citations_count": len(citations),
        "warnings": list(response.get("data", {}).get("warnings", []))
        or list(response.get("debug_view", {}).get("warnings", [])),
        "metrics": {
            "recall_at_k": round(recall_at_k, 4),
            "precision_at_k": round(precision_at_k, 4),
            "precision_at_retrieved": round(precision_at_retrieved, 4),
            "labeled_precision_ceiling": round(labeled_precision_ceiling, 4),
            "normalized_precision_at_k": round(normalized_precision_at_k, 4),
            "hit_at_k": round(hit_at_k, 4),
            "top1_accuracy": round(top1_accuracy, 4),
            "mrr": round(reciprocal_rank, 4),
            "ndcg_at_k": round(ndcg_at_k, 4),
        },
    }


def summarize_cases(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "cases": 0,
            "recall_at_k": 0.0,
            "precision_at_k": 0.0,
            "precision_at_retrieved": 0.0,
            "labeled_precision_ceiling": 0.0,
            "normalized_precision_at_k": 0.0,
            "hit_at_k": 0.0,
            "top1_accuracy": 0.0,
            "mrr": 0.0,
            "ndcg_at_k": 0.0,
            "route_accuracy": 0.0,
            "language_accuracy": 0.0,
            "citation_coverage": 0.0,
            "low_confidence_ratio": 0.0,
            "no_result_ratio": 0.0,
        }

    count = len(results)
    metric_names = (
        "recall_at_k",
        "precision_at_k",
        "precision_at_retrieved",
        "labeled_precision_ceiling",
        "normalized_precision_at_k",
        "hit_at_k",
        "top1_accuracy",
        "mrr",
        "ndcg_at_k",
    )
    summary = {"cases": count}
    for metric_name in metric_names:
        summary[metric_name] = round(
            sum(item["metrics"][metric_name] for item in results) / count,
            4,
        )

    summary["route_accuracy"] = round(sum(1 for item in results if item["route_ok"]) / count, 4)
    summary["language_accuracy"] = round(sum(1 for item in results if item["language_ok"]) / count, 4)
    summary["citation_coverage"] = round(
        sum(1 for item in results if item["citations_count"] > 0) / count,
        4,
    )
    summary["low_confidence_ratio"] = round(
        sum(1 for item in results if item["confidence"] < 0.4) / count,
        4,
    )
    summary["no_result_ratio"] = round(
        sum(1 for item in results if item["metrics"]["hit_at_k"] == 0.0) / count,
        4,
    )
    return summary
