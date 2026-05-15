from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.settings import Settings
from app.db.models.kb import KBChunkModel
from app.rag import retrieve_knowledge
from app.rag.evidence_normalizer import (
    confidence_floor,
    local_citations,
    local_docs,
    rag_docs,
    rag_trace_docs,
    source_rows,
    web_citations,
    web_docs,
    web_memory_citations,
    web_memory_docs,
)
from app.rag.source_policy import (
    build_retrieval_quality_gate,
    build_source_arbitration,
    merge_retrieval_warnings,
)
from app.schemas.requests import ContextInput
from app.services.local_search_service import LocalSearchService
from app.services.web_memory_service import WebMemoryService
from app.services.web_search_service import WebSearchService, should_trigger_web_search


def run_project_qa_retrieval_pipeline(
    *,
    query: str,
    context: ContextInput,
    payload: dict[str, Any],
    chunks: list[KBChunkModel],
    settings: Settings,
    output_language: str,
    db: Session | None = None,
    source_task_id: str | None = None,
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
    local_evidence = local_docs(local_search)
    local_refs = local_citations(local_search)

    web_memory = _run_web_memory(
        query=selected_query,
        context=context,
        payload=payload,
        settings=settings,
        db=db,
        evidence_sufficient=bool(result.retrieved_docs or local_evidence),
    )
    web_memory_evidence = web_memory_docs(web_memory)
    web_memory_refs = web_memory_citations(web_memory)

    web_search = _run_web_search(
        query=query,
        selected_query=selected_query,
        context=context,
        payload=payload,
        output_language=output_language,
        settings=settings,
        evidence_sufficient=bool(result.retrieved_docs or local_evidence or web_memory_evidence),
    )
    web_evidence = web_docs(web_search)
    web_refs = web_citations(web_search)
    web_memory_store = _remember_web_search(
        query=selected_query,
        web_search=web_search,
        settings=settings,
        db=db,
        source_task_id=source_task_id,
    )

    rag_evidence = rag_docs(result)
    retrieval_trace_docs = rag_trace_docs(result)
    final_evidence_count = (
        len(result.retrieved_docs) + len(local_evidence) + len(web_memory_evidence) + len(web_evidence)
    )
    source_arbitration = build_source_arbitration(
        rag_count=len(result.retrieved_docs),
        local_count=len(local_evidence),
        web_memory_count=len(web_memory_evidence),
        web_count=len(web_evidence),
        web_search=web_search,
    )
    retrieval_quality_gate = build_retrieval_quality_gate(
        evidence_count=final_evidence_count,
        rag_count=len(result.retrieved_docs),
        local_count=len(local_evidence),
        web_memory_count=len(web_memory_evidence),
        web_count=len(web_evidence),
        agentic_rag=agentic_rag,
        selected_query=selected_query,
    )
    warnings = merge_retrieval_warnings(
        rag_warnings=rag_warnings,
        result_warnings=list(result.warnings),
        local_docs=local_evidence,
        web_memory_docs=web_memory_evidence,
        web_docs=web_evidence,
        web_memory_store=web_memory_store,
        web_search=web_search,
    )

    return {
        "result": result,
        "agentic_rag": agentic_rag,
        "selected_query": selected_query,
        "rag_docs": rag_evidence,
        "rag_trace_docs": retrieval_trace_docs,
        "local_search": local_search,
        "local_docs": local_evidence,
        "local_citations": local_refs,
        "web_memory": web_memory,
        "web_memory_docs": web_memory_evidence,
        "web_memory_citations": web_memory_refs,
        "web_memory_store": web_memory_store,
        "web_search": web_search,
        "web_docs": web_evidence,
        "web_citations": web_refs,
        "retrieved_docs": [*rag_evidence, *local_evidence, *web_memory_evidence, *web_evidence],
        "retrieval_trace_docs": [*retrieval_trace_docs, *local_evidence, *web_memory_evidence, *web_evidence],
        "citations": [*result.citations, *local_refs, *web_memory_refs, *web_refs],
        "sources": source_rows(rag_evidence, local_evidence, web_memory_evidence, web_evidence),
        "source_arbitration": source_arbitration,
        "retrieval_quality_gate": retrieval_quality_gate,
        "warnings": warnings,
        "confidence_floor": confidence_floor(
            local_count=len(local_evidence),
            web_memory_count=len(web_memory_evidence),
            web_count=len(web_evidence),
        ),
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


def _run_web_memory(
    *,
    query: str,
    context: ContextInput,
    payload: dict[str, Any],
    settings: Settings,
    db: Session | None,
    evidence_sufficient: bool,
) -> dict[str, Any]:
    domain_hints = [
        str(item)
        for item in (
            payload.get("web_domain_hints")
            or payload.get("domain_hints")
            or context.kb_domains_hint
            or []
        )
        if str(item).strip()
    ]
    if not settings.web_memory_enabled:
        return _skipped_web_memory_result(query=query, reason="disabled_by_settings", domain_hints=domain_hints)
    if not db:
        return _skipped_web_memory_result(query=query, reason="db_session_unavailable", domain_hints=domain_hints)
    if payload.get("disable_web_memory"):
        return _skipped_web_memory_result(query=query, reason="disabled_by_payload", domain_hints=domain_hints)
    if evidence_sufficient and not payload.get("use_web_memory"):
        return _skipped_web_memory_result(query=query, reason="local_evidence_available", domain_hints=domain_hints)
    return WebMemoryService(db, settings).recall(
        query=query,
        domain_hints=domain_hints,
        limit=payload.get("web_memory_max_results"),
    )


def _remember_web_search(
    *,
    query: str,
    web_search: dict[str, Any],
    settings: Settings,
    db: Session | None,
    source_task_id: str | None,
) -> dict[str, Any]:
    if not settings.web_memory_enabled:
        return WebMemoryService._skipped_result(reason="disabled_by_settings")
    if not db:
        return WebMemoryService._skipped_result(reason="db_session_unavailable")
    return WebMemoryService(db, settings).remember_web_search_result(
        query=query,
        web_search=web_search,
        source_task_id=source_task_id,
    )


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


def _skipped_web_memory_result(
    *,
    query: str,
    reason: str,
    domain_hints: list[str],
) -> dict[str, Any]:
    return {
        "query": query,
        "mode": "web_memory",
        "status": "skipped",
        "reason": reason,
        "items": [],
        "summary": {
            "result_count": 0,
            "candidate_count": 0,
            "deleted_expired_count": 0,
            "domain_hints": domain_hints,
            "terms": [],
            "writes_to_kb": False,
        },
    }
