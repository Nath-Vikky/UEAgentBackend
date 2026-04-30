from __future__ import annotations

from app.agent.router import classify_request
from app.schemas.requests import UnifiedTaskRequest


def _request(
    *,
    task_type: str = "agent_chat",
    content: str,
    context: dict | None = None,
    payload: dict | None = None,
    preferred_output_language: str = "auto",
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
            "preferred_output_language": preferred_output_language,
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


def test_agent_chat_with_ue_knowledge_question_routes_to_knowledge_retrieval() -> None:
    request = _request(
        content="GAS技能系统是什么",
        context={
            "project_name": "DemoProject",
            "active_panel": "AgentChat",
        },
    )

    routing = classify_request(request)

    assert routing["intent"]["route_type"] == "project_qa"
    assert routing["route"]["selected_tool_id"] == "retrieve_project_knowledge"
    assert routing["route"]["decision_source"] == "heuristic_ue_knowledge_signal"
    assert routing["route"]["ue_knowledge_query"] is True


def test_agent_chat_with_ue_threading_keyword_routes_to_knowledge_retrieval() -> None:
    request = _request(
        content="UE多线程怎么做",
        context={
            "project_name": "DemoProject",
            "active_panel": "AgentChat",
        },
    )

    routing = classify_request(request)

    assert routing["intent"]["route_type"] == "project_qa"
    assert routing["route"]["selected_tool_id"] == "retrieve_project_knowledge"
    assert routing["route"]["decision_source"] == "heuristic_ue_knowledge_signal"


def test_agent_chat_with_current_project_asset_list_routes_to_inventory() -> None:
    request = _request(
        content="当前项目有哪些蓝图资产，你列一下",
        context={
            "project_name": "DemoProject",
            "active_panel": "AgentChat",
        },
    )

    routing = classify_request(request)

    assert routing["intent"]["route_type"] == "project_qa"
    assert routing["route"]["selected_tool_id"] == "query_project_inventory"
    assert routing["route"]["decision_source"] == "heuristic_project_inventory_signal"
    assert routing["route"]["project_inventory_query"] is True


def test_auto_language_defaults_to_chinese_even_for_english_question() -> None:
    request = _request(content="Explain dependency injection in simple terms.")

    routing = classify_request(request)

    assert routing["locale"]["detected_input_language"] == "en-US"
    assert routing["locale"]["preferred_output_language"] == "zh-CN"
    assert routing["locale"]["final_output_language"] == "zh-CN"
    assert routing["locale"]["language_source"] == "default"


def test_runtime_language_preference_overrides_default() -> None:
    request = _request(
        content="Explain dependency injection in simple terms.",
        preferred_output_language="en-US",
    )

    routing = classify_request(request)

    assert routing["locale"]["final_output_language"] == "en-US"
    assert routing["locale"]["language_source"] == "explicit_override"


def test_session_language_preference_is_used_when_runtime_is_auto() -> None:
    request = _request(content="Explain dependency injection in simple terms.")

    routing = classify_request(request, session_preference="en-US")

    assert routing["locale"]["final_output_language"] == "en-US"
    assert routing["locale"]["language_source"] == "session_preference"


def test_editor_locale_is_used_before_default() -> None:
    request = _request(
        content="Explain dependency injection in simple terms.",
        context={"active_panel": "AgentChat", "editor_state": {"locale": "en-US"}},
    )

    routing = classify_request(request)

    assert routing["locale"]["final_output_language"] == "en-US"
    assert routing["locale"]["language_source"] == "editor_locale"


def test_message_language_override_is_single_turn_source() -> None:
    request = _request(
        content="Explain dependency injection in simple terms, reply in English.",
        preferred_output_language="zh-CN",
    )

    routing = classify_request(request, session_preference="zh-CN")

    assert routing["locale"]["final_output_language"] == "en-US"
    assert routing["locale"]["language_source"] == "message_override"
