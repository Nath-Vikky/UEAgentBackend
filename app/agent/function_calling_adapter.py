from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from app.tools.registry import (
    TOOL_REGISTRY,
    ToolSpec,
    free_chat_tool_ids,
    get_tool_spec,
    iter_tool_specs,
)


def build_function_calling_tools(
    *,
    allowed_tool_ids: Iterable[str] | None = None,
    free_chat_only: bool = True,
    include_confirmed_write: bool = False,
) -> list[dict[str, Any]]:
    """Convert Tool Registry specs into provider-style function tool schemas.

    This adapter is intentionally transport-only. It does not replace the
    current deterministic planner, and it never exposes confirmed-write tools
    unless a caller explicitly opts in for a proposal-only planning context.
    """

    allowed = set(allowed_tool_ids or TOOL_REGISTRY.keys())
    if free_chat_only:
        allowed &= free_chat_tool_ids()

    tools: list[dict[str, Any]] = []
    for spec in iter_tool_specs(include_disabled=False):
        tool_id = spec.tool_id
        if tool_id not in allowed:
            continue
        if spec.effective_requires_confirmation and not include_confirmed_write:
            continue
        tools.append(_tool_spec_to_function_tool(spec))
    return tools


def normalize_function_tool_calls(
    raw_tool_calls: Iterable[Mapping[str, Any]],
    *,
    allowed_tool_ids: Iterable[str],
    max_tool_calls: int = 3,
) -> dict[str, Any]:
    """Normalize provider tool-call payloads into the existing planner contract."""

    allowed = set(allowed_tool_ids)
    requested_tool_ids: list[str] = []
    tool_inputs_by_id: dict[str, dict[str, Any]] = {}
    for raw_call in list(raw_tool_calls)[:max_tool_calls]:
        tool_id, arguments = _extract_tool_call(raw_call)
        if not tool_id or tool_id not in allowed or tool_id in requested_tool_ids:
            continue
        spec = get_tool_spec(tool_id)
        if not spec or spec.effective_requires_confirmation:
            continue
        requested_tool_ids.append(tool_id)
        tool_inputs_by_id[tool_id] = _sanitize_arguments(spec, arguments)

    return {
        "requested_tool_ids": requested_tool_ids,
        "tool_inputs_by_id": tool_inputs_by_id,
        "confidence": 0.0,
        "adapter": "function_calling",
    }


def _tool_spec_to_function_tool(spec: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": spec.tool_id,
            "description": _tool_description(spec),
            "parameters": _parameters_schema(spec),
        },
    }


def _tool_description(spec: ToolSpec) -> str:
    return (
        f"{spec.description} "
        f"Side effect level: {spec.side_effect_level}. "
        f"Permission gate: {spec.permission_gate}."
    )


def _parameters_schema(spec: ToolSpec) -> dict[str, Any]:
    schema = dict(spec.input_schema or {})
    if schema.get("type") != "object":
        schema["type"] = "object"
    schema.setdefault("properties", {})
    schema.setdefault("additionalProperties", False)
    return schema


def _extract_tool_call(raw_call: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    if isinstance(raw_call.get("function"), Mapping):
        function_payload = raw_call["function"]
        name = str(function_payload.get("name") or "").strip()
        return name, _parse_arguments(function_payload.get("arguments"))

    name = str(raw_call.get("name") or raw_call.get("tool_id") or "").strip()
    arguments = raw_call.get("arguments", raw_call.get("input", {}))
    return name, _parse_arguments(arguments)


def _parse_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _sanitize_arguments(spec: ToolSpec, arguments: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = set(spec.required_payload_fields) | set(spec.optional_payload_fields)
    allowed_keys.update((spec.input_schema.get("properties") or {}).keys())
    sanitized: dict[str, Any] = {}
    for key in allowed_keys:
        if key not in arguments:
            continue
        value = _sanitize_value(arguments[key])
        if value is not None:
            sanitized[key] = value
    return sanitized


def _sanitize_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return value[:2000]
    if isinstance(value, list):
        sanitized_items = [_sanitize_value(item) for item in value[:50]]
        return [item for item in sanitized_items if item is not None]
    if isinstance(value, Mapping):
        return {
            str(key)[:128]: sanitized
            for key, item in list(value.items())[:50]
            if (sanitized := _sanitize_value(item)) is not None
        }
    return str(value)[:500]


__all__ = [
    "build_function_calling_tools",
    "normalize_function_tool_calls",
]
