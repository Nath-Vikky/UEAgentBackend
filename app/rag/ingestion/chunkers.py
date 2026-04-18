from __future__ import annotations

from app.core.settings import Settings
from app.rag.schemas import ChunkPayload


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))


def chunk_text(text: str, settings: Settings, title: str) -> list[ChunkPayload]:
    paragraphs = [item.strip() for item in text.split("\n\n") if item.strip()]
    if not paragraphs:
        return []

    chunks: list[ChunkPayload] = []
    current_parts: list[str] = []
    current_tokens = 0
    section_path = title
    for paragraph in paragraphs:
        paragraph_tokens = _estimate_tokens(paragraph)
        if paragraph.startswith("#"):
            section_path = paragraph.lstrip("# ").strip() or title
        if current_parts and current_tokens + paragraph_tokens > settings.kb_chunk_size:
            joined = "\n\n".join(current_parts).strip()
            chunks.append(
                ChunkPayload(
                    chunk_index=len(chunks),
                    section_path=section_path,
                    text=joined,
                    token_count=_estimate_tokens(joined),
                )
            )
            overlap_text = joined.split()
            overlap_size = min(len(overlap_text), settings.kb_chunk_overlap)
            current_parts = [" ".join(overlap_text[-overlap_size:])] if overlap_size else []
            current_tokens = _estimate_tokens(current_parts[0]) if current_parts else 0
        current_parts.append(paragraph)
        current_tokens += paragraph_tokens

    if current_parts:
        joined = "\n\n".join(current_parts).strip()
        chunks.append(
            ChunkPayload(
                chunk_index=len(chunks),
                section_path=section_path,
                text=joined,
                token_count=_estimate_tokens(joined),
            )
        )
    return chunks

