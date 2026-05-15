from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db
from app.api.errors import APIError
from app.core.settings import Settings
from app.schemas.requests import WebMemoryFeedbackRequest, WebMemorySearchRequest
from app.schemas.responses import (
    WebMemoryFeedbackResponse,
    WebMemorySearchResponse,
    WebMemoryStatusResponse,
)
from app.services.web_memory_service import WebMemoryService

router = APIRouter(prefix="/web-memory", tags=["web-memory"])


@router.get("/status", response_model=WebMemoryStatusResponse)
def web_memory_status(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> WebMemoryStatusResponse:
    return WebMemoryStatusResponse(success=True, summary=WebMemoryService(db, settings).status())


@router.post("/search", response_model=WebMemorySearchResponse)
def web_memory_search(
    request: WebMemorySearchRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> WebMemorySearchResponse:
    result = WebMemoryService(db, settings).recall(
        query=request.query,
        domain_hints=request.domain_hints,
        limit=request.limit,
    )
    return WebMemorySearchResponse(success=True, result=result)


@router.post("/entries/{entry_id}/feedback", response_model=WebMemoryFeedbackResponse)
def web_memory_feedback(
    entry_id: str,
    request: WebMemoryFeedbackRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> WebMemoryFeedbackResponse:
    result = WebMemoryService(db, settings).record_feedback(
        entry_id=entry_id,
        rating=request.rating,
        task_id=request.task_id,
        comment=request.comment,
        metadata=request.metadata,
    )
    if not result:
        raise APIError(404, "web_memory_entry_not_found", f"Web memory entry `{entry_id}` was not found.")
    return WebMemoryFeedbackResponse(success=True, item=result)


@router.post("/prune", response_model=WebMemoryStatusResponse)
def web_memory_prune(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> WebMemoryStatusResponse:
    return WebMemoryStatusResponse(success=True, summary=WebMemoryService(db, settings).prune())
