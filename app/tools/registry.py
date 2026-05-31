from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any

from app.skills.registry import PRIMARY_TOOL_ID_BY_TASK_TYPE
from app.tools.config_loader import load_tool_config_overlay, reload_tool_config_overlay

TOOL_PROTOCOL_VERSION = "tool_protocol_v2"
TOOL_CATEGORIES = {"context", "sensing", "retrieval", "analysis", "generation", "write"}
TOOL_TRANSPORTS = {"local_python", "http", "mcp_stdio", "mcp_tcp", "mcp_http"}
SIDE_EFFECT_LEVELS = {"read_only", "plan_only", "confirmed_write", "reversible_write", "destructive_write"}
CONFIRMATION_SIDE_EFFECT_LEVELS = {"confirmed_write", "reversible_write", "destructive_write"}
ROUTE_PREFERENCES = {"project_qa", "single_tool", "workflow", "proposal_wait"}
CONTEXT_COST_LEVELS = {"low", "medium", "high"}
TOOL_TIERS = {"core", "extended", "experimental"}
SAFE_OVERLAY_FIELDS = {
    "enabled",
    "title",
    "description",
    "category",
    "trigger_keywords",
    "allowed_in_free_chat",
    "context_cost",
    "tier",
}
UNSAFE_OVERLAY_FIELDS = {
    "tool_id",
    "task_type",
    "side_effect_level",
    "route_preference",
    "transport",
    "requires_confirmation",
    "active_context_keys",
    "owned_by_skill",
    "permission_gate",
    "mcp_tool_name",
    "requires_retrieval",
    "required_payload_fields",
    "optional_payload_fields",
    "timeout_ms",
    "executor",
    "input_schema",
    "output_schema",
}

TOOL_EXECUTION_POLICY = {
    "free_chat_auto_execute": "read_only_only",
    "plan_only_behavior": "return_proposal_or_draft_without_side_effects",
    "confirmed_write_behavior": "requires_frontend_confirmation_and_backend_safety_check",
    "reversible_write_behavior": "requires_frontend_confirmation; expected to provide undo or rollback hint",
    "destructive_write_behavior": "requires_explicit_frontend_confirmation and should expose strongest warning copy",
    "explicit_panel_behavior": "use_skill_owned_tools_before_llm_free_tool_selection",
    "debug_contract": [
        "tool_id",
        "transport",
        "side_effect_level",
        "input_summary",
        "output_summary",
        "latency_ms",
        "status",
        "approval_state",
    ],
}


