from __future__ import annotations

from typing import Any

from app.skills.registry import get_skill_by_task_type


def build_skill_runtime_descriptor(
    *,
    requested_task_type: str,
    actual_task_type: str,
    routing: dict[str, Any],
    retrieval_trace: dict[str, Any],
) -> dict[str, Any]:
    skill = get_skill_by_task_type(actual_task_type)
    route = routing.get("route") or {}
    intent = routing.get("intent") or {}
    retrieval_mode = str(retrieval_trace.get("mode") or "not_used")
    retrieval_active = bool(intent.get("requires_rag")) or retrieval_mode != "not_used"

    if not skill:
        return {
            "skill_id": None,
            "task_type": actual_task_type,
            "requested_task_type": requested_task_type,
            "status": "deferred_or_legacy",
            "route_type": intent.get("route_type"),
            "selected_tool_id": route.get("selected_tool_id"),
            "retrieval_active": retrieval_active,
            "retrieval_mode": retrieval_mode,
            "notes": "This task is retained for compatibility and is not part of the fixed core skill catalog.",
        }

    return {
        "skill_id": skill.skill_id,
        "task_type": skill.task_type,
        "requested_task_type": requested_task_type,
        "actual_task_type": actual_task_type,
        "title": skill.title,
        "panel_id": skill.panel_id,
        "frontend_ui": skill.frontend_ui,
        "route_type": intent.get("route_type"),
        "route_preference": skill.route_preference,
        "selected_tool_id": route.get("selected_tool_id") or skill.primary_tool_id,
        "side_effect_level": skill.side_effect_level,
        "collector": skill.collector,
        "rules": skill.rules,
        "retrieval_domains": skill.retrieval_domains,
        "retrieval_active": retrieval_active,
        "retrieval_mode": retrieval_mode,
        "projector_outputs": skill.projector_outputs,
    }
