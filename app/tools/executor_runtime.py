from __future__ import annotations

import importlib
import time
from collections.abc import Callable
from typing import Any

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
