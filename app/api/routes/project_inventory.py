from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_app_settings
from app.core.settings import Settings
from app.schemas.requests import ProjectInventoryQueryRequest, ProjectInventorySnapshotRequest
from app.schemas.responses import (
    ProjectInventoryItemResponse,
    ProjectInventoryItemsResponse,
    ProjectInventoryQueryResponse,
    ProjectInventorySnapshotResponse,
    ProjectInventorySummaryResponse,
)
from app.services.project_inventory_service import ProjectInventoryService

router = APIRouter(prefix="/project-inventory", tags=["project-inventory"])


@router.post("/snapshot", response_model=ProjectInventorySnapshotResponse)
def save_inventory_snapshot(
    request: ProjectInventorySnapshotRequest,
    settings: Settings = Depends(get_app_settings),
) -> ProjectInventorySnapshotResponse:
    snapshot = ProjectInventoryService(settings).save_snapshot(request)
    return ProjectInventorySnapshotResponse(success=True, snapshot=snapshot)


@router.get("/summary", response_model=ProjectInventorySummaryResponse)
def get_inventory_summary(
    project_id: str | None = None,
    settings: Settings = Depends(get_app_settings),
) -> ProjectInventorySummaryResponse:
    summary = ProjectInventoryService(settings).summary(project_id)
    return ProjectInventorySummaryResponse(success=True, summary=summary)


@router.get("/assets", response_model=ProjectInventoryItemsResponse)
def list_inventory_assets(
    project_id: str | None = None,
    asset_type: str | None = None,
    query: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    settings: Settings = Depends(get_app_settings),
) -> ProjectInventoryItemsResponse:
    service = ProjectInventoryService(settings)
    items = service.list_assets(project_id=project_id, asset_type=asset_type, query=query, limit=limit)
    return ProjectInventoryItemsResponse(success=True, items=items, summary=service.summary(project_id))


@router.get("/assets/{asset_id}", response_model=ProjectInventoryItemResponse)
def get_inventory_asset(
    asset_id: str,
    project_id: str | None = None,
    settings: Settings = Depends(get_app_settings),
) -> ProjectInventoryItemResponse:
    item = ProjectInventoryService(settings).get_asset(asset_id, project_id)
    return ProjectInventoryItemResponse(success=bool(item), item=item or {})


@router.get("/code-files", response_model=ProjectInventoryItemsResponse)
def list_inventory_code_files(
    project_id: str | None = None,
    query: str | None = None,
    module_name: str | None = None,
    limit: int = Query(default=200, ge=1, le=2000),
    settings: Settings = Depends(get_app_settings),
) -> ProjectInventoryItemsResponse:
    service = ProjectInventoryService(settings)
    items = service.list_code_files(project_id=project_id, query=query, module_name=module_name, limit=limit)
    return ProjectInventoryItemsResponse(success=True, items=items, summary=service.summary(project_id))


@router.get("/level-actors", response_model=ProjectInventoryItemsResponse)
def list_inventory_level_actors(
    project_id: str | None = None,
    query: str | None = None,
    level_name: str | None = None,
    limit: int = Query(default=200, ge=1, le=2000),
    settings: Settings = Depends(get_app_settings),
) -> ProjectInventoryItemsResponse:
    service = ProjectInventoryService(settings)
    items = service.list_level_actors(project_id=project_id, query=query, level_name=level_name, limit=limit)
    return ProjectInventoryItemsResponse(success=True, items=items, summary=service.summary(project_id))


@router.get("/material-instances", response_model=ProjectInventoryItemsResponse)
def list_inventory_material_instances(
    project_id: str | None = None,
    query: str | None = None,
    parent_material: str | None = None,
    limit: int = Query(default=200, ge=1, le=2000),
    settings: Settings = Depends(get_app_settings),
) -> ProjectInventoryItemsResponse:
    service = ProjectInventoryService(settings)
    items = service.list_material_instances(
        project_id=project_id,
        query=query,
        parent_material=parent_material,
        limit=limit,
    )
    return ProjectInventoryItemsResponse(success=True, items=items, summary=service.summary(project_id))


@router.post("/query", response_model=ProjectInventoryQueryResponse)
def query_inventory(
    request: ProjectInventoryQueryRequest,
    settings: Settings = Depends(get_app_settings),
) -> ProjectInventoryQueryResponse:
    result = ProjectInventoryService(settings).query(
        query=request.query,
        project_id=request.project_id,
        asset_path=request.asset_path,
        asset_type=request.asset_type,
        fields=request.fields,
        selected_assets=request.selected_assets,
        limit=request.limit,
    )
    return ProjectInventoryQueryResponse(
        success=True,
        query=request.query,
        items=result["items"],
        summary=result["summary"],
    )
