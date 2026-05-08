from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.core.settings import Settings
from app.db.models.kb import KBChunkModel
from app.rag.retrieval.citations import build_citations
from app.rag.retrieval.hybrid import retrieve
from app.rag.schemas import RetrievalCandidate, RetrievalResult
from app.schemas.requests import ContextInput

MIN_SUFFICIENT_CONFIDENCE = 0.4
MIN_TOP_SCORE = 0.03
MAX_AGENTIC_ROUNDS = 2

DOMAIN_REWRITE_HINTS = {
    "asset_rules": "Blueprint StaticMesh asset naming Nanite LOD collision reference viewer",
    "code_reference": "Unreal C++ example header source Build.cs module dependency",
    "engine_notes": "Unreal Engine API lifecycle subsystem reflection gameplay framework",
    "examples": "complete Unreal C++ example implementation",
    "project_docs": "project architecture setup workflow API guide",
    "prompt_packs": "UE C++ assistant rules best practices",
    "team_rules": "team coding convention Unreal project rule",
}

QUERY_REWRITE_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("actor", "lifecycle", "life cycle", "\u751f\u547d\u5468\u671f"),
        "Actor lifecycle constructor BeginPlay Tick EndPlay Destroy UObject garbage collection",
    ),
    (
        ("enhanced input", "input action", "mapping context", "\u589e\u5f3a\u8f93\u5165"),
        "EnhancedInput UInputAction UInputMappingContext UEnhancedInputComponent AddMappingContext BindAction",
    ),
    (
        ("gas", "gameplay ability", "ability system", "\u6280\u80fd\u7cfb\u7edf"),
        "Gameplay Ability System AbilitySystemComponent AttributeSet GameplayEffect GameplayTag",
    ),
    (
        ("thread", "multithread", "frunnable", "async", "\u591a\u7ebf\u7a0b"),
        "FRunnable AsyncTask TaskGraph GameThread ParallelFor thread safety",
    ),
    (
        ("http", "json request", "api request"),
        "FHttpModule IHttpRequest Json JsonUtilities BlueprintAsyncActionBase",
    ),
    (
        ("websocket", "web socket", "\u957f\u8fde\u63a5"),
        "WebSockets IWebSocket GameInstanceSubsystem connect onmessage onclosed",
    ),
    (
        ("blueprint", "\u84dd\u56fe"),
        "Blueprint parent class component variable compile reference graph",
    ),
    (
        ("static mesh", "staticmesh", "nanite", "\u9759\u6001\u7f51\u683c\u4f53"),
        "StaticMesh Nanite LOD collision material slots lightmap",
    ),
    (
        ("delegate", "event", "\u59d4\u6258"),
        "delegate multicast dynamic delegate Bind Broadcast AddDynamic RemoveDynamic",
    ),
    (
        ("replication", "rpc", "\u7f51\u7edc\u540c\u6b65"),
        "replication DOREPLIFETIME OnRep RPC authority NetMulticast",
    ),
)


def _top_score(result: RetrievalResult) -> float:
    if not result.retrieved_docs:
        return 0.0
    return float(result.retrieved_docs[0].final_score or 0.0)


def evaluate_evidence(result: RetrievalResult) -> dict[str, Any]:
    retrieved_count = len(result.retrieved_docs)
    top_score = _top_score(result)
    confidence = float(result.confidence or 0.0)
    sufficient = (
        retrieved_count > 0
        and confidence >= MIN_SUFFICIENT_CONFIDENCE
        and top_score >= MIN_TOP_SCORE
    )
    reason = "sufficient"
    if not retrieved_count:
        reason = "no_retrieved_docs"
    elif confidence < MIN_SUFFICIENT_CONFIDENCE:
        reason = "low_confidence"
    elif top_score < MIN_TOP_SCORE:
        reason = "low_top_score"
    return {
        "status": "sufficient" if sufficient else "insufficient",
        "sufficient": sufficient,
        "reason": reason,
        "retrieved_count": retrieved_count,
        "confidence": round(confidence, 4),
        "top_score": round(top_score, 4),
        "thresholds": {
            "min_confidence": MIN_SUFFICIENT_CONFIDENCE,
            "min_top_score": MIN_TOP_SCORE,
        },
    }


def rewrite_query_for_retrieval(
    *,
    query: str,
    domain_filters: list[str] | None = None,
    context: ContextInput | None = None,
) -> str:
    hints: list[str] = []
    lowered = query.lower()
    for triggers, hint in QUERY_REWRITE_HINTS:
        if any(trigger.lower() in lowered for trigger in triggers):
            hints.append(hint)

    for domain in domain_filters or []:
        hint = DOMAIN_REWRITE_HINTS.get(domain)
        if hint:
            hints.append(hint)

    if context and context.current_module:
        hints.append(f"module {context.current_module}")
    if context and context.current_file:
        hints.append(f"current file {context.current_file}")

    deduped: list[str] = []
    seen: set[str] = set()
    for hint in hints:
        normalized = hint.strip()
        if normalized and normalized.lower() not in seen:
            deduped.append(normalized)
            seen.add(normalized.lower())

    if not deduped:
        deduped.append("Unreal Engine C++ project knowledge documentation example")

    return f"{query.strip()} {' '.join(deduped)}".strip()


