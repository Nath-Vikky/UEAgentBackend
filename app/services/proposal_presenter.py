from __future__ import annotations

from typing import Any

from app.db.models.proposal import ProposalModel


def proposal_payload(proposal: ProposalModel) -> dict[str, Any]:
    """Serialize a proposal model into the public ActionProposal response shape."""
    return {
        "proposal_id": proposal.proposal_id,
        "title": proposal.title,
        "proposal_type": proposal.proposal_type,
        "before_summary": proposal.before_summary,
        "after_summary": proposal.after_summary,
        "rationale": proposal.rationale,
        "risk_flags": proposal.risk_flags,
        "dry_run_preview": dict(proposal.dry_run_preview_json or {}),
        "display_hints": dict(proposal.display_hints_json or {}),
        "requires_confirmation": proposal.requires_confirmation,
        "confirmation": {
            "state": proposal.confirmation_state,
            "decision_endpoint": proposal.decision_endpoint,
        },
    }


__all__ = ["proposal_payload"]
