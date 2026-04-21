from __future__ import annotations

from pathlib import Path

from app.core.settings import Settings
from app.rag.ingestion.parsers import TEXT_SOURCE_SUFFIXES
from app.rag.schemas import resolve_local_path

SUPPORTED_SUFFIXES = set(TEXT_SOURCE_SUFFIXES) | {".pdf", ".docx"}


def discover_source_paths(settings: Settings, source_paths: list[str] | None = None) -> list[Path]:
    base_dir = Path.cwd()
    resolved_items: list[Path] = []
    for item in source_paths or settings.kb_source_paths:
        candidate = resolve_local_path(item, base_dir)
        if candidate.is_dir():
            for file_path in candidate.rglob("*"):
                if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_SUFFIXES:
                    resolved_items.append(file_path.resolve())
        elif candidate.is_file() and candidate.suffix.lower() in SUPPORTED_SUFFIXES:
            resolved_items.append(candidate.resolve())
    return sorted(dict.fromkeys(resolved_items))
