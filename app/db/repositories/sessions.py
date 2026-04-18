from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models.session import MessageModel, SessionModel
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

