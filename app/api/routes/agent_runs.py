from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from queue import Empty, Queue

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db
from app.api.errors import APIError
from app.core.settings import Settings
from app.db.session import get_session_factory
from app.schemas.common import DebugView, UserView
from app.schemas.requests import UnifiedTaskRequest
from app.schemas.responses import UnifiedTaskResponse
from app.services.task_service import TaskService

router = APIRouter(prefix="/chat/runs", tags=["chat"])


def _sse_payload(events: list[dict]) -> Iterator[str]:
    for item in events:
        yield f"event: {item['event']}\n"
        yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"


def _sse_item(item: dict) -> str:
    event_name = str(item.get("event") or "message")
    return f"event: {event_name}\ndata: {json.dumps(item, ensure_ascii=False)}\n\n"


def _stream_chat_run_payload(
    request: UnifiedTaskRequest,
    settings: Settings,
) -> Iterator[str]:
    event_queue: Queue[dict | None] = Queue()

    def enqueue(item: dict) -> None:
        event_queue.put(item)

    def worker() -> None:
        try:
            session_factory = get_session_factory()
            with session_factory() as db:
                request.task_type = "agent_chat"
                request.runtime_options.stream = True
                TaskService(db, settings).create_task(request, stream_sink=enqueue)
        except Exception as exc:  # pragma: no cover - defensive streaming wrapper
            enqueue(
                {
                    "event": "error",
                    "seq": -1,
                    "run_id": None,
                    "task_id": None,
                    "payload": {
                        "reason": "stream_execution_failed",
                        "error": str(exc),
                    },
                }
            )
        finally:
            event_queue.put(None)

    yield _sse_item(
        {
            "event": "stream_opened",
            "seq": 0,
            "run_id": None,
            "task_id": None,
            "payload": {
                "streaming_mode": "token_sse_optional",
                "fallback_endpoint": "/api/v1/chat/runs",
            },
        }
    )
    thread = threading.Thread(target=worker, name="chat-run-sse-worker", daemon=True)
    thread.start()
    while True:
        try:
            item = event_queue.get(timeout=15.0)
        except Empty:
            yield _sse_item(
                {
                    "event": "heartbeat",
                    "seq": -1,
                    "run_id": None,
                    "task_id": None,
                    "payload": {"status": "running"},
                }
            )
            continue
        if item is None:
            break
        yield _sse_item(item)


@router.post("", response_model=UnifiedTaskResponse)
def create_chat_run(
    request: UnifiedTaskRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> UnifiedTaskResponse:
    request.task_type = "agent_chat"
    return TaskService(db, settings).create_task(request)


@router.post("/stream")
def create_chat_run_stream(
    request: UnifiedTaskRequest,
    settings: Settings = Depends(get_app_settings),
) -> StreamingResponse:
    return StreamingResponse(
        _stream_chat_run_payload(request, settings),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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
