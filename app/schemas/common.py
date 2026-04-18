from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

TaskStatus = Literal[
    "accepted",
    "running",
    "waiting_confirmation",
    "completed",
    "failed",
    "cancelled",
]
IntentType = Literal["casual_chat", "project_qa", "task_request", "mixed_request", "ambiguous"]
KnowledgeRelevance = Literal["strong", "possible", "none"]
RouteType = Literal[
    "direct_answer",
    "project_qa",
    "single_tool",
    "workflow",
    "proposal_wait",
    "fallback",
]
LanguageSource = Literal["latest_user_message", "session_preference", "explicit_override", "default"]


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class TaskDescriptor(BaseModel):
    task_id: str
    run_id: str
    task_type: str
    status: TaskStatus
    trace_id: str
    output_complete: bool = True
    finish_reason: str = "completed"


class IntentDescriptor(BaseModel):
    intent_type: IntentType
    knowledge_relevance: KnowledgeRelevance
    requires_rag: bool = False
    requires_tool: bool = False
    route_type: RouteType
    reason: str


class LocaleDescriptor(BaseModel):
    detected_input_language: str
    preferred_output_language: str
    final_output_language: str
    language_source: LanguageSource


class UserViewBlock(BaseModel):
    block_type: str
    title: str | None = None
    text: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class CitationPreview(BaseModel):
    title: str
    source: str
    snippet: str | None = None


class QuickAction(BaseModel):
    action_id: str
    label: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ArtifactDescriptor(BaseModel):
    artifact_id: str
    artifact_type: str
    label: str
    path: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class UserView(BaseModel):
    title: str
    text: str
    blocks: list[UserViewBlock] = Field(default_factory=list)
    citations_preview: list[CitationPreview] = Field(default_factory=list)
    quick_actions: list[QuickAction] = Field(default_factory=list)
    status_hint: str | None = None


class DebugView(BaseModel):
    raw_request: dict[str, Any] = Field(default_factory=dict)
    normalized_request: dict[str, Any] = Field(default_factory=dict)
    intent: dict[str, Any] = Field(default_factory=dict)
    route: dict[str, Any] = Field(default_factory=dict)
    retrieval: dict[str, Any] = Field(default_factory=dict)
    retrieval_summary: dict[str, Any] = Field(default_factory=dict)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    step_results: list[dict[str, Any]] = Field(default_factory=list)
    raw_result: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    trace_links: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    session_summary: dict[str, Any] = Field(default_factory=dict)
    memory_summary: dict[str, Any] = Field(default_factory=dict)
    output_complete: bool = True
    finish_reason: str = "completed"
    warnings: list[str] = Field(default_factory=list)


class Presentation(BaseModel):
    user_title: str
    user_text: str


class UsageSummary(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    latency_ms: int = 0


class StepResult(BaseModel):
    step_id: str
    title: str
    status: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class ActionProposal(BaseModel):
    proposal_id: str
    title: str
    proposal_type: str
    before_summary: str | None = None
    after_summary: str | None = None
    rationale: str | None = None
    risk_flags: str = "LOW"
    dry_run_preview: dict[str, Any] = Field(default_factory=dict)
    display_hints: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = True
    confirmation: dict[str, Any] = Field(default_factory=dict)
