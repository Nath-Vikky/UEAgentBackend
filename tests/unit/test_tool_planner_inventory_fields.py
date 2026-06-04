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
                    "selected_actor_references": ["BP_Hero_1"],
                    "current_material_instance_path": "/Game/Materials/MI_Player",
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
    assert calls[0]["input"]["selected_actor_references"] == ["BP_Hero_1"]
    assert calls[0]["input"]["current_material_instance_path"] == "/Game/Materials/MI_Player"
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


def test_project_inventory_context_snapshot_resolves_current_blueprint_graph_focus() -> None:
    storage_dir = Path("storage/test-tmp") / f"inventory-blueprint-focus-{uuid.uuid4().hex}"
    try:
        service = ProjectInventoryService(Settings(storage_dir=str(storage_dir)))
        service.save_snapshot(
            ProjectInventorySnapshotRequest(
                project_id="FocusProject",
                project_name="FocusProject",
                assets=[
                    {
                        "asset_path": "/Game/Blueprints/BP_FocusedActor",
                        "asset_name": "BP_FocusedActor",
                        "asset_type": "Blueprint",
                        "blueprint": {
                            "parent_class": "AActor",
                            "graphs": ["EventGraph"],
                            "graph_summaries": [
                                {
                                    "graph_name": "EventGraph",
                                    "graph_type": "event",
                                    "node_count": 2,
                                    "pin_count": 4,
                                    "link_count": 1,
                                    "nodes": [
                                        {
                                            "node_id": "event-begin-play",
                                            "node_name": "K2Node_Event_0",
                                            "node_class": "K2Node_Event",
                                            "title": "Event BeginPlay",
                                        },
                                        {
                                            "node_id": "print-string",
                                            "node_name": "K2Node_CallFunction_0",
                                            "node_class": "K2Node_CallFunction",
                                            "title": "Print String",
                                            "pins": [
                                                {
                                                    "pin_id": "exec-in",
                                                    "pin_name": "execute",
                                                    "direction": "input",
                                                    "category": "exec",
                                                }
                                            ],
                                        },
                                    ],
                                }
                            ],
                        },
                    }
                ],
            )
        )

        by_object_path = service.get_asset("/Game/Blueprints/BP_FocusedActor.BP_FocusedActor", "FocusProject")
        by_asset_name = service.get_asset("BP_FocusedActor", "FocusProject")
        context = service.context_snapshot(
            project_id="FocusProject",
            current_blueprint_path="/Game/Blueprints/BP_FocusedActor.BP_FocusedActor",
            current_graph_name="EventGraph",
            current_node_id="print-string",
        )

        assert by_object_path is not None
        assert by_asset_name is not None
        assert context["current_blueprint"]["asset_name"] == "BP_FocusedActor"
        assert context["current_blueprint_graph"]["graph_name"] == "EventGraph"
        assert context["current_blueprint_graph"]["nodes"][0]["title"] == "Event BeginPlay"
        assert context["current_blueprint_node"]["title"] == "Print String"
        assert context["current_blueprint_node"]["pins"][0]["pin_name"] == "execute"
    finally:
        shutil.rmtree(storage_dir, ignore_errors=True)


