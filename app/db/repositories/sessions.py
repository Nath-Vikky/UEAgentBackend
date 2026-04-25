from __future__ import annotations

import uuid

from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.orm import Session

from app.db.models.session import MessageModel, SessionModel
from app.db.models.task import TaskModel
from app.i18n.language import normalize_output_language
from app.utils.time import utc_isoformat


def get_or_create_session(
    db: Session,
    session_id: str,
    *,
    project_name: str | None,
    preferred_output_language: str | None,
    profile_id: str | None,
) -> SessionModel:
    normalized_language = normalize_output_language(preferred_output_language)
    session_model = db.get(SessionModel, session_id)
    if session_model:
        if project_name:
            session_model.project_name = project_name
        if normalized_language and normalized_language != "auto":
            session_model.preferred_output_language = normalized_language
        if profile_id:
            session_model.current_profile_id = profile_id
        db.commit()
        db.refresh(session_model)
        return session_model

    session_model = SessionModel(
        session_id=session_id,
        project_name=project_name,
        preferred_output_language=(
            normalized_language if normalized_language and normalized_language != "auto" else None
        ),
        current_profile_id=profile_id,
        metadata_json={"created_via": "phase_1_scaffold"},
    )
    db.add(session_model)
    db.commit()
    db.refresh(session_model)
    return session_model


def _normalize_messages(messages: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user").strip() or "user"
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        language = str(item.get("language") or "").strip() or None
        metadata_json = item.get("metadata_json") or item.get("metadata") or {}
        normalized.append(
            {
                "role": role,
                "content": content,
                "language": language,
                "metadata_json": dict(metadata_json) if isinstance(metadata_json, dict) else {},
            }
        )
    return normalized


def _message_signature(item: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(item.get("role") or "user"),
        str(item.get("content") or ""),
        str(item.get("language") or ""),
    )


def _longest_prefix_match(existing: list[tuple[str, str, str]], incoming: list[tuple[str, str, str]]) -> int:
    max_size = min(len(existing), len(incoming))
    for size in range(max_size, 0, -1):
        prefix = incoming[:size]
        for start in range(len(existing) - size + 1):
            if existing[start : start + size] == prefix:
                return size
    return 0


def append_messages(db: Session, session_id: str, messages: list[dict]) -> None:
    normalized = _normalize_messages(messages)
    if not normalized:
        return

    existing_models = list(
        db.scalars(
            select(MessageModel)
            .where(MessageModel.session_id == session_id)
            .order_by(MessageModel.created_at.asc(), MessageModel.message_id.asc())
        )
    )
    existing = [
        {
            "role": item.role,
            "content": item.content,
            "language": item.language,
        }
        for item in existing_models
    ]
    existing_signatures = [_message_signature(item) for item in existing]
    incoming_signatures = [_message_signature(item) for item in normalized]

    if len(normalized) == 1:
        overlap = 1 if existing_signatures and existing_signatures[-1] == incoming_signatures[0] else 0
    else:
        overlap = _longest_prefix_match(existing_signatures, incoming_signatures)
        if overlap == len(normalized):
            return

    for item in normalized[overlap:]:
        db.add(
            MessageModel(
                message_id=f"msg_{utc_isoformat()}_{uuid.uuid4().hex}",
                session_id=session_id,
                role=item["role"],
                content=item["content"],
                language=item["language"],
                metadata_json=item["metadata_json"],
            )
        )
    db.commit()


def get_session(db: Session, session_id: str) -> SessionModel | None:
    return db.get(SessionModel, session_id)


def list_session_messages(
    db: Session,
    session_id: str,
    *,
    limit: int = 100,
) -> list[MessageModel]:
    statement = (
        select(MessageModel)
        .where(MessageModel.session_id == session_id)
        .order_by(MessageModel.created_at.asc(), MessageModel.message_id.asc())
        .limit(limit)
    )
    return list(db.scalars(statement))


def list_session_tasks(
    db: Session,
    session_id: str,
    *,
    limit: int = 50,
) -> list[TaskModel]:
    statement = (
        select(TaskModel)
        .where(TaskModel.session_id == session_id)
        .order_by(desc(TaskModel.created_at))
        .limit(limit)
    )
    return list(db.scalars(statement))


def clear_session_state(db: Session, session_id: str) -> SessionModel | None:
    session_model = db.get(SessionModel, session_id)
    if not session_model:
        return None
    message_count = (
        db.scalar(select(func.count()).select_from(MessageModel).where(MessageModel.session_id == session_id))
        or 0
    )
    task_count = (
        db.scalar(select(func.count()).select_from(TaskModel).where(TaskModel.session_id == session_id)) or 0
    )
    db.execute(delete(MessageModel).where(MessageModel.session_id == session_id))
    db.execute(update(TaskModel).where(TaskModel.session_id == session_id).values(session_id=None))
    session_model.preferred_output_language = None
    session_model.metadata_json = {
        **dict(session_model.metadata_json or {}),
        "cleared": True,
        "last_clear_message_count": message_count,
        "last_clear_task_count": task_count,
    }
    db.commit()
    db.refresh(session_model)
    return session_model
