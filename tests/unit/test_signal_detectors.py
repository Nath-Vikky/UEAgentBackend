from __future__ import annotations

from app.agent.signal_detectors import evaluate_signal_detectors
from app.schemas.requests import UnifiedTaskRequest


def _request(content: str, task_type: str = "agent_chat") -> UnifiedTaskRequest:
    return UnifiedTaskRequest(
        task_type=task_type,
        session={
            "session_id": "signal_detector_test_session",
            "messages": [{"role": "user", "content": content, "language": "auto"}],
        },
        context={"active_panel": "AgentChat", "project_name": "DemoProject"},
        payload={"user_query": content},
        ui_state={"active_view": "user", "selected_panel": "AgentChat"},
        runtime_options={
            "profile_id": "default",
            "stream": False,
            "debug": True,
            "preferred_output_language": "auto",
            "return_debug_projection": True,
        },
    )


def test_signal_detectors_rank_inventory_query_from_legacy_signals() -> None:
    request = _request("当前项目有哪些蓝图资产，你列一下")

    result = evaluate_signal_detectors(
        "当前项目有哪些蓝图资产，你列一下",
        request,
        legacy_signals={"project_inventory_query": True},
    )

    assert result["mode"] == "compatibility_observer"
    assert result["errors"] == []
    assert result["top"]["detector"] == "inventory_query"
    assert result["top"]["selected_tool_id"] == "query_project_inventory"
    assert result["items"][0]["score"] >= result["items"][-1]["score"]


def test_signal_detectors_can_observe_ue_knowledge_question() -> None:
    request = _request("UE多线程怎么做")

    result = evaluate_signal_detectors(
        "UE多线程怎么做",
        request,
        legacy_signals={"ue_knowledge_query": True, "ue_knowledge_hint_count": 2},
        selected_tool_id="retrieve_project_knowledge",
    )

    detectors = [item["detector"] for item in result["items"]]
    assert "ue_knowledge" in detectors
    assert result["top"]["route_hint"] == "project_qa"


def test_signal_detectors_build_scoring_shadow_recommendation() -> None:
    request = _request("List current project Blueprint assets")

    result = evaluate_signal_detectors(
        "List current project Blueprint assets",
        request,
        legacy_signals={"project_inventory_query": True},
        mode="scoring_shadow",
    )

    assert result["mode"] == "scoring_shadow"
    assert result["recommendation"]["status"] == "eligible"
    assert result["recommendation"]["route_hint"] == "project_qa"
    assert result["recommendation"]["selected_tool_id"] == "query_project_inventory"
    assert result["recommendation"]["override_applied"] is False
