from __future__ import annotations

from app.agent.tool_use_summary import summarize_tool_use, summarize_tool_uses


def test_summarize_tool_use_hides_raw_payload() -> None:
    summary = summarize_tool_use(
        tool_id="mcp_get_asset_details",
        result={
            "status": "completed",
            "summary": "Read asset details.",
            "output": {
                "items": [{"asset_path": "/Game/A"}],
                "raw_payload": {"large": True},
                "structuredContent": {"hidden": True},
                "warnings": ["partial"],
            },
        },
    )

    assert summary["version"] == "tool_use_summary_v1"
    assert summary["user_summary"] == "Read asset details."
    assert summary["item_count"] == 1
    assert summary["warning_count"] == 1
    assert summary["raw_payload_hidden"] is True
    assert "raw_payload" not in summary["safe_output_keys"]
    assert "structuredContent" not in summary["safe_output_keys"]


def test_summarize_tool_uses_batches_debug_entries() -> None:
    summaries = summarize_tool_uses(
        [
            {"tool_id": "query_project_inventory", "status": "completed", "summary": "Matched 2 items."},
            {"tool_id": "retrieve_project_knowledge", "status": "skipped"},
        ]
    )

    assert [item["tool_id"] for item in summaries] == [
        "query_project_inventory",
        "retrieve_project_knowledge",
    ]
    assert summaries[1]["status"] == "skipped"


def test_summarize_asset_details_uses_domain_fields_without_tool_leak() -> None:
    summary = summarize_tool_use(
        tool_id="mcp_get_asset_details",
        result={
            "status": "completed",
            "output": {
                "item": {
                    "asset_name": "SM_Rock",
                    "asset_path": "/Game/Props/SM_Rock.SM_Rock",
                    "asset_type": "StaticMesh",
                    "static_mesh": {
                        "nanite_enabled": True,
                        "collision_complexity": "UseComplexAsSimple",
                    },
                }
            },
        },
    )

    assert summary["tool_label"] == "Asset details"
    assert summary["target_names"] == ["SM_Rock"]
    assert "SM_Rock" in summary["user_summary"]
    assert "Nanite: enabled" in summary["user_summary"]
    assert "mcp_get_asset_details" not in summary["user_summary"]


def test_summarize_actor_widget_and_material_details() -> None:
    actor = summarize_tool_use(
        tool_id="mcp_get_level_actor_details",
        result={
            "output": {
                "item": {
                    "actor_label": "BP_EnemySpawner_1",
                    "actor_class": "BP_EnemySpawner_C",
                    "components": [{"component_name": "SceneRoot"}, {"component_name": "Billboard"}],
                }
            }
        },
    )
    widget = summarize_tool_use(
        tool_id="mcp_get_umg_widget_details",
        result={
            "output": {
                "widget_name": "TitleText",
                "widget_class": "TextBlock",
                "parent_widget_name": "RootCanvas",
                "visibility": "Visible",
            }
        },
    )
    material = summarize_tool_use(
        tool_id="mcp_get_material_instance_parameters",
        result={
            "output": {
                "items": [
                    {
                        "material_instance_name": "MI_Rock",
                        "parent_material": "M_Rock",
                        "scalar_parameters": [{"name": "Roughness", "value": 0.6}],
                        "vector_parameters": [{"name": "BaseColor", "value": "(1,1,1,1)"}],
                    }
                ]
            }
        },
    )

    assert actor["target_names"] == ["BP_EnemySpawner_1"]
    assert "2 component" in actor["user_summary"]
    assert widget["target_names"] == ["TitleText"]
    assert "TextBlock" in widget["user_summary"]
    assert material["target_names"] == ["MI_Rock"]
    assert "Roughness" in material["user_summary"]
    assert "BaseColor" in material["user_summary"]


def test_summarize_tool_use_fallback_does_not_expose_internal_tool_id() -> None:
    summary = summarize_tool_use(
        tool_id="mcp_get_selected_assets",
        result={"status": "completed", "output": {"items": [{"asset_path": "/Game/A.A"}]}},
    )

    assert summary["user_summary"] == "Selected assets: /Game/A.A."
    assert "mcp_get" not in summary["user_summary"]
