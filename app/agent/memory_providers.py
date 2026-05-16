from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.agent.memory_manager import recall_long_term_memory
from app.core.settings import Settings
from app.services.web_memory_service import WebMemoryService


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
