from __future__ import annotations

from app.db.models.proposal import ProposalModel
from app.services.proposal_presenter import proposal_payload


def test_proposal_payload_matches_action_proposal_contract() -> None:
    proposal = ProposalModel(
        proposal_id="proposal_1",
        task_id="task_1",
        title="Rename asset",
        proposal_type="editor_operation",
        before_summary="Before",
        after_summary="After",
        rationale="Reason",
        risk_flags="LOW",
        dry_run_preview_json={"operation_type": "rename_selected_asset"},
        display_hints_json={"ui": "editor_operation_confirmation"},
        requires_confirmation=True,
        confirmation_state="pending",
        decision_endpoint="/api/v1/proposals/proposal_1/decision",
    )

    payload = proposal_payload(proposal)

    assert payload == {
        "proposal_id": "proposal_1",
        "title": "Rename asset",
        "proposal_type": "editor_operation",
        "before_summary": "Before",
        "after_summary": "After",
        "rationale": "Reason",
        "risk_flags": "LOW",
        "dry_run_preview": {"operation_type": "rename_selected_asset"},
        "display_hints": {"ui": "editor_operation_confirmation"},
        "requires_confirmation": True,
        "confirmation": {
            "state": "pending",
            "decision_endpoint": "/api/v1/proposals/proposal_1/decision",
        },
    }


def test_proposal_payload_normalizes_nullable_json_fields() -> None:
    proposal = ProposalModel(
        proposal_id="proposal_empty",
        title="Empty",
        proposal_type="config_change",
        risk_flags="LOW",
        dry_run_preview_json=None,
        display_hints_json=None,
        requires_confirmation=True,
        confirmation_state="confirmed",
        decision_endpoint=None,
    )

    payload = proposal_payload(proposal)

    assert payload["dry_run_preview"] == {}
    assert payload["display_hints"] == {}
    assert payload["confirmation"] == {
        "state": "confirmed",
        "decision_endpoint": None,
    }
