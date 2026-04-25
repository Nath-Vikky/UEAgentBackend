from __future__ import annotations

from typing import Any

from app.skills.registry import SKILL_PROTOCOL_VERSION, get_skill_by_task_type


def _llm_lifecycle(data: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(data or {})
    llm_analysis = payload.get("llm_analysis")
    if isinstance(llm_analysis, dict):
        return {
            "status": llm_analysis.get("status") or "unknown",
            "reason": llm_analysis.get("reason_code") or llm_analysis.get("reason"),
            "model": llm_analysis.get("model"),
            "profile_id": llm_analysis.get("profile_id"),
        }
    llm_review = payload.get("llm_review")
    if isinstance(llm_review, dict):
        return {
            "status": "completed" if llm_review.get("ok") else "skipped",
            "reason": llm_review.get("reason"),
            "model": llm_review.get("model"),
            "profile_id": llm_review.get("profile_id"),
        }
    answer_generation = payload.get("answer_generation")
    if isinstance(answer_generation, dict):
        mode = str(answer_generation.get("mode") or "")
        return {
            "status": "completed" if "llm" in mode or "live" in mode else "skipped",
            "reason": mode,
            "model": answer_generation.get("model"),
            "profile_id": answer_generation.get("profile_id"),
        }
    generation_mode = str(payload.get("generation_mode") or "")
    if generation_mode:
        return {
            "status": "completed" if "llm" in generation_mode or "live" in generation_mode else "skipped",
            "reason": generation_mode,
            "model": None,
            "profile_id": None,
        }
    return {"status": "not_reported", "reason": "skill_did_not_report_llm_status"}


def build_skill_runtime_descriptor(
    *,
    requested_task_type: str,
    actual_task_type: str,
    routing: dict[str, Any],
    retrieval_trace: dict[str, Any],
    execution_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    skill = get_skill_by_task_type(actual_task_type)
    route = routing.get("route") or {}
    intent = routing.get("intent") or {}
    retrieval_mode = str(retrieval_trace.get("mode") or "not_used")
    retrieval_active = bool(intent.get("requires_rag")) or retrieval_mode != "not_used"

    if not skill:
        return {
            "protocol_version": SKILL_PROTOCOL_VERSION,
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
        "protocol_version": SKILL_PROTOCOL_VERSION,
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
        "lifecycle": {
            "collector": {
                "status": "completed",
                "name": skill.collector,
            },
            "rules": {
                "status": "completed" if skill.rules else "not_configured",
                "items": skill.rules,
            },
            "retrieval": {
                "status": "completed" if retrieval_active else "skipped",
                "mode": retrieval_mode,
                "domains": skill.retrieval_domains,
            },
            "llm": _llm_lifecycle(execution_data),
            "projector": {
                "status": "completed",
                "outputs": skill.projector_outputs,
            },
        },
    }
