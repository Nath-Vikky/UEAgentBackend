from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db
from app.core.settings import Settings
from app.schemas.responses import HealthResponse
from app.services.system_service import SystemService

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db), settings: Settings = Depends(get_app_settings)) -> HealthResponse:
    payload = SystemService(db, settings).health()
    return HealthResponse(success=payload["service_status"] != "error", **payload)

