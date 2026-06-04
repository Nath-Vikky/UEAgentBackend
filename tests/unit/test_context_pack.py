from __future__ import annotations

from app.agent.context_pack import build_context_pack, context_pack_prompt_excerpt, select_memory_items


def test_select_memory_items_ranks_relevant_memory_without_llm() -> None:
    memory_context = {
        "items": [
            {
                "provider_id": "session_long_term_memory",
                "memory_id": "m1",
                "category": "naming",
                "text": "Blueprint assets should use BP_ prefix.",
                "score": 0.1,
            },
            {
                "provider_id": "web_memory",
                "entry_id": "w1",
                "title": "Enhanced Input",
                "text": "Enhanced Input uses Input Actions and Mapping Contexts.",
                "score": 0.8,
                "retrieval_source": "web_memory",
            },
        ]
    }

    selected = select_memory_items(memory_context, query="How do I use Enhanced Input Mapping Context?")

    assert selected[0]["source_id"] == "w1"
    assert selected[0]["provider_id"] == "web_memory"
    assert selected[0]["score"] > selected[1]["score"]


def test_build_context_pack_projects_bundle_into_stable_layers() -> None:
    bundle = {
        "version": "context_bundle_v1",
        "input_summary": {
            "actual_task_type": "project_qa",
            "route_type": "project_qa",
            "selected_tool_id": "project_qa",
            "latest_user_message": "Enhanced Input setup",
        },
        "language_context": {"final_output_language": "en-US"},
        "active_context": {
            "version": "active_context_v1",
            "project": {"project_name": "DemoProject", "active_panel": "AgentChat"},
            "asset": {"selected_assets": ["/Game/UI/WBP_Main"]},
            "blueprint": {
                "current_blueprint_path": "/Game/BP_Demo",
                "current_graph_name": "EventGraph",
                "has_blueprint_focus": True,
            },
            "code": {"current_file": "Source/Demo/DemoCharacter.cpp"},
            "log": {"has_log_text": False},
            "level_actor": {
                "selected_actor_references": ["BP_EnemySpawner_1"],
                "current_actor_reference": "BP_EnemySpawner_1",
                "selected_actor_count": 1,
                "current_actor_inventory": {
                    "actor_label": "BP_EnemySpawner_1",
                    "actor_class": "BP_EnemySpawner_C",
                    "level_name": "L_Test",
                    "blueprint_path": "/Game/Blueprints/BP_EnemySpawner.BP_EnemySpawner",
                    "components": [{"component_name": "SceneRoot", "component_class": "SceneComponent"}],
                },
            },
            "material": {
                "selected_material_instance_paths": ["/Game/Materials/MI_Player.MI_Player"],
                "current_material_instance_path": "/Game/Materials/MI_Player.MI_Player",
                "selected_material_instance_count": 1,
                "current_material_instance_inventory": {
                    "material_instance_path": "/Game/Materials/MI_Player.MI_Player",
                    "material_instance_name": "MI_Player",
                    "parent_material": "/Game/Materials/M_Player",
                    "scalar_parameters": [{"name": "Roughness", "value": 0.42}],
                },
            },
            "editor_focus": {"active_view": "user", "selected_panel": "AgentChat"},
            "kb": {"requires_rag": True},
            "editor_operation": {"status": "not_available"},
        },
        "editor_context": {"project_name": "DemoProject"},
        "project_inventory_context": {
            "status": "available",
            "has_snapshot": True,
            "snapshot_id": "snap_1",
            "project_id": "DemoProject",
            "summary": {
                "asset_count": 12,
                "code_file_count": 4,
                "level_actor_count": 3,
                "material_instance_count": 2,
            },
            "selected_assets": [{"asset_path": "/Game/UI/WBP_Main"}],
            "query_candidates": [{"path": "/Game/Input/IMC_Default"}],
            "query_summary": {"matched_count": 1},
        },
        "recent_messages": [{"role": "user", "content": "Enhanced Input setup", "source": "request"}],
        "session_summary": {"status": "not_available"},
        "memory": {
            "sources": [{"provider_id": "web_memory", "status": "completed", "item_count": 1}],
            "items": [
                {
                    "provider_id": "web_memory",
                    "entry_id": "w1",
                    "title": "Enhanced Input",
                    "text": "Enhanced Input uses Input Actions and Mapping Contexts.",
                    "score": 0.8,
                    "retrieval_source": "web_memory",
                }
            ],
        },
        "tool_context": [
            {
                "task_id": "task_1",
                "task_type": "code_review",
                "status": "completed",
                "summary": "Reviewed DemoCharacter.cpp.",
            }
        ],
        "recent_editor_operations": [
            {
                "operation_type": "add_blueprint_node_template",
                "tool_id": "editor.add_blueprint_node_template",
                "success": True,
                "execution_state": "completed",
                "target": {"blueprint_path": "/Game/BP_Demo"},
            }
        ],
        "budget": {"char_budget": 6000, "estimated_chars": 900, "within_budget": True},
    }

    pack = build_context_pack(bundle)

    assert pack["version"] == "context_pack_v1"
    assert pack["system_layer"]["tool_policy"].startswith("Read-only context")
    assert pack["project_layer"]["inventory"]["summary"]["asset_count"] == 12
    assert pack["active_layer"]["blueprint"]["current_graph_name"] == "EventGraph"
    assert pack["active_layer"]["level_actor"]["current_actor_inventory"]["actor_label"] == "BP_EnemySpawner_1"
    assert pack["active_layer"]["level_actor"]["current_actor_inventory"]["component_count"] == 1
    assert pack["active_layer"]["material"]["current_material_instance_inventory"]["material_instance_name"] == "MI_Player"
    assert pack["active_layer"]["material"]["current_material_instance_inventory"]["scalar_parameters"][0] == {
        "name": "Roughness",
        "value": 0.42,
    }
    assert pack["memory_layer"]["selected_items"][0]["source_id"] == "w1"
    assert pack["tool_layer"]["tool_observation_summary"][0]["task_type"] == "code_review"
    assert pack["debug_summary"]["has_inventory_snapshot"] is True
    assert pack["debug_summary"]["has_level_actor_focus"] is True
    assert pack["debug_summary"]["has_material_focus"] is True

    excerpt = context_pack_prompt_excerpt(pack)
    assert "Context Pack v1" in excerpt
    assert "Enhanced Input" in excerpt
    assert "/Game/BP_Demo" in excerpt
    assert "EventGraph" in excerpt
    assert "BP_EnemySpawner_1" in excerpt
    assert "MI_Player" in excerpt
    assert "Recent tool observations" in excerpt