def test_project_inventory_context_snapshot_resolves_actor_and_material_focus() -> None:
    storage_dir = Path("storage/test-tmp") / f"inventory-actor-material-focus-{uuid.uuid4().hex}"
    try:
        service = ProjectInventoryService(Settings(storage_dir=str(storage_dir)))
        service.save_snapshot(
            ProjectInventorySnapshotRequest(
                project_id="FocusProject",
                project_name="FocusProject",
                level_actors=[
                    {
                        "actor_label": "BP_EnemySpawner_1",
                        "actor_name": "BP_EnemySpawner_C_1",
                        "actor_class": "BP_EnemySpawner_C",
                        "level_name": "L_Test",
                        "blueprint_path": "/Game/Blueprints/BP_EnemySpawner",
                        "transform": {"location": {"x": 100, "y": 200, "z": 0}},
                        "components": ["SceneRoot", "Billboard"],
                    }
                ],
                material_instances=[
                    {
                        "material_instance_path": "/Game/Materials/MI_Player.MI_Player",
                        "material_instance_name": "MI_Player",
                        "parent_material": "/Game/Materials/M_Player",
                        "scalar_parameters": [{"name": "Roughness", "value": 0.4}],
                        "vector_parameters": [{"name": "Tint", "value": [1, 0, 0, 1]}],
                    }
                ],
            )
        )

        context = service.context_snapshot(
            project_id="FocusProject",
            selected_actor_references=["BP_EnemySpawner_1"],
            current_actor_reference="BP_EnemySpawner_1",
            selected_material_instance_paths=["MI_Player"],
            current_material_instance_path="/Game/Materials/MI_Player",
        )

        assert context["selected_level_actors"][0]["actor_label"] == "BP_EnemySpawner_1"
        assert context["current_level_actor"]["actor_class"] == "BP_EnemySpawner_C"
        assert context["current_level_actor"]["component_count"] == 2
        assert context["selected_material_instances"][0]["material_instance_name"] == "MI_Player"
        assert context["current_material_instance"]["material_instance_path"] == "/Game/Materials/MI_Player.MI_Player"
        assert context["current_material_instance"]["scalar_parameter_count"] == 1
        assert context["current_material_instance"]["vector_parameter_count"] == 1
    finally:
        shutil.rmtree(storage_dir, ignore_errors=True)


def test_project_inventory_query_can_use_current_actor_and_material_focus() -> None:
    storage_dir = Path("storage/test-tmp") / f"inventory-focus-query-{uuid.uuid4().hex}"
    try:
        service = ProjectInventoryService(Settings(storage_dir=str(storage_dir)))
        service.save_snapshot(
            ProjectInventorySnapshotRequest(
                project_id="FocusQueryProject",
                project_name="FocusQueryProject",
                level_actors=[
                    {
                        "actor_label": "BP_EnemySpawner_1",
                        "actor_class": "BP_EnemySpawner_C",
                        "level_name": "L_Test",
                        "components": ["SceneRoot", "Billboard"],
                    }
                ],
                material_instances=[
                    {
                        "material_instance_path": "/Game/Materials/MI_Player.MI_Player",
                        "material_instance_name": "MI_Player",
                        "parent_material": "/Game/Materials/M_Player",
                        "scalar_parameters": [{"name": "Roughness", "value": 0.4}],
                    }
                ],
            )
        )

        actor_result = service.query(
            query="这个对象有哪些组件？",
            project_id="FocusQueryProject",
            fields=["components", "actor_class"],
            selected_actor_references=["BP_EnemySpawner_1"],
            current_actor_reference="BP_EnemySpawner_1",
            limit=5,
        )
        material_result = service.query(
            query="这个材质的 Roughness 是多少？",
            project_id="FocusQueryProject",
            fields=["scalar_parameters", "parent_material"],
            selected_material_instance_paths=["/Game/Materials/MI_Player"],
            current_material_instance_path="/Game/Materials/MI_Player",
            limit=5,
        )

        assert actor_result["items"][0]["kind"] == "level_actor"
        assert actor_result["items"][0]["actor_label"] == "BP_EnemySpawner_1"
        assert actor_result["items"][0]["field_view"]["actor_class"] == "BP_EnemySpawner_C"
        assert actor_result["items"][0]["field_view"]["components"] == ["SceneRoot", "Billboard"]
        assert actor_result["summary"]["level_actor_match_count"] == 1
        assert material_result["items"][0]["kind"] == "material_instance"
        assert material_result["items"][0]["material_instance_name"] == "MI_Player"
        assert material_result["items"][0]["field_view"]["scalar_parameters"][0]["name"] == "Roughness"
        assert material_result["items"][0]["field_view"]["scalar_parameters"][0]["value"] == 0.4
        assert material_result["summary"]["material_instance_match_count"] == 1
    finally:
        shutil.rmtree(storage_dir, ignore_errors=True)
