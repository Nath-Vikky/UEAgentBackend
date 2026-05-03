from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db
from app.api.errors import APIError
from app.core.settings import Settings
from app.schemas.responses import (
    AlertsResponse,
    BootstrapResponse,
    CapabilitiesResponse,
    RuntimeProfilesResponse,
    SettingsSnapshotResponse,
)
from app.services.monitoring_service import MonitoringService
from app.services.runtime_profile_service import RuntimeProfileService
from app.services.system_service import SystemService

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/bootstrap", response_model=BootstrapResponse)
def bootstrap(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> BootstrapResponse:
    return BootstrapResponse(success=True, **SystemService(db, settings).bootstrap())


@router.get("/capabilities", response_model=CapabilitiesResponse)
def capabilities(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> CapabilitiesResponse:
    return CapabilitiesResponse(success=True, capabilities=SystemService(db, settings).capabilities())


@router.get("/settings", response_model=SettingsSnapshotResponse)
def settings_snapshot(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> SettingsSnapshotResponse:
    return SettingsSnapshotResponse(
        success=True,
        settings=SystemService(db, settings).settings_snapshot(),
    )


@router.get("/alerts", response_model=AlertsResponse)
def alerts_snapshot(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> AlertsResponse:
    payload = MonitoringService(db, settings).alerts_snapshot()
    return AlertsResponse(success=True, **payload)


@router.get("/runtime-profiles", response_model=RuntimeProfilesResponse)
def list_runtime_profiles(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> RuntimeProfilesResponse:
    service = RuntimeProfileService(db, settings)
    service.ensure_seeded()
    return RuntimeProfilesResponse(success=True, **service.list_payload())


@router.post("/runtime-profiles/{profile_id}/activate", response_model=RuntimeProfilesResponse)
def activate_runtime_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> RuntimeProfilesResponse:
    service = RuntimeProfileService(db, settings)
    service.ensure_seeded()
    payload = service.activate(profile_id)
    if not payload:
        raise APIError(404, "profile_not_found", f"Profile `{profile_id}` was not found.")
    return RuntimeProfilesResponse(success=True, **service.list_payload())


@router.post("/runtime-profiles/{profile_id}/set-default", response_model=RuntimeProfilesResponse)
def set_default_runtime_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> RuntimeProfilesResponse:
    service = RuntimeProfileService(db, settings)
    service.ensure_seeded()
    payload = service.set_default(profile_id)
    if not payload:
        raise APIError(404, "profile_not_found", f"Profile `{profile_id}` was not found.")
    return RuntimeProfilesResponse(success=True, **service.list_payload())
