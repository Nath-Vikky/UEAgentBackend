from __future__ import annotations

from app.services.editor_operations.targets import build_affected_targets


def test_build_affected_targets_for_batch_rename_assets() -> None:
    targets = build_affected_targets(
        "batch_rename_assets",
        {
            "renames": [
                {"asset_path": "/Game/A/BP_Old", "target_path": "/Game/A/BP_New"},
                {"asset_path": "/Game/A/SM_Old", "target_path": "/Game/A/SM_New"},
            ]
        },
    )

    assert targets == [
        {"kind": "asset", "action": "rename", "path": "/Game/A/BP_Old", "target_path": "/Game/A/BP_New"},
        {"kind": "asset", "action": "rename", "path": "/Game/A/SM_Old", "target_path": "/Game/A/SM_New"},
    ]


def test_build_affected_targets_for_blueprint_node_template_keeps_context_fields() -> None:
    targets = build_affected_targets(
        "add_blueprint_node_template",
        {
            "blueprint_path": "/Game/Blueprints/BP_TestActor",
            "template_id": "custom_event_print_string",
            "graph_name": "EventGraph",
            "custom_event_name": "OnAgentTriggered",
            "entry_event": "",
            "message": "Hello",
        },
    )

    assert targets == [
        {
            "kind": "blueprint",
            "action": "add_blueprint_node_template",
            "path": "/Game/Blueprints/BP_TestActor",
            "template_id": "custom_event_print_string",
            "graph_name": "EventGraph",
            "custom_event_name": "OnAgentTriggered",
        }
    ]


def test_build_affected_targets_for_umg_appearance_reports_field_names() -> None:
    targets = build_affected_targets(
        "set_umg_widget_appearance",
        {
            "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
            "widget_name": "HealthText",
            "appearance": {"opacity": 0.7, "color": {}},
        },
    )

    assert targets == [
        {
            "kind": "umg_widget",
            "action": "set_umg_widget_appearance",
            "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
            "widget_name": "HealthText",
            "appearance_fields": ["color", "opacity"],
        }
    ]


def test_build_affected_targets_for_level_arrangement_expands_actor_references() -> None:
    targets = build_affected_targets(
        "arrange_actors_pattern",
        {
            "actor_references": ["BP_EnemySpawner_1", "BP_PatrolPoint_1"],
            "pattern": {"type": "line"},
        },
    )

    assert targets == [
        {
            "kind": "level_actor",
            "action": "arrange_pattern",
            "actor_reference": "BP_EnemySpawner_1",
            "pattern_type": "line",
        },
        {
            "kind": "level_actor",
            "action": "arrange_pattern",
            "actor_reference": "BP_PatrolPoint_1",
            "pattern_type": "line",
        },
    ]


def test_build_affected_targets_for_material_parameter_includes_value() -> None:
    targets = build_affected_targets(
        "set_material_instance_parameter",
        {
            "material_instance_path": "/Game/Materials/MI_Player",
            "parameter_name": "Roughness",
            "parameter_type": "scalar",
            "value": 0.25,
        },
    )

    assert targets == [
        {
            "kind": "material_instance",
            "action": "set_material_instance_parameter",
            "path": "/Game/Materials/MI_Player",
            "parameter_name": "Roughness",
            "parameter_type": "scalar",
            "value": 0.25,
        }
    ]