def _candidate_key(item: RetrievalCandidate) -> str:
    return item.chunk_id or f"{item.source_path}:{item.section_path}"


def _merge_candidates(
    first: list[RetrievalCandidate],
    second: list[RetrievalCandidate],
    *,
    top_k: int,
) -> list[RetrievalCandidate]:
    merged: dict[str, RetrievalCandidate] = {}
    for item in [*first, *second]:
        key = _candidate_key(item)
        existing = merged.get(key)
        if not existing or item.final_score > existing.final_score:
            merged[key] = item
    return sorted(merged.values(), key=lambda item: item.final_score, reverse=True)[: max(top_k, 1)]


def _with_merged_candidates(
    *,
    first: RetrievalResult,
    second: RetrievalResult,
    output_language: str,
    settings: Settings,
) -> RetrievalResult:
    merged_docs = _merge_candidates(
        first.retrieved_docs,
        second.retrieved_docs,
        top_k=settings.rag_top_k,
    )
    selected = second if second.confidence >= first.confidence else first
    if not merged_docs:
        return selected

    summaries = [f"{item.title}: {item.text[:90]}" for item in merged_docs[:3]]
    if output_language.startswith("zh"):
        answer = (
            "\u57fa\u4e8e\u591a\u8f6e\u68c0\u7d22\uff0c"
            "\u5f53\u524d\u6700\u76f8\u5173\u7684\u8bc1\u636e\u662f\uff1a"
            + "\uff1b".join(summaries)
            + "\u3002"
        )
    else:
        answer = "After query refinement, the strongest evidence is: " + "; ".join(summaries) + "."
    confidence = max(first.confidence, second.confidence)
    if len({item.source_path for item in merged_docs[:3]}) > 1:
        confidence = min(0.95, confidence + 0.04)

    return replace(
        selected,
        retrieved_docs=merged_docs,
        confidence=round(confidence, 4),
        answer=answer,
        citations=build_citations(merged_docs),
        warnings=[item for item in [*first.warnings, *second.warnings] if item != "no_retrieval_hits"],
    )


def refine_retrieval_if_needed(
    *,
    query: str,
    context: ContextInput,
    payload: dict[str, Any],
    chunks: list[KBChunkModel],
    settings: Settings,
    output_language: str,
    initial_result: RetrievalResult,
) -> tuple[RetrievalResult, dict[str, Any], list[str]]:
    domain_filters = payload.get("domain_filters") or context.kb_domains_hint or []
    initial_quality = evaluate_evidence(initial_result)
    attempts = [
        {
            "round": 1,
            "query": query,
            "quality": initial_quality,
            "selected": True,
            "rewrite_applied": False,
        }
    ]
    if initial_quality["sufficient"] or payload.get("disable_agentic_rag"):
        trace = {
            "enabled": not bool(payload.get("disable_agentic_rag")),
            "max_rounds": MAX_AGENTIC_ROUNDS,
            "attempts": attempts,
            "selected_round": 1,
            "selected_query": query,
            "evidence_sufficient": bool(initial_quality["sufficient"]),
            "evidence_insufficient": not bool(initial_quality["sufficient"]),
            "final_reason": initial_quality["reason"],
        }
        warnings = [] if initial_quality["sufficient"] else ["evidence_insufficient"]
        return initial_result, trace, warnings

    rewritten_query = rewrite_query_for_retrieval(
        query=query,
        domain_filters=domain_filters,
        context=context,
    )
    second_result = retrieve(
        query=rewritten_query,
        context=context,
        payload=payload,
        chunks=chunks,
        settings=settings,
        output_language=output_language,
    )
    second_quality = evaluate_evidence(second_result)
    selected_result = _with_merged_candidates(
        first=initial_result,
        second=second_result,
        output_language=output_language,
        settings=settings,
    )
    final_quality = evaluate_evidence(selected_result)
    selected_round = 2 if selected_result.confidence >= initial_result.confidence and second_result.retrieved_docs else 1

    attempts[0]["selected"] = selected_round == 1
    attempts.append(
        {
            "round": 2,
            "query": rewritten_query,
            "quality": second_quality,
            "selected": selected_round == 2,
            "rewrite_applied": True,
            "rewrite_reason": initial_quality["reason"],
        }
    )
    trace = {
        "enabled": True,
        "max_rounds": MAX_AGENTIC_ROUNDS,
        "attempts": attempts,
        "selected_round": selected_round,
        "selected_query": rewritten_query if selected_round == 2 else query,
        "evidence_sufficient": bool(final_quality["sufficient"]),
        "evidence_insufficient": not bool(final_quality["sufficient"]),
        "final_reason": final_quality["reason"],
    }
    warnings = ["agentic_rag_query_rewrite_used"]
    if not final_quality["sufficient"]:
        warnings.append("evidence_insufficient")
    return selected_result, trace, warnings
