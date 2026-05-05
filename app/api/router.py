from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    agent_runs,
    editor_operations,
    health,
    kb_admin,
    project_inventory,
    proposals,
    sessions,
    settings,
    tasks,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(settings.router)
api_router.include_router(tasks.router)
api_router.include_router(agent_runs.router)
api_router.include_router(sessions.router)
api_router.include_router(kb_admin.router)
api_router.include_router(proposals.router)
api_router.include_router(project_inventory.router)
api_router.include_router(editor_operations.router)
