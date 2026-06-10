from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db
from app.api.errors import APIError
from app.core.settings import Settings
from app.schemas.requests import SessionCreateRequest, SessionMemoryForgetRequest, SessionUpdateRequest
from app.schemas.responses import (
    SessionHistoryResponse,
    SessionListResponse,
    SessionMemoryResponse,
    SessionResponse,
    SessionTasksResponse,
)
from app.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=SessionListResponse)
def list_sessions(
    project_name: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> SessionListResponse:
    result = SessionService(db, settings).list(
        project_name=project_name,
        include_archived=include_archived,
        limit=limit,
    )
    return SessionListResponse(success=True, items=result["items"], summary=result["summary"])


@router.post("", response_model=SessionResponse)
def create_session(
    request: SessionCreateRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> SessionResponse:
    item = SessionService(db, settings).create_or_restore(request)
    return SessionResponse(success=True, item=item)


@router.patch("/{session_id}", response_model=SessionResponse)
def update_session(
    session_id: str,
    request: SessionUpdateRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> SessionResponse:
    item = SessionService(db, settings).update(session_id, request)
    if not item:
        raise APIError(404, "session_not_found", f"Session `{session_id}` was not found.")
    return SessionResponse(success=True, item=item)


@router.get("/{session_id}", response_model=SessionResponse)
def get_session_summary(
    session_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> SessionResponse:
    item = SessionService(db, settings).get_summary(session_id)
    if not item:
        raise APIError(404, "session_not_found", f"Session `{session_id}` was not found.")
    return SessionResponse(success=True, item=item)


@router.get("/{session_id}/memory", response_model=SessionMemoryResponse)
def get_session_memory(
    session_id: str,
    query: str | None = Query(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> SessionMemoryResponse:
    memory = SessionService(db, settings).get_memory(session_id, query=query)
    if memory is None:
        raise APIError(404, "session_not_found", f"Session `{session_id}` was not found.")
    return SessionMemoryResponse(success=True, session_id=session_id, memory=memory)


@router.post("/{session_id}/memory/forget", response_model=SessionMemoryResponse)
def forget_session_memory(
    session_id: str,
    request: SessionMemoryForgetRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> SessionMemoryResponse:
    result = SessionService(db, settings).forget_memory(session_id, request)
    if result is None:
        raise APIError(404, "session_not_found", f"Session `{session_id}` was not found.")
    return SessionMemoryResponse(success=True, session_id=session_id, memory=result)


@router.get("/{session_id}/history", response_model=SessionHistoryResponse)
def get_session_history(
    session_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> SessionHistoryResponse:
    items = SessionService(db, settings).get_history(session_id, limit=limit)
    if items is None:
        raise APIError(404, "session_not_found", f"Session `{session_id}` was not found.")
    return SessionHistoryResponse(success=True, session_id=session_id, items=items)


@router.get("/{session_id}/tasks", response_model=SessionTasksResponse)
def get_session_tasks(
    session_id: str,
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> SessionTasksResponse:
    items = SessionService(db, settings).get_tasks(session_id, limit=limit)
    if items is None:
        raise APIError(404, "session_not_found", f"Session `{session_id}` was not found.")
    return SessionTasksResponse(success=True, session_id=session_id, items=items)


@router.post("/{session_id}/archive", response_model=SessionResponse)
def archive_session(
    session_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> SessionResponse:
    item = SessionService(db, settings).archive(session_id, archived=True)
    if not item:
        raise APIError(404, "session_not_found", f"Session `{session_id}` was not found.")
    return SessionResponse(success=True, item=item)


@router.post("/{session_id}/clear", response_model=SessionResponse)
def clear_session(
    session_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> SessionResponse:
    item = SessionService(db, settings).clear(session_id)
    if not item:
        raise APIError(404, "session_not_found", f"Session `{session_id}` was not found.")
    return SessionResponse(success=True, item=item)
