from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from app.schemas.requests import UnifiedTaskRequest
from app.services.llm_service import ChatRuntimeConfig


StreamEventSink = Callable[[dict[str, Any]], None]


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


class TaskHandler(Protocol):
    handler_id: str

    def execute(self, host: Any, context: TaskExecutionContext) -> dict[str, Any]:
        """Execute the task against the current TaskService host."""
