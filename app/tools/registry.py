from __future__ import annotations

from dataclasses import dataclass

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


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "retrieve_project_knowledge": ToolSpec(
        tool_id="retrieve_project_knowledge",
        task_type="project_qa",
        title="Project Knowledge Retrieval",
        description="Retrieve project-specific evidence from the knowledge base.",
        side_effect_level="read_only",
        route_preference="project_qa",
        requires_retrieval=True,
    ),
    "review_ue_cpp_files": ToolSpec(
        tool_id="review_ue_cpp_files",
        task_type="code_review",
        title="UE C++ Code Review",
        description="Scan UE C++ code or diffs for lifecycle, threading, loading, and boundary issues.",
        side_effect_level="read_only",
        route_preference="workflow",
        requires_retrieval=True,
    ),
    "generate_code_draft": ToolSpec(
        tool_id="generate_code_draft",
        task_type="code_generate",
        title="Code Draft Generation",
        description="Generate a code draft and file layout suggestions without writing to the project.",
        side_effect_level="plan_only",
        route_preference="single_tool",
        requires_retrieval=True,
    ),
    "analyze_ue_log": ToolSpec(
        tool_id="analyze_ue_log",
        task_type="logs_analyze",
        title="UE Log Analysis",
        description="Parse logs, extract signatures, and summarize likely failure families.",
        side_effect_level="read_only",
        route_preference="workflow",
        requires_retrieval=True,
    ),
    "generate_design_config": ToolSpec(
        tool_id="generate_design_config",
        task_type="config_generate",
        title="Config Generation",
        description="Generate a structured config draft from requirements, schemas, and examples.",
        side_effect_level="plan_only",
        route_preference="workflow",
        requires_retrieval=True,
    ),
    "validate_design_config": ToolSpec(
        tool_id="validate_design_config",
        task_type="config_validate",
        title="Config Validation",
        description="Validate a config payload against a schema and emit structured diagnostics.",
        side_effect_level="read_only",
        route_preference="single_tool",
        requires_retrieval=False,
    ),
    "inspect_asset_metadata": ToolSpec(
        tool_id="inspect_asset_metadata",
        task_type="assets_inspect",
        title="Asset Inspection",
        description="Inspect asset naming, folder hygiene, and duplicate candidates.",
        side_effect_level="read_only",
        route_preference="single_tool",
        requires_retrieval=True,
    ),
    "plan_asset_operation": ToolSpec(
        tool_id="plan_asset_operation",
        task_type="assets_plan",
        title="Asset Operation Planning",
        description="Plan asset rename or reorganization actions without executing them.",
        side_effect_level="plan_only",
        route_preference="workflow",
        requires_retrieval=True,
    ),
    "execute_asset_operation": ToolSpec(
        tool_id="execute_asset_operation",
        task_type="assets_execute",
        title="Asset Operation Execution",
        description="Execute a previously approved asset operation.",
        side_effect_level="confirmed_write",
        route_preference="proposal_wait",
        requires_retrieval=False,
    ),
    "analyze_memory_perf_signals": ToolSpec(
        tool_id="analyze_memory_perf_signals",
        task_type="perf_analyze",
        title="Performance Signal Analysis",
        description="Parse performance and memory evidence and summarize bottlenecks.",
        side_effect_level="read_only",
        route_preference="workflow",
        requires_retrieval=True,
    ),
    "load_schema_examples": ToolSpec(
        tool_id="load_schema_examples",
        task_type="config_generate",
        title="Schema and Example Retrieval",
        description="Retrieve config schemas and example payloads from the knowledge base.",
        side_effect_level="read_only",
        route_preference="workflow",
        requires_retrieval=True,
    ),
    "lookup_incident_history": ToolSpec(
        tool_id="lookup_incident_history",
        task_type="logs_analyze",
        title="Incident History Lookup",
        description="Look up prior incidents or troubleshooting notes for log signatures.",
        side_effect_level="read_only",
        route_preference="workflow",
        requires_retrieval=True,
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


def candidate_tools_for_text(text_lower: str) -> list[str]:
    candidates: list[str] = []
    mapping = {
        "review": "review_ue_cpp_files",
        "code review": "review_ue_cpp_files",
        "analyze log": "analyze_ue_log",
        "log": "analyze_ue_log",
        "config generate": "generate_design_config",
        "generate config": "generate_design_config",
        "validate config": "validate_design_config",
        "asset": "inspect_asset_metadata",
        "perf": "analyze_memory_perf_signals",
        "performance": "analyze_memory_perf_signals",
        "memory": "analyze_memory_perf_signals",
    }
    for token, tool_id in mapping.items():
        if token in text_lower and tool_id not in candidates:
            candidates.append(tool_id)
    return candidates
