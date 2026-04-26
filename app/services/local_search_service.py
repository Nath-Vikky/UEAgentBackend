from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.settings import Settings
from app.rag.ingestion.capabilities import SUPPORTED_SUFFIXES
from app.rag.ingestion.loaders import discover_source_paths
from app.rag.indexing.sparse import tokenize_query


DOMAIN_DIR_ALIASES = {
    "asset-rules": "asset_rules",
    "asset_rules": "asset_rules",
    "code-reference": "code_reference",
    "code_reference": "code_reference",
    "engine-notes": "engine_notes",
    "engine_notes": "engine_notes",
    "examples": "examples",
    "incident-history": "incident_history",
    "incident_history": "incident_history",
    "perf-notes": "perf_notes",
    "perf_notes": "perf_notes",
    "project-docs": "project_docs",
    "project_docs": "project_docs",
    "team-rules": "team_rules",
    "team_rules": "team_rules",
}

CODE_SUFFIXES = {".h", ".hpp", ".hh", ".inl", ".c", ".cc", ".cpp", ".cxx", ".cs", ".py"}
MIN_TERM_LENGTH = 2


@dataclass(frozen=True, slots=True)
class LocalSearchItem:
    item_id: str
    title: str
    source_path: str
    domain: str
    snippet: str
    score: float
    matched_terms: list[str]
    line_start: int
    line_end: int
    file_extension: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "title": self.title,
            "source_path": self.source_path,
            "domain": self.domain,
            "snippet": self.snippet,
            "score": self.score,
            "matched_terms": self.matched_terms,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "file_extension": self.file_extension,
        }


def _relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _infer_domain(path: Path) -> str:
    parts = [part.lower().replace("_", "-") for part in path.parts]
    for part in reversed(parts):
        if part in DOMAIN_DIR_ALIASES:
            return DOMAIN_DIR_ALIASES[part]
    suffix = path.suffix.lower()
    path_lower = path.as_posix().lower()
    if suffix in CODE_SUFFIXES:
        return "code_reference"
    if "example" in path_lower or "sample" in path_lower or "template" in path_lower:
        return "examples"
    if "asset" in path_lower or "nanite" in path_lower or "blueprint" in path_lower:
        return "asset_rules"
    if "engine" in path_lower or "unreal" in path_lower or "ue-" in path_lower:
        return "engine_notes"
    if "rule" in path_lower or "style" in path_lower or "convention" in path_lower:
        return "team_rules"
    return "project_docs"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _title_from_text(path: Path, text: str) -> str:
    for line in text.splitlines()[:20]:
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title
    return path.stem.replace("_", " ").replace("-", " ").strip() or path.name


