from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401
from app.core.settings import Settings
from app.db.base import Base
from app.schemas.requests import ContextInput
from app.services.kb_service import KnowledgeBaseService
from app.services.web_memory_service import WebMemoryService


def _runtime_root(name: str) -> Path:
    return Path(".test-runtime") / f"{name}-{uuid.uuid4().hex}"


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


def _web_search_result() -> dict:
    return {
        "provider": "mock",
        "status": "completed",
        "reason": "matched",
        "trigger_reason": "explicit_user_request",
        "items": [
            {
                "rank": 1,
                "title": "Enhanced Input in Unreal Engine",
                "url": "https://dev.epicgames.com/documentation/en-us/unreal-engine/enhanced-input-in-unreal-engine",
                "domain": "dev.epicgames.com",
                "snippet": "Enhanced Input uses Input Actions and Mapping Contexts.",
                "source_type": "official",
                "score": 0.82,
                "provider": "mock",
            }
        ],
    }


def _multi_web_search_result() -> dict:
    return {
        "provider": "mock",
        "status": "completed",
        "reason": "matched",
        "trigger_reason": "explicit_user_request",
        "items": [
            {
                "rank": 1,
                "title": "Official Enhanced Input",
                "url": "https://dev.epicgames.com/enhanced-input",
                "domain": "dev.epicgames.com",
                "snippet": "Enhanced Input uses Input Actions and Mapping Contexts.",
                "source_type": "official",
                "score": 0.82,
                "provider": "mock",
            },
            {
                "rank": 2,
                "title": "Community Enhanced Input Note",
                "url": "https://example.com/enhanced-input-note",
                "domain": "example.com",
                "snippet": "Enhanced Input Mapping Context setup with Input Actions.",
                "source_type": "community",
                "score": 0.4,
                "provider": "mock",
            },
        ],
    }


def test_web_memory_disabled_does_not_store_or_recall() -> None:
    with _memory_session() as session:
        service = WebMemoryService(session, Settings(_env_file=None, web_memory_enabled=False))

        stored = service.remember_web_search_result(query="Enhanced Input", web_search=_web_search_result())
        recalled = service.recall(query="Enhanced Input")

    assert stored["status"] == "skipped"
    assert stored["reason"] == "disabled_by_settings"
    assert recalled["status"] == "skipped"
    assert recalled["items"] == []


def test_web_memory_stores_recalls_and_accepts_feedback() -> None:
    with _memory_session() as session:
        service = WebMemoryService(
            session,
            Settings(_env_file=None, web_memory_enabled=True, web_memory_ttl_days=7),
        )

        stored = service.remember_web_search_result(query="UE Enhanced Input", web_search=_web_search_result())
        recalled = service.recall(query="Enhanced Input Mapping Context")
        entry_id = recalled["items"][0]["entry_id"]
        feedback = service.record_feedback(entry_id=entry_id, rating="helpful", task_id="task_1")
        recalled_after_feedback = service.recall(query="Enhanced Input Mapping Context")

    assert stored["stored_count"] == 1
    assert recalled["status"] == "completed"
    assert recalled["reason"] == "matched"
    assert recalled["items"][0]["retrieval_source"] == "web_memory"
    assert feedback is not None
    assert feedback["entry"]["helpful_count"] == 1
    assert recalled_after_feedback["items"][0]["helpful_count"] == 1


def test_web_memory_recall_uses_fts5_or_safe_fallback() -> None:
    with _memory_session() as session:
        service = WebMemoryService(
            session,
            Settings(_env_file=None, web_memory_enabled=True, web_memory_ttl_days=7),
        )

        service.remember_web_search_result(query="UE Enhanced Input", web_search=_web_search_result())
        recalled = service.recall(query="Enhanced Input Mapping Context")

    assert recalled["status"] == "completed"
    assert recalled["items"]
    assert recalled["summary"]["search_mode"] in {"sqlite_fts5", "python_token_fallback"}
    assert recalled["summary"]["fts5"]["enabled"] is True


