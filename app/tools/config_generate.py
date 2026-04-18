from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.tools.config_validate import validate_design_config


def _default_value(field_name: str, schema: dict[str, Any], requirement_description: str, object_type: str) -> Any:
    if "default" in schema:
        return deepcopy(schema["default"])
    expected_type = schema.get("type")
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]
    if expected_type == "string":
        if "name" in field_name.lower():
            return object_type or "GeneratedConfig"
        if "description" in field_name.lower():
            return requirement_description or f"Generated from {object_type or 'the requested object'}."
        return ""
    if expected_type == "integer":
        return schema.get("minimum", 0)
    if expected_type == "number":
        return float(schema.get("minimum", 0.0))
    if expected_type == "boolean":
        return False
    if expected_type == "array":
        return []
    if expected_type == "object":
        return {}
    return None


def generate_design_config(payload: dict[str, Any]) -> dict[str, Any]:
    requirement_description = str(payload.get("requirement_description") or payload.get("user_query") or "").strip()
    object_type = str(payload.get("object_type") or "GeneratedObject").strip()
    schema = payload.get("schema") or {}
    examples = payload.get("examples") or []

    draft_config: dict[str, Any] = {}
    missing_fields: list[str] = []
    if isinstance(schema, dict) and schema.get("properties"):
        for field_name, field_schema in schema["properties"].items():
            draft_config[field_name] = _default_value(
                field_name,
                field_schema,
                requirement_description,
                object_type,
            )
        for required_field in schema.get("required") or []:
            if required_field not in draft_config:
                missing_fields.append(required_field)
    elif examples and isinstance(examples[0], dict):
        draft_config = deepcopy(examples[0])
    else:
        draft_config = {
            "object_type": object_type,
            "display_name": object_type,
            "enabled": True,
            "notes": requirement_description or "Generated without an explicit schema.",
        }

    validation_results = validate_design_config(
        {
            "config_json": draft_config,
            "schema": schema if isinstance(schema, dict) else {},
        }
    )
    explanation = (
        "Generated a first-pass config draft. Review required fields, defaults, and semantic constraints before applying it."
    )
    return {
        "draft_config": draft_config,
        "explanation": explanation,
        "missing_fields": missing_fields,
        "validation_results": validation_results,
        "export_format": "json",
        "schema_loaded": bool(schema),
        "example_count": len(examples) if isinstance(examples, list) else 0,
    }
