from __future__ import annotations

from typing import Any

BLUEPRINT_STEP_NAME_TO_TEMPLATE_ID = {
    "print": "print_string",
    "printstring": "print_string",
    "print_string": "print_string",
    "print string": "print_string",
    "delay": "delay_print_string",
    "delay print": "delay_print_string",
    "delay print string": "delay_print_string",
    "branch": "branch_print_string",
    "branch print": "branch_print_string",
    "sequence": "sequence_print_strings",
    "sequence print": "sequence_print_strings",
    "custom event": "custom_event_print_string",
    "custom event print": "custom_event_print_string",
    "enhanced input": "enhanced_input_print_string",
    "enhanced input print": "enhanced_input_print_string",
}
BLUEPRINT_CONTEXT_OPERATION_TYPES = {
    "add_blueprint_node_template",
    "connect_blueprint_nodes",
    "compile_blueprint",
}
UMG_CONTEXT_OPERATION_TYPES = {
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
}
UMG_CURSOR_TARGET_OPERATION_TYPES = UMG_CONTEXT_OPERATION_TYPES - {"add_umg_widget"}
MATERIAL_CONTEXT_OPERATION_TYPES = {
    "set_material_instance_parameter",
    "set_material_instance_texture_parameter",
    "set_material_instance_static_switch",
}


