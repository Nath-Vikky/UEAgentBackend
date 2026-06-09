from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401
from app.agent.context_manager import build_context_bundle
from app.agent.memory_manager import (
    read_active_target_memory,
    read_conversation_focus_memory,
    update_active_target_memory,
    update_conversation_focus_memory,
)
from app.db.base import Base
from app.db.models.session import SessionModel
from app.schemas.requests import UnifiedTaskRequest


@contextmanager
def _session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _add_session(db: Session, session_id: str = "active-target-session") -> None:
    db.add(SessionModel(session_id=session_id, project_name="RushBa", metadata_json={}))
    db.commit()


def test_active_target_memory_records_compact_editor_targets() -> None:
    with _session() as db:
        _add_session(db)

        result = update_active_target_memory(
            db,
            "active-target-session",
            task_id="task-asset",
            context_bundle={
                "agent_turn_context": {
                    "active_targets": {
                        "asset": {
                            "available": True,
                            "selected_assets": ["/Game/Characters/BP_Player.BP_Player"],
                        },
                        "code": {
                            "available": True,
                            "current_file": "Source/RushBa/Private/RushBaCharacter.cpp",
                        },
                    }
                }
            },
        )
        memory = read_active_target_memory(db, "active-target-session")

    assert result["status"] == "updated"
    assert memory["status"] == "available"
    assert [item["target_kind"] for item in memory["items"]] == ["asset", "code"]
    assert memory["items"][0]["target_id"] == "/Game/Characters/BP_Player.BP_Player"
    assert memory["items"][0]["display_name"] == "BP_Player"


def test_context_bundle_uses_active_target_memory_for_implicit_asset_reference() -> None:
    with _session() as db:
        _add_session(db)
        update_active_target_memory(
            db,
            "active-target-session",
            task_id="previous-asset-inspect",
            context_bundle={
                "agent_turn_context": {
                    "active_targets": {
                        "asset": {
                            "available": True,
                            "selected_assets": ["/Game/Characters/BP_Player.BP_Player"],
                        }
                    }
                }
            },
        )
        request = UnifiedTaskRequest.model_validate(
            {
                "task_type": "agent_chat",
                "session": {
                    "session_id": "active-target-session",
                    "messages": [{"role": "user", "content": "分析一下这个资产"}],
                },
                "context": {"project_name": "RushBa", "active_panel": "AgentChat"},
                "payload": {"user_query": "分析一下这个资产"},
            }
        )
        bundle = build_context_bundle(
            db=db,
            request=request,
            routing={
                "intent": {"route_type": "tool_execution"},
                "route": {"selected_tool_id": "inspect_assets"},
                "locale": {"final_output_language": "zh-CN"},
            },
            actual_task_type="asset_inspect",
        )

    assert bundle["active_context"]["asset"]["selected_assets"] == ["/Game/Characters/BP_Player.BP_Player"]
    assert bundle["active_context"]["asset"]["memory_source"] == "active_target_memory"
    assert bundle["agent_turn_context"]["active_targets"]["asset"]["available"] is True
    assert bundle["agent_turn_context"]["context_sources"]["active_target_memory"] is True


def test_active_target_memory_does_not_override_current_explicit_context() -> None:
    with _session() as db:
        _add_session(db)
        update_active_target_memory(
            db,
            "active-target-session",
            context_bundle={
                "agent_turn_context": {
                    "active_targets": {
                        "asset": {
                            "available": True,
                            "selected_assets": ["/Game/Old/BP_Old.BP_Old"],
                        }
                    }
                }
            },
        )
        request = UnifiedTaskRequest.model_validate(
            {
                "task_type": "agent_chat",
                "session": {
                    "session_id": "active-target-session",
                    "messages": [{"role": "user", "content": "分析一下这个资产"}],
                },
                "context": {
                    "project_name": "RushBa",
                    "active_panel": "AgentChat",
                    "selected_assets": ["/Game/New/BP_New.BP_New"],
                },
                "payload": {"user_query": "分析一下这个资产"},
            }
        )
        bundle = build_context_bundle(
            db=db,
            request=request,
            routing={
                "intent": {"route_type": "tool_execution"},
                "route": {"selected_tool_id": "inspect_assets"},
                "locale": {"final_output_language": "zh-CN"},
            },
            actual_task_type="asset_inspect",
        )

    assert bundle["active_context"]["asset"]["selected_assets"] == ["/Game/New/BP_New.BP_New"]
    assert "memory_source" not in bundle["active_context"]["asset"]


