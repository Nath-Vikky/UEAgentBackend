from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.skills.registry import PRIMARY_TOOL_ID_BY_TASK_TYPE


@dataclass(frozen=True, slots=True)
class ToolSpec:
    tool_id: str
    task_type: str
    title: str
    description: str
    side_effect_level: str
    route_preference: str
    requires_retrieval: bool = False
    trigger_keywords: tuple[str, ...] = ()
    required_payload_fields: tuple[str, ...] = ()
    optional_payload_fields: tuple[str, ...] = ()
    timeout_ms: int = 30_000
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)

    def capability_card(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "task_type": self.task_type,
            "title": self.title,
            "description": self.description,
            "side_effect_level": self.side_effect_level,
            "route_preference": self.route_preference,
            "requires_retrieval": self.requires_retrieval,
            "trigger_keywords": list(self.trigger_keywords),
            "required_payload_fields": list(self.required_payload_fields),
            "optional_payload_fields": list(self.optional_payload_fields),
            "timeout_ms": self.timeout_ms,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "retrieve_project_knowledge": ToolSpec(
        tool_id="retrieve_project_knowledge",
        task_type="project_qa",
        title="Project Knowledge Retrieval",
        description="Retrieve project-specific evidence from the knowledge base.",
        side_effect_level="read_only",
        route_preference="project_qa",
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
    "query_project_inventory": ToolSpec(
        tool_id="query_project_inventory",
        task_type="project_qa",
        title="Project Inventory Query",
        description="Query the latest submitted project inventory snapshot for assets, code files, and UE metadata.",
        side_effect_level="read_only",
        route_preference="project_qa",
        requires_retrieval=False,
        trigger_keywords=(
            "current project assets",
            "project assets",
            "blueprint assets",
            "static mesh",
            "nanite",
            "asset settings",
            "code files",
            "modules",
            "当前项目",
            "当前工程",
            "项目资产",
            "蓝图资产",
            "静态网格体",
            "资产属性",
            "代码文件",
            "模块",
        ),
        required_payload_fields=("user_query",),
        optional_payload_fields=("project_id", "asset_type", "limit"),
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "user_query": {"type": "string"},
                "project_id": {"type": "string"},
                "asset_type": {"type": "string"},
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
    "review_ue_cpp_files": ToolSpec(
        tool_id="review_ue_cpp_files",
        task_type="code_review",
        title="UE C++ Code Review",
        description="Scan UE C++ code or diffs for lifecycle, threading, loading, and boundary issues.",
        side_effect_level="read_only",
        route_preference="workflow",
        requires_retrieval=True,
        trigger_keywords=("code review", "review", "审查", "代码审查"),
        required_payload_fields=("user_query",),
        optional_payload_fields=("files", "file_paths", "diff_text", "code_text", "project_root"),
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
    "analyze_ue_log": ToolSpec(
        tool_id="analyze_ue_log",
        task_type="logs_analyze",
        title="UE Log Analysis",
        description="Parse logs, extract signatures, and summarize likely failure families.",
        side_effect_level="read_only",
        route_preference="workflow",
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
        requires_retrieval=False,
        trigger_keywords=("validate config", "config validate", "校验配置"),
        required_payload_fields=("schema", "config_json"),
    ),
    "inspect_asset_metadata": ToolSpec(
        tool_id="inspect_asset_metadata",
        task_type="assets_inspect",
        title="Asset Inspection",
        description="Inspect asset naming, folder hygiene, and duplicate candidates.",
        side_effect_level="read_only",
        route_preference="single_tool",
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
    ),
    "plan_asset_operation": ToolSpec(
        tool_id="plan_asset_operation",
        task_type="assets_plan",
        title="Asset Operation Planning",
        description="Plan asset rename or reorganization actions without executing them.",
        side_effect_level="plan_only",
        route_preference="workflow",
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
        requires_retrieval=False,
        trigger_keywords=("execute asset", "apply asset", "执行资产"),
    ),
    "analyze_memory_perf_signals": ToolSpec(
        tool_id="analyze_memory_perf_signals",
        task_type="perf_analyze",
        title="Performance Signal Analysis",
        description="Parse performance and memory evidence and summarize bottlenecks.",
        side_effect_level="read_only",
        route_preference="workflow",
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


def get_tool_spec(tool_id: str | None) -> ToolSpec | None:
    if not tool_id:
        return None
    return TOOL_REGISTRY.get(tool_id)


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
    for tool_id, spec in TOOL_REGISTRY.items():
        if any(_keyword_matches(text, token) for token in spec.trigger_keywords):
            candidates.append(tool_id)
    return candidates


def detect_tool_for_text(text: str) -> str | None:
    candidates = candidate_tools_for_text(text)
    return candidates[0] if candidates else None


def tool_capability_cards() -> list[dict[str, Any]]:
    return [spec.capability_card() for spec in TOOL_REGISTRY.values()]
