from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import Settings
from app.db.models.runtime_profile import RuntimeProfileModel


def seed_builtin_profiles(db: Session, settings: Settings) -> None:
    existing = db.get(RuntimeProfileModel, settings.default_profile_id)
    if existing:
        if existing.is_builtin:
            changed = False
            desired_values = {
                "name": settings.default_profile_name,
                "chat_model": settings.chat_model,
                "embedding_model": settings.embedding_model,
                "temperature": settings.default_profile_temperature,
                "max_tokens": settings.default_profile_max_tokens,
                "rag_top_k": settings.rag_top_k,
                "rerank_top_n": settings.rag_rerank_top_n,
                "allow_streaming": settings.default_profile_allow_streaming,
                "debug_mode": settings.default_profile_debug_mode,
                "tool_timeout_ms": settings.default_profile_tool_timeout_ms,
                "cost_guard_usd": settings.default_profile_cost_guard_usd,
            }
            for key, value in desired_values.items():
                if getattr(existing, key) != value:
                    setattr(existing, key, value)
                    changed = True
            if changed:
                db.commit()
        return

    profile = RuntimeProfileModel(
        profile_id=settings.default_profile_id,
        name=settings.default_profile_name,
        description="Phase 1 default runtime profile.",
        chat_model=settings.chat_model,
        embedding_model=settings.embedding_model,
        temperature=settings.default_profile_temperature,
        max_tokens=settings.default_profile_max_tokens,
        rag_top_k=settings.rag_top_k,
        rerank_top_n=settings.rag_rerank_top_n,
        allow_streaming=settings.default_profile_allow_streaming,
        debug_mode=settings.default_profile_debug_mode,
        tool_timeout_ms=settings.default_profile_tool_timeout_ms,
        cost_guard_usd=settings.default_profile_cost_guard_usd,
        is_active=True,
        is_default=True,
        is_builtin=True,
    )
    db.add(profile)
    db.commit()


def list_profiles(db: Session) -> list[RuntimeProfileModel]:
    return list(db.scalars(select(RuntimeProfileModel).order_by(RuntimeProfileModel.profile_id)))


def get_active_profile(db: Session) -> RuntimeProfileModel | None:
    statement = select(RuntimeProfileModel).where(RuntimeProfileModel.is_active.is_(True))
    return db.scalars(statement).first()


def get_default_profile(db: Session) -> RuntimeProfileModel | None:
    statement = select(RuntimeProfileModel).where(RuntimeProfileModel.is_default.is_(True))
    return db.scalars(statement).first()


def activate_profile(db: Session, profile_id: str) -> RuntimeProfileModel | None:
    target = db.get(RuntimeProfileModel, profile_id)
    if not target:
        return None
    for profile in list_profiles(db):
        profile.is_active = profile.profile_id == profile_id
    db.commit()
    db.refresh(target)
    return target


def set_default_profile(db: Session, profile_id: str) -> RuntimeProfileModel | None:
    target = db.get(RuntimeProfileModel, profile_id)
    if not target:
        return None
    for profile in list_profiles(db):
        profile.is_default = profile.profile_id == profile_id
    db.commit()
    db.refresh(target)
    return target
