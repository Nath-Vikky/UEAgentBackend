from __future__ import annotations

from app.agent.context_route_refiner import refine_route_from_resolved_context


def test_context_route_refiner_selects_readonly_tool_for_resolved_asset() -> None:
    routing = {
        "locale": {"final_output_language": "zh-CN"},
        "intent": {"route_type": "single_tool", "intent_type": "asset_question"},
        "route": {"selected_tool_id": None, "candidate_tool_ids": []},
    }
    context_bundle = {
        "context_resolution": {
            "status": "resolved",
            "target_kind": "selected_asset",
            "target_id": "/Game/Props/SM_Rock.SM_Rock",
        }
    }

    refined, report = refine_route_from_resolved_context(
        routing=routing,
        context_bundle=context_bundle,
        free_chat=True,
    )

    assert report["status"] == "applied"
    assert refined["route"]["selected_tool_id"] == "mcp_get_asset_details"
    assert refined["intent"]["route_type"] == "single_tool"
    assert refined["intent"]["requires_tool"] is True


def test_context_route_refiner_keeps_existing_selected_tool() -> None:
    routing = {
        "locale": {"final_output_language": "en-US"},
        "intent": {"route_type": "proposal_wait", "intent_type": "write"},
        "route": {"selected_tool_id": "editor_rename_asset"},
    }
    context_bundle = {
        "context_resolution": {
            "status": "resolved",
            "target_kind": "selected_asset",
            "target_id": "/Game/Props/SM_Rock.SM_Rock",
        }
    }

    refined, report = refine_route_from_resolved_context(
        routing=routing,
        context_bundle=context_bundle,
        free_chat=True,
    )

    assert report["status"] == "skipped"
    assert report["reason"] == "selected_tool_already_present"
    assert refined is routing
