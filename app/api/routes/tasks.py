from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db
from app.api.errors import APIError
from app.core.settings import Settings
from app.schemas.common import DebugView, UserView
from app.schemas.requests import CodeReviewFileListRequest, UnifiedTaskRequest
from app.schemas.responses import (
    ArtifactListResponse,
    CodeReviewFileListResponse,
    TasksRecentResponse,
    TraceResponse,
    UnifiedTaskResponse,
)
from app.services.task_service import TaskService
from app.utils.project_files import ProjectFileAccessError, list_project_code_files

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _run_task(
    task_type: str,
    request: UnifiedTaskRequest,
    db: Session,
    settings: Settings,
) -> UnifiedTaskResponse:
    request.task_type = task_type
    return TaskService(db, settings).create_task(request)


@router.post("/project-qa", response_model=UnifiedTaskResponse)
def project_qa(
    request: UnifiedTaskRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> UnifiedTaskResponse:
    return _run_task("project_qa", request, db, settings)


@router.post("/code-review", response_model=UnifiedTaskResponse)
def code_review(
    request: UnifiedTaskRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> UnifiedTaskResponse:
    return _run_task("code_review", request, db, settings)


@router.post("/code-review/files", response_model=CodeReviewFileListResponse)
def list_code_review_files(
    request: CodeReviewFileListRequest,
) -> CodeReviewFileListResponse:
    try:
        payload = list_project_code_files(
            project_root=request.project_root,
            source_roots=request.source_roots,
            extensions=request.extensions,
            query=request.query,
            limit=request.limit,
        )
    except ProjectFileAccessError as exc:
        return CodeReviewFileListResponse(
            success=False,
            project_root=request.project_root,
            source_roots=request.source_roots,
            extensions=request.extensions,
            query=request.query or "",
            items=[],
            total_count=0,
            returned_count=0,
            truncated=False,
            scan_diagnostics={
                "project_root": request.project_root,
                "requested_source_roots": request.source_roots,
                "empty_reason": "project_file_access_error",
                "error": str(exc),
            },
            errors=[
                {
                    "code": "project_file_access_error",
                    "message": str(exc),
                    "details": {"project_root": request.project_root},
                }
            ],
        )
    return CodeReviewFileListResponse(success=True, **payload)


@router.post("/code-generate", response_model=UnifiedTaskResponse)
def code_generate(
    request: UnifiedTaskRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> UnifiedTaskResponse:
    return _run_task("code_generate", request, db, settings)


@router.post("/logs-analyze", response_model=UnifiedTaskResponse)
def logs_analyze(
    request: UnifiedTaskRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> UnifiedTaskResponse:
    return _run_task("logs_analyze", request, db, settings)


@router.post("/config-generate", response_model=UnifiedTaskResponse)
def config_generate(
    request: UnifiedTaskRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> UnifiedTaskResponse:
    return _run_task("config_generate", request, db, settings)


@router.post("/config-validate", response_model=UnifiedTaskResponse)
def config_validate(
    request: UnifiedTaskRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> UnifiedTaskResponse:
    return _run_task("config_validate", request, db, settings)


@router.post("/assets-inspect", response_model=UnifiedTaskResponse)
def assets_inspect(
    request: UnifiedTaskRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> UnifiedTaskResponse:
    return _run_task("assets_inspect", request, db, settings)


@router.post("/perf-analyze", response_model=UnifiedTaskResponse)
def perf_analyze(
    request: UnifiedTaskRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> UnifiedTaskResponse:
    return _run_task("perf_analyze", request, db, settings)


@router.get("/recent", response_model=TasksRecentResponse)
def recent_tasks(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> TasksRecentResponse:
    items = TaskService(db, settings).list_recent()[:limit]
    return TasksRecentResponse(success=True, items=items)


@router.get("/{task_id}", response_model=UnifiedTaskResponse)
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> UnifiedTaskResponse:
    payload = TaskService(db, settings).get_task_response(task_id)
    if not payload:
        raise APIError(404, "task_not_found", f"Task `{task_id}` was not found.")
    return payload


@router.get("/{task_id}/user-view", response_model=UserView)
def get_task_user_view(
    task_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> UserView:
    payload = TaskService(db, settings).get_task_response(task_id)
    if not payload:
        raise APIError(404, "task_not_found", f"Task `{task_id}` was not found.")
    return payload.user_view


@router.get("/{task_id}/debug-view", response_model=DebugView)
def get_task_debug_view(
    task_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> DebugView:
    payload = TaskService(db, settings).get_task_response(task_id)
    if not payload:
        raise APIError(404, "task_not_found", f"Task `{task_id}` was not found.")
    return payload.debug_view


@router.get("/{task_id}/trace", response_model=TraceResponse)
def get_task_trace(
    task_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> TraceResponse:
    service = TaskService(db, settings)
    payload = service.get_task_response(task_id)
    if not payload:
        raise APIError(404, "task_not_found", f"Task `{task_id}` was not found.")
    return TraceResponse(
        success=True,
        task_id=task_id,
        trace_summary=payload.trace_summary,
        step_results=[item.model_dump(mode="json") for item in payload.step_results],
        events=service.get_task_events(task_id),
    )


@router.get("/{task_id}/artifacts", response_model=ArtifactListResponse)
def get_task_artifacts(
    task_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> ArtifactListResponse:
    service = TaskService(db, settings)
    payload = service.get_task_response(task_id)
    if not payload:
        raise APIError(404, "task_not_found", f"Task `{task_id}` was not found.")
    return ArtifactListResponse(
        success=True,
        task_id=task_id,
        items=service.get_task_artifacts(task_id),
    )
