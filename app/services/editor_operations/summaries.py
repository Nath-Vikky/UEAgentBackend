from __future__ import annotations

from typing import Any


def build_operation_summaries(operation_type: str, payload: dict[str, Any]) -> tuple[str, str]:
    if operation_type == "rename_selected_asset":
        return (
            f"Current asset path: {payload['asset_path']}",
            f"Rename to: {payload['target_path']}",
        )
    if operation_type == "apply_static_mesh_basic_settings":
        fields = ", ".join(sorted(payload["settings"].keys()))
        return (
            f"Current Static Mesh settings snapshot will be compared for {payload['asset_path']}.",
            f"Apply whitelisted settings: {fields}. Asset package will be marked dirty, not auto-saved.",
        )
    if operation_type == "create_blueprint_asset":
        return (
            f"No Blueprint will be created before confirmation. Parent class: {payload['parent_class']}",
            f"Create Blueprint `{payload['asset_name']}` at {payload['target_path']}.",
        )
    if operation_type == "add_blueprint_variable":
        return (
            f"Blueprint before change: {payload['blueprint_path']}",
            f"Add variable `{payload['variable_name']}` of type `{payload['variable_type']}`.",
        )
    if operation_type == "add_blueprint_component":
        return (
            f"Blueprint before change: {payload['blueprint_path']}",
            f"Add component `{payload['component_name']}` of class `{payload['component_class']}`.",
        )
    if operation_type == "create_blueprint_event_stub":
        return (
            f"Blueprint graph before change: {payload['blueprint_path']}::{payload['graph_name']}",
            f"Create event stub `{payload['event_name']}`. No complex node graph is generated in v1.",
        )
    if operation_type == "add_blueprint_node_template":
        details = f"Add `{payload['template_id']}` node template to `{payload['graph_name']}`"
        if payload["template_id"] == "print_string":
            details += f" with message `{payload['message']}`"
        if payload["template_id"] == "delay_print_string":
            details += (
                f" as Delay `{payload['delay_seconds']}` seconds"
                f" then PrintString `{payload['message']}`"
            )
        if payload["template_id"] == "branch_print_string":
            details += (
                f" with `{payload['branch_path']}` branch path connected to PrintString"
                f" and condition default `{payload['condition_default']}`"
            )
        if payload["template_id"] == "sequence_print_strings":
            details += f" with `{payload['sequence_output_count']}` sequence outputs connected to PrintString nodes"
        if payload["template_id"] == "get_variable":
            details += f" for existing variable `{payload['variable_name']}`"
        if payload["template_id"] == "set_variable":
            details += f" for existing variable `{payload['variable_name']}`"
            if payload.get("variable_value"):
                details += f" with default value `{payload['variable_value']}`"
        if payload["template_id"] == "call_function":
            details += f" for existing self function `{payload['function_name']}`"
        if payload["template_id"] == "custom_event_print_string":
            details += (
                f" for Custom Event `{payload['custom_event_name']}`"
                f" and connect it to PrintString `{payload['message']}`"
            )
        if payload["template_id"] == "enhanced_input_action_event":
            details += f" for Input Action `{payload['input_action_path']}`"
        if payload["template_id"] == "enhanced_input_print_string":
            details += (
                f" for Input Action `{payload['input_action_path']}`"
                f" and connect Triggered to PrintString `{payload['message']}`"
            )
        if payload.get("entry_event"):
            details += f" and connect from `{payload['entry_event']}`"
        if payload.get("compile_after_edit"):
            details += " and compile once after edit"
        return (
            f"Blueprint graph before change: {payload['blueprint_path']}::{payload['graph_name']}",
            f"{details}. The package is marked dirty, not auto-saved.",
        )
    if operation_type == "connect_blueprint_nodes":
        return (
            f"Blueprint graph before change: {payload['blueprint_path']}::{payload['graph_name']}",
            (
                "Connect explicit pins "
                f"`{payload['source_node_id']}.{payload['source_pin_name']}` -> "
                f"`{payload['target_node_id']}.{payload['target_pin_name']}`"
                ". The package is marked dirty, not auto-saved."
            ),
        )
    if operation_type == "compile_blueprint":
        return (
            f"Blueprint before compile: {payload['blueprint_path']}",
            "Compile the Blueprint in Unreal Editor and return compile status. The package is not auto-saved.",
        )
    if operation_type == "batch_rename_assets":
        preview = ", ".join(
            f"{item['asset_path']} -> {item['target_path']}"
            for item in payload["renames"][:5]
        )
        if payload["item_count"] > 5:
            preview += f", ... (+{payload['item_count'] - 5} more)"
        return (
            f"Batch rename {payload['item_count']} assets. No asset is changed before confirmation.",
            f"Rename plan: {preview}. Redirectors are not fixed automatically in this operation.",
        )
    if operation_type == "move_assets":
        preview = ", ".join(
            f"{item['asset_path']} -> {item['target_path']}"
            for item in payload["moves"][:5]
        )
        if payload["item_count"] > 5:
            preview += f", ... (+{payload['item_count'] - 5} more)"
        return (
            f"Move {payload['item_count']} assets to {payload['target_folder']}. No asset is changed before confirmation.",
            f"Move plan: {preview}. Redirectors are not fixed automatically in this operation.",
        )
    if operation_type == "duplicate_asset":
        return (
            f"Duplicate source asset: {payload['source_asset_path']}. No asset is changed before confirmation.",
            f"Create duplicate `{payload['target_path']}`. The duplicated package is marked dirty, not auto-saved.",
        )
    if operation_type == "fixup_redirectors":
        recursive_note = "recursively" if payload["recursive"] else "non-recursively"
        return (
            f"Fix redirectors under {payload['folder_path']} {recursive_note}. No asset is changed before confirmation.",
            (
                "Run Unreal redirector fixup for at most "
                f"{payload['max_redirectors']} redirectors. This may update referencers or redirector packages."
            ),
        )
    if operation_type == "add_umg_widget":
        parent = payload.get("parent_widget_name") or "root widget"
        return (
            f"Widget Blueprint before change: {payload['widget_blueprint_path']}",
            f"Add `{payload['widget_name']}` ({payload['widget_class']}) under {parent}. The package is not auto-saved.",
        )
    if operation_type == "set_umg_widget_text":
        return (
            f"Widget Blueprint before change: {payload['widget_blueprint_path']}",
            f"Set TextBlock `{payload['widget_name']}` text to `{payload['text']}`. The package is not auto-saved.",
        )
    if operation_type == "set_umg_widget_layout":
        fields = ", ".join(sorted(payload["layout"].keys()))
        return (
            f"Widget Blueprint before change: {payload['widget_blueprint_path']}",
            f"Set CanvasPanelSlot layout for `{payload['widget_name']}` fields: {fields}. The package is not auto-saved.",
        )
    if operation_type == "set_umg_widget_visibility":
        return (
            f"Widget Blueprint before change: {payload['widget_blueprint_path']}",
            f"Set widget `{payload['widget_name']}` visibility to `{payload['visibility']}`. The package is not auto-saved.",
        )
    if operation_type == "set_umg_widget_appearance":
        fields = ", ".join(sorted(payload["appearance"].keys()))
        return (
            f"Widget Blueprint before change: {payload['widget_blueprint_path']}",
            f"Set widget `{payload['widget_name']}` appearance fields: {fields}. The package is not auto-saved.",
        )
    if operation_type == "set_umg_widget_brush":
        brush = payload["brush"]
        return (
            f"Widget Blueprint before change: {payload['widget_blueprint_path']}",
            f"Set widget `{payload['widget_name']}` brush {brush['resource_type']} to `{brush['resource_path']}`. The package is not auto-saved.",
        )
    if operation_type == "set_umg_slot_layout_v2":
        fields = ", ".join(sorted(payload["layout"].keys()))
        return (
            f"Widget Blueprint before change: {payload['widget_blueprint_path']}",
            f"Set `{payload['slot_type']}` layout for `{payload['widget_name']}` fields: {fields}. The package is not auto-saved.",
        )
    if operation_type == "reparent_umg_widget":
        return (
            f"Widget Blueprint before change: {payload['widget_blueprint_path']}",
            f"Move widget `{payload['widget_name']}` under panel `{payload['new_parent_name']}`. The package is not auto-saved.",
        )
    if operation_type == "duplicate_umg_widget":
        return (
            f"Widget Blueprint before change: {payload['widget_blueprint_path']}",
            f"Duplicate widget `{payload['widget_name']}` as `{payload['new_widget_name']}` under the same parent. The package is not auto-saved.",
        )
    if operation_type == "delete_umg_widget":
        return (
            f"Widget Blueprint before change: {payload['widget_blueprint_path']}",
            f"Remove widget `{payload['widget_name']}` from its parent. The package is not auto-saved and editor Undo can restore it.",
        )
    if operation_type == "place_actor_in_level":
        location = payload["transform"]["location"]
        label = payload.get("actor_label") or "(default label)"
        return (
            f"Current level before change: no Actor is spawned before confirmation. Class: {payload['actor_class']}",
            f"Place Actor label `{label}` at ({location['x']}, {location['y']}, {location['z']}). The level is marked dirty, not auto-saved.",
        )
    if operation_type == "select_level_actors":
        selection = payload["selection"]
        selector_parts = []
        if selection.get("actor_references"):
            selector_parts.append(f"{len(selection['actor_references'])} explicit references")
        for key in ("query", "class_contains", "tag", "folder_path"):
            if selection.get(key):
                selector_parts.append(f"{key}={selection[key]}")
        selector_text = ", ".join(selector_parts) or "current selection criteria"
        return (
            "Current editor selection before change: unchanged until confirmation.",
            f"Select Level Actors matching {selector_text}. This changes editor selection only and does not save the level.",
        )
    if operation_type == "set_actor_folder":
        selection = payload["selection"]
        selector_parts = []
        if selection.get("actor_references"):
            selector_parts.append(f"{len(selection['actor_references'])} explicit references")
        for key in ("query", "class_contains", "tag", "folder_path"):
            if selection.get(key):
                selector_parts.append(f"{key}={selection[key]}")
        selector_text = ", ".join(selector_parts) or "current selection criteria"
        return (
            f"Actor folder before change: Actors matching {selector_text}.",
            f"Move matched Actors to World Outliner folder `{payload['target_folder_path']}`. The level is marked dirty, not auto-saved.",
        )
    if operation_type == "set_actor_transform":
        transform_key = "transform_delta" if payload["transform_mode"] == "delta" else "transform"
        fields = ", ".join(sorted(payload[transform_key].keys()))
        return (
            f"Actor before change: {payload['actor_reference']}",
            f"Apply {payload['transform_mode']} transform fields: {fields}. The level is marked dirty, not auto-saved.",
        )
    if operation_type == "set_actor_metadata":
        fields = ", ".join(sorted(payload["metadata"].keys()))
        return (
            f"Actor before change: {payload['actor_reference']}",
            f"Update Actor metadata fields: {fields}. The level is marked dirty, not auto-saved.",
        )
    if operation_type == "arrange_actors_pattern":
        pattern = payload["pattern"]
        return (
            f"Arrange {payload['item_count']} existing Actors. No Actor is moved before confirmation.",
            f"Apply `{pattern['type']}` pattern with spacing `{pattern['spacing']}`. The level is marked dirty, not auto-saved.",
        )
    if operation_type == "set_material_instance_parameter":
        return (
            f"Material Instance before change: {payload['material_instance_path']}",
            f"Set `{payload['parameter_name']}` {payload['parameter_type']} value. The package is marked dirty, not auto-saved.",
        )
    if operation_type == "set_material_instance_texture_parameter":
        return (
            f"Material Instance before change: {payload['material_instance_path']}",
            f"Set texture parameter `{payload['parameter_name']}` to `{payload['texture_path']}`. The package is marked dirty, not auto-saved.",
        )
    if operation_type == "set_material_instance_static_switch":
        return (
            f"Material Instance before change: {payload['material_instance_path']}",
            f"Set static switch `{payload['parameter_name']}` to `{payload['value']}`. The package is marked dirty, not auto-saved.",
        )
    return ("", "")


__all__ = ["build_operation_summaries"]
