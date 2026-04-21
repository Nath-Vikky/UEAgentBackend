from __future__ import annotations

from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.orm import Session

from app.db.models.session import MessageModel, SessionModel
from app.db.models.task import TaskModel
from app.utils.time import utc_isoformat


def get_or_create_session(
    db: Session,
    session_id: str,
    *,
    project_name: str | None,
    preferred_output_language: str | None,
    profile_id: str | None,
) -> SessionModel:
    session_model = db.get(SessionModel, session_id)
    if session_model:
        if project_name:
            session_model.project_name = project_name
        if preferred_output_language and preferred_output_language != "auto":
            session_model.preferred_output_language = preferred_output_language
        if profile_id:
            session_model.current_profile_id = profile_id
        db.commit()
        db.refresh(session_model)
        return session_model

    session_model = SessionModel(
        session_id=session_id,
        project_name=project_name,
        preferred_output_language=preferred_output_language,
        current_profile_id=profile_id,
        metadata_json={"created_via": "phase_1_scaffold"},
    )
    db.add(session_model)
    db.commit()
    db.refresh(session_model)
    return session_model


def append_messages(db: Session, session_id: str, messages: list[dict]) -> None:
    for item in messages:
        db.add(
            MessageModel(
                message_id=f"msg_{utc_isoformat()}_{abs(hash(item['content']))}",
                session_id=session_id,
                role=item["role"],
                content=item["content"],
                language=item.get("language"),
                metadata_json={},
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
        .order_by(MessageModel.created_at.asc())
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
