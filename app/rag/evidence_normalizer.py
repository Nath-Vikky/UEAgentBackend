from __future__ import annotations

from typing import Any


def local_docs(local_search: dict[str, Any]) -> list[dict[str, Any]]:
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


def local_citations(local_search: dict[str, Any]) -> list[dict[str, Any]]:
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


def web_memory_docs(web_memory: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": item["entry_id"],
            "doc_id": item["url"],
            "title": item["title"],
            "source_path": item["url"],
            "domain": item["domain"],
            "section_path": item.get("source_type") or "web_memory",
            "text": item["snippet"][:800],
            "lexical_score": item["score"],
            "semantic_score": 0.0,
            "final_score": item["score"],
            "matched_terms": [],
            "retrieval_source": "web_memory",
            "source_type": item.get("source_type") or "web_memory",
            "entry_id": item["entry_id"],
            "expires_at": item.get("expires_at"),
        }
        for item in web_memory.get("items", [])
    ]


def web_memory_citations(web_memory: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "title": item["title"],
            "source": item["url"],
            "section_path": item.get("source_type") or "web_memory",
            "snippet": item["snippet"][:220],
            "score": item["score"],
            "domain": item["domain"],
            "retrieval_source": "web_memory",
            "source_type": item.get("source_type") or "web_memory",
            "entry_id": item["entry_id"],
            "expires_at": item.get("expires_at"),
        }
        for item in web_memory.get("items", [])[:3]
    ]


def web_docs(web_search: dict[str, Any]) -> list[dict[str, Any]]:
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


def web_citations(web_search: dict[str, Any]) -> list[dict[str, Any]]:
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


def rag_docs(result: Any) -> list[dict[str, Any]]:
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


def rag_trace_docs(result: Any) -> list[dict[str, Any]]:
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


def source_rows(*doc_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for docs in doc_groups:
        rows.extend(
            {
                "title": item["title"],
                "source": item["source_path"],
                "domain": item["domain"],
            }
            for item in docs
        )
    return rows


def confidence_floor(*, local_count: int, web_memory_count: int, web_count: int) -> float:
    if web_count:
        return 0.42
    if web_memory_count:
        return 0.4
    if local_count:
        return 0.38
    return 0.0
