from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db
from app.api.errors import APIError
from app.core.settings import Settings
from app.schemas.requests import ProposalDecisionRequest
from app.schemas.responses import ProposalDecisionResponse, ProposalDetailResponse, ProposalListResponse
from app.services.proposal_service import ProposalService

router = APIRouter(prefix="/proposals", tags=["proposals"])


@router.get("/pending", response_model=ProposalListResponse)
def pending_proposals(db: Session = Depends(get_db)) -> ProposalListResponse:
    return ProposalListResponse(success=True, items=ProposalService(db).pending())


@router.get("/{proposal_id}", response_model=ProposalDetailResponse)
def get_proposal_detail(proposal_id: str, db: Session = Depends(get_db)) -> ProposalDetailResponse:
    payload = ProposalService(db).get_detail(proposal_id)
    if not payload:
        raise APIError(404, "proposal_not_found", f"Proposal `{proposal_id}` was not found.")
    return ProposalDetailResponse(success=True, **payload)


@router.post("/{proposal_id}/decision", response_model=ProposalDecisionResponse)
def record_proposal_decision(
    proposal_id: str,
    request: ProposalDecisionRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> ProposalDecisionResponse:
    service = ProposalService(db, settings)
    try:
        payload = service.record_decision(proposal_id, request)
    except ValueError as exc:
        raise APIError(409, "proposal_already_decided", str(exc)) from exc
    if not payload:
        raise APIError(404, "proposal_not_found", f"Proposal `{proposal_id}` was not found.")
    return ProposalDecisionResponse(success=True, **payload)


@router.get("/decisions/{decision_id}", response_model=ProposalDecisionResponse)
def get_proposal_decision(decision_id: str, db: Session = Depends(get_db)) -> ProposalDecisionResponse:
    payload = ProposalService(db).get_decision(decision_id)
    if not payload:
        raise APIError(404, "proposal_decision_not_found", f"Decision `{decision_id}` was not found.")
    return ProposalDecisionResponse(success=True, **payload)
