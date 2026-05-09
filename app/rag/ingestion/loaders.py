from __future__ import annotations

from pathlib import Path

from app.core.settings import Settings
from app.rag.ingestion.capabilities import SUPPORTED_SUFFIXES
from app.rag.schemas import resolve_local_path


LOCAL_ONLY_DOC_NAMES = {
    "agent-architecture-study.md",
    "agent-project-study-notes.md",
    "architecture.md",
    "backend-dev-log.md",
    "benchmark-report.md",
    "code-review-benchmark-report.md",
    "frontend-unified-handoff.md",
    "improveplan.md",
    "project-demo-script.md",
    "rag-agentic-ab-report.md",
    "rag-and-memory-study.md",
    "rag-eval-report.md",
    "request-lifecycle.md",
    "skill-development-guide.md",
}


def _is_supported_source_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES


def _is_default_directory_scan_candidate(path: Path) -> bool:
    if not _is_supported_source_file(path):
        return False
    return path.name.lower() not in LOCAL_ONLY_DOC_NAMES


def discover_source_paths(settings: Settings, source_paths: list[str] | None = None) -> list[Path]:
    base_dir = Path.cwd()
    resolved_items: list[Path] = []
    for item in source_paths or settings.kb_source_paths:
        candidate = resolve_local_path(item, base_dir)
        if candidate.is_dir():
            for file_path in candidate.rglob("*"):
                if _is_default_directory_scan_candidate(file_path):
                    resolved_items.append(file_path.resolve())
        elif _is_supported_source_file(candidate):
            resolved_items.append(candidate.resolve())
    return sorted(dict.fromkeys(resolved_items))
