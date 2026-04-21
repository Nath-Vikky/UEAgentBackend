from __future__ import annotations

SUPPORTED_LANGUAGES = ["zh-CN", "en-US"]
SUPPORTED_VIEWS = ["user", "debug"]

CORE_TASK_TYPES = [
    "agent_chat",
    "project_qa",
    "code_review",
    "code_generate",
    "logs_analyze",
    "assets_inspect",
]

DEFERRED_TASK_TYPES = [
    "config_generate",
    "config_validate",
    "assets_plan",
    "assets_execute",
    "perf_analyze",
]

FEATURE_CATALOG = [
    {
        "task_type": "agent_chat",
        "title": "Agent Chat / Project QA",
        "status": "core",
        "entry_mode": "chat",
        "panel_id": "AgentChat",
        "frontend_ui": "chat_timeline",
        "notes": "The backend decides whether to stay in direct chat or promote the request to retrieval-backed project QA.",
    },
    {
        "task_type": "code_review",
        "title": "Code Review",
        "status": "core",
        "entry_mode": "explicit_task",
        "panel_id": "CodeReview",
        "frontend_ui": "file_picker",
        "notes": "Use the dedicated file list endpoint and submit a selected file for single-file review.",
    },
    {
        "task_type": "code_generate",
        "title": "Code Generation",
        "status": "core",
        "entry_mode": "explicit_task",
        "panel_id": "CodeGenerator",
        "frontend_ui": "prompt_plus_code_results",
        "notes": "Show the user prompt in the timeline, but render generated code as result buttons or tabs instead of one long chat block.",
    },
    {
        "task_type": "logs_analyze",
        "title": "Log Analysis",
        "status": "core",
        "entry_mode": "explicit_task",
        "panel_id": "LogAnalyzer",
        "frontend_ui": "log_preview_plus_result",
        "notes": "The plugin should collect or preview logs locally and send log_text to the backend for analysis.",
    },
    {
        "task_type": "assets_inspect",
        "title": "Asset Inspection",
        "status": "core",
        "entry_mode": "explicit_task",
        "panel_id": "AssetInspector",
        "frontend_ui": "selected_assets_plus_groups",
        "notes": "The plugin must send selected asset metadata from the editor; the backend does not inspect raw .uasset files directly.",
    },
    {
        "task_type": "config_generate",
        "title": "Config Generation",
        "status": "deferred",
        "entry_mode": "hidden",
        "panel_id": "ConfigGenerator",
        "frontend_ui": "hidden",
        "notes": "Kept in the backend for compatibility, but no longer part of the main plugin scope.",
    },
    {
        "task_type": "config_validate",
        "title": "Config Validation",
        "status": "deferred",
        "entry_mode": "hidden",
        "panel_id": "ConfigValidator",
        "frontend_ui": "hidden",
        "notes": "Kept in the backend for compatibility, but no longer part of the main plugin scope.",
    },
    {
        "task_type": "assets_plan",
        "title": "Asset Planning",
        "status": "deferred",
        "entry_mode": "hidden",
        "panel_id": "AssetPlanner",
        "frontend_ui": "hidden",
        "notes": "Deferred for the narrowed portfolio scope.",
    },
    {
        "task_type": "assets_execute",
        "title": "Asset Execution",
        "status": "deferred",
        "entry_mode": "hidden",
        "panel_id": "AssetExecutor",
        "frontend_ui": "hidden",
        "notes": "Deferred for the narrowed portfolio scope.",
    },
    {
        "task_type": "perf_analyze",
        "title": "Performance Analysis",
        "status": "deferred",
        "entry_mode": "hidden",
        "panel_id": "PerfAnalysis",
        "frontend_ui": "hidden",
        "notes": "Deferred for the narrowed portfolio scope.",
    },
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
    "supported_task_types": CORE_TASK_TYPES,
    "deferred_task_types": DEFERRED_TASK_TYPES,
    "feature_catalog": FEATURE_CATALOG,
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
    "core_panels": [
        {"panel_id": "AgentChat", "task_type": "agent_chat", "ui_mode": "chat_timeline"},
        {"panel_id": "CodeReview", "task_type": "code_review", "ui_mode": "file_picker"},
        {"panel_id": "CodeGenerator", "task_type": "code_generate", "ui_mode": "prompt_plus_code_results"},
        {"panel_id": "LogAnalyzer", "task_type": "logs_analyze", "ui_mode": "log_preview_plus_result"},
        {"panel_id": "AssetInspector", "task_type": "assets_inspect", "ui_mode": "selected_assets_plus_groups"},
    ],
    "notes": [
        "User View should render `user_view` or `presentation` instead of inferring content from raw data.",
        "Debug View should show route, usage, trace summary, retrieval details, task events, proposals, and raw structured results.",
        "The narrowed scope keeps only five core plugin panels. Deferred backend tasks should be hidden from the main frontend menu.",
        "Do not force every feature into the same chat UI. Only Agent Chat / Project QA should use a full chat timeline.",
    ],
}
