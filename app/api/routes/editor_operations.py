from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db
from app.api.errors import APIError
from app.core.settings import Settings
from app.schemas.requests import (
    EditorOperationProposalRequest,
    EditorOperationResultRequest,
    ProposalDecisionRequest,
)
from app.schemas.responses import (
    EditorOperationProposalResponse,
    EditorOperationResultResponse,
    ProposalDecisionResponse,
)
from app.services.editor_operation_service import (
    EditorOperationService,
    EditorOperationValidationError,
)
from app.services.proposal_service import ProposalService

router = APIRouter(prefix="/editor-operations", tags=["editor-operations"])


@router.get("/capabilities")
def editor_operation_capabilities() -> dict:
    return {
        "success": True,
        "capabilities": EditorOperationService.supported_operations(),
        "errors": [],
    }


@router.get("/history")
def editor_operation_history(
    operation_type: str | None = None,
    needs_user_attention: bool | None = None,
    diagnostic_flag: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    payload = EditorOperationService(db).list_operation_history(
        limit=limit,
        operation_type=operation_type,
        needs_user_attention=needs_user_attention,
        diagnostic_flag=diagnostic_flag,
    )
    return {"success": True, **payload, "errors": []}


@router.get("/diagnostics")
def editor_operation_diagnostics(
    operation_type: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    payload = EditorOperationService(db).operation_diagnostics_summary(
        limit=limit,
        operation_type=operation_type,
    )
    return {"success": True, **payload, "errors": []}


@router.post("/proposals", response_model=EditorOperationProposalResponse)
def create_editor_operation_proposal(
    request: EditorOperationProposalRequest,
    db: Session = Depends(get_db),
) -> EditorOperationProposalResponse:
    service = EditorOperationService(db)
    try:
        payload = service.create_operation_proposal(request)
    except EditorOperationValidationError as exc:
        raise APIError(400, exc.reason, "Editor operation proposal validation failed.", exc.details) from exc
    return EditorOperationProposalResponse(success=True, **payload)


@router.get("/proposals/{proposal_id}")
def get_editor_operation_proposal(proposal_id: str, db: Session = Depends(get_db)) -> dict:
    payload = ProposalService(db).get_detail(proposal_id)
    if not payload:
        raise APIError(404, "proposal_not_found", f"Proposal `{proposal_id}` was not found.")
    proposal_type = payload.get("item", {}).get("proposal_type")
    if proposal_type != "editor_operation":
        raise APIError(
            404,
            "editor_operation_proposal_not_found",
            f"Proposal `{proposal_id}` is not an editor operation proposal.",
            {"proposal_type": proposal_type},
        )
    return {"success": True, **payload, "errors": []}


def _record_editor_operation_decision(
    *,
    proposal_id: str,
    decision: str,
    db: Session,
    settings: Settings,
) -> ProposalDecisionResponse:
    service = ProposalService(db, settings)
    try:
        payload = service.record_decision(
            proposal_id,
            ProposalDecisionRequest(
                decision=decision,  # type: ignore[arg-type]
                actor="ue_plugin_user",
                metadata={
                    "source": "editor_operations_route",
                    "requires_ue_plugin_execution": decision == "confirmed",
                },
            ),
        )
    except ValueError as exc:
        raise APIError(409, "proposal_already_decided", str(exc)) from exc
    if not payload:
        raise APIError(404, "proposal_not_found", f"Proposal `{proposal_id}` was not found.")
    proposal_type = payload.get("proposal", {}).get("proposal_type")
    if proposal_type != "editor_operation":
        raise APIError(
            400,
            "proposal_is_not_editor_operation",
            f"Proposal `{proposal_id}` is not an editor operation proposal.",
            {"proposal_type": proposal_type},
        )
    return ProposalDecisionResponse(success=True, **payload)


@router.post("/proposals/{proposal_id}/confirm", response_model=ProposalDecisionResponse)
def confirm_editor_operation_proposal(
    proposal_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> ProposalDecisionResponse:
    return _record_editor_operation_decision(
        proposal_id=proposal_id,
        decision="confirmed",
        db=db,
        settings=settings,
    )


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalDecisionResponse)
def reject_editor_operation_proposal(
    proposal_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> ProposalDecisionResponse:
    return _record_editor_operation_decision(
        proposal_id=proposal_id,
        decision="rejected",
        db=db,
        settings=settings,
    )


@router.post("/results", response_model=EditorOperationResultResponse)
def record_editor_operation_result(
    request: EditorOperationResultRequest,
    db: Session = Depends(get_db),
) -> EditorOperationResultResponse:
    service = EditorOperationService(db)
    try:
        payload = service.record_operation_result(request)
    except EditorOperationValidationError as exc:
        status_code = 409 if "confirmed" in exc.reason or "mismatch" in exc.reason else 400
        raise APIError(status_code, exc.reason, "Editor operation result validation failed.", exc.details) from exc
    if not payload:
        raise APIError(404, "proposal_not_found", f"Proposal `{request.proposal_id}` was not found.")
    return EditorOperationResultResponse(success=True, **payload)
