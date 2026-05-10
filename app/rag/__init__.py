from __future__ import annotations

from typing import Any

from app.core.settings import Settings
from app.db.models.kb import KBChunkModel
from app.rag.retrieval.agentic import refine_retrieval_if_needed
from app.rag.retrieval.hybrid import retrieve as retrieve_hybrid
from app.rag.schemas import RetrievalResult
from app.schemas.requests import ContextInput


def retrieve_knowledge(
    *,
    query: str,
    context: ContextInput,
    payload: dict[str, Any],
    chunks: list[KBChunkModel],
    settings: Settings,
    output_language: str,
    use_agentic: bool = True,
) -> dict[str, Any]:
    """Unified read-only RAG facade for service and tool callers.

    The existing project still calls the lower-level retrieval modules in a few
    places. This facade gives future callers one stable entry point without
    forcing a risky all-at-once migration.
    """
    result = retrieve_hybrid(
        query=query,
        context=context,
        payload=payload,
        chunks=chunks,
        settings=settings,
        output_language=output_language,
    )
    if not use_agentic:
        return {
            "result": result,
            "agentic_rag": {
                "enabled": False,
                "selected_query": query,
                "selected_round": 1,
                "final_reason": "agentic_disabled",
            },
            "warnings": list(result.warnings),
        }

    refined, agentic_rag, agentic_warnings = refine_retrieval_if_needed(
        query=query,
        context=context,
        payload=payload,
        chunks=chunks,
        settings=settings,
        output_language=output_language,
        initial_result=result,
    )
    return {
        "result": refined,
        "agentic_rag": agentic_rag,
        "warnings": list(dict.fromkeys([*refined.warnings, *agentic_warnings])),
    }


__all__ = [
    "RetrievalResult",
    "retrieve_hybrid",
    "retrieve_knowledge",
]
