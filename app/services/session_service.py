from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.settings import Settings
from app.db.repositories.sessions import (
    clear_session_state,
    get_or_create_session,
    get_session,
    list_session_messages,
    list_session_tasks,
)
from app.i18n.language import DEFAULT_OUTPUT_LANGUAGE
from app.schemas.requests import SessionCreateRequest
from app.schemas.responses import UnifiedTaskResponse
from app.services.task_service import TaskService


class SessionService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings
        self.task_service = TaskService(db, settings)

    def create_or_restore(self, request: SessionCreateRequest) -> dict:
        session_model = get_or_create_session(
            self.db,
            request.session_id,
            project_name=request.project_name,
            preferred_output_language=request.preferred_output_language,
            profile_id=request.profile_id,
        )
        metadata = dict(session_model.metadata_json or {})
        metadata.update(request.metadata or {})
        metadata.setdefault("created_via", "session_api")
        session_model.metadata_json = metadata
        self.db.add(session_model)
        self.db.commit()
        self.db.refresh(session_model)
        return self._serialize_session(session_model)

    def get_summary(self, session_id: str) -> dict | None:
        session_model = get_session(self.db, session_id)
        return self._serialize_session(session_model) if session_model else None

    def get_history(self, session_id: str, *, limit: int = 100) -> list[dict] | None:
        session_model = get_session(self.db, session_id)
        if not session_model:
            return None
        return [
            {
                "message_id": item.message_id,
                "role": item.role,
                "content": item.content,
                "language": item.language or "auto",
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in list_session_messages(self.db, session_id, limit=limit)
        ]

    def get_tasks(self, session_id: str, *, limit: int = 30) -> list[UnifiedTaskResponse] | None:
        session_model = get_session(self.db, session_id)
        if not session_model:
            return None
        return [
            response
            for response in (
                self.task_service._to_response(task)
                for task in list_session_tasks(self.db, session_id, limit=limit)
            )
            if response is not None
        ]

    def clear(self, session_id: str) -> dict | None:
        session_model = clear_session_state(self.db, session_id)
        if not session_model:
            return None
        return self.get_summary(session_id)

    def _serialize_session(self, session_model) -> dict:
        if not session_model:
            return {}
        messages = sorted(
            list(session_model.messages),
            key=lambda item: (
                item.created_at.isoformat() if item.created_at else "",
                item.message_id,
            ),
        )
        tasks = sorted(
            list(session_model.tasks),
            key=lambda item: item.created_at.isoformat() if item.created_at else "",
            reverse=True,
        )
        latest_task = tasks[0] if tasks else None
        return {
            "session_id": session_model.session_id,
            "project_name": session_model.project_name,
            "preferred_output_language": session_model.preferred_output_language or DEFAULT_OUTPUT_LANGUAGE,
            "current_profile_id": session_model.current_profile_id,
            "message_count": len(messages),
            "task_count": len(tasks),
            "latest_message_at": messages[-1].created_at.isoformat() if messages else None,
            "latest_task_id": latest_task.task_id if latest_task else None,
            "latest_run_id": latest_task.run_id if latest_task else None,
            "created_at": session_model.created_at.isoformat() if session_model.created_at else None,
            "updated_at": session_model.updated_at.isoformat() if session_model.updated_at else None,
            "metadata": session_model.metadata_json or {},
        }
