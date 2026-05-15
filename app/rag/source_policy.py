from __future__ import annotations

from typing import Any


SOURCE_PRIORITY_ORDER = [
    "project_inventory",
    "project_file",
    "team_rules",
    "rag",
    "local_grep",
    "web_memory",
    "web_search",
]


def build_source_arbitration(
    *,
    rag_count: int,
    local_count: int,
    web_memory_count: int,
    web_count: int,
    web_search: dict[str, Any],
) -> dict[str, Any]:
    primary_source = "none"
    if rag_count:
        primary_source = "rag"
    elif local_count:
        primary_source = "local_grep"
    elif web_memory_count:
        primary_source = "web_memory"
    elif web_count:
        primary_source = "web_search"
    return {
        "policy": "local_kb_and_project_rules_first_web_supplemental",
        "priority_order": SOURCE_PRIORITY_ORDER,
        "primary_source": primary_source,
        "web_used": bool(web_count),
        "web_memory_used": bool(web_memory_count),
        "web_trigger_reason": web_search.get("trigger_reason") or web_search.get("reason"),
        "source_counts": {
            "rag": rag_count,
            "local_grep": local_count,
            "web_memory": web_memory_count,
            "web_search": web_count,
        },
        "conflicts": [],
    }


def build_retrieval_quality_gate(
    *,
    evidence_count: int,
    rag_count: int,
    local_count: int,
    web_memory_count: int,
    web_count: int,
    agentic_rag: dict[str, Any],
    selected_query: str,
) -> dict[str, Any]:
    evidence_sufficient = evidence_count > 0
    return {
        "status": "passed" if evidence_sufficient else "warning",
        "evidence_sufficient": evidence_sufficient,
        "evidence_insufficient": not evidence_sufficient,
        "reason": (
            "rag_or_local_or_web_evidence_available"
            if evidence_sufficient
            else agentic_rag.get("final_reason", "no_evidence")
        ),
        "selected_round": agentic_rag.get("selected_round", 1),
        "selected_query": selected_query,
        "retrieved_count": evidence_count,
        "rag_retrieved_count": rag_count,
        "local_retrieved_count": local_count,
        "web_memory_retrieved_count": web_memory_count,
        "web_retrieved_count": web_count,
    }


def merge_retrieval_warnings(
    *,
    rag_warnings: list[str],
    result_warnings: list[str],
    local_docs: list[dict[str, Any]],
    web_memory_docs: list[dict[str, Any]],
    web_docs: list[dict[str, Any]],
    web_memory_store: dict[str, Any],
    web_search: dict[str, Any],
) -> list[str]:
    warnings = list(dict.fromkeys(rag_warnings or result_warnings))
    if local_docs or web_memory_docs or web_docs:
        warnings = [
            item
            for item in warnings
            if item not in {"no_retrieval_hits", "evidence_insufficient"}
        ]
    if local_docs:
        warnings.append("local_search_fallback_used")
    if web_memory_docs:
        warnings.append("web_memory_fallback_used")
    if web_docs:
        warnings.append("web_search_fallback_used")
    if web_memory_store.get("status") == "completed" and (
        web_memory_store.get("stored_count", 0) or web_memory_store.get("updated_count", 0)
    ):
        warnings.append("web_memory_updated")
    if web_search.get("status") != "skipped" and not web_docs:
        warnings.append(f"web_search_{web_search.get('reason') or 'no_results'}")
    warnings.extend(str(item) for item in web_search.get("warnings", []) if item)
    return list(dict.fromkeys(warnings))
