from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.settings import Settings
from app.rag.retrieval.hybrid import retrieve
from app.schemas.requests import ContextInput


def _chunk(*, chunk_id: str, text: str) -> SimpleNamespace:
    return SimpleNamespace(
        chunk_id=chunk_id,
        doc_id="doc_demo",
        title="Demo Doc",
        source_path="backend.md",
        domain="project_docs",
        section_path="Architecture",
        text=text,
        metadata_json={},
        module="Backend",
        doc_type="reference",
    )


def test_retrieve_uses_vector_scores_when_embeddings_and_qdrant_are_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.rag.retrieval.hybrid.embedding_available", lambda settings: True)
    monkeypatch.setattr("app.rag.retrieval.hybrid.qdrant_available", lambda settings: (True, "connected"))
    monkeypatch.setattr("app.rag.retrieval.hybrid.embed_query", lambda settings, text: [0.1, 0.2])
    monkeypatch.setattr(
        "app.rag.retrieval.hybrid.search_similar_chunks",
        lambda settings, query_vector, top_k, filters: [
            {"chunk_id": "chunk_a", "score": 0.91, "payload": {"domain": "project_docs"}}
        ],
    )

    settings = Settings(
        openai_api_key="demo-key",
        embedding_enabled=True,
        rag_mode="hybrid",
    )
    result = retrieve(
        query="Explain the backend architecture.",
        context=ContextInput(project_name="DemoProject", current_module="Backend"),
        payload={"domain_filters": ["project_docs"]},
        chunks=[
            _chunk(chunk_id="chunk_a", text="The backend uses FastAPI and a task service."),
            _chunk(chunk_id="chunk_b", text="This chunk is unrelated to the architecture."),
        ],
        settings=settings,
        output_language="en-US",
    )

    assert result.mode == "hybrid_vector"
    assert result.reason == "hybrid_vector_ready"
    assert result.retrieved_docs
    assert result.retrieved_docs[0].chunk_id == "chunk_a"
    assert result.retrieved_docs[0].semantic_score > 0


def test_retrieve_falls_back_to_lexical_only_when_embedding_is_unavailable() -> None:
    settings = Settings(
        openai_api_key="",
        embedding_enabled=False,
        rag_mode="hybrid",
        rag_fallback_mode="lexical_only",
    )
    result = retrieve(
        query="Explain the backend architecture.",
        context=ContextInput(project_name="DemoProject", current_module="Backend"),
        payload={"domain_filters": ["project_docs"]},
        chunks=[_chunk(chunk_id="chunk_a", text="The backend architecture uses FastAPI services.")],
        settings=settings,
        output_language="en-US",
    )

    assert result.mode == "lexical_only"
    assert result.degraded_mode is True
    assert "embedding_not_available" in result.warnings
