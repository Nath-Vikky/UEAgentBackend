from __future__ import annotations

from typing import Any, Literal

from app.agent.context_pack import context_pack_prompt_excerpt
from app.schemas.requests import UnifiedTaskRequest
from app.tools.registry import get_tool_spec


LLM_INTENT_DRAFTER_VERSION = "llm_intent_drafter_v2"
LLM_INTENT_MODES = {"disabled", "shadow", "active"}
ROUTE_TYPES = {"direct_answer", "project_qa", "single_tool", "workflow"}
TARGET_KINDS = {
    "none",
    "knowledge_base",
    "project_inventory",
    "project_file",
    "selected_context",
    "selected_asset",
    "asset",
    "selected_actor",
    "level_actor",
    "current_blueprint",
    "blueprint",
    "widget",
    "selected_material_instance",
    "material",
    "current_code_file",
    "current_log",
}


def build_llm_intent_draft_messages(
    *,
    request: UnifiedTaskRequest,
    routing: dict[str, Any],
    context_bundle: dict[str, Any],
    output_language: str,
) -> list[dict[str, str]]:
    deterministic_draft = dict(context_bundle.get("intent_draft") or {})
    route = dict(routing.get("route") or {})
    intent = dict(routing.get("intent") or {})
    context_pack = dict(context_bundle.get("context_pack") or {})
    active_targets = dict((context_bundle.get("agent_turn_context") or {}).get("active_targets") or {})

    system_prompt = (
        "You are an intent drafter for a local Unreal Engine editor Agent. "
        "Draft the user's intent as JSON only. "
        "You may suggest a route/tool, but confirmed editor writes must remain Proposal-only. "
        "Do not invent current-project facts. Prefer selected/current editor context only when the prompt refers to it. "
        "Allowed route_type values: direct_answer, project_qa, single_tool, workflow. "
        "Allowed target_kind values: "
        + ", ".join(sorted(TARGET_KINDS))
        + ". "
        f"Write rationale in {'Simplified Chinese' if output_language.startswith('zh') else 'English'}. "
        'Return JSON with keys: {"intent_type":"...","route_type":"...","target_kind":"...",'
        '"target_reference":"...","needs_project_context":false,"needs_live_editor_context":false,'
        '"needs_knowledge":false,"requested_write":false,"selected_tool_id":null,'
        '"candidate_tools":[],"confidence":0.0,"rationale":"..."}'
    )
    user_prompt = "\n\n".join(
        [
            f"Latest user query:\n{_latest_user_message(request) or '(empty)'}",
            f"Deterministic route:\n{_compact_json({'intent': intent, 'route': route})}",
            f"Deterministic intent draft:\n{_compact_json(deterministic_draft)}",
            f"Active targets:\n{_compact_json(active_targets)}",
            f"Compact context:\n{context_pack_prompt_excerpt(context_pack) if context_pack else '(none)'}",
        ]
    )
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]


