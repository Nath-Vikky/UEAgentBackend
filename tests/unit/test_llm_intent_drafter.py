from __future__ import annotations

from app.agent.llm_intent_drafter import apply_llm_intent_draft, normalize_llm_intent_payload


def _routing(tool_id: str | None = None, route_type: str = "direct_answer") -> dict:
    return {
        "locale": {"final_output_language": "en-US"},
        "intent": {
            "intent_type": "casual_chat",
            "route_type": route_type,
            "requires_rag": False,
            "requires_tool": bool(tool_id),
            "knowledge_relevance": "none",
            "reason": "test",
        },
        "route": {
            "route_type": route_type,
            "selected_tool_id": tool_id,
            "candidate_tool_ids": [tool_id] if tool_id else [],
            "planner_confidence": 0.55,
        },
    }


def _draft() -> dict:
    return {
        "user_goal": "Analyze this asset",
        "intent_type": "casual_chat",
        "target_kind": "selected_asset",
        "target_reference": "",
        "needs_project_context": True,
        "needs_live_editor_context": True,
        "needs_knowledge": False,
        "requested_write": False,
        "candidate_tools": [],
        "confidence": 0.55,
        "rationale": "test",
        "source": "deterministic_router_projection",
        "version": "intent_draft_v1",
    }


def test_normalize_llm_intent_payload_filters_unknown_tools() -> None:
    result = normalize_llm_intent_payload(
        {
            "route_type": "single_tool",
            "target_kind": "selected_asset",
            "selected_tool_id": "not_a_tool",
            "candidate_tools": ["mcp_get_asset_details"],
            "confidence": 0.9,
        },
        deterministic_draft=_draft(),
    )

    assert result["errors"] == ["unknown_tool_id:not_a_tool"]
    assert result["draft"]["candidate_tools"] == ["mcp_get_asset_details"]


def test_shadow_mode_records_llm_draft_without_overriding_route() -> None:
    outcome = apply_llm_intent_draft(
        deterministic_draft=_draft(),
        routing=_routing(),
        llm_result={
            "ok": True,
            "payload": {
                "route_type": "single_tool",
                "target_kind": "selected_asset",
                "selected_tool_id": "mcp_get_asset_details",
                "confidence": 0.96,
                "rationale": "Selected asset should be inspected.",
            },
            "provider": "test",
            "model": "fake",
            "profile_id": "default",
        },
        mode="shadow",
        min_confidence=0.78,
    )

    assert outcome["routing"]["intent"]["route_type"] == "direct_answer"
    assert outcome["intent_draft"]["source"] == "deterministic_router_projection"
    assert outcome["report"]["status"] == "shadow_completed"
    assert outcome["report"]["llm_draft"]["candidate_tools"] == ["mcp_get_asset_details"]


def test_active_mode_can_override_to_safe_readonly_tool() -> None:
    outcome = apply_llm_intent_draft(
        deterministic_draft=_draft(),
        routing=_routing(),
        llm_result={
            "ok": True,
            "payload": {
                "intent_type": "selected_context_question",
                "route_type": "single_tool",
                "target_kind": "selected_asset",
                "selected_tool_id": "mcp_get_asset_details",
                "needs_project_context": True,
                "needs_live_editor_context": True,
                "confidence": 0.96,
                "rationale": "The user refers to the selected asset.",
            },
            "provider": "test",
            "model": "fake",
            "profile_id": "default",
        },
        mode="active",
        min_confidence=0.78,
    )

    assert outcome["report"]["status"] == "active_applied"
    assert outcome["report"]["applied"] is True
    assert outcome["intent_draft"]["source"] == "llm_intent_drafter_active"
    assert outcome["routing"]["intent"]["route_type"] == "single_tool"
    assert outcome["routing"]["route"]["selected_tool_id"] == "mcp_get_asset_details"


def test_active_mode_blocks_new_confirmed_write_without_rule_write_signal() -> None:
    outcome = apply_llm_intent_draft(
        deterministic_draft=_draft(),
        routing=_routing(),
        llm_result={
            "ok": True,
            "payload": {
                "route_type": "single_tool",
                "target_kind": "selected_asset",
                "selected_tool_id": "editor_rename_asset",
                "requested_write": True,
                "confidence": 0.96,
            },
            "provider": "test",
            "model": "fake",
            "profile_id": "default",
        },
        mode="active",
        min_confidence=0.78,
    )

    assert outcome["report"]["status"] == "blocked"
    assert outcome["report"]["reason"] == "confirmed_write_override_requires_deterministic_write_signal"
    assert outcome["routing"]["route"]["selected_tool_id"] is None
