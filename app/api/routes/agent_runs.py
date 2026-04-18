from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db
from app.api.errors import APIError
from app.core.settings import Settings
from app.schemas.common import DebugView, UserView
from app.schemas.requests import UnifiedTaskRequest
from app.schemas.responses import UnifiedTaskResponse
from app.services.task_service import TaskService

router = APIRouter(prefix="/chat/runs", tags=["chat"])


def _sse_payload(events: list[dict]) -> Iterator[str]:
    for item in events:
        yield f"event: {item['event']}\n"
        yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"


@router.post("", response_model=UnifiedTaskResponse)
def create_chat_run(
    request: UnifiedTaskRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> UnifiedTaskResponse:
    request.task_type = "agent_chat"
    return TaskService(db, settings).create_task(request)


@router.get("/{run_id}", response_model=UnifiedTaskResponse)
def get_chat_run(
    run_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> UnifiedTaskResponse:
    payload = TaskService(db, settings).get_run_response(run_id)
    if not payload:
        raise APIError(404, "run_not_found", f"Run `{run_id}` was not found.")
    return payload


@router.get("/{run_id}/user-view", response_model=UserView)
def get_chat_run_user_view(
    run_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> UserView:
    payload = TaskService(db, settings).get_run_response(run_id)
    if not payload:
        raise APIError(404, "run_not_found", f"Run `{run_id}` was not found.")
    return payload.user_view


@router.get("/{run_id}/debug-view", response_model=DebugView)
def get_chat_run_debug_view(
    run_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> DebugView:
    payload = TaskService(db, settings).get_run_response(run_id)
    if not payload:
        raise APIError(404, "run_not_found", f"Run `{run_id}` was not found.")
    return payload.debug_view


@router.get("/{run_id}/events/stream")
def stream_chat_run_events(
    run_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> StreamingResponse:
    events = TaskService(db, settings).get_run_events(run_id)
    if events is None:
        raise APIError(404, "run_not_found", f"Run `{run_id}` was not found.")
    return StreamingResponse(_sse_payload(events), media_type="text/event-stream")


@router.post("/{run_id}/cancel", response_model=UnifiedTaskResponse)
def cancel_chat_run(
    run_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> UnifiedTaskResponse:
    payload = TaskService(db, settings).cancel_run(run_id)
    if not payload:
        raise APIError(404, "run_not_found", f"Run `{run_id}` was not found.")
    return payload
