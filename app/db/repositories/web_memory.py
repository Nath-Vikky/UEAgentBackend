from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, desc, func, or_, select
from sqlalchemy.orm import Session

from app.db.models.web_memory import WebMemoryEntryModel, WebMemoryFeedbackModel
from app.utils.time import now_utc


def count_web_memory_entries(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(WebMemoryEntryModel)) or 0


def get_web_memory_entry(db: Session, entry_id: str) -> WebMemoryEntryModel | None:
    return db.get(WebMemoryEntryModel, entry_id)


def get_web_memory_entry_by_url(db: Session, url: str) -> WebMemoryEntryModel | None:
    statement = select(WebMemoryEntryModel).where(WebMemoryEntryModel.url == url)
    return db.scalars(statement).first()


def save_web_memory_entry(db: Session, entry: WebMemoryEntryModel) -> WebMemoryEntryModel:
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def list_active_web_memory_entries(
    db: Session,
    *,
    now: datetime | None = None,
    domain_hints: list[str] | None = None,
    limit: int = 200,
) -> list[WebMemoryEntryModel]:
    checked_at = now or now_utc()
    statement = select(WebMemoryEntryModel).where(
        or_(
            WebMemoryEntryModel.expires_at.is_(None),
            WebMemoryEntryModel.expires_at > checked_at,
        )
    )
    clean_domains = [item.lower().strip() for item in domain_hints or [] if item.strip()]
    if clean_domains:
        statement = statement.where(
            or_(*[WebMemoryEntryModel.domain.ilike(f"%{domain}%") for domain in clean_domains])
        )
    statement = statement.order_by(desc(WebMemoryEntryModel.quality_score), desc(WebMemoryEntryModel.updated_at)).limit(
        limit
    )
    return list(db.scalars(statement))


def list_recent_web_memory_entries(db: Session, *, limit: int = 20) -> list[WebMemoryEntryModel]:
    statement = select(WebMemoryEntryModel).order_by(desc(WebMemoryEntryModel.updated_at)).limit(limit)
    return list(db.scalars(statement))


def add_web_memory_feedback(db: Session, feedback: WebMemoryFeedbackModel) -> WebMemoryFeedbackModel:
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


def delete_expired_web_memory_entries(db: Session, *, now: datetime | None = None) -> int:
    checked_at = now or now_utc()
    result = db.execute(
        delete(WebMemoryEntryModel).where(
            WebMemoryEntryModel.expires_at.is_not(None),
            WebMemoryEntryModel.expires_at <= checked_at,
        )
    )
    db.commit()
    return int(result.rowcount or 0)


def trim_web_memory_entries(db: Session, *, max_entries: int) -> int:
    if max_entries <= 0:
        result = db.execute(delete(WebMemoryEntryModel))
        db.commit()
        return int(result.rowcount or 0)
    total = count_web_memory_entries(db)
    overflow = total - max_entries
    if overflow <= 0:
        return 0
    statement = (
        select(WebMemoryEntryModel.entry_id)
        .order_by(WebMemoryEntryModel.quality_score.asc(), WebMemoryEntryModel.updated_at.asc())
        .limit(overflow)
    )
    entry_ids = list(db.scalars(statement))
    if not entry_ids:
        return 0
    result = db.execute(delete(WebMemoryEntryModel).where(WebMemoryEntryModel.entry_id.in_(entry_ids)))
    db.commit()
    return int(result.rowcount or 0)