def _query_terms(query: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for token in tokenize_query(query):
        token = token.strip().lower()
        if not token:
            continue
        if len(token) < MIN_TERM_LENGTH and not ("\u4e00" <= token <= "\u9fff"):
            continue
        if token not in seen:
            terms.append(token)
            seen.add(token)
    return terms


def _line_match_score(line: str, terms: list[str]) -> int:
    lowered = line.lower()
    return sum(lowered.count(term) for term in terms)


def _snippet(text: str, terms: list[str], *, window: int = 2) -> tuple[str, int, int]:
    lines = text.splitlines()
    if not lines:
        return ("", 1, 1)
    best_index = 0
    best_score = -1
    for index, line in enumerate(lines):
        score = _line_match_score(line, terms)
        if score > best_score:
            best_score = score
            best_index = index
    start = max(0, best_index - window)
    end = min(len(lines), best_index + window + 1)
    selected = [line.rstrip() for line in lines[start:end]]
    return ("\n".join(selected).strip()[:1200], start + 1, end)


def _score(
    *,
    query: str,
    title: str,
    text: str,
    terms: list[str],
) -> tuple[float, list[str]]:
    lowered_text = text.lower()
    lowered_title = title.lower()
    matched_terms = [term for term in terms if term in lowered_text or term in lowered_title]
    if not matched_terms:
        return (0.0, [])

    term_ratio = len(matched_terms) / max(len(terms), 1)
    occurrence_count = sum(len(re.findall(re.escape(term), lowered_text)) for term in matched_terms)
    occurrence_score = min(0.35, occurrence_count * 0.025)
    title_score = 0.2 if any(term in lowered_title for term in matched_terms) else 0.0
    phrase_score = 0.25 if len(query.strip()) >= 6 and query.lower().strip() in lowered_text else 0.0
    code_symbol_bonus = 0.15 if any("_" in term or "::" in term or "/" in term for term in matched_terms) else 0.0
    return (round(min(1.0, term_ratio * 0.55 + occurrence_score + title_score + phrase_score + code_symbol_bonus), 4), matched_terms)


class LocalSearchService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def discover_files(self, source_paths: list[str] | None = None) -> list[Path]:
        return discover_source_paths(self.settings, source_paths)

    def status(self, *, source_paths: list[str] | None = None) -> dict[str, Any]:
        files = self.discover_files(source_paths)
        domain_counts: dict[str, int] = {}
        for path in files:
            if path.stat().st_size > self.settings.kb_max_file_bytes:
                continue
            domain = _infer_domain(path)
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        return {
            "enabled": True,
            "status": "ready" if files else "empty",
            "source_paths": source_paths or self.settings.kb_source_paths,
            "searchable_files": len(files),
            "domain_counts": domain_counts,
            "supported_suffixes": sorted(SUPPORTED_SUFFIXES),
            "max_file_bytes": self.settings.kb_max_file_bytes,
        }

    def search(
        self,
        *,
        query: str,
        domain_filters: list[str] | None = None,
        source_paths: list[str] | None = None,
        top_k: int = 6,
    ) -> dict[str, Any]:
        terms = _query_terms(query)
        filters = [item for item in (domain_filters or []) if item]
        if not terms:
            return self._empty_result(query=query, domain_filters=filters, reason="empty_query_terms")

        items: list[LocalSearchItem] = []
        skipped_files = 0
        for path in self.discover_files(source_paths):
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            if path.stat().st_size > self.settings.kb_max_file_bytes:
                skipped_files += 1
                continue
            domain = _infer_domain(path)
            if filters and domain not in filters:
                continue
            text = _read_text(path)
            title = _title_from_text(path, text)
            score, matched_terms = _score(query=query, title=title, text=text, terms=terms)
            if score <= 0:
                continue
            snippet, line_start, line_end = _snippet(text, matched_terms)
            items.append(
                LocalSearchItem(
                    item_id=f"local_{len(items) + 1}",
                    title=title,
                    source_path=_relative_path(path),
                    domain=domain,
                    snippet=snippet,
                    score=score,
                    matched_terms=matched_terms,
                    line_start=line_start,
                    line_end=line_end,
                    file_extension=path.suffix.lower().lstrip("."),
                )
            )

        sorted_items = sorted(items, key=lambda item: item.score, reverse=True)[: max(top_k, 1)]
        return {
            "query": query,
            "mode": "local_grep",
            "status": "completed",
            "reason": "matched" if sorted_items else "no_local_matches",
            "items": [item.to_dict() for item in sorted_items],
            "summary": {
                "result_count": len(sorted_items),
                "candidate_count": len(items),
                "searched_file_count": len(self.discover_files(source_paths)),
                "skipped_file_count": skipped_files,
                "domain_filters": filters,
                "terms": terms,
            },
        }

    @staticmethod
    def _empty_result(*, query: str, domain_filters: list[str], reason: str) -> dict[str, Any]:
        return {
            "query": query,
            "mode": "local_grep",
            "status": "skipped",
            "reason": reason,
            "items": [],
            "summary": {
                "result_count": 0,
                "candidate_count": 0,
                "searched_file_count": 0,
                "skipped_file_count": 0,
                "domain_filters": domain_filters,
                "terms": [],
            },
        }
