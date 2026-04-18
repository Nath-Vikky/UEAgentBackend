from __future__ import annotations

from app.rag.schemas import RetrievalCandidate


def rerank_candidates(candidates: list[RetrievalCandidate], top_n: int) -> list[RetrievalCandidate]:
    return sorted(candidates, key=lambda item: item.final_score, reverse=True)[:top_n]

