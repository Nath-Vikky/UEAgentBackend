from __future__ import annotations

from sqlalchemy.orm import Session

from app.agent.memory_manager import (
    read_active_target_memory,
    read_conversation_focus_memory,
    recall_long_term_memory,
)
from app.core.settings import Settings
from app.db.repositories.sessions import (
    clear_session_state,
    get_or_create_session,
    get_session,
    list_session_messages,
    list_sessions,
    list_session_tasks,
)
from app.i18n.language import DEFAULT_OUTPUT_LANGUAGE
from app.schemas.requests import SessionCreateRequest, SessionMemoryForgetRequest, SessionUpdateRequest
from app.schemas.responses import UnifiedTaskResponse
from app.services.task_service import TaskService


class SessionService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings
        self.task_service = TaskService(db, settings)

    def list(
        self,
        *,
        project_name: str | None = None,
        include_archived: bool = False,
        limit: int = 50,
    ) -> dict:
        sessions = list_sessions(
            self.db,
            project_name=project_name,
            include_archived=include_archived,
            limit=limit,
        )
        items = [self._serialize_session(item) for item in sessions]
        return {
            "items": items,
            "summary": {
                "count": len(items),
                "project_name": project_name,
                "include_archived": include_archived,
                "limit": limit,
            },
        }

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

    def update(self, session_id: str, request: SessionUpdateRequest) -> dict | None:
        session_model = get_session(self.db, session_id)
        if not session_model:
            return None
        metadata = dict(session_model.metadata_json or {})
        if request.title is not None:
            title = request.title.strip()
            if title:
                metadata["title"] = title[:120]
            else:
                metadata.pop("title", None)
        if request.window_kind is not None:
            metadata["window_kind"] = request.window_kind.strip()[:64] or "agent_chat"
        if request.archived is not None:
            metadata["archived"] = bool(request.archived)
        if request.pinned is not None:
            metadata["pinned"] = bool(request.pinned)
        if request.memory_policy is not None:
            metadata["memory_policy"] = dict(request.memory_policy)
        metadata.update(request.metadata or {})
        session_model.metadata_json = metadata
        self.db.add(session_model)
        self.db.commit()
        self.db.refresh(session_model)
        return self._serialize_session(session_model)

    def archive(self, session_id: str, *, archived: bool = True) -> dict | None:
        session_model = get_session(self.db, session_id)
        if not session_model:
            return None
        metadata = dict(session_model.metadata_json or {})
        metadata["archived"] = archived
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

    def get_memory(self, session_id: str, *, query: str | None = None) -> dict | None:
        session_model = get_session(self.db, session_id)
        if not session_model:
            return None
        metadata = dict(session_model.metadata_json or {})
        query_text = query or self._latest_message_text(session_id) or ""
        return {
            "session": {
                "session_id": session_model.session_id,
                "project_name": session_model.project_name,
                "title": metadata.get("title"),
            },
            "scopes": {
                "turn": {
                    "status": "request_only",
                    "policy": "Built per request from frontend context and not persisted.",
                },
                "session": {
                    "status": "available",
                    "memory_summary": metadata.get("memory_summary") or {},
                    "active_target_memory": read_active_target_memory(self.db, session_id),
                    "conversation_focus_memory": read_conversation_focus_memory(self.db, session_id),
                },
                "project": recall_long_term_memory(
                    self.db,
                    project_name=session_model.project_name,
                    query=query_text,
                ),
            },
            "policy": {
                "session_memory_isolated_by_session_id": True,
                "project_memory_requires_matching_project_name": True,
                "fresh_active_context_priority": "fresh_frontend_context > active_target_memory > conversation_focus_memory > session_summary > project_memory",
            },
        }

    def forget_memory(self, session_id: str, request: SessionMemoryForgetRequest) -> dict | None:
        session_model = get_session(self.db, session_id)
        if not session_model:
            return None
        metadata = dict(session_model.metadata_json or {})
        scopes = set(request.scopes or [])
        memory_ids = {item for item in request.memory_ids if item}
        changed: list[str] = []

        if not scopes and memory_ids:
            scopes.update({"active_target", "conversation_focus"})

        if "summary" in scopes:
            metadata.pop("memory_summary", None)
            metadata.pop("session_summary", None)
            changed.append("summary")

        if "active_target" in scopes:
            if memory_ids:
                memory = dict(metadata.get("active_target_memory") or {})
                memory["items"] = [
                    item
                    for item in list(memory.get("items") or [])
                    if isinstance(item, dict)
                    if str(item.get("target_id") or item.get("memory_id") or "") not in memory_ids
                ]
                metadata["active_target_memory"] = memory
            else:
                metadata.pop("active_target_memory", None)
            changed.append("active_target")

        if "conversation_focus" in scopes:
            if memory_ids:
                memory = dict(metadata.get("conversation_focus_memory") or {})
                memory["items"] = [
                    item
                    for item in list(memory.get("items") or [])
                    if isinstance(item, dict)
                    if str(item.get("focus_id") or item.get("memory_id") or item.get("target_id") or "") not in memory_ids
                ]
                metadata["conversation_focus_memory"] = memory
            else:
                metadata.pop("conversation_focus_memory", None)
            changed.append("conversation_focus")

        session_model.metadata_json = metadata
        self.db.add(session_model)
        self.db.commit()
        self.db.refresh(session_model)
        return {
            "session_id": session_id,
            "forgotten_scopes": changed,
            "memory": self.get_memory(session_id) or {},
        }

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
        metadata = dict(session_model.metadata_json or {})
        return {
            "session_id": session_model.session_id,
            "title": metadata.get("title") or self._fallback_title(messages),
            "window_kind": metadata.get("window_kind") or "agent_chat",
            "archived": bool(metadata.get("archived")),
            "pinned": bool(metadata.get("pinned")),
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
            "memory_summary": metadata.get("memory_summary") or {},
            "memory_policy": metadata.get("memory_policy") or {},
            "metadata": metadata,
        }

    def _latest_message_text(self, session_id: str) -> str:
        messages = list_session_messages(self.db, session_id, limit=200)
        return messages[-1].content if messages else ""

    @staticmethod
    def _fallback_title(messages) -> str:
        for message in messages:
            if message.role == "user" and message.content.strip():
                text = message.content.strip().replace("\n", " ")
                return text[:60]
        return "New Chat"
