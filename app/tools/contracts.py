from __future__ import annotations

from typing import Any

from app.tools.registry import TOOL_REGISTRY, ToolSpec, get_tool_spec

_TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
}


def _validate_schema_payload(schema: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    required = [str(item) for item in schema.get("required", [])]
    missing_fields = [
        field
        for field in required
        if field not in payload or payload.get(field) is None or payload.get(field) == ""
    ]
    type_errors: list[dict[str, str]] = []
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    for field, rules in properties.items():
        if field not in payload or payload.get(field) is None:
            continue
        expected_type = rules.get("type") if isinstance(rules, dict) else None
        expected_python_type = _TYPE_MAP.get(str(expected_type))
        if expected_python_type and not isinstance(payload[field], expected_python_type):
            type_errors.append(
                {
                    "field": str(field),
                    "expected": str(expected_type),
                    "actual": type(payload[field]).__name__,
                }
            )
            continue
        if expected_type == "integer" and isinstance(payload[field], bool):
            type_errors.append(
                {"field": str(field), "expected": "integer", "actual": "bool"}
            )
            continue
        if expected_type == "number" and isinstance(payload[field], bool):
            type_errors.append(
                {"field": str(field), "expected": "number", "actual": "bool"}
            )

    return {
        "ok": not missing_fields and not type_errors,
        "missing_fields": missing_fields,
        "type_errors": type_errors,
    }


def validate_tool_call_input(tool_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    spec = get_tool_spec(tool_id)
    if not spec:
        return {
            "tool_id": tool_id,
            "ok": False,
            "status": "unknown_tool",
            "missing_fields": [],
            "type_errors": [],
        }
    schema = spec.input_schema or {
        "type": "object",
        "required": list(spec.required_payload_fields),
        "properties": {},
    }
    result = _validate_schema_payload(schema, payload)
    return {"tool_id": tool_id, "status": "ok" if result["ok"] else "invalid_input", **result}


def validate_tool_result(tool_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    spec = get_tool_spec(tool_id)
    if not spec:
        return {
            "tool_id": tool_id,
            "ok": False,
            "status": "unknown_tool",
            "missing_fields": [],
            "type_errors": [],
        }
    if not spec.output_schema:
        return {
            "tool_id": tool_id,
            "ok": True,
            "status": "no_output_schema",
            "missing_fields": [],
            "type_errors": [],
        }
    result = _validate_schema_payload(spec.output_schema, payload)
    return {"tool_id": tool_id, "status": "ok" if result["ok"] else "invalid_output", **result}


def _validate_spec(tool_id: str, spec: ToolSpec) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if tool_id != spec.tool_id:
        issues.append({"tool_id": tool_id, "field": "tool_id", "message": "Tool key and spec.tool_id differ."})
    if spec.side_effect_level not in {"read_only", "plan_only", "confirmed_write"}:
        issues.append(
            {
                "tool_id": tool_id,
                "field": "side_effect_level",
                "message": f"Unsupported side effect level: {spec.side_effect_level}",
            }
        )
    if spec.route_preference not in {"project_qa", "single_tool", "workflow", "proposal_wait"}:
        issues.append(
            {
                "tool_id": tool_id,
                "field": "route_preference",
                "message": f"Unsupported route preference: {spec.route_preference}",
            }
        )
    for schema_name, schema in (("input_schema", spec.input_schema), ("output_schema", spec.output_schema)):
        if not schema:
            continue
        if schema.get("type") != "object":
            issues.append(
                {
                    "tool_id": tool_id,
                    "field": schema_name,
                    "message": "Only object schemas are supported by the lightweight validator.",
                }
            )
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            issues.append(
                {
                    "tool_id": tool_id,
                    "field": schema_name,
                    "message": "Schema must define a properties object.",
                }
            )
            continue
        missing_required = [
            field for field in schema.get("required", []) if field not in properties
        ]
        if missing_required:
            issues.append(
                {
                    "tool_id": tool_id,
                    "field": schema_name,
                    "message": f"Required fields missing from properties: {', '.join(missing_required)}",
                }
            )
    return issues


def validate_tool_registry() -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    for tool_id, spec in TOOL_REGISTRY.items():
        issues.extend(_validate_spec(tool_id, spec))
    return {
        "ok": not issues,
        "tool_count": len(TOOL_REGISTRY),
        "issue_count": len(issues),
        "issues": issues,
    }
