from __future__ import annotations

from typing import Any


def build_affected_targets(operation_type: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    if operation_type == "rename_selected_asset":
        return [
            {
                "kind": "asset",
                "action": "rename",
                "path": payload["asset_path"],
                "target_path": payload["target_path"],
            }
        ]
    if operation_type == "apply_static_mesh_basic_settings":
        return [
            {
                "kind": "static_mesh",
                "action": "modify_settings",
                "path": payload["asset_path"],
                "fields": sorted(payload["settings"].keys()),
            }
        ]
    if operation_type == "create_blueprint_asset":
        return [
            {
                "kind": "blueprint_asset",
                "action": "create",
                "path": payload["target_path"],
                "parent_class": payload["parent_class"],
            }
        ]
    if operation_type in {
        "add_blueprint_variable",
        "add_blueprint_component",
        "create_blueprint_event_stub",
        "add_blueprint_node_template",
        "connect_blueprint_nodes",
        "compile_blueprint",
    }:
        target: dict[str, Any] = {
            "kind": "blueprint",
            "action": operation_type,
            "path": payload["blueprint_path"],
        }
        for key in (
            "variable_name",
            "component_name",
            "event_name",
            "template_id",
            "graph_name",
            "entry_event",
            "branch_path",
            "delay_seconds",
            "sequence_output_count",
            "function_name",
            "function_target",
            "custom_event_name",
            "input_action_path",
            "source_node_id",
            "source_pin_name",
            "target_node_id",
            "target_pin_name",
            "variable_scope",
            "variable_value",
        ):
            if payload.get(key):
                target[key] = payload[key]
        return [target]
    if operation_type == "batch_rename_assets":
        return [
            {
                "kind": "asset",
                "action": "rename",
                "path": item["asset_path"],
                "target_path": item["target_path"],
            }
            for item in payload["renames"]
        ]
    if operation_type == "move_assets":
        return [
            {
                "kind": "asset",
                "action": "move",
                "path": item["asset_path"],
                "target_path": item["target_path"],
            }
            for item in payload["moves"]
        ]
    if operation_type == "duplicate_asset":
        return [
            {
                "kind": "asset",
                "action": "duplicate",
                "path": payload["source_asset_path"],
                "target_path": payload["target_path"],
            }
        ]
    if operation_type == "fixup_redirectors":
        return [
            {
                "kind": "asset_folder",
                "action": "fixup_redirectors",
                "path": payload["folder_path"],
                "recursive": payload["recursive"],
                "max_redirectors": payload["max_redirectors"],
            }
        ]
    if operation_type in {
        "add_umg_widget",
        "set_umg_widget_text",
        "set_umg_widget_layout",
        "set_umg_widget_visibility",
        "set_umg_widget_appearance",
        "set_umg_widget_brush",
        "set_umg_slot_layout_v2",
        "reparent_umg_widget",
        "duplicate_umg_widget",
        "delete_umg_widget",
    }:
        target = {
            "kind": "umg_widget",
            "action": operation_type,
            "widget_blueprint_path": payload["widget_blueprint_path"],
            "widget_name": payload["widget_name"],
        }
        for key in ("widget_class", "slot_type", "visibility"):
            if payload.get(key):
                target[key] = payload[key]
        if payload.get("appearance"):
            target["appearance_fields"] = sorted(payload["appearance"].keys())
        if payload.get("brush"):
            target["brush"] = dict(payload["brush"])
        if payload.get("layout"):
            target["layout_fields"] = sorted(payload["layout"].keys())
        if payload.get("new_parent_name"):
            target["new_parent_name"] = payload["new_parent_name"]
        if payload.get("new_widget_name"):
            target["new_widget_name"] = payload["new_widget_name"]
        return [target]
    if operation_type == "place_actor_in_level":
        return [
            {
                "kind": "level_actor",
                "action": "place_actor",
                "actor_class": payload["actor_class"],
                "actor_label": payload.get("actor_label"),
            }
        ]
    if operation_type == "set_actor_transform":
        return [
            {
                "kind": "level_actor",
                "action": "set_transform",
                "actor_reference": payload["actor_reference"],
                "transform_mode": payload["transform_mode"],
            }
        ]
    if operation_type == "select_level_actors":
        selection = payload["selection"]
        return [
            {
                "kind": "level_actor",
                "action": "select_actors",
                "actor_references": selection.get("actor_references", []),
                "query": selection.get("query"),
                "class_contains": selection.get("class_contains"),
                "tag": selection.get("tag"),
                "folder_path": selection.get("folder_path"),
                "max_count": selection.get("max_count"),
            }
        ]
    if operation_type == "set_actor_metadata":
        return [
            {
                "kind": "level_actor",
                "action": "set_metadata",
                "actor_reference": payload["actor_reference"],
                "metadata_fields": sorted(payload["metadata"].keys()),
            }
        ]
    if operation_type == "arrange_actors_pattern":
        return [
            {
                "kind": "level_actor",
                "action": "arrange_pattern",
                "actor_reference": actor_reference,
                "pattern_type": payload["pattern"]["type"],
            }
            for actor_reference in payload["actor_references"]
        ]
    if operation_type in {
        "set_material_instance_parameter",
        "set_material_instance_texture_parameter",
        "set_material_instance_static_switch",
    }:
        target = {
            "kind": "material_instance",
            "action": operation_type,
            "path": payload["material_instance_path"],
            "parameter_name": payload["parameter_name"],
        }
        if payload.get("parameter_type"):
            target["parameter_type"] = payload["parameter_type"]
        if payload.get("texture_path"):
            target["texture_path"] = payload["texture_path"]
        if "value" in payload:
            target["value"] = payload["value"]
        return [target]
    return [{"kind": "editor_operation", "action": operation_type}]


__all__ = ["build_affected_targets"]
