from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
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
from app.services.editor_workflow_planner_service import EditorWorkflowPlannerService
from app.services.project_inventory_service import ProjectInventoryService
from app.services.proposal_service import ProposalService

router = APIRouter(prefix="/editor-operations", tags=["editor-operations"])


class EditorWorkflowPlanRequest(BaseModel):
    goal: str = Field(default="")
    workflow_type: str | None = None
    payload: dict = Field(default_factory=dict)
    context: dict = Field(default_factory=dict)
    requested_by: str = "workflow_planner"


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


@router.post("/workflows/plan")
def plan_editor_operation_workflow(request: EditorWorkflowPlanRequest) -> dict:
    plan = EditorWorkflowPlannerService().plan_workflow(
        goal=request.goal,
        workflow_type=request.workflow_type,
        payload=request.payload,
        context=request.context,
        requested_by=request.requested_by,
    )
    return {"success": plan["status"] != "unsupported", "workflow_plan": plan, "errors": []}


@router.get("/inspect/level-actors")
def inspect_level_actors(
    project_id: str | None = None,
    query: str | None = None,
    level_name: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    settings: Settings = Depends(get_app_settings),
) -> dict:
    service = ProjectInventoryService(settings)
    items = service.list_level_actors(
        project_id=project_id,
        query=query,
        level_name=level_name,
        limit=limit,
    )
    summary = service.summary(project_id)
    empty_reason = ""
    if not summary.get("has_snapshot"):
        empty_reason = "no_project_inventory_snapshot"
    elif not items:
        empty_reason = "no_matching_level_actors"
    return {
        "success": True,
        "inspection": {
            "operation_type": "inspect_level_actors",
            "side_effect_level": "read_only",
            "source": "project_inventory",
            "query": query or "",
            "project_id": project_id or summary.get("project_id") or "",
            "level_name": level_name or "",
            "match_count": len(items),
            "empty_reason": empty_reason,
        },
        "summary": summary,
        "items": items,
        "errors": [],
    }


@router.get("/inspect/material-instance-parameters")
def inspect_material_instance_parameters(
    project_id: str | None = None,
    material_instance_path: str | None = None,
    query: str | None = None,
    parent_material: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    settings: Settings = Depends(get_app_settings),
) -> dict:
    service = ProjectInventoryService(settings)
    search_query = material_instance_path or query
    items = service.list_material_instances(
        project_id=project_id,
        query=search_query,
        parent_material=parent_material,
        limit=limit,
    )
    if material_instance_path:
        expected = material_instance_path.lower()
        items = [
            item
            for item in items
            if expected
            in {
                str(item.get("material_instance_path") or "").lower(),
                str(item.get("material_instance_name") or "").lower(),
            }
            or expected in str(item.get("material_instance_path") or "").lower()
        ]
    summary = service.summary(project_id)
    empty_reason = ""
    if not summary.get("has_snapshot"):
        empty_reason = "no_project_inventory_snapshot"
    elif not items:
        empty_reason = "no_matching_material_instances"
    return {
        "success": True,
        "inspection": {
            "operation_type": "inspect_material_instance_parameters",
            "side_effect_level": "read_only",
            "source": "project_inventory",
            "query": query or "",
            "project_id": project_id or summary.get("project_id") or "",
            "material_instance_path": material_instance_path or "",
            "parent_material": parent_material or "",
            "match_count": len(items),
            "empty_reason": empty_reason,
        },
        "summary": summary,
        "items": items,
        "errors": [],
    }


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


@router.get("/proposals/{proposal_id}/follow-ups")
def get_editor_operation_follow_ups(proposal_id: str, db: Session = Depends(get_db)) -> dict:
    payload = EditorOperationService(db).operation_follow_up_candidates(proposal_id)
    if not payload:
        raise APIError(404, "proposal_not_found", f"Proposal `{proposal_id}` was not found.")
    return {"success": True, **payload, "errors": []}


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