def test_conversation_focus_memory_records_compact_turn_focus() -> None:
    with _session() as db:
        _add_session(db)

        result = update_conversation_focus_memory(
            db,
            "active-target-session",
            task_id="task-focus",
            context_bundle={
                "input_summary": {
                    "route_type": "single_tool",
                    "selected_tool_id": "mcp_get_asset_details",
                    "latest_user_message": "分析一下这个资产",
                },
                "context_resolution": {
                    "status": "resolved",
                    "target_kind": "selected_asset",
                    "target_id": "/Game/Characters/BP_Player.BP_Player",
                    "source": "selected_assets",
                },
                "tool_plan_v1": {"mode": "read_only", "tool_id": "mcp_get_asset_details"},
            },
            execution={
                "user_view": {"title": "资产分析", "text": "BP_Player 是一个蓝图资产。"},
                "assistant_message": "BP_Player 是一个蓝图资产。",
                "action_proposals": [],
            },
        )
        memory = read_conversation_focus_memory(db, "active-target-session")

    assert result["status"] == "updated"
    assert memory["status"] == "available"
    assert memory["items"][0]["target_id"] == "/Game/Characters/BP_Player.BP_Player"
    assert memory["items"][0]["display_name"] == "BP_Player"
    assert memory["items"][0]["selected_tool_id"] == "mcp_get_asset_details"
    assert "BP_Player" in memory["items"][0]["assistant_summary"]


def test_context_bundle_uses_conversation_focus_memory_for_followup_asset_reference() -> None:
    with _session() as db:
        _add_session(db)
        update_conversation_focus_memory(
            db,
            "active-target-session",
            task_id="previous-focus",
            context_bundle={
                "input_summary": {
                    "route_type": "single_tool",
                    "selected_tool_id": "mcp_get_asset_details",
                    "latest_user_message": "Analyze BP_Player",
                },
                "context_resolution": {
                    "status": "resolved",
                    "target_kind": "selected_asset",
                    "target_id": "/Game/Characters/BP_Player.BP_Player",
                    "source": "selected_assets",
                },
                "tool_plan_v1": {"mode": "read_only", "tool_id": "mcp_get_asset_details"},
            },
            execution={"user_view": {"title": "Asset", "text": "BP_Player summary."}, "action_proposals": []},
        )
        request = UnifiedTaskRequest.model_validate(
            {
                "task_type": "agent_chat",
                "session": {
                    "session_id": "active-target-session",
                    "messages": [{"role": "user", "content": "它有哪些依赖？"}],
                },
                "context": {"project_name": "RushBa", "active_panel": "AgentChat"},
                "payload": {"user_query": "它有哪些依赖？"},
            }
        )
        bundle = build_context_bundle(
            db=db,
            request=request,
            routing={
                "intent": {"route_type": "direct_answer"},
                "route": {"selected_tool_id": None},
                "locale": {"final_output_language": "zh-CN"},
            },
            actual_task_type="agent_chat",
        )

    assert bundle["active_context"]["asset"]["selected_assets"] == ["/Game/Characters/BP_Player.BP_Player"]
    assert bundle["active_context"]["asset"]["memory_source"] == "conversation_focus_memory"
    assert bundle["agent_turn_context"]["context_sources"]["conversation_focus_memory"] is True
    assert bundle["context_pack"]["conversation_layer"]["conversation_focus_memory"]["items"][0]["display_name"] == "BP_Player"
