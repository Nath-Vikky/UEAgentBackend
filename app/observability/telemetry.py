from __future__ import annotations

from typing import Any


def service_health_snapshot() -> dict[str, Any]:
    return {
        "tracing": "langsmith_stubbed",
        "metrics": "prometheus_text",
        "metrics_endpoint": "/metrics",
        "otel": "local_stub",
        "audit": "enabled",
    }
