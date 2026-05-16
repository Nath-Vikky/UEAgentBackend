from __future__ import annotations

from typing import Any

from app.schemas.requests import UnifiedTaskRequest
from app.services.llm_service import ChatRuntimeConfig
from app.services.task_handlers import RouteExecutionDispatcher, TaskExecutionContext


def _request(task_type: str = "agent_chat") -> UnifiedTaskRequest:
    return UnifiedTaskRequest(
        task_type=task_type,
        session={
            "session_id": "dispatcher_test_session",
            "messages": [{"role": "user", "content": "hello", "language": "auto"}],
        },
        context={"active_panel": "AgentChat"},
        payload={"user_query": "hello"},
        ui_state={"active_view": "user", "selected_panel": "AgentChat"},
        runtime_options={"profile_id": "default", "stream": False, "debug": True},
    )


def _context(
    *,
    route_type: str = "direct_answer",
    actual_task_type: str = "agent_chat",
) -> TaskExecutionContext:
    return TaskExecutionContext(
        request=_request(actual_task_type if actual_task_type != "project_qa" else "agent_chat"),
        routing={
            "intent": {"route_type": route_type},
            "locale": {"final_output_language": "en-US"},
            "route": {},
        },
        task_id="task_test",
        run_id="run_test",
        trace_id="trace_test",
        actual_task_type=actual_task_type,
        output_language="en-US",
        chat_config=ChatRuntimeConfig(
            profile_id="default",
            profile_name="Default",
            model="offline",
            temperature=0.0,
            max_tokens=128,
            timeout_ms=1000,
        ),
        context_bundle={},
    )


class _FakeHost:
    def __init__(self, editor_operation_request: Any | None = None) -> None:
        self.editor_operation_request = editor_operation_request

    def _detect_editor_operation_request(self, request: UnifiedTaskRequest) -> Any | None:
        return self.editor_operation_request


def test_route_dispatcher_selects_project_qa_by_route_type() -> None:
    dispatcher = RouteExecutionDispatcher()

    handler = dispatcher.select_handler(_FakeHost(), _context(route_type="project_qa"))

    assert handler.handler_id == "project_qa"


def test_route_dispatcher_selects_direct_answer_by_route_type() -> None:
    dispatcher = RouteExecutionDispatcher()

    handler = dispatcher.select_handler(_FakeHost(), _context(route_type="direct_answer"))

    assert handler.handler_id == "direct_answer"


def test_route_dispatcher_selects_task_type_handler_after_route_handlers() -> None:
    dispatcher = RouteExecutionDispatcher()

    handler = dispatcher.select_handler(
        _FakeHost(),
        _context(route_type="workflow", actual_task_type="code_generate"),
    )

    assert handler.handler_id == "code_generate"


def test_route_dispatcher_editor_operation_overrides_route_type() -> None:
    dispatcher = RouteExecutionDispatcher()

    handler = dispatcher.select_handler(
        _FakeHost(editor_operation_request={"operation_type": "rename_selected_asset"}),
        _context(route_type="project_qa", actual_task_type="project_qa"),
    )

    assert handler.handler_id == "editor_operation_proposal"


def test_route_dispatcher_annotates_debug_view_with_handler_id() -> None:
    result = {"debug_view": {}}

    RouteExecutionDispatcher._annotate_handler(result, "code_review")

    assert result["debug_view"]["task_handler"] == {
        "handler_id": "code_review",
        "strategy": "task_handler_adapter_v1",
    }
