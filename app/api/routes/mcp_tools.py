from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_app_settings
from app.core.settings import Settings
from app.services.mcp_executor import MCPToolExecutor
from app.services.tool_manifest_service import build_tool_manifest

router = APIRouter(prefix="/mcp", tags=["mcp"])


class MCPToolCallRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.get("/tools")
def list_mcp_tools(settings: Settings = Depends(get_app_settings)) -> dict[str, Any]:
    result = MCPToolExecutor(settings).discover_tools()
    return {"success": bool(result.get("ok")), **result}


@router.get("/tool-registry/manifest")
def tool_registry_manifest(
    include_disabled: bool = True,
    category: str | None = None,
    side_effect_level: str | None = None,
    transport: str | None = None,
) -> dict[str, Any]:
    return {
        "success": True,
        "manifest": build_tool_manifest(
            include_disabled=include_disabled,
            category=category,
            side_effect_level=side_effect_level,
            transport=transport,
        ),
        "errors": [],
    }


@router.post("/tools/{tool_name}/call")
def call_mcp_tool(
    tool_name: str,
    request: MCPToolCallRequest,
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    result = MCPToolExecutor(settings).call_readonly_tool(tool_name, request.arguments)
    return {"success": bool(result.get("ok")), **result}
