from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db
from app.api.errors import APIError
from app.core.settings import Settings
from app.schemas.requests import SessionCreateRequest
from app.schemas.responses import SessionHistoryResponse, SessionResponse, SessionTasksResponse
from app.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse)
def create_session(
    request: SessionCreateRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> SessionResponse:
    item = SessionService(db, settings).create_or_restore(request)
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
