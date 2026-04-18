from __future__ import annotations

from app.agent.router import classify_request
from app.schemas.requests import UnifiedTaskRequest


def _request(
    *,
    task_type: str = "agent_chat",
    content: str,
    context: dict | None = None,
    payload: dict | None = None,
) -> UnifiedTaskRequest:
    return UnifiedTaskRequest(
        task_type=task_type,
        session={
            "session_id": "router_test_session",
            "messages": [{"role": "user", "content": content, "language": "auto"}],
        },
        context=context or {"active_panel": "AgentChat"},
        payload=payload or {"user_query": content},
        ui_state={"active_view": "user", "selected_panel": "AgentChat"},
        runtime_options={
            "profile_id": "default",
            "stream": False,
            "debug": True,
            "preferred_output_language": "auto",
            "return_debug_projection": True,
        },
    )


def test_agent_chat_with_context_stays_direct_answer_when_question_is_generic() -> None:
    request = _request(
        content="Explain dependency injection in simple terms.",
        context={
            "project_name": "DemoProject",
            "active_panel": "AgentChat",
            "current_file": "Source/Demo/Subsystem.cpp",
            "current_module": "Demo",
        },
    )

    routing = classify_request(request)

    assert routing["intent"]["route_type"] == "direct_answer"
    assert routing["route"]["project_signal_strength"] == "weak"
    assert routing["route"]["decision_source"] == "heuristic_weak_project_signal"


def test_agent_chat_with_explicit_file_reference_routes_to_project_qa() -> None:
    request = _request(
        content="Explain how this file initializes the subsystem.",
        context={
            "project_name": "DemoProject",
            "active_panel": "AgentChat",
            "current_file": "Source/Demo/Subsystem.cpp",
            "current_module": "Demo",
        },
    )

    routing = classify_request(request)

    assert routing["intent"]["route_type"] == "project_qa"
    assert routing["route"]["project_signal_strength"] == "strong"
    assert routing["route"]["decision_source"] == "heuristic_strong_project_signal"


def test_explicit_project_qa_task_type_forces_retrieval_route() -> None:
    request = _request(
        task_type="project_qa",
        content="Summarize the backend runtime profile design.",
        context={"active_panel": "AgentChat"},
        payload={"user_query": "Summarize the backend runtime profile design."},
    )

    routing = classify_request(request)

    assert routing["intent"]["route_type"] == "project_qa"
    assert routing["route"]["decision_source"] == "explicit_task_type"
