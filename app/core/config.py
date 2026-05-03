from __future__ import annotations

from app.skills.registry import (
    CORE_SKILL_IDS,
    CORE_TASK_TYPES,
    SKILL_CATALOG,
    SKILL_PROTOCOL_COMPONENTS,
    SKILL_PROTOCOL_VERSION,
    UI_RECOMMENDATIONS as SKILL_UI_RECOMMENDATIONS,
)
from app.tools.registry import tool_capability_cards, tool_protocol_summary

SUPPORTED_LANGUAGES = ["zh-CN", "en-US"]
SUPPORTED_VIEWS = ["user", "debug"]
UI_RECOMMENDATIONS = SKILL_UI_RECOMMENDATIONS

DEFERRED_TASK_TYPES = [
    "config_generate",
    "config_validate",
    "assets_plan",
    "assets_execute",
    "perf_analyze",
]

FEATURE_CATALOG = [
    *SKILL_CATALOG,
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
    "core_skill_ids": CORE_SKILL_IDS,
    "skill_catalog": SKILL_CATALOG,
    "skill_architecture": {
        "mode": "fixed_built_in_skills",
        "protocol_version": SKILL_PROTOCOL_VERSION,
        "protocol_components": SKILL_PROTOCOL_COMPONENTS,
        "runtime_lifecycle_field": "debug_view.skill.lifecycle",
        "runtime_dynamic_skills": False,
        "extension_policy": "Add collectors, rules, retrieval domains, and projectors inside an existing built-in skill before adding a new user-visible feature.",
        "public_skill_count": len(CORE_SKILL_IDS),
    },
    "tool_registry": {
        "mode": "declarative_static_registry",
        "protocol_version": tool_protocol_summary()["protocol_version"],
        "protocol": tool_protocol_summary(),
        "runtime_hot_reload": False,
        "extension_policy": "Add or adjust tool capability cards in app/tools/registry.py; router and capabilities consume the same registry.",
        "tools": tool_capability_cards(),
    },
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
        "sse_token_stream_optional",
        "prometheus_metrics",
        "audit_logs",
        "alerts_snapshot",
    ],
    "approval_policies": ["read_only", "plan_only", "confirmed_write"],
    "proposal_states": ["pending", "confirmed", "rejected"],
    "run_controls": ["cancel", "agent_chat_sse_stream_optional"],
}