def apply_llm_intent_draft(
    *,
    deterministic_draft: dict[str, Any],
    routing: dict[str, Any],
    llm_result: dict[str, Any] | None,
    mode: Literal["disabled", "shadow", "active"] | str,
    min_confidence: float,
    context_resolution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_mode = str(mode or "disabled").strip().lower()
    if normalized_mode not in LLM_INTENT_MODES:
        normalized_mode = "disabled"

    report_base = {
        "version": LLM_INTENT_DRAFTER_VERSION,
        "mode": normalized_mode,
        "status": "disabled" if normalized_mode == "disabled" else "skipped",
        "applied": False,
        "reason": "",
        "error": "",
        "min_confidence": min_confidence,
        "provider": None,
        "model": None,
        "profile_id": None,
        "llm_draft": {},
        "deterministic_draft": deterministic_draft,
        "routing_override": {},
        "draft_delta": {},
        "safety_checks": [],
    }
    if normalized_mode == "disabled":
        report_base["reason"] = "agent_intent_drafter_disabled"
        return {"routing": routing, "intent_draft": deterministic_draft, "report": report_base}

    if not isinstance(llm_result, dict):
        report_base.update({"reason": "llm_result_missing", "error": "No LLM result was provided."})
        return {"routing": routing, "intent_draft": deterministic_draft, "report": report_base}

    report_base.update(
        {
            "provider": llm_result.get("provider"),
            "model": llm_result.get("model"),
            "profile_id": llm_result.get("profile_id"),
        }
    )
    if not llm_result.get("ok"):
        report_base.update(
            {
                "reason": str(llm_result.get("reason") or "llm_intent_draft_failed"),
                "error": str(llm_result.get("error") or ""),
                "status": "skipped",
            }
        )
        return {"routing": routing, "intent_draft": deterministic_draft, "report": report_base}

    payload = llm_result.get("payload")
    normalized = normalize_llm_intent_payload(payload, deterministic_draft=deterministic_draft)
    report_base["llm_draft"] = normalized["draft"]
    report_base["routing_override"] = normalized["routing_override"]
    report_base["draft_delta"] = _draft_delta(deterministic_draft, normalized["draft"])
    if normalized["errors"]:
        report_base.update(
            {
                "status": "skipped",
                "reason": "llm_intent_draft_invalid",
                "error": "; ".join(normalized["errors"]),
            }
        )
        return {"routing": routing, "intent_draft": deterministic_draft, "report": report_base}

    safety_checks = _override_safety_checks(
        normalized=normalized,
        routing=routing,
        deterministic_draft=deterministic_draft,
        context_resolution=dict(context_resolution or {}),
    )
    report_base["safety_checks"] = safety_checks

    if normalized_mode == "shadow":
        report_base.update({"status": "shadow_completed", "reason": "shadow_mode_no_override"})
        return {"routing": routing, "intent_draft": deterministic_draft, "report": report_base}

    confidence = float(normalized["draft"].get("confidence") or 0.0)
    if confidence < min_confidence:
        report_base.update(
            {
                "status": "skipped",
                "reason": "confidence_below_threshold",
                "error": f"confidence={confidence:.3f} < min_confidence={min_confidence:.3f}",
            }
        )
        return {"routing": routing, "intent_draft": deterministic_draft, "report": report_base}

    block_reason = _active_override_block_reason(safety_checks)
    if block_reason:
        report_base.update({"status": "blocked", "reason": block_reason})
        return {"routing": routing, "intent_draft": deterministic_draft, "report": report_base}

    final_draft = {**deterministic_draft, **normalized["draft"]}
    final_draft["source"] = "llm_intent_drafter_active"
    final_routing = _apply_routing_override(routing, normalized["routing_override"], confidence=confidence)
    report_base.update({"status": "active_applied", "applied": True, "reason": "active_override_passed_quality_gate"})
    return {"routing": final_routing, "intent_draft": final_draft, "report": report_base}


def normalize_llm_intent_payload(payload: Any, *, deterministic_draft: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"draft": {}, "routing_override": {}, "errors": ["payload_must_be_object"]}

    errors: list[str] = []
    selected_tool_id = _clean_tool_id(payload.get("selected_tool_id") or payload.get("tool_id"))
    candidate_tools = _clean_candidate_tools(payload.get("candidate_tools"), selected_tool_id=selected_tool_id)
    route_type = str(payload.get("route_type") or "").strip()
    if route_type and route_type not in ROUTE_TYPES:
        errors.append(f"unsupported_route_type:{route_type}")
    target_kind = str(payload.get("target_kind") or deterministic_draft.get("target_kind") or "none").strip()
    if target_kind not in TARGET_KINDS:
        errors.append(f"unsupported_target_kind:{target_kind}")
    confidence = _clamp_float(payload.get("confidence"), default=float(deterministic_draft.get("confidence") or 0.0))

    if selected_tool_id and not get_tool_spec(selected_tool_id):
        errors.append(f"unknown_tool_id:{selected_tool_id}")

    draft = {
        "user_goal": str(deterministic_draft.get("user_goal") or ""),
        "intent_type": str(payload.get("intent_type") or deterministic_draft.get("intent_type") or "unknown"),
        "target_kind": target_kind,
        "target_reference": str(payload.get("target_reference") or deterministic_draft.get("target_reference") or ""),
        "needs_project_context": _bool(payload.get("needs_project_context"), deterministic_draft.get("needs_project_context")),
        "needs_live_editor_context": _bool(
            payload.get("needs_live_editor_context"),
            deterministic_draft.get("needs_live_editor_context"),
        ),
        "needs_knowledge": _bool(payload.get("needs_knowledge"), deterministic_draft.get("needs_knowledge")),
        "requested_write": _bool(payload.get("requested_write"), deterministic_draft.get("requested_write")),
        "candidate_tools": candidate_tools,
        "confidence": confidence,
        "rationale": str(payload.get("rationale") or deterministic_draft.get("rationale") or ""),
        "source": "llm_intent_drafter",
        "version": str(deterministic_draft.get("version") or "intent_draft_v1"),
    }
    if selected_tool_id and get_tool_spec(selected_tool_id) and selected_tool_id not in draft["candidate_tools"]:
        draft["candidate_tools"].insert(0, selected_tool_id)

    return {
        "draft": draft,
        "routing_override": {
            "route_type": route_type or None,
            "selected_tool_id": selected_tool_id,
            "candidate_tool_ids": draft["candidate_tools"],
        },
        "errors": errors,
    }


def _apply_routing_override(
    routing: dict[str, Any],
    override: dict[str, Any],
    *,
    confidence: float,
) -> dict[str, Any]:
    route_type = override.get("route_type")
    selected_tool_id = override.get("selected_tool_id")
    updated = {
        "locale": dict(routing.get("locale") or {}),
        "intent": dict(routing.get("intent") or {}),
        "route": dict(routing.get("route") or {}),
    }
    updated["route"]["llm_intent_drafter_override"] = {
        "route_type": route_type,
        "selected_tool_id": selected_tool_id,
        "confidence": confidence,
    }
    updated["route"]["decision_source"] = "llm_intent_drafter_active"
    updated["route"]["planner_confidence"] = max(float(updated["route"].get("planner_confidence") or 0.0), confidence)

    if route_type == "direct_answer":
        updated["intent"].update(
            {
                "intent_type": "casual_chat",
                "knowledge_relevance": "none",
                "requires_rag": False,
                "requires_tool": False,
                "route_type": "direct_answer",
                "reason": "LLM intent drafter selected direct answer; rule gate allowed the override.",
            }
        )
        updated["route"].update({"route_type": "direct_answer", "selected_tool_id": None, "candidate_tool_ids": []})
        return updated

    if route_type == "project_qa":
        updated["intent"].update(
            {
                "intent_type": "project_qa",
                "knowledge_relevance": "strong",
                "requires_rag": True,
                "requires_tool": bool(selected_tool_id),
                "route_type": "project_qa",
                "reason": "LLM intent drafter selected project QA; rule gate allowed the override.",
            }
        )
        updated["route"].update(
            {
                "route_type": "project_qa",
                "selected_tool_id": selected_tool_id,
                "candidate_tool_ids": override.get("candidate_tool_ids") or ([selected_tool_id] if selected_tool_id else []),
            }
        )
        return updated

    if route_type == "single_tool" and selected_tool_id:
        spec = get_tool_spec(selected_tool_id)
        updated["intent"].update(
            {
                "intent_type": "task_request",
                "knowledge_relevance": "possible",
                "requires_rag": False,
                "requires_tool": True,
                "route_type": "single_tool",
                "reason": "LLM intent drafter selected a tool; rule gate allowed the override.",
            }
        )
        updated["route"].update(
            {
                "route_type": "single_tool",
                "selected_tool_id": selected_tool_id,
                "candidate_tool_ids": override.get("candidate_tool_ids") or [selected_tool_id],
                "selected_tool_side_effect_level": spec.side_effect_level if spec else "unknown",
            }
        )
    return updated


def _override_safety_checks(
    *,
    normalized: dict[str, Any],
    routing: dict[str, Any],
    deterministic_draft: dict[str, Any],
    context_resolution: dict[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    _add_check(checks, "payload_valid", True, "normalized_payload_valid")

    missing_context = context_resolution.get("status") == "missing_active_context"
    _add_check(
        checks,
        "missing_context_gate",
        not missing_context,
        "missing_active_context_blocks_llm_override" if missing_context else "context_available_or_not_required",
    )

    override = dict(normalized.get("routing_override") or {})
    route_type = override.get("route_type")
    selected_tool_id = override.get("selected_tool_id")
    route_supported = route_type in {"direct_answer", "project_qa", "single_tool", None}
    _add_check(checks, "route_supported", route_supported, f"route_type={route_type}")

    single_tool_has_tool = route_type != "single_tool" or bool(selected_tool_id)
    _add_check(
        checks,
        "single_tool_has_tool",
        single_tool_has_tool,
        "single_tool_override_requires_selected_tool",
    )

    spec = get_tool_spec(selected_tool_id) if selected_tool_id else None
    tool_registered = not selected_tool_id or spec is not None
    _add_check(checks, "selected_tool_registered", tool_registered, f"selected_tool_id={selected_tool_id or 'none'}")

    existing_tool_id = str((routing.get("route") or {}).get("selected_tool_id") or "")
    existing_spec = get_tool_spec(existing_tool_id)
    deterministic_write = bool(deterministic_draft.get("requested_write"))
    existing_write = bool(existing_spec and existing_spec.side_effect_level not in {"read_only", "plan_only"})
    requested_write_safe = True
    if spec and spec.side_effect_level not in {"read_only", "plan_only"}:
        requested_write_safe = deterministic_write or existing_write
    _add_check(
        checks,
        "write_override_has_rule_signal",
        requested_write_safe,
        (
            "confirmed_write_override_requires_deterministic_write_signal"
            if not requested_write_safe
            else "write_override_has_deterministic_signal_or_not_write"
        ),
    )

    direct_answer_safe = True
    target_kind = str(deterministic_draft.get("target_kind") or "none")
    selected_or_current_target = target_kind.startswith(("selected_", "current_")) or target_kind in {
        "asset",
        "blueprint",
        "widget",
        "material",
        "level_actor",
    }
    if route_type == "direct_answer" and (deterministic_write or existing_write):
        direct_answer_safe = False
        reason = "write_intent_cannot_downgrade_to_direct_answer"
    elif route_type == "direct_answer" and selected_or_current_target and bool(deterministic_draft.get("needs_live_editor_context")):
        direct_answer_safe = False
        reason = "selected_context_cannot_downgrade_to_direct_answer"
    else:
        reason = "direct_answer_override_safe_or_not_requested"
    _add_check(checks, "direct_answer_downgrade_safe", direct_answer_safe, reason)
    return checks


def _active_override_block_reason(safety_checks: list[dict[str, Any]]) -> str:
    for check in safety_checks:
        if not bool(check.get("passed")):
            return str(check.get("reason") or check.get("check_id") or "llm_override_blocked")
    return ""


def _add_check(checks: list[dict[str, Any]], check_id: str, passed: bool, reason: str) -> None:
    checks.append({"check_id": check_id, "passed": bool(passed), "reason": reason})


def _draft_delta(deterministic_draft: dict[str, Any], llm_draft: dict[str, Any]) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    for key in (
        "intent_type",
        "target_kind",
        "target_reference",
        "needs_project_context",
        "needs_live_editor_context",
        "needs_knowledge",
        "requested_write",
        "candidate_tools",
    ):
        before = deterministic_draft.get(key)
        after = llm_draft.get(key)
        if before != after:
            changed[key] = {"deterministic": before, "llm": after}
    return {"changed_field_count": len(changed), "changed_fields": changed}


def _clean_tool_id(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _clean_candidate_tools(value: Any, *, selected_tool_id: str | None) -> list[str]:
    raw_items = value if isinstance(value, list) else []
    items: list[str] = []
    if selected_tool_id:
        raw_items = [selected_tool_id, *raw_items]
    for item in raw_items:
        tool_id = str(item or "").strip()
        if tool_id and get_tool_spec(tool_id) and tool_id not in items:
            items.append(tool_id)
    return items


def _bool(value: Any, fallback: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return bool(fallback)


def _clamp_float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0.0, min(parsed, 1.0))


def _latest_user_message(request: UnifiedTaskRequest) -> str:
    text = str(request.payload.get("user_query") or request.payload.get("requirement_description") or "").strip()
    if text:
        return text
    for message in reversed(request.session.messages):
        if message.role == "user" and message.content.strip():
            return message.content.strip()
    return ""


def _compact_json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, default=str)[:4000]


__all__ = [
    "LLM_INTENT_DRAFTER_VERSION",
    "apply_llm_intent_draft",
    "build_llm_intent_draft_messages",
    "normalize_llm_intent_payload",
]
