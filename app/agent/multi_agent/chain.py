from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, TypeVar

from app.agent.multi_agent.schemas import AgentNodeResult

T = TypeVar("T")


def run_timed_node(
    *,
    node_id: str,
    role: str,
    input_summary: str,
    runner: Callable[[], T],
    output_summary: Callable[[T], str],
    data_summary: Callable[[T], dict[str, Any]] | None = None,
    warnings: Callable[[T], list[str]] | None = None,
) -> tuple[T, AgentNodeResult]:
    started = time.perf_counter()
    result = runner()
    latency_ms = int((time.perf_counter() - started) * 1000)
    node_result = AgentNodeResult(
        node_id=node_id,
        role=role,
        status="completed",
        input_summary=input_summary,
        output_summary=output_summary(result),
        data=data_summary(result) if data_summary else {},
        warnings=warnings(result) if warnings else [],
        latency_ms=latency_ms,
    )
    return result, node_result
