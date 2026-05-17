from __future__ import annotations

import difflib
from typing import Any

from app.tools.registry import (
    ROUTE_PREFERENCES,
    CONFIRMATION_SIDE_EFFECT_LEVELS,
    SIDE_EFFECT_LEVELS,
    TOOL_CATEGORIES,
    TOOL_REGISTRY,
    TOOL_TRANSPORTS,
    ToolSpec,
    get_tool_spec,
    iter_tool_specs,
)

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
    unknown_fields = sorted(set(payload) - set(properties))
    unknown_field_suggestions = {
        field: difflib.get_close_matches(field, list(properties), n=1)
        for field in unknown_fields
    }
    enum_errors: list[dict[str, Any]] = []
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
            continue
        allowed_values = rules.get("enum") if isinstance(rules, dict) else None
        if isinstance(allowed_values, list) and payload[field] not in allowed_values:
            enum_errors.append(
                {
                    "field": str(field),
                    "allowed": allowed_values,
                    "actual": payload[field],
                }
            )

    unknown_fields_blocking = schema.get("additionalProperties") is False
    return {
        "ok": not missing_fields and not type_errors and not enum_errors and not (unknown_fields_blocking and unknown_fields),
        "missing_fields": missing_fields,
        "type_errors": type_errors,
        "enum_errors": enum_errors,
        "unknown_fields": unknown_fields,
        "unknown_field_suggestions": unknown_field_suggestions,
        "unknown_fields_blocking": unknown_fields_blocking,
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
    if spec.side_effect_level not in SIDE_EFFECT_LEVELS:
        issues.append(
            {
                "tool_id": tool_id,
                "field": "side_effect_level",
                "message": f"Unsupported side effect level: {spec.side_effect_level}",
            }
        )
    if spec.route_preference not in ROUTE_PREFERENCES:
        issues.append(
            {
                "tool_id": tool_id,
                "field": "route_preference",
                "message": f"Unsupported route preference: {spec.route_preference}",
            }
        )
    if spec.category not in TOOL_CATEGORIES:
        issues.append(
            {
                "tool_id": tool_id,
                "field": "category",
                "message": f"Unsupported tool category: {spec.category}",
            }
        )
    if spec.transport not in TOOL_TRANSPORTS:
        issues.append(
            {
                "tool_id": tool_id,
                "field": "transport",
                "message": f"Unsupported tool transport: {spec.transport}",
            }
        )
    if spec.side_effect_level in CONFIRMATION_SIDE_EFFECT_LEVELS and not spec.effective_requires_confirmation:
        issues.append(
            {
                "tool_id": tool_id,
                "field": "requires_confirmation",
                "message": "Write-like side-effect tools must require confirmation.",
            }
        )
    if spec.side_effect_level in CONFIRMATION_SIDE_EFFECT_LEVELS and spec.permission_gate in {"", "none"}:
        issues.append(
            {
                "tool_id": tool_id,
                "field": "permission_gate",
                "message": "Write-like side-effect tools must define a permission gate.",
            }
        )
    if spec.allowed_in_free_chat and spec.side_effect_level != "read_only":
        issues.append(
            {
                "tool_id": tool_id,
                "field": "allowed_in_free_chat",
                "message": "Only read-only tools may be auto-selected from free chat.",
            }
        )
    if spec.transport.startswith("mcp") and not spec.mcp_tool_name:
        issues.append(
            {
                "tool_id": tool_id,
                "field": "mcp_tool_name",
                "message": "MCP transport tools must define mcp_tool_name.",
            }
        )
    if spec.executor is not None and not spec.executor.strip():
        issues.append(
            {
                "tool_id": tool_id,
                "field": "executor",
                "message": "Tool executor metadata must not be blank when provided.",
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
    for spec in iter_tool_specs(include_disabled=True):
        issues.extend(_validate_spec(spec.tool_id, spec))
    return {
        "ok": not issues,
        "tool_count": len(TOOL_REGISTRY),
        "enabled_tool_count": len(iter_tool_specs(include_disabled=False)),
        "issue_count": len(issues),
        "issues": issues,
    }