@dataclass(frozen=True, slots=True)
class ToolSpec:
    tool_id: str
    task_type: str
    title: str
    description: str
    side_effect_level: str
    route_preference: str
    category: str = "analysis"
    transport: str = "local_python"
    requires_confirmation: bool = False
    active_context_keys: tuple[str, ...] = ()
    owned_by_skill: str | None = None
    allowed_in_free_chat: bool = False
    permission_gate: str = "none"
    mcp_tool_name: str | None = None
    context_cost: str = "medium"
    requires_retrieval: bool = False
    trigger_keywords: tuple[str, ...] = ()
    required_payload_fields: tuple[str, ...] = ()
    optional_payload_fields: tuple[str, ...] = ()
    timeout_ms: int = 30_000
    executor: str | None = None
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    tier: str = "core"
    config_source: str = "builtin"
    config_warnings: tuple[str, ...] = ()

    def capability_card(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "task_type": self.task_type,
            "title": self.title,
            "description": self.description,
            "protocol_version": TOOL_PROTOCOL_VERSION,
            "category": self.category,
            "transport": self.transport,
            "side_effect_level": self.side_effect_level,
            "requires_confirmation": self.effective_requires_confirmation,
            "active_context_keys": list(self.active_context_keys),
            "owned_by_skill": self.owned_by_skill,
            "allowed_in_free_chat": self.allowed_in_free_chat,
            "permission_gate": self.permission_gate,
            "mcp_tool_name": self.mcp_tool_name,
            "context_cost": self.context_cost,
            "route_preference": self.route_preference,
            "requires_retrieval": self.requires_retrieval,
            "trigger_keywords": list(self.trigger_keywords),
            "required_payload_fields": list(self.required_payload_fields),
            "optional_payload_fields": list(self.optional_payload_fields),
            "timeout_ms": self.timeout_ms,
            "executor": self.executor,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "enabled": self.enabled,
            "tier": self.tier,
            "config_source": self.config_source,
            "config_warnings": list(self.config_warnings),
        }

    @property
    def effective_requires_confirmation(self) -> bool:
        return self.requires_confirmation or self.side_effect_level in CONFIRMATION_SIDE_EFFECT_LEVELS

    def debug_policy_card(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "title": self.title,
            "category": self.category,
            "transport": self.transport,
            "side_effect_level": self.side_effect_level,
            "requires_confirmation": self.effective_requires_confirmation,
            "active_context_keys": list(self.active_context_keys),
            "owned_by_skill": self.owned_by_skill,
            "allowed_in_free_chat": self.allowed_in_free_chat,
            "permission_gate": self.permission_gate,
            "executor": self.executor,
            "enabled": self.enabled,
            "tier": self.tier,
            "config_source": self.config_source,
            "config_warnings": list(self.config_warnings),
        }


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "retrieve_project_knowledge": ToolSpec(
        tool_id="retrieve_project_knowledge",
        task_type="project_qa",
        title="Project Knowledge Retrieval",
        description="Retrieve project-specific evidence from the knowledge base.",
        side_effect_level="read_only",
        route_preference="project_qa",
        category="retrieval",
        active_context_keys=("project", "kb"),
        owned_by_skill="ProjectQASkill",
        allowed_in_free_chat=True,
        permission_gate="read_only_whitelist",
        context_cost="medium",
        requires_retrieval=True,
        trigger_keywords=(
            "knowledge base",
            "kb",
            "docs",
            "documentation",
            "project docs",
            "知识库",
            "文档",
            "项目文档",
        ),
        required_payload_fields=("user_query",),
        optional_payload_fields=("domain_filters", "kb_domains_hint"),
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "user_query": {"type": "string"},
                "domain_filters": {"type": "array", "items": {"type": "string"}},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 20},
            },
        },
        output_schema={
            "type": "object",
            "required": ["retrieved_docs", "retrieval_trace"],
            "properties": {
                "retrieved_docs": {"type": "array"},
                "retrieval_trace": {"type": "object"},
                "confidence": {"type": "number"},
            },
        },
    ),
    "web_search_knowledge": ToolSpec(
        tool_id="web_search_knowledge",
        task_type="project_qa",
        title="Controlled Web Search",
        description=(
            "Search limited public web evidence when local project knowledge is insufficient "
            "or the user explicitly asks for online/official documentation evidence."
        ),
        side_effect_level="read_only",
        route_preference="project_qa",
        category="retrieval",
        active_context_keys=("web", "kb"),
        owned_by_skill="ProjectQASkill",
        allowed_in_free_chat=True,
        permission_gate="read_only_web_budget",
        context_cost="medium",
        requires_retrieval=True,
        trigger_keywords=(
            "web search",
            "search web",
            "online search",
            "official docs",
            "latest docs",
            "look up",
            "上网查",
            "联网查",
            "搜一下",
            "搜索一下",
            "官方文档",
            "最新文档",
        ),
        required_payload_fields=("query",),
        optional_payload_fields=("domain_hints", "language", "trigger_reason", "max_results"),
        timeout_ms=10_000,
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "domain_hints": {"type": "array", "items": {"type": "string"}},
                "language": {"type": "string"},
                "trigger_reason": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
            },
        },
        output_schema={
            "type": "object",
            "required": ["items", "summary"],
            "properties": {
                "items": {"type": "array"},
                "summary": {"type": "object"},
                "status": {"type": "string"},
                "reason": {"type": "string"},
                "budget": {"type": "object"},
            },
        },
    ),
    "recall_web_memory": ToolSpec(
        tool_id="recall_web_memory",
        task_type="project_qa",
        title="Web Memory Recall",
        description=(
            "Recall previously stored controlled Web Search summaries without performing a new web request. "
            "The tool returns URL/domain/snippet metadata only and never writes to the knowledge base."
        ),
        side_effect_level="read_only",
        route_preference="project_qa",
        category="retrieval",
        active_context_keys=("web", "memory", "kb"),
        owned_by_skill="ProjectQASkill",
        allowed_in_free_chat=True,
        permission_gate="read_only_local_memory",
        context_cost="low",
        requires_retrieval=True,
        trigger_keywords=(
            "web memory",
            "cached docs",
            "previous web search",
            "history docs",
            "鍘嗗彶鎼滅储",
            "缂撳瓨鏂囨。",
        ),
        required_payload_fields=("query",),
        optional_payload_fields=("domain_hints", "limit"),
        timeout_ms=3_000,
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "domain_hints": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
        },
        output_schema={
            "type": "object",
            "required": ["items", "summary"],
            "properties": {
                "items": {"type": "array"},
                "summary": {"type": "object"},
                "status": {"type": "string"},
                "reason": {"type": "string"},
            },
        },
    ),
    "query_project_inventory": ToolSpec(
        tool_id="query_project_inventory",
        task_type="project_qa",
        title="Project Inventory Query",
        description="Query the latest submitted project inventory snapshot for assets, code files, and UE metadata.",
        side_effect_level="read_only",
        route_preference="project_qa",
        category="sensing",
        active_context_keys=("project", "asset", "code", "level", "actor", "material"),
        owned_by_skill="ProjectQASkill",
        allowed_in_free_chat=True,
        permission_gate="read_only_whitelist",
        context_cost="low",
        requires_retrieval=False,
        trigger_keywords=(
            "current project assets",
            "project assets",
            "blueprint assets",
            "static mesh",
            "nanite",
            "asset settings",
            "level actors",
            "current level actors",
            "level objects",
            "scene objects",
            "material instance parameters",
            "material parameters",
            "roughness",
            "code files",
            "modules",
            "当前项目",
            "当前工程",
            "项目资产",
            "蓝图资产",
            "静态网格体",
            "资产属性",
            "关卡对象",
            "场景对象",
            "材质实例参数",
            "材质参数",
            "代码文件",
            "模块",
        ),
        required_payload_fields=("user_query",),
        optional_payload_fields=("project_id", "asset_path", "asset_type", "fields", "limit"),
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "user_query": {"type": "string"},
                "project_id": {"type": "string"},
                "asset_path": {"type": "string"},
                "asset_type": {"type": "string"},
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional field names such as components, variables, parent_class, nanite_enabled, lod_count, dependencies, module_name, actor_class, transform, parent_material, parameters.",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        },
        output_schema={
            "type": "object",
            "required": ["items", "summary"],
            "properties": {
                "items": {"type": "array"},
                "summary": {"type": "object"},
            },
        },
    ),
    "read_project_file": ToolSpec(
        tool_id="read_project_file",
        task_type="project_qa",
        title="Read Project File",
        description="Read a small text/code file from the current UE project root for project QA synthesis.",
        side_effect_level="read_only",
        route_preference="project_qa",
        category="context",
        active_context_keys=("project", "code"),
        owned_by_skill="ProjectQASkill",
        allowed_in_free_chat=True,
        permission_gate="project_root_read_only",
        context_cost="high",
        requires_retrieval=False,
        trigger_keywords=(
            "this file",
            "current file",
            "read file",
            "open file",
            "当前文件",
            "这个文件",
            "读取文件",
            "查看文件",
        ),
        required_payload_fields=("project_root", "file_path"),
        optional_payload_fields=("current_file", "max_bytes"),
        timeout_ms=10_000,
        executor="app.tools.project_file:read_project_file_executor",
        input_schema={
            "type": "object",
            "required": ["project_root", "file_path"],
            "properties": {
                "project_root": {"type": "string"},
                "file_path": {"type": "string"},
                "max_bytes": {"type": "integer", "minimum": 1024, "maximum": 120000},
            },
        },
        output_schema={
            "type": "object",
            "required": ["status", "reason", "file_path"],
            "properties": {
                "status": {"type": "string"},
                "reason": {"type": "string"},
                "file_path": {"type": "string"},
                "resolved_path": {"type": "string"},
                "bytes_read": {"type": "integer"},
                "truncated": {"type": "boolean"},
                "text_excerpt": {"type": "string"},
            },
        },
    ),
    "multi_agent_code_review_and_fix": ToolSpec(
        tool_id="multi_agent_code_review_and_fix",
        task_type="code_review",
        title="Multi-Agent Review / Fix / Validate Chain",
        description=(
            "Run a lightweight non-destructive chain: review selected UE C++ code, "
            "draft fixes when findings pass the threshold, then validate the draft."
        ),
        side_effect_level="plan_only",
        route_preference="workflow",
        category="analysis",
        active_context_keys=("project", "code", "kb"),
        owned_by_skill="CodeReviewSkill",
        allowed_in_free_chat=False,
        permission_gate="draft_only",
        context_cost="high",
        requires_retrieval=True,
        trigger_keywords=(
            "review and fix",
            "fix review issues",
            "auto fix",
            "review fix validate",
            "审查并修复",
            "检查并修复",
            "自动修复",
        ),
        required_payload_fields=("user_query",),
        optional_payload_fields=(
            "files",
            "file_paths",
            "diff_text",
            "code_text",
            "project_root",
            "workflow_mode",
            "enable_multi_agent",
        ),
        timeout_ms=90_000,
        input_schema={
            "type": "object",
            "required": ["user_query"],
            "properties": {
                "user_query": {"type": "string"},
                "files": {"type": "array", "items": {"type": "object"}},
                "file_paths": {"type": "array", "items": {"type": "string"}},
                "diff_text": {"type": "string"},
                "code_text": {"type": "string"},
                "workflow_mode": {"type": "string"},
                "enable_multi_agent": {"type": "boolean"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["multi_agent", "review_phase", "validate_phase"],
            "properties": {
                "multi_agent": {"type": "object"},
                "review_phase": {"type": "object"},
                "generate_phase": {"type": "object"},
                "validate_phase": {"type": "object"},
                "generated_items": {"type": "array"},
            },
        },
    ),
    "review_ue_cpp_files": ToolSpec(
        tool_id="review_ue_cpp_files",
        task_type="code_review",
        title="UE C++ Code Review",
        description="Scan UE C++ code or diffs for lifecycle, threading, loading, and boundary issues.",
        side_effect_level="read_only",
        route_preference="workflow",
        category="analysis",
        active_context_keys=("project", "code", "kb"),
        owned_by_skill="CodeReviewSkill",
        permission_gate="read_only_panel_scope",
        context_cost="high",
        requires_retrieval=True,
        trigger_keywords=("code review", "review", "审查", "代码审查"),
        required_payload_fields=("user_query",),
        optional_payload_fields=("files", "file_paths", "diff_text", "code_text", "project_root"),
        executor="app.tools.code_review:review_ue_cpp_files_executor",
        input_schema={
            "type": "object",
            "required": ["user_query"],
            "properties": {
                "user_query": {"type": "string"},
                "files": {"type": "array", "items": {"type": "object"}},
                "file_paths": {"type": "array", "items": {"type": "string"}},
                "diff_text": {"type": "string"},
                "code_text": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["issue_list", "summary"],
            "properties": {"issue_list": {"type": "array"}, "summary": {"type": "object"}},
        },
    ),
    "generate_code_draft": ToolSpec(
        tool_id="generate_code_draft",
        task_type="code_generate",
        title="Code Draft Generation",
        description="Generate a code draft and file layout suggestions without writing to the project.",
        side_effect_level="plan_only",
        route_preference="single_tool",
        category="generation",
        active_context_keys=("project", "code", "kb"),
        owned_by_skill="CodeGenerateSkill",
        permission_gate="draft_only",
        context_cost="high",
        requires_retrieval=True,
        trigger_keywords=("code generate", "generate code", "生成代码", "代码生成"),
        required_payload_fields=("user_query",),
        optional_payload_fields=("module_name", "class_name", "preferred_paths"),
        input_schema={
            "type": "object",
            "required": ["user_query"],
            "properties": {
                "user_query": {"type": "string"},
                "module_name": {"type": "string"},
                "class_name": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["generated_items"],
            "properties": {"generated_items": {"type": "array"}},
        },
    ),
    "preflight_generated_code": ToolSpec(
        tool_id="preflight_generated_code",
        task_type="code_generate",
        title="Generated Code Preflight",
        description="Run lightweight UE C++ static checks on generated code drafts before adoption.",
        side_effect_level="read_only",
        route_preference="single_tool",
        category="analysis",
        active_context_keys=("project", "code"),
        owned_by_skill="CodeGenerateSkill",
        permission_gate="read_only_generated_draft",
        context_cost="low",
        requires_retrieval=False,
        trigger_keywords=("preflight code", "validate generated code", "check generated code"),
        required_payload_fields=("generated_items",),
        executor="app.tools.code_preflight:preflight_generated_code_executor",
        input_schema={
            "type": "object",
            "required": ["generated_items"],
            "properties": {
                "generated_items": {"type": "array", "items": {"type": "object"}},
                "requirement": {"type": "string"},
                "target_module": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["preflight_report"],
            "properties": {"preflight_report": {"type": "object"}},
        },
    ),
    "write_code_files": ToolSpec(
        tool_id="write_code_files",
        task_type="code_generate",
        title="Confirmed Code File Write",
        description="Write generated code files into a UE project only after proposal confirmation and path safety checks.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        requires_confirmation=True,
        active_context_keys=("project", "code"),
        owned_by_skill="CodeGenerateSkill",
        permission_gate="proposal_confirmed_project_root_write",
        context_cost="high",
        requires_retrieval=False,
        trigger_keywords=("write generated code", "apply generated code", "写入生成代码", "应用生成代码"),
        required_payload_fields=("write_plan",),
        input_schema={
            "type": "object",
            "required": ["write_plan"],
            "properties": {
                "write_plan": {"type": "object"},
                "proposal_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["execution_state", "written_to_disk"],
            "properties": {
                "execution_state": {"type": "string"},
                "written_to_disk": {"type": "boolean"},
                "written_files": {"type": "array"},
                "blocked_files": {"type": "array"},
            },
        },
    ),
    "analyze_ue_log": ToolSpec(
        tool_id="analyze_ue_log",
        task_type="logs_analyze",
        title="UE Log Analysis",
        description="Parse logs, extract signatures, and summarize likely failure families.",
        side_effect_level="read_only",
        route_preference="workflow",
        category="analysis",
        active_context_keys=("project", "log", "kb"),
        owned_by_skill="LogsAnalyzeSkill",
        permission_gate="read_only_panel_scope",
        context_cost="high",
        requires_retrieval=True,
        trigger_keywords=("analyze log", "logs", "log", "日志", "日志分析"),
        optional_payload_fields=(
            "log_text",
            "selected_log_text",
            "log_excerpt",
            "error_lines",
            "log_file_path",
            "attachment_paths",
        ),
        executor="app.tools.log_analysis:analyze_ue_log_executor",
        input_schema={
            "type": "object",
            "properties": {
                "log_text": {"type": "string"},
                "log_file_path": {"type": "string"},
                "selected_log_text": {"type": "string"},
                "attachment_paths": {"type": "array", "items": {"type": "string"}},
            },
        },
        output_schema={
            "type": "object",
            "required": ["findings", "structured_events"],
            "properties": {
                "findings": {"type": "array"},
                "structured_events": {"type": "array"},
            },
        },
    ),
    "generate_design_config": ToolSpec(
        tool_id="generate_design_config",
        task_type="config_generate",
        title="Config Generation",
        description="Generate a structured config draft from requirements, schemas, and examples.",
        side_effect_level="plan_only",
        route_preference="workflow",
        category="generation",
        active_context_keys=("project", "kb"),
        permission_gate="draft_only",
        requires_retrieval=True,
        trigger_keywords=("config generate", "generate config", "生成配置"),
        required_payload_fields=("user_query",),
    ),
    "validate_design_config": ToolSpec(
        tool_id="validate_design_config",
        task_type="config_validate",
        title="Config Validation",
        description="Validate a config payload against a schema and emit structured diagnostics.",
        side_effect_level="read_only",
        route_preference="single_tool",
        category="analysis",
        active_context_keys=("project",),
        permission_gate="read_only_panel_scope",
        requires_retrieval=False,
        trigger_keywords=("validate config", "config validate", "校验配置"),
        required_payload_fields=("schema", "config_json"),
        executor="app.tools.config_validate:validate_design_config_executor",
        input_schema={
            "type": "object",
            "required": ["schema", "config_json"],
            "properties": {
                "schema": {"type": "object"},
                "config_json": {"type": "object"},
                "schema_body": {"type": "object"},
                "draft_config": {"type": "object"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["validation_summary", "errors", "warnings"],
            "properties": {
                "validation_summary": {"type": "object"},
                "errors": {"type": "array"},
                "warnings": {"type": "array"},
                "suggestions": {"type": "array"},
            },
        },
    ),
    "inspect_asset_metadata": ToolSpec(
        tool_id="inspect_asset_metadata",
        task_type="assets_inspect",
        title="Asset Inspection",
        description="Inspect asset naming, folder hygiene, and duplicate candidates.",
        side_effect_level="read_only",
        route_preference="single_tool",
        category="analysis",
        active_context_keys=("project", "asset", "kb"),
        owned_by_skill="AssetsInspectSkill",
        permission_gate="read_only_panel_scope",
        context_cost="medium",
        requires_retrieval=True,
        trigger_keywords=(
            "asset inspect",
            "inspect asset",
            "selected asset",
            "资产检查",
            "检查资产",
            "检查当前资产",
            "检查选中资产",
        ),
        optional_payload_fields=("assets", "selected_assets", "asset_metadata"),
        executor="app.tools.asset_inspect:inspect_asset_metadata_executor",
        input_schema={
            "type": "object",
            "properties": {
                "asset_items": {"type": "array", "items": {"type": "object"}},
                "asset_paths": {"type": "array", "items": {"type": "string"}},
                "assets": {"type": "array", "items": {"type": "object"}},
                "selected_assets": {"type": "array", "items": {"type": "string"}},
                "asset_metadata": {"type": "object"},
            },
        },
    ),
    "plan_asset_operation": ToolSpec(
        tool_id="plan_asset_operation",
        task_type="assets_plan",
        title="Asset Operation Planning",
        description="Plan asset rename or reorganization actions without executing them.",
        side_effect_level="plan_only",
        route_preference="workflow",
        category="generation",
        active_context_keys=("project", "asset", "kb"),
        permission_gate="proposal_required",
        requires_retrieval=True,
        trigger_keywords=("asset plan", "rename asset", "plan asset", "资产规划", "资产重命名"),
    ),
    "execute_asset_operation": ToolSpec(
        tool_id="execute_asset_operation",
        task_type="assets_execute",
        title="Asset Operation Execution",
        description="Execute a previously approved asset operation.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        requires_confirmation=True,
        active_context_keys=("project", "asset"),
        permission_gate="proposal_confirmed",
        requires_retrieval=False,
        trigger_keywords=("execute asset", "apply asset", "执行资产"),
    ),
    "editor_rename_asset": ToolSpec(
        tool_id="editor_rename_asset",
        task_type="editor_operation",
        title="Rename Selected Asset",
        description="Create a confirmed editor operation proposal to rename one selected UE asset.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset"),
        owned_by_skill="AssetsInspectSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        requires_retrieval=False,
        trigger_keywords=("rename selected asset", "rename asset", "重命名资产", "改名资产"),
        required_payload_fields=("asset_path", "new_name"),
        optional_payload_fields=("reason", "source_task_id"),
        input_schema={
            "type": "object",
            "required": ["asset_path", "new_name"],
            "properties": {
                "asset_path": {"type": "string"},
                "new_name": {"type": "string"},
                "reason": {"type": "string"},
                "source_task_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_batch_rename_assets": ToolSpec(
        tool_id="editor_batch_rename_assets",
        task_type="editor_operation",
        title="Batch Rename Assets",
        description="Create a confirmed editor operation proposal to rename multiple UE assets in one transaction.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset"),
        owned_by_skill="AssetsInspectSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="high",
        requires_retrieval=False,
        trigger_keywords=("batch rename assets", "rename multiple assets", "批量重命名资产", "批量改名资产"),
        required_payload_fields=("renames",),
        optional_payload_fields=("reason", "source_task_id"),
        input_schema={
            "type": "object",
            "required": ["renames"],
            "properties": {
                "renames": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["asset_path", "new_name"],
                        "properties": {
                            "asset_path": {"type": "string"},
                            "new_name": {"type": "string"},
                        },
                    },
                },
                "reason": {"type": "string"},
                "source_task_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_move_assets": ToolSpec(
        tool_id="editor_move_assets",
        task_type="editor_operation",
        title="Move Assets",
        description="Create a confirmed editor operation proposal to move multiple UE assets to one folder.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset"),
        owned_by_skill="AssetsInspectSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="high",
        requires_retrieval=False,
        trigger_keywords=("move assets", "move asset folder", "移动资产", "迁移资产"),
        required_payload_fields=("asset_paths", "target_folder"),
        optional_payload_fields=("reason", "source_task_id"),
        input_schema={
            "type": "object",
            "required": ["asset_paths", "target_folder"],
            "properties": {
                "asset_paths": {"type": "array", "items": {"type": "string"}},
                "target_folder": {"type": "string"},
                "reason": {"type": "string"},
                "source_task_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_duplicate_asset": ToolSpec(
        tool_id="editor_duplicate_asset",
        task_type="editor_operation",
        title="Duplicate Asset",
        description="Create a confirmed editor operation proposal to duplicate one UE asset to a new /Game path.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset"),
        owned_by_skill="AssetsInspectSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        requires_retrieval=False,
        trigger_keywords=("duplicate asset", "copy asset", "clone asset", "复制资产"),
        required_payload_fields=("source_asset_path", "new_name"),
        optional_payload_fields=("target_folder", "reason", "source_task_id"),
        input_schema={
            "type": "object",
            "required": ["source_asset_path", "new_name"],
            "properties": {
                "source_asset_path": {"type": "string"},
                "new_name": {"type": "string"},
                "target_folder": {"type": "string"},
                "reason": {"type": "string"},
                "source_task_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_fixup_redirectors": ToolSpec(
        tool_id="editor_fixup_redirectors",
        task_type="editor_operation",
        title="Fixup Redirectors",
        description="Create a confirmed editor operation proposal to fix redirectors under one bounded /Game folder.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset"),
        owned_by_skill="AssetsInspectSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        requires_retrieval=False,
        trigger_keywords=("fix redirectors", "fixup redirectors", "cleanup redirectors", "修复重定向器"),
        required_payload_fields=("folder_path",),
        optional_payload_fields=("recursive", "max_redirectors", "reason", "source_task_id"),
        input_schema={
            "type": "object",
            "required": ["folder_path"],
            "properties": {
                "folder_path": {"type": "string"},
                "recursive": {"type": "boolean"},
                "max_redirectors": {"type": "integer", "minimum": 1, "maximum": 200},
                "reason": {"type": "string"},
                "source_task_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_apply_static_mesh_settings": ToolSpec(
        tool_id="editor_apply_static_mesh_settings",
        task_type="editor_operation",
        title="Apply Static Mesh Basic Settings",
        description="Create a confirmed editor operation proposal to apply whitelisted Static Mesh settings.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset"),
        owned_by_skill="AssetsInspectSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        requires_retrieval=False,
        trigger_keywords=("static mesh settings", "nanite", "collision settings", "静态网格体设置", "应用nanite"),
        required_payload_fields=("asset_path", "settings"),
        optional_payload_fields=("before_snapshot", "reason", "source_task_id"),
        input_schema={
            "type": "object",
            "required": ["asset_path", "settings"],
            "properties": {
                "asset_path": {"type": "string"},
                "settings": {"type": "object"},
                "before_snapshot": {"type": "object"},
                "reason": {"type": "string"},
                "source_task_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_create_blueprint_asset": ToolSpec(
        tool_id="editor_create_blueprint_asset",
        task_type="editor_operation",
        title="Create Blueprint Asset",
        description="Create a confirmed editor operation proposal to create one Blueprint asset under /Game.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset", "code"),
        owned_by_skill="CodeGenerateSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        requires_retrieval=False,
        trigger_keywords=("create blueprint", "blueprint asset", "创建蓝图", "新建蓝图"),
        required_payload_fields=("parent_class", "target_folder", "asset_name"),
        optional_payload_fields=("reason", "source_task_id"),
        input_schema={
            "type": "object",
            "required": ["parent_class", "target_folder", "asset_name"],
            "properties": {
                "parent_class": {"type": "string"},
                "target_folder": {"type": "string"},
                "asset_name": {"type": "string"},
                "reason": {"type": "string"},
                "source_task_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_add_blueprint_variable": ToolSpec(
        tool_id="editor_add_blueprint_variable",
        task_type="editor_operation",
        title="Add Blueprint Variable",
        description="Create a confirmed editor operation proposal to add one variable to one Blueprint.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset"),
        owned_by_skill="BlueprintGraphAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        trigger_keywords=("add blueprint variable", "blueprint variable", "添加蓝图变量"),
        required_payload_fields=("blueprint_path", "variable_name", "variable_type"),
        optional_payload_fields=("category", "default_value", "editable", "expose_on_spawn"),
        input_schema={
            "type": "object",
            "required": ["blueprint_path", "variable_name", "variable_type"],
            "properties": {
                "blueprint_path": {"type": "string"},
                "variable_name": {"type": "string"},
                "variable_type": {"type": "string"},
                "category": {"type": "string"},
                "default_value": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_add_blueprint_component": ToolSpec(
        tool_id="editor_add_blueprint_component",
        task_type="editor_operation",
        title="Add Blueprint Component",
        description="Create a confirmed editor operation proposal to add one component to one Blueprint.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset"),
        owned_by_skill="BlueprintGraphAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        trigger_keywords=("add blueprint component", "blueprint component", "添加蓝图组件"),
        required_payload_fields=("blueprint_path", "component_name", "component_class"),
        optional_payload_fields=("attach_to", "transform"),
        input_schema={
            "type": "object",
            "required": ["blueprint_path", "component_name", "component_class"],
            "properties": {
                "blueprint_path": {"type": "string"},
                "component_name": {"type": "string"},
                "component_class": {"type": "string"},
                "attach_to": {"type": "string"},
                "transform": {"type": "object"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_create_blueprint_event_stub": ToolSpec(
        tool_id="editor_create_blueprint_event_stub",
        task_type="editor_operation",
        title="Create Blueprint Event Stub",
        description="Create a confirmed editor operation proposal for a small Blueprint event stub.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset"),
        owned_by_skill="BlueprintGraphAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        trigger_keywords=("blueprint event", "event graph", "蓝图事件节点"),
        required_payload_fields=("blueprint_path", "event_name"),
        optional_payload_fields=("graph_name", "node_comment"),
        input_schema={
            "type": "object",
            "required": ["blueprint_path", "event_name"],
            "properties": {
                "blueprint_path": {"type": "string"},
                "event_name": {"type": "string"},
                "graph_name": {"type": "string"},
                "node_comment": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_add_blueprint_node_template": ToolSpec(
        tool_id="editor_add_blueprint_node_template",
        task_type="editor_operation",
        title="Add Blueprint Node Template",
        description="Create a confirmed editor operation proposal to add one whitelisted Blueprint node template.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset"),
        owned_by_skill="BlueprintGraphAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        trigger_keywords=("print string node", "blueprint node template", "添加蓝图节点", "打印字符串节点"),
        required_payload_fields=("blueprint_path", "template_id"),
        optional_payload_fields=(
            "graph_name",
            "message",
            "messages",
            "duration",
            "delay_seconds",
            "print_to_screen",
            "print_to_log",
            "entry_event",
            "condition_default",
            "branch_path",
            "variable_name",
            "variable_scope",
            "variable_value",
            "function_name",
            "function_target",
            "input_action_path",
            "node_position",
            "node_comment",
            "compile_after_edit",
        ),
        input_schema={
            "type": "object",
            "required": ["blueprint_path", "template_id"],
            "properties": {
                "blueprint_path": {"type": "string"},
                "template_id": {
                    "type": "string",
                    "enum": [
                        "branch_print_string",
                        "call_function",
                        "delay_print_string",
                        "enhanced_input_action_event",
                        "get_variable",
                        "print_string",
                        "sequence_print_strings",
                        "set_variable",
                    ],
                },
                "graph_name": {"type": "string"},
                "message": {"type": "string"},
                "messages": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2},
                "duration": {"type": "number"},
                "delay_seconds": {"type": "number", "minimum": 0, "maximum": 60},
                "print_to_screen": {"type": "boolean"},
                "print_to_log": {"type": "boolean"},
                "entry_event": {"type": "string", "enum": ["BeginPlay", ""]},
                "condition_default": {"type": "boolean"},
                "branch_path": {"type": "string", "enum": ["true", "false"]},
                "variable_name": {"type": "string"},
                "variable_scope": {"type": "string", "enum": ["self"]},
                "variable_value": {"type": "string"},
                "function_name": {"type": "string"},
                "function_target": {"type": "string", "enum": ["self"]},
                "input_action_path": {"type": "string"},
                "node_position": {"type": "object"},
                "node_comment": {"type": "string"},
                "compile_after_edit": {"type": "boolean"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_connect_blueprint_nodes": ToolSpec(
        tool_id="editor_connect_blueprint_nodes",
        task_type="editor_operation",
        title="Connect Blueprint Nodes",
        description="Create a confirmed editor operation proposal to connect two explicit Blueprint pins in one graph.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset"),
        owned_by_skill="BlueprintGraphAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        trigger_keywords=("connect blueprint pins", "connect blueprint nodes", "blueprint pin link"),
        required_payload_fields=(
            "blueprint_path",
            "graph_name",
            "source_node_id",
            "source_pin_name",
            "target_node_id",
            "target_pin_name",
        ),
        optional_payload_fields=("compile_after_edit",),
        input_schema={
            "type": "object",
            "required": [
                "blueprint_path",
                "graph_name",
                "source_node_id",
                "source_pin_name",
                "target_node_id",
                "target_pin_name",
            ],
            "properties": {
                "blueprint_path": {"type": "string"},
                "graph_name": {"type": "string"},
                "source_node_id": {"type": "string"},
                "source_pin_name": {"type": "string"},
                "target_node_id": {"type": "string"},
                "target_pin_name": {"type": "string"},
                "compile_after_edit": {"type": "boolean"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_compile_blueprint": ToolSpec(
        tool_id="editor_compile_blueprint",
        task_type="editor_operation",
        title="Compile Blueprint",
        description="Create a confirmed editor operation proposal to compile one Blueprint in Unreal Editor.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset"),
        owned_by_skill="BlueprintGraphAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        trigger_keywords=("compile blueprint", "blueprint compile", "编译蓝图"),
        required_payload_fields=("blueprint_path",),
        optional_payload_fields=("compile_mode",),
        input_schema={
            "type": "object",
            "required": ["blueprint_path"],
            "properties": {
                "blueprint_path": {"type": "string"},
                "compile_mode": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "mcp_get_blueprint_graph": ToolSpec(
        tool_id="mcp_get_blueprint_graph",
        task_type="editor_operation",
        title="Get Blueprint Graph",
        description="Read Blueprint graph metadata from the optional UEAgentTool TCP tool server.",
        side_effect_level="read_only",
        route_preference="single_tool",
        category="sensing",
        transport="mcp_tcp",
        mcp_tool_name="get_blueprint_graph",
        requires_confirmation=False,
        active_context_keys=("project", "asset"),
        owned_by_skill="BlueprintGraphAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="mcp_allowed_tools",
        context_cost="medium",
        trigger_keywords=("get blueprint graph", "blueprint graph", "读取蓝图图谱"),
        required_payload_fields=("blueprint_path",),
        input_schema={
            "type": "object",
            "required": ["blueprint_path"],
            "properties": {
                "blueprint_path": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "content": {"type": "array"},
                "structuredContent": {
                    "type": "object",
                    "properties": {
                        "graph_schema_version": {"type": "string"},
                        "blueprint_path": {"type": "string"},
                        "graph_metrics": {"type": "object"},
                        "graphs": {"type": "array"},
                        "variables": {"type": "array"},
                        "components": {"type": "array"},
                    },
                },
            },
        },
    ),
    "mcp_get_widget_tree": ToolSpec(
        tool_id="mcp_get_widget_tree",
        task_type="editor_operation",
        title="Get Widget Tree",
        description="Read UMG Widget Blueprint tree metadata from the optional UEAgentTool TCP tool server.",
        side_effect_level="read_only",
        route_preference="single_tool",
        category="sensing",
        transport="mcp_tcp",
        mcp_tool_name="get_widget_tree",
        requires_confirmation=False,
        active_context_keys=("project", "asset"),
        owned_by_skill="UMGAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="mcp_allowed_tools",
        context_cost="medium",
        trigger_keywords=("get widget tree", "umg widget tree", "读取widget树", "读取控件树"),
        required_payload_fields=("widget_blueprint_path",),
        input_schema={
            "type": "object",
            "required": ["widget_blueprint_path"],
            "properties": {
                "widget_blueprint_path": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "content": {"type": "array"},
                "structuredContent": {"type": "object"},
            },
        },
    ),
    "editor_add_umg_widget": ToolSpec(
        tool_id="editor_add_umg_widget",
        task_type="editor_operation",
        title="Add UMG Widget",
        description="Create a confirmed editor operation proposal to add one simple widget to a Widget Blueprint.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset"),
        owned_by_skill="UMGAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        trigger_keywords=("add umg widget", "add widget", "添加控件", "添加umg控件"),
        required_payload_fields=("widget_blueprint_path", "widget_name", "widget_class"),
        optional_payload_fields=("parent_widget_name", "text", "is_variable"),
        input_schema={
            "type": "object",
            "required": ["widget_blueprint_path", "widget_name", "widget_class"],
            "properties": {
                "widget_blueprint_path": {"type": "string"},
                "widget_name": {"type": "string"},
                "widget_class": {"type": "string"},
                "parent_widget_name": {"type": "string"},
                "text": {"type": "string"},
                "is_variable": {"type": "boolean"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_set_umg_widget_text": ToolSpec(
        tool_id="editor_set_umg_widget_text",
        task_type="editor_operation",
        title="Set UMG Widget Text",
        description="Create a confirmed editor operation proposal to set text on one TextBlock in a Widget Blueprint.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset", "umg"),
        owned_by_skill="UMGAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        trigger_keywords=("set umg text", "set widget text", "set textblock text", "设置UMG文本"),
        required_payload_fields=("widget_blueprint_path", "widget_name", "text"),
        optional_payload_fields=("reason", "source_task_id"),
        input_schema={
            "type": "object",
            "required": ["widget_blueprint_path", "widget_name", "text"],
            "properties": {
                "widget_blueprint_path": {"type": "string"},
                "widget_name": {"type": "string"},
                "text": {"type": "string"},
                "reason": {"type": "string"},
                "source_task_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_set_umg_widget_layout": ToolSpec(
        tool_id="editor_set_umg_widget_layout",
        task_type="editor_operation",
        title="Set UMG Widget Layout",
        description="Create a confirmed editor operation proposal to set CanvasPanelSlot layout fields on one UMG widget.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset", "umg"),
        owned_by_skill="UMGAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        trigger_keywords=("set umg layout", "set widget position", "set widget size", "设置UMG布局"),
        required_payload_fields=("widget_blueprint_path", "widget_name", "layout"),
        optional_payload_fields=("reason", "source_task_id"),
        input_schema={
            "type": "object",
            "required": ["widget_blueprint_path", "widget_name", "layout"],
            "properties": {
                "widget_blueprint_path": {"type": "string"},
                "widget_name": {"type": "string"},
                "layout": {"type": "object"},
                "reason": {"type": "string"},
                "source_task_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_set_umg_widget_visibility": ToolSpec(
        tool_id="editor_set_umg_widget_visibility",
        task_type="editor_operation",
        title="Set UMG Widget Visibility",
        description="Create a confirmed editor operation proposal to set visibility on one UMG widget.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset", "umg"),
        owned_by_skill="UMGAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="low",
        trigger_keywords=("set umg visibility", "hide widget", "show widget", "设置UMG可见性"),
        required_payload_fields=("widget_blueprint_path", "widget_name", "visibility"),
        optional_payload_fields=("reason", "source_task_id"),
        input_schema={
            "type": "object",
            "required": ["widget_blueprint_path", "widget_name", "visibility"],
            "properties": {
                "widget_blueprint_path": {"type": "string"},
                "widget_name": {"type": "string"},
                "visibility": {"type": "string"},
                "reason": {"type": "string"},
                "source_task_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_set_umg_widget_appearance": ToolSpec(
        tool_id="editor_set_umg_widget_appearance",
        task_type="editor_operation",
        title="Set UMG Widget Appearance",
        description="Create a confirmed editor operation proposal to set safe visual fields on one UMG widget.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset", "umg"),
        owned_by_skill="UMGAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        trigger_keywords=("set umg appearance", "set widget opacity", "set widget font size", "set textblock color"),
        required_payload_fields=("widget_blueprint_path", "widget_name", "appearance"),
        optional_payload_fields=("reason", "source_task_id"),
        input_schema={
            "type": "object",
            "required": ["widget_blueprint_path", "widget_name", "appearance"],
            "properties": {
                "widget_blueprint_path": {"type": "string"},
                "widget_name": {"type": "string"},
                "appearance": {
                    "type": "object",
                    "properties": {
                        "render_opacity": {"type": "number", "minimum": 0, "maximum": 1},
                        "is_enabled": {"type": "boolean"},
                        "color_and_opacity": {
                            "type": "object",
                            "properties": {
                                "r": {"type": "number"},
                                "g": {"type": "number"},
                                "b": {"type": "number"},
                                "a": {"type": "number"},
                            },
                        },
                        "font_size": {"type": "integer"},
                    },
                },
                "reason": {"type": "string"},
                "source_task_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_set_umg_widget_brush": ToolSpec(
        tool_id="editor_set_umg_widget_brush",
        task_type="editor_operation",
        title="Set UMG Widget Brush",
        description="Create a confirmed editor operation proposal to set one Image or Border brush texture/material reference.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset", "umg", "texture", "material"),
        owned_by_skill="UMGAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        trigger_keywords=("set umg brush", "set image texture", "set border brush", "set widget material"),
        required_payload_fields=("widget_blueprint_path", "widget_name", "brush"),
        optional_payload_fields=("reason", "source_task_id"),
        input_schema={
            "type": "object",
            "required": ["widget_blueprint_path", "widget_name", "brush"],
            "properties": {
                "widget_blueprint_path": {"type": "string"},
                "widget_name": {"type": "string"},
                "brush": {
                    "type": "object",
                    "required": ["resource_type", "resource_path"],
                    "properties": {
                        "resource_type": {"type": "string", "enum": ["texture", "material"]},
                        "resource_path": {"type": "string"},
                        "texture_path": {"type": "string"},
                        "material_path": {"type": "string"},
                    },
                },
                "reason": {"type": "string"},
                "source_task_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_set_umg_slot_layout_v2": ToolSpec(
        tool_id="editor_set_umg_slot_layout_v2",
        task_type="editor_operation",
        title="Set UMG Slot Layout v2",
        description="Create a confirmed editor operation proposal to set safe HorizontalBox, VerticalBox, or Overlay slot layout fields.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset", "umg"),
        owned_by_skill="UMGAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        trigger_keywords=("set umg slot layout", "set widget padding", "set horizontal box slot", "set vertical box slot"),
        required_payload_fields=("widget_blueprint_path", "widget_name", "slot_type", "layout"),
        optional_payload_fields=("reason", "source_task_id"),
        input_schema={
            "type": "object",
            "required": ["widget_blueprint_path", "widget_name", "slot_type", "layout"],
            "properties": {
                "widget_blueprint_path": {"type": "string"},
                "widget_name": {"type": "string"},
                "slot_type": {"type": "string", "enum": ["HorizontalBoxSlot", "VerticalBoxSlot", "OverlaySlot"]},
                "layout": {
                    "type": "object",
                    "properties": {
                        "padding": {"type": ["number", "array", "object"]},
                        "horizontal_alignment": {"type": "string", "enum": ["fill", "left", "center", "right"]},
                        "vertical_alignment": {"type": "string", "enum": ["fill", "top", "center", "bottom"]},
                        "size": {
                            "type": "object",
                            "properties": {
                                "rule": {"type": "string", "enum": ["auto", "fill"]},
                                "value": {"type": "number"},
                            },
                        },
                    },
                },
                "reason": {"type": "string"},
                "source_task_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_reparent_umg_widget": ToolSpec(
        tool_id="editor_reparent_umg_widget",
        task_type="editor_operation",
        title="Reparent UMG Widget",
        description="Create a confirmed editor operation proposal to move one existing widget under another existing panel widget.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset", "umg"),
        owned_by_skill="UMGAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        trigger_keywords=("reparent umg widget", "move widget under", "move widget into", "set widget parent"),
        required_payload_fields=("widget_blueprint_path", "widget_name", "new_parent_name"),
        optional_payload_fields=("reason", "source_task_id"),
        input_schema={
            "type": "object",
            "required": ["widget_blueprint_path", "widget_name", "new_parent_name"],
            "properties": {
                "widget_blueprint_path": {"type": "string"},
                "widget_name": {"type": "string"},
                "new_parent_name": {"type": "string"},
                "reason": {"type": "string"},
                "source_task_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_duplicate_umg_widget": ToolSpec(
        tool_id="editor_duplicate_umg_widget",
        task_type="editor_operation",
        title="Duplicate UMG Widget",
        description="Create a confirmed editor operation proposal to duplicate one existing non-panel UMG widget under the same parent.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset", "umg"),
        owned_by_skill="UMGAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        trigger_keywords=("duplicate umg widget", "copy widget", "clone widget"),
        required_payload_fields=("widget_blueprint_path", "widget_name", "new_widget_name"),
        optional_payload_fields=("reason", "source_task_id"),
        input_schema={
            "type": "object",
            "required": ["widget_blueprint_path", "widget_name", "new_widget_name"],
            "properties": {
                "widget_blueprint_path": {"type": "string"},
                "widget_name": {"type": "string"},
                "new_widget_name": {"type": "string"},
                "reason": {"type": "string"},
                "source_task_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_place_actor_in_level": ToolSpec(
        tool_id="editor_place_actor_in_level",
        task_type="editor_operation",
        title="Place Actor In Level",
        description="Create a confirmed editor operation proposal to place one Actor in the current level.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset", "level"),
        owned_by_skill="LevelAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        trigger_keywords=("place actor", "spawn actor", "add actor to level", "放置Actor", "摆放Actor"),
        required_payload_fields=("actor_class",),
        optional_payload_fields=("actor_label", "transform", "reason", "source_task_id"),
        input_schema={
            "type": "object",
            "required": ["actor_class"],
            "properties": {
                "actor_class": {"type": "string"},
                "actor_label": {"type": "string"},
                "transform": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "object"},
                        "rotation": {"type": "object"},
                        "scale": {"type": "object"},
                    },
                },
                "reason": {"type": "string"},
                "source_task_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_set_material_instance_parameter": ToolSpec(
        tool_id="editor_set_material_instance_parameter",
        task_type="editor_operation",
        title="Set Material Instance Parameter",
        description="Create a confirmed editor operation proposal to set one scalar or vector Material Instance parameter.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset", "material"),
        owned_by_skill="MaterialAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        trigger_keywords=("material instance parameter", "set material parameter", "材质实例参数", "设置材质参数"),
        required_payload_fields=("material_instance_path", "parameter_name", "parameter_type", "value"),
        optional_payload_fields=("reason", "source_task_id"),
        input_schema={
            "type": "object",
            "required": ["material_instance_path", "parameter_name", "parameter_type", "value"],
            "properties": {
                "material_instance_path": {"type": "string"},
                "parameter_name": {"type": "string"},
                "parameter_type": {"type": "string", "enum": ["scalar", "vector"]},
                "value": {},
                "reason": {"type": "string"},
                "source_task_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_set_actor_transform": ToolSpec(
        tool_id="editor_set_actor_transform",
        task_type="editor_operation",
        title="Set Actor Transform",
        description="Create a confirmed editor operation proposal to modify one existing Actor transform in the current level.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "level", "actor"),
        owned_by_skill="LevelAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        trigger_keywords=("move actor", "rotate actor", "set actor transform", "移动Actor", "旋转Actor", "缩放Actor"),
        required_payload_fields=("actor_reference", "transform_mode"),
        optional_payload_fields=("actor_name", "actor_label", "transform", "transform_delta", "reason", "source_task_id"),
        input_schema={
            "type": "object",
            "required": ["actor_reference", "transform_mode"],
            "properties": {
                "actor_reference": {"type": "string"},
                "actor_name": {"type": "string"},
                "actor_label": {"type": "string"},
                "transform_mode": {"type": "string", "enum": ["absolute", "delta"]},
                "transform": {"type": "object"},
                "transform_delta": {"type": "object"},
                "reason": {"type": "string"},
                "source_task_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_set_actor_metadata": ToolSpec(
        tool_id="editor_set_actor_metadata",
        task_type="editor_operation",
        title="Set Actor Metadata",
        description="Create a confirmed editor operation proposal to update one Actor label, folder, or tags in the current level.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "level", "actor"),
        owned_by_skill="LevelAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        trigger_keywords=("rename actor", "set actor label", "set actor folder", "set actor tags", "actor metadata"),
        required_payload_fields=("actor_reference", "metadata"),
        optional_payload_fields=("reason", "source_task_id"),
        input_schema={
            "type": "object",
            "required": ["actor_reference", "metadata"],
            "properties": {
                "actor_reference": {"type": "string"},
                "metadata": {
                    "type": "object",
                    "properties": {
                        "actor_label": {"type": "string"},
                        "folder_path": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "tag_mode": {"type": "string", "enum": ["replace", "append", "remove"]},
                    },
                },
                "reason": {"type": "string"},
                "source_task_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_arrange_actors_pattern": ToolSpec(
        tool_id="editor_arrange_actors_pattern",
        task_type="editor_operation",
        title="Arrange Actors Pattern",
        description="Create a confirmed editor operation proposal to arrange a bounded Actor set with line, grid, or circle placement templates.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "level", "actor"),
        owned_by_skill="LevelAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        trigger_keywords=("arrange actors", "layout actors", "actor grid", "actor line", "actor circle"),
        required_payload_fields=("actor_references", "pattern"),
        optional_payload_fields=("reason", "source_task_id"),
        input_schema={
            "type": "object",
            "required": ["actor_references", "pattern"],
            "properties": {
                "actor_references": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 12},
                "pattern": {
                    "type": "object",
                    "required": ["type"],
                    "properties": {
                        "type": {"type": "string", "enum": ["line", "grid", "circle"]},
                        "spacing": {"type": "number"},
                        "columns": {"type": "integer"},
                        "radius": {"type": "number"},
                        "axis": {"type": "string", "enum": ["x", "y"]},
                        "origin": {"type": "object"},
                    },
                },
                "reason": {"type": "string"},
                "source_task_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_set_material_instance_texture_parameter": ToolSpec(
        tool_id="editor_set_material_instance_texture_parameter",
        task_type="editor_operation",
        title="Set Material Instance Texture Parameter",
        description="Create a confirmed editor operation proposal to set one texture parameter on a Material Instance.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset", "material", "texture"),
        owned_by_skill="MaterialAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        trigger_keywords=("material texture parameter", "set texture parameter", "材质贴图参数", "设置材质贴图"),
        required_payload_fields=("material_instance_path", "parameter_name", "texture_path"),
        optional_payload_fields=("reason", "source_task_id"),
        input_schema={
            "type": "object",
            "required": ["material_instance_path", "parameter_name", "texture_path"],
            "properties": {
                "material_instance_path": {"type": "string"},
                "parameter_name": {"type": "string"},
                "texture_path": {"type": "string"},
                "reason": {"type": "string"},
                "source_task_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "editor_set_material_instance_static_switch": ToolSpec(
        tool_id="editor_set_material_instance_static_switch",
        task_type="editor_operation",
        title="Set Material Instance Static Switch",
        description="Create a confirmed editor operation proposal to set one static switch parameter on a Material Instance.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        category="write",
        transport="http",
        requires_confirmation=True,
        active_context_keys=("project", "asset", "material"),
        owned_by_skill="MaterialAutomationSkill",
        allowed_in_free_chat=False,
        permission_gate="editor_operation_proposal",
        context_cost="medium",
        trigger_keywords=("material static switch", "set material switch", "材质静态开关", "材质开关参数"),
        required_payload_fields=("material_instance_path", "parameter_name", "value"),
        optional_payload_fields=("reason", "source_task_id"),
        input_schema={
            "type": "object",
            "required": ["material_instance_path", "parameter_name", "value"],
            "properties": {
                "material_instance_path": {"type": "string"},
                "parameter_name": {"type": "string"},
                "value": {"type": "boolean"},
                "reason": {"type": "string"},
                "source_task_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["proposal_id", "operation_type", "confirmation"],
            "properties": {
                "proposal_id": {"type": "string"},
                "operation_type": {"type": "string"},
                "confirmation": {"type": "object"},
            },
        },
    ),
    "analyze_memory_perf_signals": ToolSpec(
        tool_id="analyze_memory_perf_signals",
        task_type="perf_analyze",
        title="Performance Signal Analysis",
        description="Parse performance and memory evidence and summarize bottlenecks.",
        side_effect_level="read_only",
        route_preference="workflow",
        category="analysis",
        active_context_keys=("project", "log", "kb"),
        permission_gate="read_only_panel_scope",
        requires_retrieval=True,
        trigger_keywords=("perf", "performance", "memory", "性能", "内存"),
    ),
    "load_schema_examples": ToolSpec(
        tool_id="load_schema_examples",
        task_type="config_generate",
        title="Schema and Example Retrieval",
        description="Retrieve config schemas and example payloads from the knowledge base.",
        side_effect_level="read_only",
        route_preference="workflow",
        category="retrieval",
        active_context_keys=("project", "kb"),
        permission_gate="read_only_panel_scope",
        requires_retrieval=True,
        trigger_keywords=("schema", "examples", "配置示例", "配置模板"),
    ),
    "lookup_incident_history": ToolSpec(
        tool_id="lookup_incident_history",
        task_type="logs_analyze",
        title="Incident History Lookup",
        description="Look up prior incidents or troubleshooting notes for log signatures.",
        side_effect_level="read_only",
        route_preference="workflow",
        category="retrieval",
        active_context_keys=("project", "log", "kb"),
        permission_gate="read_only_panel_scope",
        requires_retrieval=True,
        trigger_keywords=("incident", "prior log", "历史故障", "历史日志"),
    ),
}

TASK_TYPE_TO_TOOL_ID = {
    **PRIMARY_TOOL_ID_BY_TASK_TYPE,
    "config_generate": "generate_design_config",
    "config_validate": "validate_design_config",
    "assets_plan": "plan_asset_operation",
    "assets_execute": "execute_asset_operation",
    "perf_analyze": "analyze_memory_perf_signals",
}
TOOL_ID_TO_TASK_TYPE = {tool_id: spec.task_type for tool_id, spec in TOOL_REGISTRY.items()}


def _string_tuple(value: Any) -> tuple[str, ...] | None:
    if isinstance(value, str):
        values = [item.strip() for item in value.split(",")]
    elif isinstance(value, list | tuple):
        values = [str(item).strip() for item in value]
    else:
        return None
    return tuple(item for item in values if item)


def _apply_tool_overlay(tool_id: str, spec: ToolSpec) -> ToolSpec:
    overlay = load_tool_config_overlay()
    raw = overlay.tools.get(tool_id)
    if not raw:
        return spec
    updates: dict[str, Any] = {"config_source": "tool_config_overlay"}
    warnings: list[str] = []
    for field_name in sorted(set(raw) & UNSAFE_OVERLAY_FIELDS):
        warnings.append(f"Ignored unsafe overlay field `{field_name}`.")
    for field_name, value in raw.items():
        if field_name not in SAFE_OVERLAY_FIELDS:
            if field_name not in UNSAFE_OVERLAY_FIELDS:
                warnings.append(f"Ignored unknown overlay field `{field_name}`.")
            continue
        if field_name == "enabled":
            updates["enabled"] = bool(value)
            continue
        if field_name in {"title", "description"}:
            text = str(value or "").strip()
            if text:
                updates[field_name] = text
            else:
                warnings.append(f"Ignored blank `{field_name}` override.")
            continue
        if field_name == "category":
            category = str(value or "").strip()
            if category in TOOL_CATEGORIES:
                updates["category"] = category
            else:
                warnings.append(f"Ignored unsupported category `{category}`.")
            continue
        if field_name == "trigger_keywords":
            keywords = _string_tuple(value)
            if keywords:
                updates["trigger_keywords"] = keywords
            else:
                warnings.append("Ignored empty or invalid `trigger_keywords` override.")
            continue
        if field_name == "allowed_in_free_chat":
            allowed = bool(value)
            if allowed and spec.side_effect_level != "read_only":
                warnings.append("Ignored unsafe `allowed_in_free_chat=true` for non-read-only tool.")
            else:
                updates["allowed_in_free_chat"] = allowed
            continue
        if field_name == "context_cost":
            context_cost = str(value or "").strip()
            if context_cost in CONTEXT_COST_LEVELS:
                updates["context_cost"] = context_cost
            else:
                warnings.append(f"Ignored unsupported context_cost `{context_cost}`.")
            continue
        if field_name == "tier":
            tier = str(value or "").strip()
            if tier in TOOL_TIERS:
                updates["tier"] = tier
            else:
                warnings.append(f"Ignored unsupported tier `{tier}`.")
    updates["config_warnings"] = tuple([*spec.config_warnings, *warnings])
    return replace(spec, **updates)


def _effective_tool_registry() -> dict[str, ToolSpec]:
    return {tool_id: _apply_tool_overlay(tool_id, spec) for tool_id, spec in TOOL_REGISTRY.items()}


def iter_tool_specs(*, include_disabled: bool = True) -> list[ToolSpec]:
    specs = list(_effective_tool_registry().values())
    if include_disabled:
        return specs
    return [spec for spec in specs if spec.enabled]


def get_tool_spec(tool_id: str | None) -> ToolSpec | None:
    if not tool_id:
        return None
    spec = TOOL_REGISTRY.get(tool_id)
    return _apply_tool_overlay(tool_id, spec) if spec else None


def task_route_for_task_type(task_type: str) -> str:
    spec = get_tool_spec(TASK_TYPE_TO_TOOL_ID.get(task_type))
    return spec.route_preference if spec else "single_tool"


def _keyword_matches(text: str, token: str) -> bool:
    token_lower = token.lower()
    text_lower = text.lower()
    if token_lower.isascii() and any(ch.isalnum() for ch in token_lower):
        return bool(re.search(rf"\b{re.escape(token_lower)}\b", text_lower))
    return token_lower in text_lower or token in text


def candidate_tools_for_text(text: str) -> list[str]:
    candidates: list[str] = []
    for tool_id, spec in _effective_tool_registry().items():
        if not spec.enabled:
            continue
        if any(_keyword_matches(text, token) for token in spec.trigger_keywords):
            candidates.append(tool_id)
    return candidates


def detect_tool_for_text(text: str) -> str | None:
    candidates = candidate_tools_for_text(text)
    return candidates[0] if candidates else None


def tool_capability_cards() -> list[dict[str, Any]]:
    return [spec.capability_card() for spec in iter_tool_specs()]


def tool_protocol_summary() -> dict[str, Any]:
    overlay = load_tool_config_overlay()
    return {
        "protocol_version": TOOL_PROTOCOL_VERSION,
        "categories": sorted(TOOL_CATEGORIES),
        "transports": sorted(TOOL_TRANSPORTS),
        "side_effect_levels": sorted(SIDE_EFFECT_LEVELS),
        "route_preferences": sorted(ROUTE_PREFERENCES),
        "execution_policy": TOOL_EXECUTION_POLICY,
        "tool_config_overlay": overlay.model_dump(),
    }


def free_chat_tool_ids() -> set[str]:
    return {
        tool_id
        for tool_id, spec in _effective_tool_registry().items()
        if spec.enabled and spec.allowed_in_free_chat and spec.side_effect_level == "read_only"
    }


def reload_tool_registry_config() -> dict[str, Any]:
    return reload_tool_config_overlay().model_dump()


def enrich_tool_debug_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for entry in entries:
        item = dict(entry)
        spec = get_tool_spec(str(item.get("tool_id") or ""))
        if spec:
            item.setdefault("registered", True)
            item.setdefault("title", spec.title)
            item.setdefault("category", spec.category)
            item.setdefault("transport", spec.transport)
            item.setdefault("side_effect_level", spec.side_effect_level)
            item.setdefault("requires_confirmation", spec.effective_requires_confirmation)
            item.setdefault("active_context_keys", list(spec.active_context_keys))
            item.setdefault("owned_by_skill", spec.owned_by_skill)
            item.setdefault("permission_gate", spec.permission_gate)
            item.setdefault("allowed_in_free_chat", spec.allowed_in_free_chat)
            item.setdefault("enabled", spec.enabled)
            item.setdefault("tier", spec.tier)
            item.setdefault("config_source", spec.config_source)
            item.setdefault("config_warnings", list(spec.config_warnings))
            item.setdefault("approval_state", "not_required" if not spec.effective_requires_confirmation else "required")
        else:
            item.setdefault("registered", False)
            item.setdefault("transport", "internal")
            item.setdefault("side_effect_level", "read_only")
            item.setdefault("requires_confirmation", False)
            item.setdefault("approval_state", "not_required")
        item.setdefault("input_summary", {})
        item.setdefault("output_summary", item.get("summary") or "")
        item.setdefault("latency_ms", None)
        enriched.append(item)
    return enriched
