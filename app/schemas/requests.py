from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SessionMessageInput(BaseModel):
    role: Literal["system", "user", "assistant", "tool"] = "user"
    content: str
    language: str = "auto"


class SessionInput(BaseModel):
    session_id: str
    messages: list[SessionMessageInput] = Field(default_factory=list)


class ContextInput(BaseModel):
    project_root: str | None = None
    project_name: str | None = None
    active_panel: str | None = None
    selected_assets: list[str] = Field(default_factory=list)
    current_file: str | None = None
    current_module: str | None = None
    recent_open_files: list[str] = Field(default_factory=list)
    selected_panel: str | None = None
    editor_state: dict[str, Any] = Field(default_factory=dict)
    kb_domains_hint: list[str] = Field(default_factory=list)
    user_timezone: str | None = None


class UIStateInput(BaseModel):
    active_view: Literal["user", "debug"] = "user"
    selected_panel: str | None = None


class RuntimeOptionsInput(BaseModel):
    profile_id: str = "default"
    stream: bool = False
    debug: bool = True
    preferred_output_language: str = "auto"
    return_debug_projection: bool = True


class UnifiedTaskRequest(BaseModel):
    task_type: str = "agent_chat"
    session: SessionInput
    context: ContextInput = Field(default_factory=ContextInput)
    payload: dict[str, Any] = Field(default_factory=dict)
    ui_state: UIStateInput = Field(default_factory=UIStateInput)
    runtime_options: RuntimeOptionsInput = Field(default_factory=RuntimeOptionsInput)


class KnowledgeBaseRefreshRequest(BaseModel):
    source_paths: list[str] = Field(default_factory=list)
    force_rebuild: bool = False


class KnowledgeBaseImportRequest(BaseModel):
    source_type: Literal["paths", "text"] = "paths"
    source_paths: list[str] = Field(default_factory=list)
    text: str | None = None
    title: str | None = None
    domain: str | None = None
    project_id: str | None = None


class ProposalDecisionRequest(BaseModel):
    decision: Literal["confirmed", "rejected"]
    actor: str | None = None
    comment: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionCreateRequest(BaseModel):
    session_id: str
    project_name: str | None = None
    preferred_output_language: str | None = None
    profile_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CodeReviewFileListRequest(BaseModel):
    project_root: str
    source_roots: list[str] = Field(default_factory=lambda: ["Source", "Plugins"])
    extensions: list[str] = Field(
        default_factory=lambda: [".h", ".hpp", ".hh", ".inl", ".c", ".cc", ".cpp", ".cxx", ".cs"]
    )
    query: str | None = None
    limit: int = Field(default=200, ge=1, le=5000)
