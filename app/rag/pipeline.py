from __future__ import annotations

from typing import Any

from app.core.settings import Settings
from app.db.models.kb import KBChunkModel
from app.rag import retrieve_knowledge
from app.schemas.requests import ContextInput
from app.services.local_search_service import LocalSearchService
from app.services.web_search_service import WebSearchService, should_trigger_web_search


def run_project_qa_retrieval_pipeline(
    *,
    query: str,
    context: ContextInput,
    payload: dict[str, Any],
    chunks: list[KBChunkModel],
    settings: Settings,
    output_language: str,
) -> dict[str, Any]:
    """Run the Project QA evidence pipeline without composing the final answer.

    The pipeline keeps the orchestration small and explicit:
    RAG -> optional local grep fallback -> optional controlled web search ->
    source arbitration -> quality gate. It is intentionally read-only.
    """

    rag_result = retrieve_knowledge(
        query=query,
        context=context,
        payload=payload,
        chunks=chunks,
        settings=settings,
        output_language=output_language,
    )
    result = rag_result["result"]
    agentic_rag = dict(rag_result.get("agentic_rag") or {})
    rag_warnings = list(rag_result.get("warnings") or [])
    selected_query = str(agentic_rag.get("selected_query") or query)

    local_search = _run_local_search(
        query=selected_query,
        context=context,
        payload=payload,
        result_warnings=list(result.warnings),
        rag_has_hits=bool(result.retrieved_docs),
        settings=settings,
    )
    local_docs = _local_docs(local_search)
    local_citations = _local_citations(local_search)

    web_search = _run_web_search(
        query=query,
        selected_query=selected_query,
        context=context,
        payload=payload,
        output_language=output_language,
        settings=settings,
        evidence_sufficient=bool(result.retrieved_docs or local_docs),
    )
    web_docs = _web_docs(web_search)
    web_citations = _web_citations(web_search)

    rag_docs = _rag_docs(result)
    retrieval_trace_docs = _rag_trace_docs(result)
    final_evidence_count = len(result.retrieved_docs) + len(local_docs) + len(web_docs)
    source_arbitration = _source_arbitration(
        rag_count=len(result.retrieved_docs),
        local_count=len(local_docs),
        web_count=len(web_docs),
        web_search=web_search,
    )
    retrieval_quality_gate = _retrieval_quality_gate(
        evidence_count=final_evidence_count,
        rag_count=len(result.retrieved_docs),
        local_count=len(local_docs),
        web_count=len(web_docs),
        agentic_rag=agentic_rag,
        selected_query=selected_query,
    )
    warnings = _merged_warnings(
        rag_warnings=rag_warnings,
        result_warnings=list(result.warnings),
        local_docs=local_docs,
        web_docs=web_docs,
        web_search=web_search,
    )

    return {
        "result": result,
        "agentic_rag": agentic_rag,
        "selected_query": selected_query,
        "rag_docs": rag_docs,
        "rag_trace_docs": retrieval_trace_docs,
        "local_search": local_search,
        "local_docs": local_docs,
        "local_citations": local_citations,
        "web_search": web_search,
        "web_docs": web_docs,
        "web_citations": web_citations,
        "retrieved_docs": [*rag_docs, *local_docs, *web_docs],
        "retrieval_trace_docs": [*retrieval_trace_docs, *local_docs, *web_docs],
        "citations": [*result.citations, *local_citations, *web_citations],
        "sources": [
            {"title": item.title, "source": item.source_path, "domain": item.domain}
            for item in result.retrieved_docs
        ]
        + [{"title": item["title"], "source": item["source_path"], "domain": item["domain"]} for item in local_docs]
        + [{"title": item["title"], "source": item["source_path"], "domain": item["domain"]} for item in web_docs],
        "source_arbitration": source_arbitration,
        "retrieval_quality_gate": retrieval_quality_gate,
        "warnings": warnings,
        "confidence_floor": 0.42 if web_docs else 0.38 if local_docs else 0.0,
    }


def _run_local_search(
    *,
    query: str,
    context: ContextInput,
    payload: dict[str, Any],
    result_warnings: list[str],
    rag_has_hits: bool,
    settings: Settings,
) -> dict[str, Any]:
    local_domain_filters = payload.get("domain_filters") or context.kb_domains_hint or []
    local_search_disabled = bool(payload.get("disable_local_search"))
    local_required_terms_missing = "required_query_terms_not_found" in result_warnings
    should_run_local_search = (
        not local_search_disabled
        and not local_required_terms_missing
        and (not rag_has_hits or payload.get("use_local_search"))
    )
    local_skip_reason = "rag_hits_available"
    if local_search_disabled:
        local_skip_reason = "disabled_by_payload"
    elif local_required_terms_missing:
        local_skip_reason = "required_query_terms_not_found"
    if should_run_local_search:
        return LocalSearchService(settings).search(
            query=query,
            domain_filters=local_domain_filters,
            top_k=min(max(settings.rag_top_k, 3), 8),
        )
    return {
        "query": query,
        "mode": "local_grep",
        "status": "skipped",
        "reason": local_skip_reason,
        "items": [],
        "summary": {
            "result_count": 0,
            "candidate_count": 0,
            "searched_file_count": 0,
            "skipped_file_count": 0,
            "domain_filters": local_domain_filters,
            "terms": [],
        },
    }


