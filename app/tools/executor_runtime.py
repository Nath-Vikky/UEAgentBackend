from __future__ import annotations

import importlib
import time
from collections.abc import Callable
from typing import Any

from app.tools.contracts import validate_tool_call_input
from app.tools.context import ToolContext, ToolResult
from app.tools.registry import get_tool_spec

ToolExecutor = Callable[[ToolContext], ToolResult | dict[str, Any]]


def execute_tool_with_context(context: ToolContext) -> ToolResult:
    """Execute a ToolSpec executor through the normalized ToolContext contract."""

    started = time.perf_counter()
    spec = get_tool_spec(context.tool_id)
    if not spec or not spec.executor:
        return ToolResult.failed(
            tool_id=context.tool_id,
            error_code="executor_not_configured",
            error_message=f"Tool `{context.tool_id}` does not define a local executor.",
            latency_ms=_elapsed_ms(started),
        )
    preflight = validate_tool_call_input(context.tool_id, context.payload)
    if not preflight.get("ok"):
        return ToolResult(
            tool_id=context.tool_id,
            status="blocked",
            output={},
            summary="Tool input preflight failed before executor dispatch.",
            latency_ms=_elapsed_ms(started),
            error_code="tool_preflight_failed",
            error_message=_preflight_error_message(preflight),
            metadata={
                "preflight": preflight,
                "side_effect_level": spec.side_effect_level,
                "requires_confirmation": spec.effective_requires_confirmation,
            },
        )
    try:
        raw_result = _load_executor(spec.executor)(context)
    except Exception as exc:  # pragma: no cover - defensive tool isolation
        return ToolResult.failed(
            tool_id=context.tool_id,
            error_code=type(exc).__name__,
            error_message=str(exc),
            latency_ms=_elapsed_ms(started),
        )

    result = (
        raw_result
        if isinstance(raw_result, ToolResult)
        else ToolResult.completed(tool_id=context.tool_id, output=dict(raw_result or {}))
    )
    if result.latency_ms is None:
        result.latency_ms = _elapsed_ms(started)
    result.metadata = {
        **dict(result.metadata or {}),
        "preflight": preflight,
        "side_effect_level": spec.side_effect_level,
        "requires_confirmation": spec.effective_requires_confirmation,
    }
    return result


def _load_executor(path: str) -> ToolExecutor:
    module_name, _, attr_name = path.partition(":")
    if not module_name or not attr_name:
        raise ValueError(f"Invalid executor path: {path}")
    module = importlib.import_module(module_name)
    executor = getattr(module, attr_name)
    if not callable(executor):
        raise TypeError(f"Executor is not callable: {path}")
    return executor


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _preflight_error_message(preflight: dict[str, Any]) -> str:
    parts: list[str] = []
    if preflight.get("missing_fields"):
        parts.append(f"missing={', '.join(preflight['missing_fields'])}")
    if preflight.get("type_errors"):
        parts.append(f"type_errors={len(preflight['type_errors'])}")
    if preflight.get("enum_errors"):
        parts.append(f"enum_errors={len(preflight['enum_errors'])}")
    if preflight.get("unknown_fields_blocking") and preflight.get("unknown_fields"):
        parts.append(f"unknown={', '.join(preflight['unknown_fields'])}")
    return "; ".join(parts) or "invalid_tool_input"
