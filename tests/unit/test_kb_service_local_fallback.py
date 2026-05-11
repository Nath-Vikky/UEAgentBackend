from __future__ import annotations

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


def _write_note(root: Path) -> None:
    note_dir = root / "engine-notes"
    note_dir.mkdir(parents=True)
    (note_dir / "ue-soft-references.md").write_text(
        "# Soft References\n\nUse TSoftObjectPtr and async loading instead of LoadObject in Tick.",
        encoding="utf-8",
    )


def test_project_qa_uses_local_grep_when_lexical_index_has_no_hits() -> None:
    runtime_root = _runtime_root("kb-local-fallback")
    shutil.rmtree(runtime_root, ignore_errors=True)
    try:
        _write_note(runtime_root)
        with _memory_session() as session:
            service = KnowledgeBaseService(
                session,
                Settings(
                    openai_api_key="",
                    kb_source_paths=[str(runtime_root)],
                    embedding_enabled=False,
                    rag_mode="hybrid",
                    rag_fallback_mode="lexical_only",
                ),
            )
            service.ensure_seeded = lambda: None  # type: ignore[method-assign]

            result = service.project_qa(
                query="TSoftObjectPtr async loading",
                context=ContextInput(project_name="Demo", kb_domains_hint=["engine_notes"]),
                payload={"domain_filters": ["engine_notes"]},
                output_language="en-US",
            )
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)

    assert result["retrieval_trace"]["mode"] == "lexical_only"
    assert result["retrieval_trace"]["reason"] == "embedding_not_available"
    assert result["local_search"]["status"] == "completed"
    assert result["retrieval_quality_gate"]["local_retrieved_count"] >= 1
    assert result["retrieved_docs"][0]["retrieval_source"] == "local_grep"
    assert "local_search_fallback_used" in result["warnings"]
    assert result["answer"].startswith("The strongest local markdown/code matches")


def test_project_qa_reports_explicit_local_search_disabled_reason() -> None:
    runtime_root = _runtime_root("kb-local-disabled")
    shutil.rmtree(runtime_root, ignore_errors=True)
    try:
        _write_note(runtime_root)
        with _memory_session() as session:
            service = KnowledgeBaseService(
                session,
                Settings(
                    openai_api_key="",
                    kb_source_paths=[str(runtime_root)],
                    embedding_enabled=False,
                    rag_mode="hybrid",
                    rag_fallback_mode="lexical_only",
                ),
            )
            service.ensure_seeded = lambda: None  # type: ignore[method-assign]

            result = service.project_qa(
                query="TSoftObjectPtr async loading",
                context=ContextInput(project_name="Demo", kb_domains_hint=["engine_notes"]),
                payload={"domain_filters": ["engine_notes"], "disable_local_search": True},
                output_language="en-US",
            )
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)

    assert result["local_search"]["status"] == "skipped"
    assert result["local_search"]["reason"] == "disabled_by_payload"
    assert result["retrieval_quality_gate"]["local_retrieved_count"] == 0
    assert "local_search_fallback_used" not in result["warnings"]
