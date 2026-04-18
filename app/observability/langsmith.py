from __future__ import annotations

from app.core.settings import Settings


def build_trace_summary(
    trace_id: str,
    route_type: str,
    status: str,
    *,
    finish_reason: str,
    settings: Settings,
) -> dict[str, object]:
    provider = "langsmith_stub" if settings.langsmith_tracing else "local_trace"
    return {
        "trace_id": trace_id,
        "route_type": route_type,
        "final_status": status,
        "finish_reason": finish_reason,
        "provider": provider,
        "langsmith_enabled": settings.langsmith_tracing,
        "langsmith_project": settings.langsmith_project if settings.langsmith_tracing else "",
    }
