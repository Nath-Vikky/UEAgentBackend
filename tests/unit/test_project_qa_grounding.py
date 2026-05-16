from __future__ import annotations

from app.agent.tool_planner import build_project_qa_deterministic_tool_plan
from app.services.task_service import TaskService


def _service() -> TaskService:
    return TaskService.__new__(TaskService)


def test_project_fact_queries_require_inventory_snapshot() -> None:
    service = _service()

    assert service._inventory_fact_query_requires_snapshot("What assets are in my current project?")
    assert service._inventory_fact_query_requires_snapshot("Is Nanite enabled on the selected StaticMesh?")
    assert service._inventory_fact_query_requires_snapshot("List the code files in this project.")


def test_generic_ue_knowledge_does_not_require_inventory_snapshot() -> None:
    service = _service()

    assert not service._inventory_fact_query_requires_snapshot("How does Actor BeginPlay work in Unreal?")
    assert not service._inventory_fact_query_requires_snapshot("What is the difference between TArray and TMap?")
    assert not service._inventory_fact_query_requires_snapshot("How should I bind Enhanced Input actions?")


def test_project_qa_tool_plan_prefers_inventory_for_project_asset_questions() -> None:
    routing = {"route": {"selected_tool_id": "query_project_inventory"}}

    plan = build_project_qa_deterministic_tool_plan(
        query="What Blueprint assets are in my current project?",
        routing=routing,
    )

    assert plan["selected_tool_id"] == "query_project_inventory"
    assert plan["use_inventory"] is True
    assert plan["use_knowledge"] is False
    assert plan["reason"] == "inventory_first"


def test_project_qa_tool_plan_combines_inventory_and_knowledge_for_how_questions() -> None:
    routing = {"route": {"selected_tool_id": "query_project_inventory"}}

    plan = build_project_qa_deterministic_tool_plan(
        query="Why is this Blueprint asset risky, and how should I fix it?",
        routing=routing,
    )

    assert plan["use_inventory"] is True
    assert plan["use_knowledge"] is True


def test_inventory_fallback_refuses_current_project_claims_without_snapshot() -> None:
    service = _service()

    answer = service._inventory_fallback_answer(
        inventory_result={
            "items": [],
            "summary": {"has_snapshot": False, "empty_reason": "no_project_inventory_snapshot"},
        },
        output_language="en-US",
    )

    assert "No Project Inventory snapshot is available yet" in answer
    assert "Submit a Project Inventory snapshot" in answer


def test_inventory_fallback_lists_grounded_blueprint_fields() -> None:
    service = _service()

    answer = service._inventory_fallback_answer(
        inventory_result={
            "items": [
                {
                    "kind": "asset",
                    "asset_name": "BP_PlayerCharacter",
                    "asset_type": "Blueprint",
                    "asset_path": "/Game/Characters/BP_PlayerCharacter.BP_PlayerCharacter",
                    "blueprint": {
                        "parent_class": "ACharacter",
                        "components": ["CameraBoom", "FollowCamera"],
                        "variables": ["Health", "MoveSpeed"],
                        "functions": ["SetupPlayerInputComponent"],
                    },
                }
            ],
            "summary": {"has_snapshot": True, "asset_match_count": 1},
        },
        output_language="en-US",
    )

    assert "I found 1 matching project inventory item" in answer
    assert "BP_PlayerCharacter" in answer
    assert "parent_class=ACharacter" in answer
    assert "components=CameraBoom, FollowCamera" in answer
    assert "variables=Health, MoveSpeed" in answer
