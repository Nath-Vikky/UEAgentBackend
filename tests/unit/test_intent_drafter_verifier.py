from __future__ import annotations

from app.agent.intent_drafter import build_intent_draft
from app.agent.intent_verifier import verify_intent
from app.schemas.requests import UnifiedTaskRequest


def _request(content: str, *, selected_assets: list[str] | None = None) -> UnifiedTaskRequest:
    return UnifiedTaskRequest(
        task_type="agent_chat",
        session={"session_id": "intent_test", "messages": [{"role": "user", "content": content}]},
        context={
            "project_name": "DemoProject",
            "active_panel": "AgentChat",
            "selected_assets": selected_assets or [],
        },
        payload={"user_query": content},
    )


def _routing(
    tool_id: str = "query_project_inventory",
    route_type: str = "project_qa",
    *,
    selected_context_query: bool = True,
) -> dict:
    return {
        "locale": {"final_output_language": "en-US"},
        "intent": {
            "intent_type": "project_qa" if route_type == "project_qa" else "task_request",
            "route_type": route_type,
            "requires_rag": tool_id == "retrieve_project_knowledge",
            "requires_tool": bool(tool_id),
            "reason": "unit test route",
        },
        "route": {
            "route_type": route_type,
            "route_reason": "unit test route",
            "selected_tool_id": tool_id,
            "candidate_tool_ids": [tool_id],
            "planner_confidence": 0.91,
            "selected_context_query": selected_context_query,
        },
    }


def test_intent_draft_resolves_selected_asset_from_turn_context() -> None:
    request = _request("\u5206\u6790\u4e00\u4e0b\u8fd9\u4e2a\u8d44\u4ea7", selected_assets=["/Game/Props/SM_Rock.SM_Rock"])
    routing = _routing()
    bundle = {
        "agent_turn_context": {
            "active_targets": {
                "asset": {"available": True, "selected_assets": ["/Game/Props/SM_Rock.SM_Rock"]},
                "blueprint": {"available": False},
                "level_actor": {"available": False},
                "material": {"available": False},
                "code": {"available": False},
                "log": {"available": False},
            }
        }
    }

    draft = build_intent_draft(request=request, routing=routing, context_bundle=bundle)
    verified = verify_intent(draft=draft, routing=routing, context_bundle=bundle, free_chat=True)

    assert draft["version"] == "intent_draft_v1"
    assert draft["target_kind"] == "selected_asset"
    assert draft["target_reference"] == "/Game/Props/SM_Rock.SM_Rock"
    assert draft["needs_project_context"] is True
    assert draft["needs_live_editor_context"] is True
    assert verified["version"] == "verified_intent_v1"
    assert verified["target_resolution_status"] == "resolved"
    assert verified["permission_decision"]["status"] == "allow"


def test_intent_verifier_maps_write_tool_to_proposal() -> None:
    request = _request("Rename this asset to SM_Rock_A")
    routing = _routing(tool_id="editor_rename_asset", route_type="single_tool")
    bundle = {
        "agent_turn_context": {
            "active_targets": {
                "asset": {"available": True, "selected_assets": ["/Game/Props/SM_Rock.SM_Rock"]},
                "blueprint": {"available": False},
                "level_actor": {"available": False},
                "material": {"available": False},
                "code": {"available": False},
                "log": {"available": False},
            }
        }
    }

    draft = build_intent_draft(request=request, routing=routing, context_bundle=bundle)
    verified = verify_intent(draft=draft, routing=routing, context_bundle=bundle)

    assert draft["requested_write"] is True
    assert verified["route_type"] == "proposal_wait"
    assert verified["permission_decision"]["status"] == "proposal"
    assert "requires_user_confirmation" in verified["safety_flags"]
    assert verified["corrections"][0]["correction_id"] == "write_tool_requires_proposal"


def test_intent_verifier_flags_missing_selected_context() -> None:
    request = _request("Analyze this asset")
    routing = _routing()
    bundle = {
        "agent_turn_context": {
            "active_targets": {
                "asset": {"available": False, "selected_assets": []},
                "blueprint": {"available": False},
                "level_actor": {"available": False},
                "material": {"available": False},
                "code": {"available": False},
                "log": {"available": False},
            }
        }
    }

    draft = build_intent_draft(request=request, routing=routing, context_bundle=bundle)
    verified = verify_intent(draft=draft, routing=routing, context_bundle=bundle, free_chat=True)

    assert draft["target_kind"] == "selected_asset"
    assert verified["target_resolution_status"] == "missing_active_context"
    assert "missing_active_context" in verified["safety_flags"]
    assert verified["corrections"][0]["correction_id"] == "selected_context_needs_active_target"


def test_inventory_scope_current_project_does_not_require_selected_asset() -> None:
    request = _request("List the assets in my current project.")
    routing = _routing(tool_id="query_project_inventory", route_type="project_qa", selected_context_query=False)
    bundle = {
        "agent_turn_context": {
            "active_targets": {
                "asset": {"available": False, "selected_assets": []},
                "blueprint": {"available": False},
                "level_actor": {"available": False},
                "material": {"available": False},
                "code": {"available": False},
                "log": {"available": False},
            }
        }
    }

    draft = build_intent_draft(request=request, routing=routing, context_bundle=bundle)
    verified = verify_intent(draft=draft, routing=routing, context_bundle=bundle, free_chat=True)

    assert draft["target_kind"] == "project_inventory"
    assert draft["needs_live_editor_context"] is False
    assert verified["target_resolution_status"] == "not_required"


def test_level_actor_list_does_not_require_selected_actor() -> None:
    request = _request("List enemy actors in the current level.")
    routing = _routing(tool_id="mcp_get_level_actors", route_type="single_tool", selected_context_query=False)
    bundle = {
        "agent_turn_context": {
            "active_targets": {
                "asset": {"available": False},
                "blueprint": {"available": False},
                "level_actor": {"available": False},
                "material": {"available": False},
                "code": {"available": False},
                "log": {"available": False},
            }
        }
    }

    draft = build_intent_draft(request=request, routing=routing, context_bundle=bundle)
    verified = verify_intent(draft=draft, routing=routing, context_bundle=bundle, free_chat=True)

    assert draft["target_kind"] == "project_inventory"
    assert verified["target_resolution_status"] == "not_required"


def test_place_actor_request_does_not_require_existing_selected_actor() -> None:
    request = _request("Place BP_EnemySpawner in the current level.")
    routing = _routing(tool_id="editor_place_actor_in_level", route_type="single_tool", selected_context_query=False)
    bundle = {
        "agent_turn_context": {
            "active_targets": {
                "asset": {"available": False},
                "blueprint": {"available": False},
                "level_actor": {"available": False},
                "material": {"available": False},
                "code": {"available": False},
                "log": {"available": False},
            }
        }
    }

    draft = build_intent_draft(request=request, routing=routing, context_bundle=bundle)
    verified = verify_intent(draft=draft, routing=routing, context_bundle=bundle)

    assert draft["target_kind"] == "project_inventory"
    assert draft["requested_write"] is True
    assert verified["target_resolution_status"] == "not_required"
    assert verified["route_type"] == "proposal_wait"
