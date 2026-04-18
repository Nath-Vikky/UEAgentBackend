from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.settings import get_settings


def _engine_options(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        options = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in database_url:
            options["poolclass"] = StaticPool
        return options
    return {}


@lru_cache(maxsize=1)
def get_engine():
    settings = get_settings()
    return create_engine(settings.database_url, **_engine_options(settings.database_url))


@lru_cache(maxsize=1)
def get_session_factory():
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, class_=Session)


def db_session() -> Session:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
