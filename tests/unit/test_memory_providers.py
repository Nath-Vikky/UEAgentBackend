from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401
from app.agent.memory_providers import (
    MemoryQuery,
    SessionLongTermMemoryProvider,
    WebMemoryProvider,
)
from app.core.settings import Settings
from app.db.base import Base
from app.db.models.session import SessionModel


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
