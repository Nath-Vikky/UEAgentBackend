from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from app.schemas.requests import UnifiedTaskRequest
from app.services.llm_service import ChatRuntimeConfig


StreamEventSink = Callable[[dict[str, Any]], None]
BaseDebugBuilder = Callable[..., dict[str, Any]]
StreamEventEmitterFn = Callable[..., None]


@dataclass(slots=True)
class TaskHandlerDependencies:
    """Explicit service dependencies available to route handlers.

    Older handlers may still use the TaskService host directly. New handlers should prefer
    this dependency object so they are easier to unit test and migrate to alternate hosts.
    """

    db: Any
    settings: Any
    kb_service: Any
    llm_service: Any
    inventory_service: Any
    base_debug_builder: BaseDebugBuilder
    stream_event_emitter: StreamEventEmitterFn


@dataclass(slots=True)
class TaskExecutionContext:
    request: UnifiedTaskRequest
    routing: dict[str, Any]
    task_id: str
    run_id: str
    trace_id: str
    actual_task_type: str
    output_language: str
    chat_config: ChatRuntimeConfig
    context_bundle: dict[str, Any]
    stream_sink: StreamEventSink | None = None
    dependencies: TaskHandlerDependencies | None = None


class TaskHandler(Protocol):
    handler_id: str

    def execute(self, host: Any, context: TaskExecutionContext) -> dict[str, Any]:
        """Execute the task against the current TaskService host."""
