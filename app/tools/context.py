from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.schemas.requests import UnifiedTaskRequest
from app.tools.registry import ToolSpec


TOOL_RESULT_PROTOCOL_VERSION = "tool_result_v1"
TOOL_STATUSES = {"completed", "skipped", "blocked", "degraded", "failed"}


@dataclass(slots=True)
class ToolContext:
    """Normalized execution context for future tool executors.

    Current handlers and skill executors can keep their existing paths. This
    context object is the compatibility contract for newly migrated tools.
    """

    tool_id: str
    task_id: str | None = None
    run_id: str | None = None
    trace_id: str | None = None
    user_query: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    active_context: dict[str, Any] = field(default_factory=dict)
    runtime_options: dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 30_000
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_request(
        cls,
        *,
        spec: ToolSpec,
        request: UnifiedTaskRequest,
        task_id: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolContext:
        user_query = str(
            request.payload.get("user_query")
            or request.payload.get("requirement_description")
            or (request.session.messages[-1].content if request.session.messages else "")
            or ""
        )
        return cls(
            tool_id=spec.tool_id,
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            user_query=user_query,
            payload=dict(request.payload or {}),
            active_context=request.context.model_dump(mode="json"),
            runtime_options=request.runtime_options.model_dump(mode="json"),
            timeout_ms=spec.timeout_ms,
            metadata=dict(metadata or {}),
        )

    def input_summary(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "has_user_query": bool(self.user_query),
            "payload_keys": sorted(self.payload.keys()),
            "active_context_keys": sorted(key for key, value in self.active_context.items() if value),
            "timeout_ms": self.timeout_ms,
        }


@dataclass(slots=True)
class ToolResult:
    """Normalized tool result for debug traces and future executors."""

    tool_id: str
    status: str
    output: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    latency_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    warnings: list[str] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    approval_state: str = "not_required"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in TOOL_STATUSES:
            raise ValueError(f"Unsupported tool result status: {self.status}")

    @property
    def ok(self) -> bool:
        return self.status == "completed"

    @classmethod
    def completed(
        cls,
        *,
        tool_id: str,
        output: dict[str, Any],
        summary: str = "",
        latency_ms: int | None = None,
    ) -> ToolResult:
        return cls(
            tool_id=tool_id,
            status="completed",
            output=output,
            summary=summary,
            latency_ms=latency_ms,
        )

    @classmethod
    def failed(
        cls,
        *,
        tool_id: str,
        error_code: str,
        error_message: str,
        latency_ms: int | None = None,
    ) -> ToolResult:
        return cls(
            tool_id=tool_id,
            status="failed",
            output={},
            summary=error_message,
            latency_ms=latency_ms,
            error_code=error_code,
            error_message=error_message,
        )

    def output_summary(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "output_keys": sorted(self.output.keys()),
            "warning_count": len(self.warnings),
            "citation_count": len(self.citations),
            "artifact_count": len(self.artifacts),
            "error_code": self.error_code,
        }

    def to_debug_entry(self, *, context: ToolContext | None = None) -> dict[str, Any]:
        return {
            "protocol_version": TOOL_RESULT_PROTOCOL_VERSION,
            "tool_id": self.tool_id,
            "status": self.status,
            "input_summary": context.input_summary() if context else {},
            "output_summary": self.output_summary(),
            "latency_ms": self.latency_ms,
            "approval_state": self.approval_state,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }

    def model_dump(self) -> dict[str, Any]:
        return {
            "protocol_version": TOOL_RESULT_PROTOCOL_VERSION,
            "tool_id": self.tool_id,
            "status": self.status,
            "ok": self.ok,
            "output": self.output,
            "summary": self.summary,
            "latency_ms": self.latency_ms,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "warnings": self.warnings,
            "citations": self.citations,
            "artifacts": self.artifacts,
            "approval_state": self.approval_state,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class CompositeToolResult:
    """Container for multi-tool workflows while preserving individual traces."""

    tool_id: str
    results: list[ToolResult] = field(default_factory=list)
    summary: str = ""

    @property
    def ok(self) -> bool:
        return all(result.ok for result in self.results)

    def to_debug_entries(self, contexts: dict[str, ToolContext] | None = None) -> list[dict[str, Any]]:
        context_map = contexts or {}
        return [
            result.to_debug_entry(context=context_map.get(result.tool_id))
            for result in self.results
        ]

    def model_dump(self) -> dict[str, Any]:
        return {
            "protocol_version": TOOL_RESULT_PROTOCOL_VERSION,
            "tool_id": self.tool_id,
            "ok": self.ok,
            "summary": self.summary,
            "results": [result.model_dump() for result in self.results],
        }
