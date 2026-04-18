from __future__ import annotations

SUPPORTED_LANGUAGES = ["zh-CN", "en-US"]
SUPPORTED_VIEWS = ["user", "debug"]
SUPPORTED_TASK_TYPES = [
    "agent_chat",
    "project_qa",
    "code_review",
    "code_generate",
    "logs_analyze",
    "config_generate",
    "config_validate",
    "assets_inspect",
    "assets_plan",
    "assets_execute",
    "perf_analyze",
]

CAPABILITIES = {
    "routing_modes": [
        "direct_answer",
        "project_qa",
        "single_tool",
        "workflow",
        "proposal_wait",
        "fallback",
    ],
    "supported_task_types": SUPPORTED_TASK_TYPES,
    "supported_languages": SUPPORTED_LANGUAGES,
    "supported_views": SUPPORTED_VIEWS,
    "observability": [
        "json_debug_snapshot",
        "task_history",
        "runtime_profiles",
        "trace_summary",
        "task_events",
        "artifacts",
        "sse_event_replay",
        "prometheus_metrics",
        "audit_logs",
        "alerts_snapshot",
    ],
    "approval_policies": ["read_only", "plan_only", "confirmed_write"],
    "proposal_states": ["pending", "confirmed", "rejected"],
    "run_controls": ["cancel"],
}

UI_RECOMMENDATIONS = {
    "initial_endpoints": [
        "/api/v1/system/health",
        "/api/v1/system/bootstrap",
        "/api/v1/system/capabilities",
        "/api/v1/system/runtime-profiles",
    ],
    "preferred_user_view_source": "user_view",
    "preferred_debug_view_source": "debug_view",
    "notes": [
        "User View should render `user_view` or `presentation` instead of inferring content from raw data.",
        "Debug View should show route, usage, trace summary, retrieval details, task events, proposals, and raw structured results.",
    ],
}
