from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any

from sqlalchemy.orm import Session

from app.agent.memory_manager import recall_long_term_memory
from app.core.settings import Settings
from app.services.web_memory_service import WebMemoryService


LOCAL_MEMORY_DIRS = ("user", "project", "feedback", "incidents")


def _clip(value: str, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 3, 0)]}..."


def _tokens(value: str) -> set[str]:
    text = str(value or "").lower()
    return {
        token
        for token in re.findall(r"[a-z0-9_./:-]+|[\u4e00-\u9fff]{2,}", text)
        if len(token) >= 2
    }


def _heading(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or fallback
    return fallback


def _score_text(query: str, text: str, title: str = "") -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    haystack = f"{title}\n{text}".lower()
    haystack_tokens = _tokens(haystack)
    score = len(query_tokens & haystack_tokens) / max(len(query_tokens), 1)
    query_text = query.lower().strip()
    if query_text and query_text in haystack:
        score += 0.5
    return round(min(score, 1.0), 4)


@dataclass(slots=True)
class MemoryQuery:
    query: str
    project_name: str | None = None
    limit: int = 5
    domain_hints: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MemoryProviderResult:
    provider_id: str
    status: str
    items: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)

    def model_dump(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "status": self.status,
            "items": self.items,
            "raw": self.raw,
            "summary": self.summary,
        }


class MemoryProvider(ABC):
    provider_id: str

    @abstractmethod
    def recall(self, query: MemoryQuery) -> MemoryProviderResult:
        """Recall compact memory snippets for prompt/context use."""


class SessionLongTermMemoryProvider(MemoryProvider):
    provider_id = "session_long_term_memory"

    def __init__(self, db: Session):
        self.db = db

    def recall(self, query: MemoryQuery) -> MemoryProviderResult:
        raw = recall_long_term_memory(
            self.db,
            project_name=query.project_name,
            query=query.query,
            limit=query.limit,
        )
        items = [item for item in raw.get("items", []) if isinstance(item, dict)]
        return MemoryProviderResult(
            provider_id=self.provider_id,
            status=str(raw.get("status") or "not_found"),
            items=items,
            raw=raw,
            summary={
                "mode": raw.get("mode"),
                "count": raw.get("count", len(items)),
                "project_name": raw.get("project_name"),
            },
        )


class FileMemoryProvider(MemoryProvider):
    provider_id = "local_file_memory"

    def __init__(self, settings: Settings):
        self.settings = settings

    def recall(self, query: MemoryQuery) -> MemoryProviderResult:
        if not self.settings.local_memory_enabled:
            return MemoryProviderResult(
                provider_id=self.provider_id,
                status="skipped",
                items=[],
                raw={
                    "status": "skipped",
                    "reason": "disabled_by_settings",
                    "items": [],
                    "root": self.settings.local_memory_root,
                },
                summary={"enabled": False, "root": self.settings.local_memory_root, "count": 0},
            )

        root = Path(self.settings.local_memory_root)
        if not root.exists() or not root.is_dir():
            return MemoryProviderResult(
                provider_id=self.provider_id,
                status="not_found",
                items=[],
                raw={
                    "status": "not_found",
                    "reason": "root_not_found",
                    "items": [],
                    "root": str(root),
                },
                summary={"enabled": True, "root": str(root), "count": 0},
            )

        candidates = self._candidate_files(root)
        items: list[dict[str, Any]] = []
        skipped_too_large = 0
        for path in candidates[: max(self.settings.local_memory_max_files, 1)]:
            try:
                if path.stat().st_size > max(self.settings.local_memory_max_file_bytes, 1):
                    skipped_too_large += 1
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            title = _heading(text, path.stem)
            score = _score_text(query.query, text, title)
            if score <= 0 and _tokens(query.query):
                continue
            relative_path = self._relative_path(root, path)
            items.append(
                {
                    "memory_id": f"file:{relative_path}",
                    "scope": "local_private",
                    "project_name": query.project_name,
                    "category": self._category(root, path),
                    "title": title,
                    "path": relative_path,
                    "score": score,
                    "text": _clip(text, 620),
                    "retrieval_source": self.provider_id,
                    "source": "local_private_file",
                }
            )
        items.sort(key=lambda item: (float(item.get("score") or 0.0), str(item.get("path") or "")), reverse=True)
        limited = items[: max(query.limit, 1)]
        status = "available" if limited else "not_found"
        raw = {
            "status": status,
            "mode": "local_file_memory_v1",
            "root": str(root),
            "query": _clip(query.query, 300),
            "items": limited,
            "count": len(limited),
            "scanned_file_count": len(candidates),
            "skipped_too_large_count": skipped_too_large,
            "policy": "Local private memory is read-only and never written into knowledge/.",
        }
        return MemoryProviderResult(
            provider_id=self.provider_id,
            status=status,
            items=limited,
            raw=raw,
            summary={
                "enabled": True,
                "root": str(root),
                "count": len(limited),
                "scanned_file_count": len(candidates),
                "skipped_too_large_count": skipped_too_large,
            },
        )

    @staticmethod
    def _candidate_files(root: Path) -> list[Path]:
        files: list[Path] = []
        manifest = root / "MEMORY.md"
        if manifest.exists():
            files.append(manifest)
        for dirname in LOCAL_MEMORY_DIRS:
            folder = root / dirname
            if not folder.exists() or not folder.is_dir():
                continue
            for path in folder.rglob("*"):
                if path.is_file() and path.suffix.lower() in {".md", ".txt"}:
                    files.append(path)
        return files

    @staticmethod
    def _relative_path(root: Path, path: Path) -> str:
        try:
            return str(path.relative_to(root)).replace("\\", "/")
        except ValueError:
            return path.name

    @staticmethod
    def _category(root: Path, path: Path) -> str:
        relative = FileMemoryProvider._relative_path(root, path)
        first = relative.split("/", 1)[0]
        if first in LOCAL_MEMORY_DIRS:
            return first
        return "manifest"


class WebMemoryProvider(MemoryProvider):
    provider_id = "web_memory"

    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def recall(self, query: MemoryQuery) -> MemoryProviderResult:
        raw = WebMemoryService(self.db, self.settings).recall(
            query=query.query,
            domain_hints=query.domain_hints,
            limit=query.limit,
        )
        items = [item for item in raw.get("items", []) if isinstance(item, dict)]
        summary = dict(raw.get("summary") or {})
        return MemoryProviderResult(
            provider_id=self.provider_id,
            status=str(raw.get("status") or "not_found"),
            items=items,
            raw=raw,
            summary=summary,
        )
