from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from app.agent.tool_planner import (
    build_project_qa_result_contracts,
    build_project_qa_tool_calls,
    build_react_lite_trace,
    sanitize_react_planner_payload,
    tool_call_input,
    tool_call_sequence,
)
from app.core.settings import Settings
from app.schemas.requests import ProjectInventorySnapshotRequest
from app.services.project_inventory_service import ProjectInventoryService


def test_tool_planner_sanitizes_inventory_field_inputs() -> None:
    payload = {
        "tool_calls": [
            {
                "tool_id": "query_project_inventory",
                "input": {
                    "query": "BP_Hero variables",
                    "asset_path": "/Game/Characters/BP_Hero",
                    "fields": ["variables", "components"],
                    "limit": 999,
                    "dangerous": "ignored",
                },
            },
            {"tool_id": "editor_rename_asset", "input": {"asset_path": "/Game/A"}},
        ],
        "confidence": 1.5,
    }

    sanitized = sanitize_react_planner_payload(
        payload,
        allowed_tool_ids={"query_project_inventory", "retrieve_project_knowledge"},
    )
    calls = build_project_qa_tool_calls(
        query="当前项目 BP_Hero 有哪些变量？",
        use_inventory=True,
        use_knowledge=False,
        use_project_file=False,
        rag_top_k=4,
        planner_inputs=sanitized["tool_inputs_by_id"],
    )

    assert sanitized["requested_tool_ids"] == ["query_project_inventory"]
    assert sanitized["confidence"] == 1.0
    assert calls[0]["input"]["limit"] == 200
    assert calls[0]["input"]["asset_path"] == "/Game/Characters/BP_Hero"
    assert calls[0]["input"]["fields"] == ["variables", "components"]
    assert tool_call_sequence(calls) == ["query_project_inventory"]


def test_tool_planner_trace_includes_project_file_read() -> None:
    tool_plan = {
        "use_inventory": False,
        "use_knowledge": False,
        "use_project_file": True,
        "tool_calls": [
            {
                "tool_id": "read_project_file",
                "input": {
                    "project_root": "D:/Demo",
                    "file_path": "Source/Demo/Private/Hero.cpp",
                    "max_bytes": 12000,
                },
            }
        ],
        "planner_decision": {"status": "skipped"},
    }
    project_file_result = {
        "status": "completed",
        "reason": "",
        "file_path": "Source/Demo/Private/Hero.cpp",
        "resolved_path": "D:/Demo/Source/Demo/Private/Hero.cpp",
        "bytes_read": 2048,
        "truncated": False,
    }

    trace = build_react_lite_trace(
        query="Summarize the selected file",
        tool_plan=tool_plan,
        qa_result={"retrieved_docs": [], "sources": [], "confidence": 0.0},
        inventory_result={"items": [], "summary": {}},
        project_file_result=project_file_result,
        answer_generation_mode="project_file_fallback",
        rag_top_k=4,
    )

    assert trace["tool_call_sequence"] == ["read_project_file"]
    assert trace["iterations_used"] == 1
    assert tool_call_input(tool_plan, "read_project_file")["file_path"] == "Source/Demo/Private/Hero.cpp"
    assert any(step.get("tool_id") == "read_project_file" for step in trace["steps"])


def test_tool_planner_builds_result_contracts_for_selected_tools() -> None:
    contracts = build_project_qa_result_contracts(
        tool_plan={
            "use_knowledge": True,
            "use_inventory": True,
            "use_project_file": True,
        },
        qa_result={
            "answer": "summary",
            "confidence": 0.6,
            "sources": [],
            "citations": [],
            "retrieved_docs": [],
            "retrieval_trace": {},
            "filters_applied": {},
            "warnings": [],
        },
        inventory_result={"items": [], "summary": {}},
        project_file_result={
            "status": "skipped",
            "reason": "not_selected",
            "file_path": "Source/Demo.cpp",
        },
    )

    assert [item["tool_id"] for item in contracts] == [
        "retrieve_project_knowledge",
        "query_project_inventory",
        "read_project_file",
    ]
    assert all(item["ok"] for item in contracts)


def test_project_inventory_query_returns_requested_field_view() -> None:
    storage_dir = Path("storage/test-tmp") / f"inventory-fields-{uuid.uuid4().hex}"
    try:
        service = ProjectInventoryService(Settings(storage_dir=str(storage_dir)))
        service.save_snapshot(
            ProjectInventorySnapshotRequest(
                project_id="SmokeProject",
                project_name="SmokeProject",
                assets=[
                    {
                        "asset_path": "/Game/Characters/BP_Hero",
                        "asset_name": "BP_Hero",
                        "asset_type": "Blueprint",
                        "parent_class": "Character",
                        "variables": [{"name": "Health", "type": "float"}],
                        "components": [{"name": "Camera", "class": "CameraComponent"}],
                        "dependencies": ["/Game/Input/IA_Move"],
                    }
                ],
            )
        )

        result = service.query(
            query="BP_Hero 的变量和组件是什么",
            project_id="SmokeProject",
            asset_path="/Game/Characters/BP_Hero",
            fields=["variables", "components", "parent_class", "dependencies"],
            limit=5,
        )

        assert result["summary"]["requested_fields"] == [
            "variables",
            "components",
            "parent_class",
            "dependencies",
        ]
        assert result["items"][0]["field_view"]["parent_class"] == "Character"
        assert result["items"][0]["field_view"]["variables"][0]["name"] == "Health"
        assert result["items"][0]["field_view"]["components"][0]["name"] == "Camera"
    finally:
        shutil.rmtree(storage_dir, ignore_errors=True)
