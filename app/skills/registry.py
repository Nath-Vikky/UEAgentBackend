from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class BuiltInSkillSpec:
    skill_id: str
    task_type: str
    title: str
    description: str
    panel_id: str
    frontend_ui: str
    entry_mode: str
    primary_tool_id: str | None
    route_preference: str
    side_effect_level: str
    requires_retrieval: bool
    collector: str
    rules: list[str] = field(default_factory=list)
    retrieval_domains: list[str] = field(default_factory=list)
    projector_outputs: list[str] = field(default_factory=list)
    notes: str = ""

    def to_catalog_item(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = "core"
        payload["architecture"] = {
            "collector": self.collector,
            "rules": self.rules,
            "retrieval_domains": self.retrieval_domains,
            "projector_outputs": self.projector_outputs,
        }
        return payload


BUILT_IN_SKILLS: tuple[BuiltInSkillSpec, ...] = (
    BuiltInSkillSpec(
        skill_id="ProjectQASkill",
        task_type="agent_chat",
        title="Agent Chat / Project QA",
        description=(
            "Free chat by default; promotes to project QA and selects read-only tools "
            "when the message asks for project knowledge or inventory facts."
        ),
        panel_id="AgentChat",
        frontend_ui="chat_timeline",
        entry_mode="chat",
        primary_tool_id="retrieve_project_knowledge",
        route_preference="direct_answer_or_project_qa",
        side_effect_level="read_only",
        requires_retrieval=False,
        collector="chat_messages_and_editor_context",
        rules=["direct_answer_vs_project_qa_router", "project_inventory_tool_selection"],
        retrieval_domains=["project_docs", "engine_notes", "team_rules"],
        projector_outputs=["user_view", "debug_view", "citations", "data.inventory", "trace_summary"],
        notes=(
            "The backend decides whether to stay in direct chat, query Project Inventory, "
            "retrieve project knowledge, or combine both read-only tools."
        ),
    ),
    BuiltInSkillSpec(
        skill_id="CodeReviewSkill",
        task_type="code_review",
        title="Code Review",
        description="Review one selected UE source file with deterministic checks, KB evidence, and optional LLM synthesis.",
        panel_id="CodeReview",
        frontend_ui="file_picker",
        entry_mode="explicit_task",
        primary_tool_id="review_ue_cpp_files",
        route_preference="workflow",
        side_effect_level="read_only",
        requires_retrieval=True,
        collector="ue_project_code_file_scanner_and_reader",
        rules=["file_access_guard", "ue_cpp_lifecycle_checks", "localized_rule_projection"],
        retrieval_domains=["code_reference", "team_rules", "engine_notes"],
        projector_outputs=["user_view.blocks", "data.review_scope", "data.localized_review"],
        notes="Use the dedicated file list endpoint and submit a selected file for single-file review.",
    ),
    BuiltInSkillSpec(
        skill_id="CodeGenerateSkill",
        task_type="code_generate",
        title="Code Generation",
        description="Generate code from a user requirement, optionally grounded by code_reference and examples.",
        panel_id="CodeGenerator",
        frontend_ui="prompt_plus_code_results",
        entry_mode="explicit_task",
        primary_tool_id="generate_code_draft",
        route_preference="single_tool",
        side_effect_level="plan_only",
        requires_retrieval=True,
        collector="user_requirement_and_optional_editor_context",
        rules=["code_reference_precheck", "non_writing_output_policy"],
        retrieval_domains=["code_reference", "examples", "engine_notes"],
        projector_outputs=["user_view.blocks", "data.generated_code", "data.reference_matches"],
        notes=(
            "Show the user prompt in the timeline, but render generated code as result "
            "buttons or tabs instead of one long chat block."
        ),
    ),
    BuiltInSkillSpec(
        skill_id="LogsAnalyzeSkill",
        task_type="logs_analyze",
        title="Log Analysis",
        description="Analyze UE logs collected by the plugin or pasted by the user.",
        panel_id="LogAnalyzer",
        frontend_ui="log_preview_plus_result",
        entry_mode="explicit_task",
        primary_tool_id="analyze_ue_log",
        route_preference="workflow",
        side_effect_level="read_only",
        requires_retrieval=True,
        collector="ue_log_text_payload",
        rules=["signature_extraction", "severity_grouping"],
        retrieval_domains=["incident_history", "engine_notes", "project_docs"],
        projector_outputs=["user_view.blocks", "data.signatures", "data.recommendations"],
        notes="The plugin should collect or preview logs locally and send log_text to the backend for analysis.",
    ),
    BuiltInSkillSpec(
        skill_id="AssetsInspectSkill",
        task_type="assets_inspect",
        title="Asset Inspection",
        description="Inspect selected UE asset metadata for naming, type, dependency, and relationship quality.",
        panel_id="AssetInspector",
        frontend_ui="selected_assets_plus_groups",
        entry_mode="explicit_task",
        primary_tool_id="inspect_asset_metadata",
        route_preference="single_tool",
        side_effect_level="read_only",
        requires_retrieval=True,
        collector="selected_asset_metadata_payload",
        rules=["asset_name_lint", "type_summary", "dependency_relationship_summary"],
        retrieval_domains=["asset_rules", "team_rules"],
        projector_outputs=["user_view.blocks", "data.violations", "data.relationship_summary"],
        notes="The plugin must send selected asset metadata from the editor; the backend does not inspect raw .uasset files directly.",
    ),
)

CORE_SKILL_IDS = [skill.skill_id for skill in BUILT_IN_SKILLS]
CORE_TASK_TYPES = ["agent_chat", "project_qa", *(skill.task_type for skill in BUILT_IN_SKILLS if skill.task_type != "agent_chat")]
SKILL_CATALOG = [skill.to_catalog_item() for skill in BUILT_IN_SKILLS]
PRIMARY_TOOL_ID_BY_TASK_TYPE = {
    skill.task_type: skill.primary_tool_id
    for skill in BUILT_IN_SKILLS
    if skill.primary_tool_id and skill.task_type != "agent_chat"
}


def get_skill_by_task_type(task_type: str) -> BuiltInSkillSpec | None:
    for skill in BUILT_IN_SKILLS:
        if skill.task_type == task_type:
            return skill
    if task_type == "project_qa":
        return BUILT_IN_SKILLS[0]
    return None


UI_RECOMMENDATIONS = {
    "initial_endpoints": [
        "/api/v1/system/health",
        "/api/v1/system/bootstrap",
        "/api/v1/system/capabilities",
        "/api/v1/system/runtime-profiles",
    ],
    "preferred_user_view_source": "user_view",
    "preferred_debug_view_source": "debug_view",
    "core_panels": [
        {
            "panel_id": skill.panel_id,
            "task_type": skill.task_type,
            "ui_mode": skill.frontend_ui,
            "skill_id": skill.skill_id,
        }
        for skill in BUILT_IN_SKILLS
    ],
    "notes": [
        "User View should render `user_view` or `presentation` instead of inferring content from raw data.",
        "Debug View should show route, usage, trace summary, retrieval details, task events, proposals, and raw structured results.",
        "The narrowed scope keeps only five core plugin panels. Deferred backend tasks should be hidden from the main frontend menu.",
        "Do not force every feature into the same chat UI. Only Agent Chat / Project QA should use a full chat timeline.",
    ],
}
