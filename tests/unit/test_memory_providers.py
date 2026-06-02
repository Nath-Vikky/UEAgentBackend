from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401
from app.agent.context_manager import build_context_bundle, context_bundle_prompt_excerpt
from app.agent.memory_providers import (
    FileMemoryProvider,
    MemoryQuery,
    SessionLongTermMemoryProvider,
    WebMemoryProvider,
)
from app.core.settings import Settings
from app.db.base import Base
from app.db.models.session import SessionModel
from app.schemas.requests import UnifiedTaskRequest
from app.services.web_memory_service import WebMemoryService


@contextmanager
def _memory_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_session_long_term_memory_provider_wraps_existing_recall_contract() -> None:
    with _memory_session() as session:
        session.add(
            SessionModel(
                session_id="s1",
                project_name="DemoProject",
                metadata_json={
                    "long_term_memory_items": [
                        {
                            "memory_id": "m1",
                            "scope": "project",
                            "project_name": "DemoProject",
                            "category": "naming_rule",
                            "text": "蓝图资产统一使用 BP_ 前缀。",
                            "last_seen_at": "2026-05-16T00:00:00+00:00",
                        }
                    ]
                },
            )
        )
        session.commit()

        result = SessionLongTermMemoryProvider(session).recall(
            MemoryQuery(query="蓝图命名规则是什么", project_name="DemoProject", limit=5)
        )

    assert result.provider_id == "session_long_term_memory"
    assert result.status == "available"
    assert result.items[0]["memory_id"] == "m1"
    assert result.raw["mode"] == "sqlite_keyword_recall"


def test_web_memory_provider_preserves_disabled_contract() -> None:
    with _memory_session() as session:
        result = WebMemoryProvider(session, Settings(_env_file=None, web_memory_enabled=False)).recall(
            MemoryQuery(query="Enhanced Input", domain_hints=["dev.epicgames.com"])
        )

    assert result.provider_id == "web_memory"
    assert result.status == "skipped"
    assert result.items == []
    assert result.raw["reason"] == "disabled_by_settings"


def test_file_memory_provider_reads_private_markdown_when_enabled() -> None:
    root = Path("storage/test-tmp/memory") / uuid.uuid4().hex
    project_dir = root / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    (root / "MEMORY.md").write_text(
        "# Memory Index\n\n- project/enhanced-input.md: Enhanced Input setup notes.\n",
        encoding="utf-8",
    )
    (project_dir / "enhanced-input.md").write_text(
        "# Enhanced Input Setup\n\nUse Input Actions and Mapping Contexts for character input.",
        encoding="utf-8",
    )
    settings = Settings(
        _env_file=None,
        local_memory_enabled=True,
        local_memory_root=str(root),
        local_memory_max_files=10,
    )

    result = FileMemoryProvider(settings).recall(
        MemoryQuery(query="Enhanced Input Mapping Context", project_name="DemoProject", limit=3)
    )

    assert result.provider_id == "local_file_memory"
    assert result.status == "available"
    assert result.items[0]["retrieval_source"] == "local_file_memory"
    assert "Enhanced Input" in result.items[0]["title"]
    assert result.raw["policy"].startswith("Local private memory")


def test_context_bundle_injects_web_memory_as_separate_source() -> None:
    with _memory_session() as session:
        settings = Settings(
            _env_file=None,
            web_memory_enabled=True,
            web_memory_ttl_days=7,
            web_memory_fts_enabled=False,
        )
        WebMemoryService(session, settings).remember_web_search_result(
            query="UE Enhanced Input",
            web_search={
                "provider": "mock",
                "status": "completed",
                "reason": "matched",
                "items": [
                    {
                        "rank": 1,
                        "title": "Enhanced Input in Unreal Engine",
                        "url": "https://dev.epicgames.com/documentation/en-us/unreal-engine/enhanced-input",
                        "domain": "dev.epicgames.com",
                        "snippet": "Enhanced Input uses Input Actions and Mapping Contexts.",
                        "source_type": "official",
                        "score": 0.82,
                        "provider": "mock",
                    }
                ],
            },
        )
        request = UnifiedTaskRequest.model_validate(
            {
                "task_type": "agent_chat",
                "session": {
                    "session_id": "web_memory_context_session",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Enhanced Input Mapping Context 怎么用？",
                            "language": "auto",
                        }
                    ],
                },
                "context": {
                    "project_name": "DemoProject",
                    "kb_domains_hint": ["dev.epicgames.com"],
                },
                "payload": {"user_query": "Enhanced Input Mapping Context 怎么用？"},
            }
        )
        routing = {
            "intent": {"route_type": "direct_answer"},
            "route": {"selected_tool_id": None},
            "locale": {"final_output_language": "zh-CN"},
        }

        bundle = build_context_bundle(
            db=session,
            request=request,
            routing=routing,
            settings=settings,
            actual_task_type="direct_answer",
        )

    assert bundle["long_term_memory"]["status"] == "not_found"
    assert bundle["web_memory"]["status"] == "completed"
    assert bundle["web_memory"]["items"][0]["retrieval_source"] == "web_memory"
    assert bundle["memory"]["version"] == "memory_context_v1"
    assert {
        source["provider_id"]: source["status"]
        for source in bundle["memory"]["sources"]
    } == {
        "session_long_term_memory": "not_found",
        "local_file_memory": "skipped",
        "web_memory": "completed",
    }
    assert any(item["provider_id"] == "web_memory" for item in bundle["memory"]["items"])
    assert bundle["memory"]["policy"]["web_memory"].startswith("Cached web-search summaries")
    assert "Web memory" in context_bundle_prompt_excerpt(bundle)
