from __future__ import annotations

from math import sqrt

from app.core.settings import Settings
from app.db.models.kb import KBChunkModel
from app.rag.indexing.embeddings import embed_query, embedding_available
from app.rag.indexing.qdrant_store import qdrant_available, search_similar_chunks
from app.rag.indexing.sparse import query_token_counter, token_counter, tokenize, tokenize_query
from app.rag.retrieval.citations import build_citations
from app.rag.retrieval.rerank import rerank_candidates
from app.rag.schemas import RetrievalCandidate, RetrievalResult
from app.schemas.requests import ContextInput


def _cosine_like(query_tokens: dict[str, int], doc_tokens: dict[str, int]) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    common = set(query_tokens).intersection(doc_tokens)
    numerator = sum(query_tokens[token] * doc_tokens[token] for token in common)
    query_norm = sqrt(sum(value * value for value in query_tokens.values()))
    doc_norm = sqrt(sum(value * value for value in doc_tokens.values()))
    if not query_norm or not doc_norm:
        return 0.0
    return numerator / query_norm / doc_norm


def _jaccard(query_tokens: list[str], doc_tokens: list[str]) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    query_set = set(query_tokens)
    doc_set = set(doc_tokens)
    intersection = len(query_set & doc_set)
    union = len(query_set | doc_set)
    return intersection / union if union else 0.0


def _confidence(candidates: list[RetrievalCandidate], filters_applied: dict) -> float:
    if not candidates:
        return 0.12
    top_score = candidates[0].final_score
    domain_bonus = 0.1 if filters_applied.get("domains") else 0.0
    source_bonus = min(0.2, 0.05 * len({item.source_path for item in candidates[:3]}))
    confidence = min(0.95, 0.35 + top_score * 0.45 + domain_bonus + source_bonus)
    return round(confidence, 3)


def _build_answer(candidates: list[RetrievalCandidate], language: str) -> str:
    if not candidates:
        if language.startswith("zh"):
            return "当前没有从知识库中找到足够相关的证据，建议补充文档或放宽过滤条件。"
        return "I could not find enough supporting evidence in the knowledge base. Try adding documents or relaxing filters."

    top = candidates[:3]
    if language.startswith("zh"):
        summaries = [f"{item.title}：{item.text[:90]}" for item in top]
        return "基于当前知识库，最相关的证据主要集中在：" + "；".join(summaries) + "。"
    summaries = [f"{item.title}: {item.text[:90]}" for item in top]
    return "The strongest evidence in the current knowledge base is: " + "; ".join(summaries) + "."


def _normalize_vector_score(score: float) -> float:
    return max(0.0, min(float(score), 1.0))


def _matches_filters(chunk: KBChunkModel, filters_applied: dict) -> bool:
    if filters_applied["domains"] and chunk.domain not in filters_applied["domains"]:
        return False
    if filters_applied["module"] and chunk.module and chunk.module != filters_applied["module"]:
        return False
    if filters_applied["doc_type"] and chunk.doc_type != filters_applied["doc_type"]:
        return False
    return True


def _resolve_mode(
    *,
    settings: Settings,
    embedding_ok: bool,
    qdrant_ok: bool,
) -> tuple[str, bool]:
    if settings.rag_mode == "lexical":
        return ("lexical_only", False)
    if not embedding_ok or not qdrant_ok:
        if settings.rag_fallback_mode == "local_hybrid_fallback":
            return ("local_hybrid_fallback", True)
        return ("lexical_only", True)
    if settings.rag_mode == "semantic":
        return ("semantic_vector", False)
    return ("hybrid_vector", False)


