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
    content: str | None = None
    title: str | None = None
    domain: str | None = None
    project_id: str | None = None
    doc_type: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProposalDecisionRequest(BaseModel):
    decision: Literal["confirmed", "rejected"]
    actor: str | None = None
    comment: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EditorOperationProposalRequest(BaseModel):
    operation_type: Literal[
        "rename_selected_asset",
        "apply_static_mesh_basic_settings",
        "create_blueprint_asset",
        "add_blueprint_variable",
        "add_blueprint_component",
        "create_blueprint_event_stub",
        "add_blueprint_node_template",
        "connect_blueprint_nodes",
        "compile_blueprint",
        "batch_rename_assets",
        "move_assets",
        "duplicate_asset",
        "fixup_redirectors",
        "add_umg_widget",
        "set_umg_widget_text",
        "set_umg_widget_layout",
        "set_umg_widget_visibility",
        "set_umg_widget_appearance",
        "set_umg_widget_brush",
        "set_umg_slot_layout_v2",
        "reparent_umg_widget",
        "duplicate_umg_widget",
        "delete_umg_widget",
        "place_actor_in_level",
        "select_level_actors",
        "set_actor_folder",
        "set_actor_tags",
        "set_actor_transform",
        "set_actor_metadata",
        "arrange_actors_pattern",
        "set_material_instance_parameter",
        "set_material_instance_texture_parameter",
        "set_material_instance_static_switch",
    ]
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    source_task_id: str | None = None
    requested_by: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class EditorOperationResultRequest(BaseModel):
    proposal_id: str
    operation_type: str | None = None
    execution_state: Literal["completed", "failed", "blocked", "cancelled"] = "completed"
    success: bool = False
    executed_by: str | None = None
    transaction_id: str | None = None
    undo_hint: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    errors: list[dict[str, Any]] = Field(default_factory=list)
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


class ProjectInventorySnapshotRequest(BaseModel):
    project_id: str | None = None
    project_name: str | None = None
    snapshot_id: str | None = None
    snapshot_time: str | None = None
    mode: Literal["full", "incremental"] = "full"
    source: str = "ue_plugin"
    plugin_version: str | None = None
    assets: list[dict[str, Any]] = Field(default_factory=list)
    code_files: list[dict[str, Any]] = Field(default_factory=list)
    level_actors: list[dict[str, Any]] = Field(default_factory=list)
    material_instances: list[dict[str, Any]] = Field(default_factory=list)
    scan_diagnostics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectInventoryQueryRequest(BaseModel):
    query: str
    project_id: str | None = None
    asset_path: str | None = None
    asset_type: str | None = None
    fields: list[str] = Field(default_factory=list)
    selected_assets: list[str] = Field(default_factory=list)
    selected_actor_references: list[str] = Field(default_factory=list)
    current_actor_reference: str | None = None
    selected_material_instance_paths: list[str] = Field(default_factory=list)
    current_material_instance_path: str | None = None
    limit: int = Field(default=20, ge=1, le=200)


class WebMemorySearchRequest(BaseModel):
    query: str
    domain_hints: list[str] = Field(default_factory=list)
    limit: int = Field(default=5, ge=1, le=20)


class WebMemoryFeedbackRequest(BaseModel):
    rating: Literal["helpful", "unhelpful"]
    task_id: str | None = None
    comment: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