def _run_web_search(
    *,
    query: str,
    selected_query: str,
    context: ContextInput,
    payload: dict[str, Any],
    output_language: str,
    settings: Settings,
    evidence_sufficient: bool,
) -> dict[str, Any]:
    explicit_web_search = bool(
        payload.get("use_web_search")
        or payload.get("force_web_search")
        or payload.get("web_search")
    )
    if payload.get("disable_web_search"):
        web_should_run, web_trigger_reason = False, "disabled_by_payload"
    else:
        web_should_run, web_trigger_reason = should_trigger_web_search(
            query=query,
            evidence_sufficient=evidence_sufficient,
            settings=settings,
            explicit=explicit_web_search or None,
        )
    web_domain_hints = [
        str(item)
        for item in (
            payload.get("web_domain_hints")
            or payload.get("domain_hints")
            or context.kb_domains_hint
            or []
        )
        if str(item).strip()
    ]
    if web_should_run:
        return WebSearchService(settings).search(
            query=selected_query,
            domain_hints=web_domain_hints,
            language=output_language,
            trigger_reason=web_trigger_reason,
            max_results=payload.get("web_search_max_results"),
        )
    return _skipped_web_search_result(
        query=selected_query,
        reason=web_trigger_reason,
        domain_hints=web_domain_hints,
        settings=settings,
    )


def _local_docs(local_search: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": item["item_id"],
            "doc_id": item["source_path"],
            "title": item["title"],
            "source_path": item["source_path"],
            "domain": item["domain"],
            "section_path": f"lines:{item['line_start']}-{item['line_end']}",
            "text": item["snippet"][:800],
            "lexical_score": item["score"],
            "semantic_score": 0.0,
            "final_score": item["score"],
            "matched_terms": item["matched_terms"],
            "retrieval_source": "local_grep",
        }
        for item in local_search["items"]
    ]


def _local_citations(local_search: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "title": item["title"],
            "source": item["source_path"],
            "section_path": f"lines:{item['line_start']}-{item['line_end']}",
            "snippet": item["snippet"][:220],
            "score": item["score"],
            "domain": item["domain"],
            "retrieval_source": "local_grep",
        }
        for item in local_search["items"][:3]
    ]


def _web_docs(web_search: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": f"web_{item['rank']}",
            "doc_id": item["url"],
            "title": item["title"],
            "source_path": item["url"],
            "domain": item["domain"],
            "section_path": item.get("source_type") or "web",
            "text": item["snippet"][:800],
            "lexical_score": item["score"],
            "semantic_score": 0.0,
            "final_score": item["score"],
            "matched_terms": [],
            "retrieval_source": "web_search",
            "source_type": item.get("source_type") or "web",
            "published_at": item.get("published_at"),
        }
        for item in web_search.get("items", [])
    ]


def _web_citations(web_search: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "title": item["title"],
            "source": item["url"],
            "section_path": item.get("source_type") or "web",
            "snippet": item["snippet"][:220],
            "score": item["score"],
            "domain": item["domain"],
            "retrieval_source": "web_search",
            "source_type": item.get("source_type") or "web",
            "published_at": item.get("published_at"),
        }
        for item in web_search.get("items", [])[:3]
    ]


def _rag_docs(result: Any) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": item.chunk_id,
            "doc_id": item.doc_id,
            "title": item.title,
            "source_path": item.source_path,
            "domain": item.domain,
            "section_path": item.section_path,
            "text": item.text[:800],
            "lexical_score": item.lexical_score,
            "semantic_score": item.semantic_score,
            "final_score": item.final_score,
            "retrieval_source": "rag",
        }
        for item in result.retrieved_docs
    ]


def _rag_trace_docs(result: Any) -> list[dict[str, Any]]:
    return [
        {
            "title": item.title,
            "source_path": item.source_path,
            "domain": item.domain,
            "section_path": item.section_path,
            "text": item.text[:400],
            "lexical_score": item.lexical_score,
            "semantic_score": item.semantic_score,
            "final_score": item.final_score,
            "retrieval_source": "rag",
        }
        for item in result.retrieved_docs
    ]


def _source_arbitration(
    *,
    rag_count: int,
    local_count: int,
    web_count: int,
    web_search: dict[str, Any],
) -> dict[str, Any]:
    primary_source = "none"
    if rag_count:
        primary_source = "rag"
    elif local_count:
        primary_source = "local_grep"
    elif web_count:
        primary_source = "web_search"
    return {
        "policy": "local_kb_and_project_rules_first_web_supplemental",
        "priority_order": ["project_inventory", "project_file", "team_rules", "rag", "local_grep", "web_search"],
        "primary_source": primary_source,
        "web_used": bool(web_count),
        "web_trigger_reason": web_search.get("trigger_reason") or web_search.get("reason"),
        "source_counts": {"rag": rag_count, "local_grep": local_count, "web_search": web_count},
        "conflicts": [],
    }


def _retrieval_quality_gate(
    *,
    evidence_count: int,
    rag_count: int,
    local_count: int,
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
        "web_retrieved_count": web_count,
    }


def _merged_warnings(
    *,
    rag_warnings: list[str],
    result_warnings: list[str],
    local_docs: list[dict[str, Any]],
    web_docs: list[dict[str, Any]],
    web_search: dict[str, Any],
) -> list[str]:
    warnings = list(dict.fromkeys(rag_warnings or result_warnings))
    if local_docs or web_docs:
        warnings = [
            item
            for item in warnings
            if item not in {"no_retrieval_hits", "evidence_insufficient"}
        ]
    if local_docs:
        warnings.append("local_search_fallback_used")
    if web_docs:
        warnings.append("web_search_fallback_used")
    if web_search.get("status") != "skipped" and not web_docs:
        warnings.append(f"web_search_{web_search.get('reason') or 'no_results'}")
    warnings.extend(str(item) for item in web_search.get("warnings", []) if item)
    return list(dict.fromkeys(warnings))


def _skipped_web_search_result(
    *,
    query: str,
    reason: str,
    domain_hints: list[str],
    settings: Settings,
) -> dict[str, Any]:
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
            "domain_hints": domain_hints,
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