def test_web_memory_recall_can_disable_fts5() -> None:
    with _memory_session() as session:
        service = WebMemoryService(
            session,
            Settings(
                _env_file=None,
                web_memory_enabled=True,
                web_memory_ttl_days=7,
                web_memory_fts_enabled=False,
            ),
        )

        service.remember_web_search_result(query="UE Enhanced Input", web_search=_web_search_result())
        recalled = service.recall(query="Enhanced Input Mapping Context")

    assert recalled["status"] == "completed"
    assert recalled["items"]
    assert recalled["summary"]["search_mode"] == "python_token"
    assert recalled["summary"]["fts5"] == {
        "enabled": False,
        "used": False,
        "reason": "disabled_by_settings",
    }
    assert "ranking_policy" in recalled["summary"]
    assert "ranking" in recalled["items"][0]


def test_web_memory_ranking_diagnostics_explain_feedback_boost() -> None:
    with _memory_session() as session:
        service = WebMemoryService(
            session,
            Settings(
                _env_file=None,
                web_memory_enabled=True,
                web_memory_ttl_days=7,
                web_memory_fts_enabled=False,
            ),
        )

        service.remember_web_search_result(query="UE Enhanced Input", web_search=_multi_web_search_result())
        first_recall = service.recall(query="Enhanced Input Mapping Context", limit=2)
        community_entry = next(
            item for item in first_recall["items"] if item["title"] == "Community Enhanced Input Note"
        )
        for _ in range(3):
            service.record_feedback(entry_id=community_entry["entry_id"], rating="helpful", task_id="task_1")
        recalled = service.recall(query="Enhanced Input Mapping Context", limit=2)

    top = recalled["items"][0]
    assert top["title"] == "Community Enhanced Input Note"
    assert top["ranking"]["score_source"] == "python_token"
    assert top["ranking"]["feedback_boost"] > 0
    assert top["ranking"]["matched_term_count"] >= 3


def test_project_qa_reuses_web_memory_before_new_web_search() -> None:
    runtime_root = _runtime_root("web-memory-project-qa")
    shutil.rmtree(runtime_root, ignore_errors=True)
    try:
        runtime_root.mkdir(parents=True)
        mock_path = runtime_root / "web-results.json"
        mock_path.write_text(json.dumps({"results": _web_search_result()["items"]}), encoding="utf-8")
        with _memory_session() as session:
            service = KnowledgeBaseService(
                session,
                Settings(
                    _env_file=None,
                    openai_api_key="",
                    kb_source_paths=[str(runtime_root / "empty-kb")],
                    embedding_enabled=False,
                    rag_mode="hybrid",
                    rag_fallback_mode="lexical_only",
                    web_search_enabled=True,
                    web_search_provider="mock",
                    web_search_mock_results_path=str(mock_path),
                    web_search_allowed_domains=["dev.epicgames.com"],
                    web_memory_enabled=True,
                ),
            )
            service.ensure_seeded = lambda: None  # type: ignore[method-assign]

            first = service.project_qa(
                query="Search official docs for UE Enhanced Input",
                context=ContextInput(project_name="Demo"),
                payload={"use_web_search": True, "disable_local_search": True},
                output_language="en-US",
                source_task_id="task_first",
            )
            second = service.project_qa(
                query="Enhanced Input Mapping Context",
                context=ContextInput(project_name="Demo"),
                payload={"disable_web_search": True, "disable_local_search": True},
                output_language="en-US",
                source_task_id="task_second",
            )
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)

    assert first["web_memory_store"]["stored_count"] == 1
    assert second["web_memory"]["status"] == "completed"
    assert second["retrieval_quality_gate"]["web_memory_retrieved_count"] == 1
    assert second["source_arbitration"]["primary_source"] == "web_memory"
    assert second["retrieved_docs"][0]["retrieval_source"] == "web_memory"
