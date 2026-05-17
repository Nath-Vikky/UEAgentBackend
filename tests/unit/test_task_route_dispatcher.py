from __future__ import annotations

from app.schemas.requests import UnifiedTaskRequest
from app.services.llm_service import ChatRuntimeConfig
from app.services.task_handlers import RouteExecutionDispatcher, TaskExecutionContext, TaskHandlerDependencies


def _request(task_type: str = "agent_chat", payload: dict | None = None) -> UnifiedTaskRequest:
    return UnifiedTaskRequest(
        task_type=task_type,
        session={
            "session_id": "dispatcher_test_session",
            "messages": [{"role": "user", "content": "hello", "language": "auto"}],
        },
        context={"active_panel": "AgentChat"},
        payload=payload or {"user_query": "hello"},
        ui_state={"active_view": "user", "selected_panel": "AgentChat"},
        runtime_options={"profile_id": "default", "stream": False, "debug": True},
    )


def _context(
    *,
    route_type: str = "direct_answer",
    actual_task_type: str = "agent_chat",
    request: UnifiedTaskRequest | None = None,
) -> TaskExecutionContext:
    return TaskExecutionContext(
        request=request or _request(actual_task_type if actual_task_type != "project_qa" else "agent_chat"),
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
    pass


def test_task_execution_context_accepts_explicit_handler_dependencies() -> None:
    dependencies = TaskHandlerDependencies(
        db=object(),
        settings=object(),
        kb_service=object(),
        llm_service=object(),
        inventory_service=object(),
        base_debug_builder=lambda **_: {},
        stream_event_emitter=lambda *_, **__: None,
    )

    context = _context()
    context.dependencies = dependencies

    assert context.dependencies is dependencies


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
        _FakeHost(),
        _context(
            route_type="project_qa",
            actual_task_type="project_qa",
            request=_request(
                payload={
                    "operation_type": "rename_selected_asset",
                    "operation_payload": {
                        "asset_path": "/Game/Maps/NewMap",
                        "new_name": "L_TestMap",
                    },
                }
            ),
        ),
    )

    assert handler.handler_id == "editor_operation_proposal"


def test_route_dispatcher_annotates_debug_view_with_handler_id() -> None:
    result = {"debug_view": {}}

    RouteExecutionDispatcher._annotate_handler(result, "code_review")

    assert result["debug_view"]["task_handler"] == {
        "handler_id": "code_review",
        "strategy": "task_handler_adapter_v1",
    }