def retrieve(
    *,
    query: str,
    context: ContextInput,
    payload: dict,
    chunks: list[KBChunkModel],
    settings: Settings,
    output_language: str,
) -> RetrievalResult:
    filters_applied = {
        "domains": payload.get("domain_filters") or context.kb_domains_hint or [],
        "module": payload.get("module") or context.current_module,
        "doc_type": payload.get("doc_type"),
    }
    query_tokens_list = tokenize_query(query)
    query_tokens = query_token_counter(query)
    embedding_ok = embedding_available(settings)
    qdrant_ok = False
    qdrant_reason = "qdrant_not_checked"
    if settings.rag_mode != "lexical" and embedding_ok:
        qdrant_ok, qdrant_reason = qdrant_available(settings)
    mode, degraded_mode = _resolve_mode(
        settings=settings,
        embedding_ok=embedding_ok,
        qdrant_ok=qdrant_ok,
    )

    semantic_scores: dict[str, float] = {}
    reason = "lexical_retrieval_ready"
    warnings: list[str] = []
    if mode in {"semantic_vector", "hybrid_vector"}:
        try:
            query_vector = embed_query(settings, query)
            hits = search_similar_chunks(
                settings,
                query_vector,
                top_k=max(settings.rag_top_k, settings.rag_rerank_top_n),
                filters=filters_applied,
            )
            semantic_scores = {
                item["chunk_id"]: round(_normalize_vector_score(item["score"]), 4)
                for item in hits
            }
            reason = "semantic_vector_ready" if mode == "semantic_vector" else "hybrid_vector_ready"
        except Exception as exc:
            degraded_mode = True
            warnings.append(f"vector_search_failed:{exc.__class__.__name__}")
            if settings.rag_fallback_mode == "local_hybrid_fallback":
                mode = "local_hybrid_fallback"
                reason = "vector_search_failed_local_fallback"
            else:
                mode = "lexical_only"
                reason = "vector_search_failed_lexical_fallback"
    elif mode == "local_hybrid_fallback":
        reason = qdrant_reason if not qdrant_ok else "local_hybrid_fallback"
        warnings.append(reason)
    elif not embedding_ok:
        reason = "embedding_not_available"
        warnings.append(reason)
    elif not qdrant_ok:
        reason = qdrant_reason
        warnings.append(reason)

    candidates: list[RetrievalCandidate] = []
    for chunk in chunks:
        if not _matches_filters(chunk, filters_applied):
            continue

        doc_tokens_list = tokenize(chunk.text)
        doc_tokens = token_counter(chunk.text)
        lexical_score = round(_cosine_like(query_tokens, doc_tokens), 4)
        local_semantic_score = round(_jaccard(query_tokens_list, doc_tokens_list), 4)
        vector_semantic_score = semantic_scores.get(chunk.chunk_id, 0.0)
        if mode == "lexical_only":
            semantic_score = 0.0
            final_score = lexical_score
        elif mode == "local_hybrid_fallback":
            semantic_score = local_semantic_score
            final_score = lexical_score * 0.7 + semantic_score * 0.3
        elif mode == "semantic_vector":
            semantic_score = vector_semantic_score
            final_score = semantic_score
        else:
            semantic_score = vector_semantic_score
            final_score = lexical_score * 0.55 + semantic_score * 0.45

        final_score = round(final_score, 4)
        if final_score <= 0:
            continue
        candidates.append(
            RetrievalCandidate(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                title=chunk.title,
                source_path=chunk.source_path,
                domain=chunk.domain,
                section_path=chunk.section_path,
                text=chunk.text,
                lexical_score=lexical_score,
                semantic_score=round(semantic_score, 4),
                final_score=final_score,
                metadata=chunk.metadata_json,
            )
        )

    reranked = rerank_candidates(candidates, settings.rag_rerank_top_n)
    top_results = reranked[: settings.rag_top_k]
    confidence = _confidence(top_results, filters_applied)
    citations = build_citations(top_results)
    if not top_results:
        warnings.append("no_retrieval_hits")
    return RetrievalResult(
        mode=mode,
        degraded_mode=degraded_mode,
        reason=reason,
        filters_applied=filters_applied,
        retrieved_docs=top_results,
        confidence=confidence,
        answer=_build_answer(top_results, output_language),
        citations=citations,
        warnings=warnings,
    )
