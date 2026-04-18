from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ParsedDocument:
    source_path: str
    source_type: str
    title: str
    text: str
    language: str
    parser_name: str
    doc_type: str
    domain: str
    project_id: str | None = None
    module: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_storage_path: str | None = None
    normalized_storage_path: str | None = None


@dataclass(slots=True)
class ChunkPayload:
    chunk_index: int
    section_path: str
    text: str
    token_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RetrievalCandidate:
    chunk_id: str
    doc_id: str
    title: str
    source_path: str
    domain: str
    section_path: str
    text: str
    lexical_score: float
    semantic_score: float
    final_score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RetrievalResult:
    mode: str
    degraded_mode: bool
    reason: str
    filters_applied: dict[str, Any]
    retrieved_docs: list[RetrievalCandidate]
    confidence: float
    answer: str
    citations: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)


def resolve_local_path(value: str, root: Path) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    return candidate

