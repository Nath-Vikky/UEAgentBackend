from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.services.editor_operations.history import (
    history_fetch_limit,
    operation_diagnostics_summary_payload,
    operation_history_payload,
)


@dataclass
class FakeProposal:
    proposal_id: str
    title: str
    confirmation_state: str
    dry_run_preview_json: dict[str, Any]
    risk_flags: list[str] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


def _proposal(
    *,
    proposal_id: str = "proposal_1",
    operation_type: str = "add_blueprint_node_template",
    success: bool | None = True,
    needs_attention: bool = False,
    diagnostic_flags: list[str] | None = None,
    repair_actions: list[str] | None = None,
) -> FakeProposal:
    result_summary = {
        "needs_user_attention": needs_attention,
        "error_codes": ["compile_failed"] if not success else [],
        "operation_diagnostics": {
            "diagnostic_flags": diagnostic_flags or [],
            "repair_advice": {
                "status": "suggested" if repair_actions else "not_needed",
                "actions": [{"action_id": action_id} for action_id in repair_actions or []],
            },
        },
    }
    operation_result = (
        {
            "execution_state": "completed" if success else "failed",
            "success": success,
            "result_summary": result_summary,
        }
        if success is not None
        else {}
    )
    return FakeProposal(
        proposal_id=proposal_id,
        title=f"Proposal {proposal_id}",
        confirmation_state="confirmed",
        risk_flags=["confirmed_write"],
        created_at=datetime(2026, 6, 3, 8, 0, tzinfo=UTC),
        updated_at=datetime(2026, 6, 3, 8, 5, tzinfo=UTC),
        dry_run_preview_json={
            "operation_type": operation_type,
            "tool_id": f"editor_{operation_type}",
            "approval_state": "executed" if success else "confirmed",
            "preview_summary": {"target_count": 1},
            "affected_targets": [{"path": "/Game/Blueprints/BP_Player"}],
            "operation_result": operation_result,
        },
    )


def test_history_fetch_limit_expands_filtered_queries() -> None:
    assert history_fetch_limit(safe_limit=20, has_filters=False) == 20
    assert history_fetch_limit(safe_limit=20, has_filters=True) == 120
    assert history_fetch_limit(safe_limit=200, has_filters=True) == 500


def test_operation_history_payload_filters_attention_and_flags() -> None:
    proposals = [
        _proposal(
            proposal_id="attention",
            needs_attention=True,
            diagnostic_flags=["expected_linked_pins_missing"],
            repair_actions=["connect_expected_exec_pins"],
        ),
        _proposal(proposal_id="clean", needs_attention=False),
        _proposal(proposal_id="other", operation_type="set_umg_widget_text", needs_attention=True),
    ]

    payload = operation_history_payload(
        proposals,
        limit=5,
        operation_type="add_blueprint_node_template",
        needs_user_attention=True,
        diagnostic_flag="expected_linked_pins_missing",
    )

    assert payload["summary"]["item_count"] == 1
    assert payload["items"][0]["proposal_id"] == "attention"
    assert payload["items"][0]["operation_type"] == "add_blueprint_node_template"
    assert payload["items"][0]["execution_state"] == "completed"
    assert payload["items"][0]["created_at"] == "2026-06-03T08:00:00+00:00"


def test_operation_diagnostics_summary_counts_executed_pending_and_attention() -> None:
    proposals = [
        _proposal(
            proposal_id="attention",
            needs_attention=True,
            diagnostic_flags=["expected_linked_pins_missing"],
            repair_actions=["connect_expected_exec_pins"],
        ),
        _proposal(proposal_id="failed", success=False, needs_attention=True, diagnostic_flags=["compile_failed"]),
        _proposal(proposal_id="pending", success=None),
    ]

    payload = operation_diagnostics_summary_payload(proposals, limit=10)
    summary = payload["summary"]

    assert summary["schema_version"] == "editor_operation_diagnostics_summary_v1"
    assert summary["inspected_count"] == 3
    assert summary["executed_count"] == 2
    assert summary["pending_count"] == 1
    assert summary["success_count"] == 1
    assert summary["failed_count"] == 1
    assert summary["needs_user_attention_count"] == 2
    assert summary["attention_rate"] == 1.0
    assert summary["diagnostic_flag_counts"]["expected_linked_pins_missing"] == 1
    assert summary["diagnostic_flag_counts"]["compile_failed"] == 1
    assert summary["repair_action_counts"]["connect_expected_exec_pins"] == 1
    assert summary["execution_state_counts"]["pending_result"] == 1
    assert len(summary["recent_attention_items"]) == 2
