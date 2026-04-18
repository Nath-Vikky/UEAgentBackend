from __future__ import annotations

from typing import Any


def _type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _matches_type(expected: str, value: Any) -> bool:
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


def _validate_node(
    value: Any,
    schema: dict[str, Any],
    *,
    path: str,
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    expected_type = schema.get("type")
    if expected_type and not _matches_type(expected_type, value):
        errors.append(
            {
                "path": path,
                "message": f"Expected `{expected_type}` but got `{_type_name(value)}`.",
            }
        )
        return

    if "enum" in schema and value not in schema["enum"]:
        errors.append(
            {
                "path": path,
                "message": f"Value `{value}` is not in the allowed enum set.",
            }
        )

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and value < minimum:
            errors.append({"path": path, "message": f"Value `{value}` is lower than minimum `{minimum}`."})
        if maximum is not None and value > maximum:
            errors.append({"path": path, "message": f"Value `{value}` is higher than maximum `{maximum}`."})

    if isinstance(value, list):
        min_items = schema.get("minItems")
        if min_items is not None and len(value) < min_items:
            errors.append(
                {
                    "path": path,
                    "message": f"Expected at least {min_items} item(s) but got {len(value)}.",
                }
            )
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_node(
                    item,
                    item_schema,
                    path=f"{path}[{index}]",
                    errors=errors,
                    warnings=warnings,
                )

    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        required = schema.get("required") or []
        for key in required:
            if key not in value:
                errors.append({"path": f"{path}.{key}", "message": "Missing required field."})
        for key, item in value.items():
            if key in properties:
                _validate_node(
                    item,
                    properties[key],
                    path=f"{path}.{key}",
                    errors=errors,
                    warnings=warnings,
                )
            else:
                warnings.append(
                    {
                        "path": f"{path}.{key}",
                        "message": "Field is not declared in the schema.",
                    }
                )


def validate_design_config(payload: dict[str, Any]) -> dict[str, Any]:
    schema = payload.get("schema") or payload.get("schema_body") or {}
    config_json = payload.get("config_json") or payload.get("draft_config") or {}
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if not isinstance(schema, dict) or not schema:
        warnings.append({"path": "$", "message": "No schema body was provided. Validation coverage is limited."})
    if not isinstance(config_json, dict):
        errors.append({"path": "$", "message": "Config payload must be a JSON object."})
        return {
            "errors": errors,
            "warnings": warnings,
            "suggestions": ["Send `config_json` as an object so the validator can inspect individual fields."],
            "validation_summary": {
                "is_valid": False,
                "error_count": len(errors),
                "warning_count": len(warnings),
                "checked_fields": 0,
            },
        }

    if isinstance(schema, dict) and schema:
        _validate_node(config_json, schema, path="$", errors=errors, warnings=warnings)

    suggestions = []
    if errors:
        suggestions.append("Fix the required-field and type mismatches before attempting to apply this config.")
    if warnings:
        suggestions.append("Review undeclared fields and confirm whether the schema is stale or the payload is over-specified.")
    if not suggestions:
        suggestions.append("The payload is structurally consistent with the provided schema.")

    checked_fields = len(config_json.keys()) if isinstance(config_json, dict) else 0
    return {
        "errors": errors,
        "warnings": warnings,
        "suggestions": suggestions,
        "validation_summary": {
            "is_valid": not errors,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "checked_fields": checked_fields,
        },
    }