def normalize_tool_arguments(
    *,
    tool_id: str,
    operation_type: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if tool_id != "editor_blueprint_add_step" or operation_type != "add_blueprint_node_template":
        return arguments
    payload = dict(arguments)
    step_name = str(
        payload.pop("step_name", "")
        or payload.pop("name", "")
        or payload.pop("node_name", "")
        or payload.get("template_id", "")
    ).strip()
    template_id = str(payload.get("template_id") or "").strip()
    if not template_id and step_name:
        template_id = BLUEPRINT_STEP_NAME_TO_TEMPLATE_ID.get(_normalize_step_name(step_name), "")
    if template_id:
        payload["template_id"] = template_id
    if "message" not in payload and "text" in payload:
        payload["message"] = payload.pop("text")
    else:
        payload.pop("text", None)
    return payload


def apply_context_defaults(
    *,
    operation_type: str,
    arguments: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    if operation_type in BLUEPRINT_CONTEXT_OPERATION_TYPES:
        return _apply_blueprint_context_defaults(operation_type=operation_type, arguments=arguments, context=context)
    if operation_type in UMG_CONTEXT_OPERATION_TYPES:
        return _apply_umg_context_defaults(operation_type=operation_type, arguments=arguments, context=context)
    if operation_type in MATERIAL_CONTEXT_OPERATION_TYPES:
        return _apply_material_context_defaults(
            operation_type=operation_type,
            arguments=arguments,
            context=context,
        )
    return arguments


def _apply_blueprint_context_defaults(
    *,
    operation_type: str,
    arguments: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    blueprint_context = _blueprint_edit_context(context)
    if not blueprint_context:
        return arguments
    payload = dict(arguments)
    _set_missing(payload, "blueprint_path", blueprint_context.get("blueprint_path"))
    if operation_type in {"add_blueprint_node_template", "connect_blueprint_nodes"}:
        _set_missing(payload, "graph_name", blueprint_context.get("graph_name"))
    if operation_type == "connect_blueprint_nodes":
        cursor_node = blueprint_context.get("cursor_node")
        cursor_node = cursor_node if isinstance(cursor_node, dict) else {}
        _set_missing(payload, "source_node_id", cursor_node.get("node_id"))
        _set_missing(payload, "source_pin_name", _first_pin_name(cursor_node, direction="output", fallback="then"))
    return payload


def _apply_umg_context_defaults(
    *,
    operation_type: str,
    arguments: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    umg_context = _umg_edit_context(context)
    if not umg_context:
        return arguments
    payload = dict(arguments)
    _set_missing(
        payload,
        "widget_blueprint_path",
        umg_context.get("widget_blueprint_path") or umg_context.get("blueprint_path"),
    )
    cursor_widget = umg_context.get("cursor_widget")
    cursor_widget = cursor_widget if isinstance(cursor_widget, dict) else {}
    cursor_widget_name = _first_text(
        cursor_widget.get("widget_name"),
        cursor_widget.get("name"),
        cursor_widget.get("id"),
    )
    if operation_type in UMG_CURSOR_TARGET_OPERATION_TYPES:
        _set_missing(payload, "widget_name", cursor_widget_name)
    if operation_type == "add_umg_widget":
        _set_missing(payload, "parent_widget_name", cursor_widget_name or umg_context.get("root_widget_name"))
    return payload


def _apply_material_context_defaults(
    *,
    operation_type: str,
    arguments: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    material_context = _material_edit_context(context)
    if not material_context:
        return arguments
    payload = dict(arguments)
    _set_missing(payload, "material_instance_path", material_context.get("material_instance_path"))
    cursor_parameter = material_context.get("cursor_parameter")
    cursor_parameter = cursor_parameter if isinstance(cursor_parameter, dict) else {}
    parameter_name = _first_text(cursor_parameter.get("parameter_name"), cursor_parameter.get("name"))
    parameter_type = _normalize_parameter_type(cursor_parameter.get("parameter_type") or cursor_parameter.get("type"))
    _set_missing(payload, "parameter_name", parameter_name)
    if operation_type == "set_material_instance_parameter" and parameter_type in {"scalar", "vector"}:
        _set_missing(payload, "parameter_type", parameter_type)
    return payload


def _normalize_step_name(value: str) -> str:
    return " ".join(value.replace("-", " ").replace("_", " ").strip().lower().split())


def _blueprint_edit_context(context: dict[str, Any]) -> dict[str, Any]:
    direct = context.get("blueprint_edit_context")
    if isinstance(direct, dict):
        return direct
    active_context = context.get("active_context")
    if isinstance(active_context, dict):
        nested = active_context.get("blueprint_edit_context")
        if isinstance(nested, dict):
            return nested
        blueprint = active_context.get("blueprint")
        if isinstance(blueprint, dict):
            return {
                "blueprint_path": blueprint.get("current_blueprint_path"),
                "graph_name": blueprint.get("current_graph_name"),
                "cursor_node": blueprint.get("current_node_summary"),
            }
    return {}


def _umg_edit_context(context: dict[str, Any]) -> dict[str, Any]:
    direct = context.get("umg_edit_context")
    if isinstance(direct, dict):
        return direct
    active_context = context.get("active_context")
    if isinstance(active_context, dict):
        nested = active_context.get("umg_edit_context")
        if isinstance(nested, dict):
            return nested
        umg = active_context.get("umg")
        if isinstance(umg, dict):
            return {
                "widget_blueprint_path": umg.get("current_widget_blueprint_path")
                or umg.get("widget_blueprint_path"),
                "root_widget_name": umg.get("root_widget_name"),
                "cursor_widget": umg.get("current_widget_summary") or umg.get("cursor_widget"),
            }
    return {}


def _material_edit_context(context: dict[str, Any]) -> dict[str, Any]:
    direct = context.get("material_edit_context")
    if isinstance(direct, dict):
        return direct
    active_context = context.get("active_context")
    if isinstance(active_context, dict):
        nested = active_context.get("material_edit_context")
        if isinstance(nested, dict):
            return nested
        material = active_context.get("material")
        if isinstance(material, dict):
            return {
                "material_instance_path": material.get("current_material_instance_path")
                or material.get("material_instance_path"),
                "cursor_parameter": material.get("current_parameter_summary") or material.get("cursor_parameter"),
            }
    return {}


def _set_missing(payload: dict[str, Any], key: str, value: Any) -> None:
    if payload.get(key) in (None, "") and value not in (None, ""):
        payload[key] = value


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _normalize_parameter_type(value: Any) -> str:
    text = " ".join(str(value or "").replace("_", " ").strip().lower().split())
    if text in {"scalar", "float"}:
        return "scalar"
    if text in {"vector", "color", "linear color", "linearcolor"}:
        return "vector"
    if text in {"texture", "texture2d", "texture 2d"}:
        return "texture"
    if text in {"static switch", "staticswitch", "switch", "bool", "boolean"}:
        return "static_switch"
    return text


def _first_pin_name(cursor_node: dict[str, Any], *, direction: str, fallback: str) -> str:
    for pin in cursor_node.get("pins") or []:
        if not isinstance(pin, dict):
            continue
        pin_direction = str(pin.get("direction") or pin.get("pin_direction") or "").strip().lower()
        pin_type = str(pin.get("pin_type") or pin.get("type") or pin.get("category") or "").strip().lower()
        if direction and pin_direction and direction not in pin_direction:
            continue
        if pin_type and "exec" not in pin_type:
            continue
        name = str(pin.get("pin_name") or pin.get("name") or "").strip()
        if name:
            return name
    return fallback
