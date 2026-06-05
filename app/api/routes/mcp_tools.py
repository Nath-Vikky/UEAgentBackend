from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db
from app.api.errors import APIError
from app.core.settings import Settings
from app.schemas.requests import EditorOperationProposalRequest
from app.services.editor_operation_service import (
    EditorOperationService,
    EditorOperationValidationError,
)
from app.services.mcp_executor import MCPToolExecutor
from app.services.tool_manifest_service import build_tool_manifest
from app.services.tool_proposal_bridge_service import ToolProposalBridgeService
from app.services.tool_registry_plan_call_service import ToolRegistryPlanCallService
from app.services.tool_registry_readonly_call_service import ToolRegistryReadOnlyCallService

router = APIRouter(prefix="/mcp", tags=["mcp"])


class MCPToolCallRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolRegistryProposalBridgeRequest(BaseModel):
    tool_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    source_task_id: str | None = None
    requested_by: str | None = "tool_registry_proposal_bridge"
    context: dict[str, Any] = Field(default_factory=dict)


class ToolRegistryReadOnlyCallRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolRegistryPlanCallRequest(BaseModel):
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
    profile: str | None = None,
) -> dict[str, Any]:
    return {
        "success": True,
        "manifest": build_tool_manifest(
            include_disabled=include_disabled,
            category=category,
            side_effect_level=side_effect_level,
            transport=transport,
            profile=profile,
        ),
        "errors": [],
    }


@router.post("/tool-registry/tools/{tool}/call")
def call_tool_registry_readonly_tool(
    tool: str,
    request: ToolRegistryReadOnlyCallRequest,
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    call = ToolRegistryReadOnlyCallService(settings).call(tool, request.arguments)
    return {
        "success": bool(call.get("ok")),
        "call": call,
        "errors": [] if call.get("ok") else call.get("errors", []),
    }


@router.post("/tool-registry/plans/{tool}/call")
def call_tool_registry_plan_tool(
    tool: str,
    request: ToolRegistryPlanCallRequest,
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    call = ToolRegistryPlanCallService(settings).call(tool, request.arguments)
    return {
        "success": bool(call.get("ok")),
        "call": call,
        "errors": [] if call.get("ok") else call.get("errors", []),
    }


@router.post("/tool-registry/proposals/prepare")
def prepare_tool_registry_proposal(request: ToolRegistryProposalBridgeRequest) -> dict[str, Any]:
    bridge = ToolProposalBridgeService.prepare_proposal(
        tool_id=request.tool_id,
        arguments=request.arguments,
        reason=request.reason,
        source_task_id=request.source_task_id,
        requested_by=request.requested_by,
        context=request.context,
    )
    success = bridge["status"] == "prepared"
    return {
        "success": success,
        "bridge": bridge,
        "errors": []
        if success
        else [
            {
                "code": bridge.get("block_reason") or "tool_registry_proposal_blocked",
                "message": bridge.get("message") or "Tool Registry proposal bridge blocked this request.",
                "details": {
                    "tool_id": bridge.get("tool_id"),
                    "side_effect_level": bridge.get("side_effect_level"),
                },
            }
        ],
    }


@router.post("/tool-registry/proposals")
def create_tool_registry_proposal(
    request: ToolRegistryProposalBridgeRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    bridge = ToolProposalBridgeService.prepare_proposal(
        tool_id=request.tool_id,
        arguments=request.arguments,
        reason=request.reason,
        source_task_id=request.source_task_id,
        requested_by=request.requested_by,
        context=request.context,
    )
    if bridge["status"] != "prepared":
        return {
            "success": False,
            "bridge": bridge,
            "errors": [
                {
                    "code": bridge.get("block_reason") or "tool_registry_proposal_blocked",
                    "message": bridge.get("message") or "Tool Registry proposal bridge blocked this request.",
                    "details": {
                        "tool_id": bridge.get("tool_id"),
                        "side_effect_level": bridge.get("side_effect_level"),
                    },
                }
            ],
        }

    try:
        proposal = EditorOperationService(db).create_operation_proposal(
            EditorOperationProposalRequest(**bridge["proposal_request"])
        )
    except EditorOperationValidationError as exc:
        raise APIError(400, exc.reason, "Invalid editor operation proposal request.", exc.details) from exc
    return {"success": True, "bridge": bridge, "proposal": proposal, "errors": []}


@router.post("/tools/{tool_name}/call")
def call_mcp_tool(
    tool_name: str,
    request: MCPToolCallRequest,
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    result = MCPToolExecutor(settings).call_readonly_tool(tool_name, request.arguments)
    return {"success": bool(result.get("ok")), **result}
