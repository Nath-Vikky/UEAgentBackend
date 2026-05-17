from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    agent_runs,
    curation,
    editor_operations,
    health,
    kb_admin,
    mcp_tools,
    project_inventory,
    proposals,
    sessions,
    settings,
    tasks,
    web_memory,
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
api_router.include_router(mcp_tools.router)
api_router.include_router(web_memory.router)
api_router.include_router(curation.router)
