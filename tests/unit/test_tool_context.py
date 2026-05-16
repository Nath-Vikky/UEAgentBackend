from __future__ import annotations

import pytest

from app.schemas.requests import UnifiedTaskRequest
from app.tools.context import CompositeToolResult, ToolContext, ToolResult
from app.tools.registry import get_tool_spec


def _request() -> UnifiedTaskRequest:
    return UnifiedTaskRequest(
        task_type="project_qa",
        session={
            "session_id": "tool_context_test_session",
            "messages": [{"role": "user", "content": "当前项目有哪些蓝图资产？", "language": "auto"}],
        },
        context={"active_panel": "AgentChat", "project_name": "DemoProject"},
        payload={"user_query": "当前项目有哪些蓝图资产？"},
        ui_state={"active_view": "user", "selected_panel": "AgentChat"},
        runtime_options={
            "profile_id": "default",
            "stream": False,
            "debug": True,
            "preferred_output_language": "auto",
            "return_debug_projection": True,
        },
    )


def test_tool_context_can_be_built_from_request_and_spec() -> None:
    spec = get_tool_spec("query_project_inventory")
    assert spec is not None

    context = ToolContext.from_request(
        spec=spec,
        request=_request(),
        task_id="task_1",
        run_id="run_1",
        trace_id="trace_1",
    )

    summary = context.input_summary()
    assert context.tool_id == "query_project_inventory"
    assert context.timeout_ms == spec.timeout_ms
    assert summary["payload_keys"] == ["user_query"]
    assert "project_name" in summary["active_context_keys"]


def test_tool_result_exports_debug_entry() -> None:
    result = ToolResult.completed(
        tool_id="query_project_inventory",
        output={"items": [{"asset_name": "BP_Player"}]},
        summary="Matched 1 item.",
        latency_ms=12,
    )

    debug_entry = result.to_debug_entry()

    assert result.ok is True
    assert debug_entry["protocol_version"] == "tool_result_v1"
    assert debug_entry["tool_id"] == "query_project_inventory"
    assert debug_entry["output_summary"]["output_keys"] == ["items"]


def test_tool_result_rejects_unknown_status() -> None:
    with pytest.raises(ValueError):
        ToolResult(tool_id="query_project_inventory", status="unknown")


def test_composite_tool_result_preserves_individual_results() -> None:
    composite = CompositeToolResult(
        tool_id="project_qa_tools",
        results=[
            ToolResult.completed(tool_id="retrieve_project_knowledge", output={"retrieved_docs": []}),
            ToolResult.failed(
                tool_id="read_project_file",
                error_code="blocked",
                error_message="Path outside project root.",
            ),
        ],
    )

    payload = composite.model_dump()

    assert composite.ok is False
    assert payload["results"][1]["status"] == "failed"
