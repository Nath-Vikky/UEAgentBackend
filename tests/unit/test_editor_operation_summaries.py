from __future__ import annotations

from app.services.editor_operations.summaries import build_operation_summaries


def test_build_operation_summaries_for_asset_rename() -> None:
    before, after = build_operation_summaries(
        "rename_selected_asset",
        {
            "asset_path": "/Game/Maps/OldMap",
            "target_path": "/Game/Maps/NewMap",
        },
    )

    assert before == "Current asset path: /Game/Maps/OldMap"
    assert after == "Rename to: /Game/Maps/NewMap"


def test_build_operation_summaries_for_blueprint_node_template() -> None:
    before, after = build_operation_summaries(
        "add_blueprint_node_template",
        {
            "blueprint_path": "/Game/Blueprints/BP_TestActor",
            "graph_name": "EventGraph",
            "template_id": "delay_print_string",
            "delay_seconds": 2.0,
            "message": "Hello",
            "entry_event": "BeginPlay",
            "compile_after_edit": True,
        },
    )

    assert before == "Blueprint graph before change: /Game/Blueprints/BP_TestActor::EventGraph"
    assert "Delay `2.0` seconds" in after
    assert "PrintString `Hello`" in after
    assert "connect from `BeginPlay`" in after
    assert "compile once after edit" in after


def test_build_operation_summaries_for_umg_appearance() -> None:
    before, after = build_operation_summaries(
        "set_umg_widget_appearance",
        {
            "widget_blueprint_path": "/Game/UI/WBP_MainHUD",
            "widget_name": "HealthText",
            "appearance": {"color": {}, "opacity": 0.8},
        },
    )

    assert before == "Widget Blueprint before change: /Game/UI/WBP_MainHUD"
    assert after == "Set widget `HealthText` appearance fields: color, opacity. The package is not auto-saved."


def test_build_operation_summaries_for_level_actor_placement() -> None:
    before, after = build_operation_summaries(
        "place_actor_in_level",
        {
            "actor_class": "/Game/Blueprints/BP_EnemySpawner.BP_EnemySpawner_C",
            "actor_label": "EnemySpawner_A",
            "transform": {"location": {"x": 100.0, "y": 200.0, "z": 50.0}},
        },
    )

    assert "no Actor is spawned before confirmation" in before
    assert "EnemySpawner_A" in after
    assert "(100.0, 200.0, 50.0)" in after


def test_build_operation_summaries_for_material_texture_parameter() -> None:
    before, after = build_operation_summaries(
        "set_material_instance_texture_parameter",
        {
            "material_instance_path": "/Game/Materials/MI_Player",
            "parameter_name": "BaseTexture",
            "texture_path": "/Game/Textures/T_Player_D",
        },
    )

    assert before == "Material Instance before change: /Game/Materials/MI_Player"
    assert after == (
        "Set texture parameter `BaseTexture` to `/Game/Textures/T_Player_D`. "
        "The package is marked dirty, not auto-saved."
    )
