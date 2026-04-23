from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import (
    ActionProposal,
    ArtifactDescriptor,
    DebugView,
    ErrorDetail,
    IntentDescriptor,
    LocaleDescriptor,
    Presentation,
    StepResult,
    TaskDescriptor,
    UsageSummary,
    UserView,
)


class UnifiedTaskResponse(BaseModel):
    success: bool
    task: TaskDescriptor
    intent: IntentDescriptor
    locale: LocaleDescriptor
    user_view: UserView
    debug_view: DebugView
    presentation: Presentation
    assistant_message: str
    data: dict[str, Any] = Field(default_factory=dict)
    usage: UsageSummary = Field(default_factory=UsageSummary)
    trace_summary: dict[str, Any] = Field(default_factory=dict)
    retrieval_trace: dict[str, Any] = Field(default_factory=dict)
    planner_diagnostics: dict[str, Any] = Field(default_factory=dict)
    step_results: list[StepResult] = Field(default_factory=list)
    action_proposals: list[ActionProposal] = Field(default_factory=list)
    errors: list[ErrorDetail] = Field(default_factory=list)


class HealthResponse(BaseModel):
    success: bool
    service_status: str
    version: str
    environment: str
    database: dict[str, Any] = Field(default_factory=dict)
    storage: dict[str, Any] = Field(default_factory=dict)
    observability: dict[str, Any] = Field(default_factory=dict)
    errors: list[ErrorDetail] = Field(default_factory=list)


class CapabilitiesResponse(BaseModel):
    success: bool
    capabilities: dict[str, Any]
    errors: list[ErrorDetail] = Field(default_factory=list)


class BootstrapResponse(BaseModel):
    success: bool
    service_status: str
    version: str
    capabilities: dict[str, Any]
    supported_languages: list[str]
    default_profile: dict[str, Any]
    knowledge_base_summary: dict[str, Any]
    ui_recommendations: dict[str, Any]
    errors: list[ErrorDetail] = Field(default_factory=list)


class SettingsSnapshotResponse(BaseModel):
    success: bool
    settings: dict[str, Any]
    errors: list[ErrorDetail] = Field(default_factory=list)


class RuntimeProfilesResponse(BaseModel):
    success: bool
    active_profile_id: str | None = None
    default_profile_id: str | None = None
    profiles: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[ErrorDetail] = Field(default_factory=list)


class TasksRecentResponse(BaseModel):
    success: bool
    items: list[UnifiedTaskResponse] = Field(default_factory=list)
    errors: list[ErrorDetail] = Field(default_factory=list)


class TraceResponse(BaseModel):
    success: bool
    task_id: str
    trace_summary: dict[str, Any]
    step_results: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[ErrorDetail] = Field(default_factory=list)


class ArtifactListResponse(BaseModel):
    success: bool
    task_id: str
    items: list[ArtifactDescriptor] = Field(default_factory=list)
    errors: list[ErrorDetail] = Field(default_factory=list)


class KnowledgeBaseStatusResponse(BaseModel):
    success: bool
    summary: dict[str, Any]
    errors: list[ErrorDetail] = Field(default_factory=list)


class KnowledgeBaseJobResponse(BaseModel):
    success: bool
    job: dict[str, Any]
    errors: list[ErrorDetail] = Field(default_factory=list)


class KnowledgeBaseDocumentsResponse(BaseModel):
    success: bool
    items: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[ErrorDetail] = Field(default_factory=list)


class KnowledgeBaseDocumentResponse(BaseModel):
    success: bool
    item: dict[str, Any]
    errors: list[ErrorDetail] = Field(default_factory=list)


class ProjectInventorySnapshotResponse(BaseModel):
    success: bool
    snapshot: dict[str, Any]
    errors: list[ErrorDetail] = Field(default_factory=list)


class ProjectInventorySummaryResponse(BaseModel):
    success: bool
    summary: dict[str, Any]
    errors: list[ErrorDetail] = Field(default_factory=list)


class ProjectInventoryItemsResponse(BaseModel):
    success: bool
    items: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    errors: list[ErrorDetail] = Field(default_factory=list)


class ProjectInventoryItemResponse(BaseModel):
    success: bool
    item: dict[str, Any]
    errors: list[ErrorDetail] = Field(default_factory=list)


class ProjectInventoryQueryResponse(BaseModel):
    success: bool
    query: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    errors: list[ErrorDetail] = Field(default_factory=list)


class ProposalListResponse(BaseModel):
    success: bool
    items: list[ActionProposal] = Field(default_factory=list)
    errors: list[ErrorDetail] = Field(default_factory=list)


class ProposalDetailResponse(BaseModel):
    success: bool
    item: ActionProposal
    task: dict[str, Any] = Field(default_factory=dict)
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[ErrorDetail] = Field(default_factory=list)


class ProposalDecisionResponse(BaseModel):
    success: bool
    item: dict[str, Any]
    proposal: ActionProposal | None = None
    errors: list[ErrorDetail] = Field(default_factory=list)


class AlertsResponse(BaseModel):
    success: bool
    summary: dict[str, Any] = Field(default_factory=dict)
    items: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[ErrorDetail] = Field(default_factory=list)


class SessionResponse(BaseModel):
    success: bool
    item: dict[str, Any] = Field(default_factory=dict)
    errors: list[ErrorDetail] = Field(default_factory=list)


class SessionHistoryResponse(BaseModel):
    success: bool
    session_id: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[ErrorDetail] = Field(default_factory=list)


class SessionTasksResponse(BaseModel):
    success: bool
    session_id: str
    items: list[UnifiedTaskResponse] = Field(default_factory=list)
    errors: list[ErrorDetail] = Field(default_factory=list)


class CodeReviewFileListResponse(BaseModel):
    success: bool
    project_root: str
    source_roots: list[str] = Field(default_factory=list)
    extensions: list[str] = Field(default_factory=list)
    query: str = ""
    items: list[dict[str, Any]] = Field(default_factory=list)
    total_count: int = 0
    returned_count: int = 0
    truncated: bool = False
    scan_diagnostics: dict[str, Any] = Field(default_factory=dict)
    errors: list[ErrorDetail] = Field(default_factory=list)
