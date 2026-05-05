from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.settings import Settings
from app.db.base import Base
from app.db.models.runtime_profile import RuntimeProfileModel
from app.db.repositories.runtime_profiles import seed_builtin_profiles


def _session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_builtin_default_profile_syncs_env_model_changes() -> None:
    session_factory = _session_factory()

    with session_factory() as db:
        seed_builtin_profiles(db, Settings(chat_model="old-model"))
        profile = db.get(RuntimeProfileModel, "default")
        assert profile is not None
        assert profile.chat_model == "old-model"

        seed_builtin_profiles(db, Settings(chat_model="new-model"))
        db.refresh(profile)

        assert profile.chat_model == "new-model"
        assert profile.is_builtin is True


def test_custom_profile_is_not_overwritten_by_builtin_sync() -> None:
    session_factory = _session_factory()

    with session_factory() as db:
        profile = RuntimeProfileModel(
            profile_id="default",
            name="Custom Default",
            description="User-managed profile.",
            chat_model="custom-model",
            embedding_model="custom-embedding",
            temperature=0.4,
            max_tokens=2048,
            rag_top_k=4,
            rerank_top_n=8,
            allow_streaming=True,
            debug_mode=True,
            tool_timeout_ms=45000,
            cost_guard_usd=5.0,
            is_active=True,
            is_default=True,
            is_builtin=False,
        )
        db.add(profile)
        db.commit()

        seed_builtin_profiles(db, Settings(chat_model="env-model"))
        db.refresh(profile)

        assert profile.chat_model == "custom-model"
