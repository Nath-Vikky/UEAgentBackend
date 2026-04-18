from __future__ import annotations

from app.rag.schemas import RetrievalCandidate


def build_citations(candidates: list[RetrievalCandidate], limit: int = 3) -> list[dict]:
    citations: list[dict] = []
    for item in candidates[:limit]:
        citations.append(
            {
                "title": item.title,
                "source": item.source_path,
                "section_path": item.section_path,
                "snippet": item.text[:220],
                "score": round(item.final_score, 4),
                "domain": item.domain,
            }
        )
    return citations

