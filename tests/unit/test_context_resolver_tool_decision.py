from __future__ import annotations

from app.agent.context_resolver import resolve_context
from app.agent.intent_drafter import build_intent_draft
from app.agent.intent_verifier import verify_intent
from app.agent.tool_decision import build_tool_plan
from app.schemas.requests import UnifiedTaskRequest


def _request(content: str, *, selected_assets: list[str] | None = None) -> UnifiedTaskRequest:
    return UnifiedTaskRequest(
        task_type="agent_chat",
        session={"session_id": "context_resolver_test", "messages": [{"role": "user", "content": content}]},
        context={
            "project_name": "DemoProject",
            "active_panel": "AgentChat",
            "selected_assets": selected_assets or [],
        },
        payload={"user_query": content},
    )


def _routing(tool_id: str = "query_project_inventory", route_type: str = "project_qa") -> dict:
    return {
        "locale": {"final_output_language": "zh-CN"},
        "intent": {
            "intent_type": "project_qa",
            "route_type": route_type,
            "requires_rag": False,
            "requires_tool": bool(tool_id),
            "reason": "unit test route",
        },
        "route": {
            "route_type": route_type,
            "route_reason": "unit test route",
            "selected_tool_id": tool_id,
            "candidate_tool_ids": [tool_id],
            "planner_confidence": 0.88,
            "selected_context_query": True,
        },
    }


def _active_targets(*, selected_assets: list[str] | None = None) -> dict:
    return {
        "asset": {"available": bool(selected_assets), "selected_assets": selected_assets or []},
        "blueprint": {"available": False},
        "level_actor": {"available": False},
        "material": {"available": False},
        "code": {"available": False},
        "log": {"available": False},
    }


def test_context_resolver_prefers_inventory_selected_asset_details() -> None:
    request = _request("\u5206\u6790\u4e00\u4e0b\u8fd9\u4e2a\u8d44\u4ea7", selected_assets=["/Game/Props/SM_Rock.SM_Rock"])
    routing = _routing()
    bundle = {
        "agent_turn_context": {"active_targets": _active_targets(selected_assets=["/Game/Props/SM_Rock.SM_Rock"])},
        "project_inventory_context": {
            "selected_assets": [
                {
                    "asset_name": "SM_Rock",
                    "asset_path": "/Game/Props/SM_Rock.SM_Rock",
                    "asset_type": "StaticMesh",
                    "static_mesh": {"nanite_enabled": True},
                }
            ]
        },
    }
    draft = build_intent_draft(request=request, routing=routing, context_bundle=bundle)

    resolved = resolve_context(request=request, routing=routing, context_bundle=bundle, intent_draft=draft)

    assert resolved["version"] == "resolved_context_v1"
    assert resolved["status"] == "resolved"
    assert resolved["source"] == "project_inventory_selected_asset"
    assert resolved["target_id"] == "/Game/Props/SM_Rock.SM_Rock"
    assert resolved["available_fields"]["asset_type"] == "StaticMesh"


def test_context_resolver_reports_missing_selected_asset() -> None:
    request = _request("Analyze this asset")
    routing = _routing()
    bundle = {"agent_turn_context": {"active_targets": _active_targets()}}
    draft = build_intent_draft(request=request, routing=routing, context_bundle=bundle)

    resolved = resolve_context(request=request, routing=routing, context_bundle=bundle, intent_draft=draft)
    verified = verify_intent(draft=draft, routing=routing, context_bundle=bundle, free_chat=True)
    plan = build_tool_plan(
        intent_draft=draft,
        verified_intent=verified,
        context_resolution=resolved,
        routing=routing,
    )

    assert resolved["status"] == "missing_active_context"
    assert plan["mode"] == "ask_for_context"


def test_tool_plan_maps_write_tool_to_proposal() -> None:
    request = _request("Rename this asset to SM_Rock_A", selected_assets=["/Game/Props/SM_Rock.SM_Rock"])
    routing = _routing(tool_id="editor_rename_asset", route_type="single_tool")
    bundle = {"agent_turn_context": {"active_targets": _active_targets(selected_assets=["/Game/Props/SM_Rock.SM_Rock"])}}
    draft = build_intent_draft(request=request, routing=routing, context_bundle=bundle)
    resolved = resolve_context(request=request, routing=routing, context_bundle=bundle, intent_draft=draft)
    verified = verify_intent(draft=draft, routing=routing, context_bundle=bundle)

    plan = build_tool_plan(
        intent_draft=draft,
        verified_intent=verified,
        context_resolution=resolved,
        routing=routing,
    )

    assert plan["version"] == "tool_plan_v1"
    assert plan["mode"] == "proposal"
    assert plan["requires_proposal"] is True
    assert plan["arguments"]["asset_path"] == "/Game/Props/SM_Rock.SM_Rock"


def test_tool_plan_builds_blueprint_argument_draft() -> None:
    request = _request("What nodes does this Blueprint have?")
    routing = _routing(tool_id="mcp_get_blueprint_graph", route_type="single_tool")
    bundle = {
        "agent_turn_context": {
            "active_targets": {
                **_active_targets(),
                "blueprint": {
                    "available": True,
                    "current_blueprint_path": "/Game/BP_Player.BP_Player",
                    "current_graph_name": "EventGraph",
                },
            }
        },
        "project_inventory_context": {
            "current_blueprint": {"asset_name": "BP_Player", "asset_path": "/Game/BP_Player.BP_Player"},
            "current_blueprint_graph": {"graph_name": "EventGraph"},
        },
    }
    draft = build_intent_draft(request=request, routing=routing, context_bundle=bundle)
    resolved = resolve_context(request=request, routing=routing, context_bundle=bundle, intent_draft=draft)
    verified = verify_intent(draft=draft, routing=routing, context_bundle=bundle, free_chat=True)

    plan = build_tool_plan(
        intent_draft=draft,
        verified_intent=verified,
        context_resolution=resolved,
        routing=routing,
    )

    assert resolved["status"] == "resolved"
    assert resolved["source"] == "current_blueprint_context"
    assert plan["mode"] == "read_only"
    assert plan["arguments"]["blueprint_path"] == "/Game/BP_Player.BP_Player"
    assert plan["arguments"]["graph_name"] == "EventGraph"
