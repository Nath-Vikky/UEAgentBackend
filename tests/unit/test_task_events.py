from __future__ import annotations

from app.agent.response_composer import compose_unified_response
from app.services.task_events import (
    StreamEventEmitter,
    build_persisted_event_payloads,
    build_run_cancelled_event_payload,
)


def test_stream_event_emitter_builds_ordered_sse_envelopes() -> None:
    events: list[dict] = []
    emitter = StreamEventEmitter()

    emitter.emit(events.append, "run_started", {"task_type": "agent_chat"}, run_id="run_1", task_id="task_1")
    emitter.emit(events.append, "final", {"status": "completed"}, run_id="run_1", task_id="task_1")

    assert [item["event"] for item in events] == ["run_started", "final"]
    assert [item["seq"] for item in events] == [1, 2]
    assert events[0]["run_id"] == "run_1"
    assert events[0]["task_id"] == "task_1"
    assert "timestamp" in events[0]


def test_build_persisted_event_payloads_preserves_existing_sequence_contract() -> None:
    response = compose_unified_response(
        task={
            "task_id": "task_1",
            "run_id": "run_1",
            "task_type": "project_qa",
            "status": "completed",
            "trace_id": "trace_1",
            "output_complete": True,
            "finish_reason": "completed",
        },
        intent={
            "intent_type": "project_qa",
            "route_type": "project_qa",
            "knowledge_relevance": "strong",
            "requires_rag": True,
            "requires_tool": True,
            "reason": "test",
        },
        locale={
            "detected_input_language": "en-US",
            "preferred_output_language": "en-US",
            "final_output_language": "en-US",
            "language_source": "latest_user_message",
        },
        user_view_payload={"title": "Answer", "text": "Hello"},
        debug_payload={"trace_id": "trace_1", "raw_request": {}},
        data={},
        usage={},
        trace_summary={},
        retrieval_trace={"mode": "lexical", "retrieved_docs": [{"title": "Doc"}]},
        planner_diagnostics={"selected_tool_id": "retrieve_project_knowledge"},
        step_results=[
            {
                "step_id": "retrieve_knowledge",
                "title": "Knowledge Retrieval",
                "status": "completed",
                "summary": "done",
                "details": {},
            }
        ],
        action_proposals=[],
        errors=[],
        assistant_message="Hello",
    )

    payloads = build_persisted_event_payloads(task_id="task_1", run_id="run_1", response=response)

    assert [item["seq"] for item in payloads] == list(range(1, len(payloads) + 1))
    assert [item["event"] for item in payloads] == [
        "run_started",
        "route_selected",
        "retrieval_started",
        "retrieval_completed",
        "step_started",
        "step_completed",
        "text_delta",
        "run_completed",
    ]
    assert payloads[-1]["payload"]["finish_reason"] == "completed"


def test_build_run_cancelled_event_payload() -> None:
    payload = build_run_cancelled_event_payload(
        run_id="run_1",
        task_id="task_1",
        finish_reason="user_cancelled",
        seq=7,
    )

    assert payload["event"] == "run_cancelled"
    assert payload["seq"] == 7
    assert payload["payload"] == {"status": "cancelled", "finish_reason": "user_cancelled"}
