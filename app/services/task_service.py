from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.agent.context_builder import build_context_summary
from app.agent.context_manager import build_context_bundle, context_bundle_prompt_excerpt
from app.agent.context_pack import build_context_pack
from app.agent.context_route_refiner import refine_route_from_resolved_context
from app.agent.agent_dag import build_agent_dag_projection
from app.agent.decision_trace import build_agent_decision_trace
from app.agent.graph_adapter import graph_framework_readiness_report, review_fix_validate_graph_spec
from app.agent.llm_intent_drafter import apply_llm_intent_draft, build_llm_intent_draft_messages
from app.agent.memory_manager import update_active_target_memory, update_conversation_focus_memory, update_session_memory
from app.agent.multi_agent import build_multi_agent_lite_trace
from app.agent.react_trace import build_react_v2_trace
from app.agent.response_composer import compose_unified_response
from app.agent.response_critic import apply_response_critic
from app.agent.response_synthesizer import synthesize_execution_response
from app.agent.router import classify_request
from app.agent.subagent_runtime import build_subagent_runtime
from app.core.settings import Settings
from app.db.models.audit import AuditLogModel
from app.db.models.proposal import ProposalModel
from app.db.models.runtime_profile import RuntimeProfileModel
from app.db.models.task import TaskArtifactModel, TaskEventModel, TaskModel
from app.db.repositories.audit_logs import create_audit_log
from app.db.repositories.proposals import create_proposal
from app.db.repositories.runtime_profiles import get_active_profile, get_default_profile
from app.db.repositories.sessions import append_messages, get_or_create_session
from app.db.repositories.tasks import (
    add_task_artifact,
    add_task_event,
    create_task,
    get_task,
    get_task_by_run_id,
    list_recent_tasks,
    list_task_artifacts,
    list_task_events,
    mark_task_cancelled,
    save_task,
)
from app.observability.audit import build_audit_entry
from app.observability.langsmith import build_trace_summary
from app.observability.metrics import summarize_usage
from app.observability.redaction import redact_payload
from app.schemas.common import ActionProposal, ArtifactDescriptor
from app.schemas.requests import UnifiedTaskRequest
from app.schemas.responses import UnifiedTaskResponse
from app.services.kb_service import KnowledgeBaseService
from app.services.llm_service import ChatRuntimeConfig, LLMService, chat_runtime_config
from app.services.mcp_tool_adapter import build_mcp_adapter_status
from app.services.project_inventory_service import ProjectInventoryService
from app.services.task_events import (
    StreamEventEmitter,
    StreamEventSink,
    build_persisted_event_payloads,
    build_run_cancelled_event_payload,
)
from app.services.task_handlers import RouteExecutionDispatcher, TaskExecutionContext, TaskHandlerDependencies
from app.skills.runtime import build_skill_runtime_descriptor
from app.tools.registry import (
    TOOL_EXECUTION_POLICY,
    TOOL_ID_TO_TASK_TYPE,
    enrich_tool_debug_entries,
    tool_protocol_summary,
)
from app.utils.json_tools import dumps_pretty
from app.utils.paths import task_artifact_dir
from app.utils.time import now_utc

CHAT_HISTORY_TASK_TYPES = {"agent_chat", "project_qa"}


def _localized(language: str, zh_text: str, en_text: str) -> str:
    return zh_text if language.startswith("zh") else en_text


def _compact_value(value: Any, *, max_len: int = 120) -> str:
    if value in (None, "", [], {}):
        return "n/a"
    if isinstance(value, (dict, list)):
        text = dumps_pretty(value)
    else:
        text = str(value)
    return text if len(text) <= max_len else f"{text[: max_len - 3]}..."


def _component_preview(components: Any, *, limit: int = 5) -> str:
    if not isinstance(components, list) or not components:
        return "n/a"
    preview: list[str] = []
    for component in components[:limit]:
        if isinstance(component, dict):
            name = component.get("component_name") or component.get("name") or component.get("label")
            class_name = component.get("component_class") or component.get("class") or component.get("type")
            mobility = component.get("mobility")
            bits = [str(part) for part in (name, class_name) if part]
            text = ":".join(bits) if bits else _compact_value(component, max_len=60)
            if mobility:
                text += f"({mobility})"
            preview.append(text)
        else:
            preview.append(str(component))
    suffix = "" if len(components) <= limit else f" (+{len(components) - limit})"
    return ", ".join(preview) + suffix


def _graph_summary_preview(graphs: Any, *, limit: int = 4) -> str:
    if not isinstance(graphs, list) or not graphs:
        return "n/a"
    preview: list[str] = []
    for graph in graphs[:limit]:
        if isinstance(graph, dict):
            graph_name = graph.get("graph_name") or graph.get("name") or "UnknownGraph"
            graph_type = graph.get("graph_type") or graph.get("type")
            node_count = graph.get("node_count")
            link_count = graph.get("link_count")
            node_titles: list[str] = []
            for node in list(graph.get("nodes") or [])[:4]:
                if isinstance(node, dict):
                    title = node.get("title") or node.get("node_name") or node.get("node_class")
                    if title:
                        node_titles.append(str(title))
            bits = [str(graph_name)]
            if graph_type:
                bits.append(f"type={graph_type}")
            if node_count is not None:
                bits.append(f"nodes={node_count}")
            if link_count is not None:
                bits.append(f"links={link_count}")
            if node_titles:
                bits.append(f"sample_nodes={', '.join(node_titles)}")
            preview.append(" | ".join(bits))
        else:
            preview.append(str(graph))
    suffix = "" if len(graphs) <= limit else f" (+{len(graphs) - limit})"
    return "; ".join(preview) + suffix


def _material_parameter_value(param: dict[str, Any]) -> Any:
    for key in ("value", "texture_path", "texture", "default_value", "default", "asset_path"):
        if key in param and param[key] not in (None, "", [], {}):
            return param[key]
    if all(key in param for key in ("r", "g", "b")):
        return {"r": param.get("r"), "g": param.get("g"), "b": param.get("b"), "a": param.get("a", 1)}
    return None


def _material_parameter_preview(params: Any, *, limit: int = 6, include_values: bool = True) -> str:
    if not isinstance(params, list) or not params:
        return "n/a"
    preview: list[str] = []
    for param in params[:limit]:
        if isinstance(param, dict):
            name = param.get("name") or param.get("parameter_name") or param.get("display_name") or "Unknown"
            param_type = param.get("parameter_type") or param.get("type")
            label = f"{name}({param_type})" if param_type else str(name)
            if include_values:
                value = _material_parameter_value(param)
                if value not in (None, "", [], {}):
                    label += f"={_compact_value(value, max_len=80)}"
            preview.append(label)
        else:
            preview.append(str(param))
    suffix = "" if len(params) <= limit else f" (+{len(params) - limit})"
    return ", ".join(preview) + suffix


class TaskService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings
        self.kb_service = KnowledgeBaseService(db, settings)
        self.llm_service = LLMService(settings)
        self.inventory_service = ProjectInventoryService(settings)
        self.route_dispatcher = RouteExecutionDispatcher()
        self.stream_events = StreamEventEmitter()

    def _emit_stream_event(
        self,
        sink: StreamEventSink | None,
        event: str,
        payload: dict[str, Any],
        *,
        run_id: str | None = None,
        task_id: str | None = None,
    ) -> None:
        self.stream_events.emit(
            sink,
            event,
            payload,
            run_id=run_id,
            task_id=task_id,
        )

    def _resolve_chat_config(self, request: UnifiedTaskRequest) -> ChatRuntimeConfig:
        requested_profile_id = (request.runtime_options.profile_id or "").strip()
        profile: RuntimeProfileModel | None = None
        if requested_profile_id:
            profile = self.db.get(RuntimeProfileModel, requested_profile_id)
        if not profile:
            profile = get_active_profile(self.db) or get_default_profile(self.db)
        return chat_runtime_config(self.settings, profile)

    def _language_label(self, language: str) -> str:
        return "Simplified Chinese" if language.startswith("zh") else "English"

    def _session_messages(
        self,
        request: UnifiedTaskRequest,
        *,
        system_prompt: str,
        fallback_user_text: str = "",
        context_bundle: dict[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": system_prompt}]
        if context_bundle:
            for item in context_bundle.get("recent_messages", [])[-10:]:
                role = str(item.get("role") or "user")
                role = role if role in {"system", "user", "assistant"} else "user"
                content = str(item.get("content") or "").strip()
                if content:
                    messages.append({"role": role, "content": content})
        else:
            for item in request.session.messages[-10:]:
                role = item.role if item.role in {"system", "user", "assistant"} else "user"
                if item.content.strip():
                    messages.append({"role": role, "content": item.content.strip()})
        if len(messages) == 1 and fallback_user_text.strip():
            messages.append({"role": "user", "content": fallback_user_text.strip()})
        return messages

    def _direct_answer_messages(
        self,
        request: UnifiedTaskRequest,
        *,
        output_language: str,
        context_bundle: dict[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        context_summary = (context_bundle or {}).get("editor_context") or build_context_summary(request)
        system_prompt = (
            "You are UE Agent, a backend assistant for Unreal Engine development and general software questions. "
            f"Reply in {self._language_label(output_language)} unless the user explicitly requests another language. "
            "Be concise, accurate, and honest about uncertainty. "
            "Do not invent project-specific facts. "
            "If editor context is included, use it only when it is relevant to the user request."
        )
        if context_summary:
            system_prompt += f"\n\nEditor context summary:\n{context_summary}"
        if context_bundle:
            system_prompt += f"\n\nCompact context bundle:\n{context_bundle_prompt_excerpt(context_bundle)}"
        fallback_user_text = str(request.payload.get("user_query") or "")
        return self._session_messages(
            request,
            system_prompt=system_prompt,
            fallback_user_text=fallback_user_text,
            context_bundle=context_bundle,
        )

    def _project_qa_messages(
        self,
        *,
        request: UnifiedTaskRequest,
        query: str,
        qa_result: dict[str, Any],
        project_file_result: dict[str, Any] | None = None,
        output_language: str,
        context_bundle: dict[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        evidence_lines: list[str] = []
        for index, item in enumerate(qa_result["retrieved_docs"][:4], start=1):
            snippet = str(item.get("source_path") or item.get("title") or "").strip()
            evidence_lines.append(
                "\n".join(
                    [
                        f"[S{index}] {item['title']}",
                        f"Source: {snippet}",
                        f"Retrieval source: {item.get('retrieval_source') or 'knowledge_base'}",
                        f"Section: {item.get('section_path') or 'n/a'}",
                        f"Excerpt: {str(item.get('text') or '')[:350]}",
                    ]
                )
            )
        inventory_lines: list[str] = []
        for index, item in enumerate(qa_result.get("inventory_items", [])[:6], start=1):
            if item.get("kind") == "level_actor":
                inventory_lines.append(
                    "\n".join(
                        [
                            f"[I{index}] Level actor: {item.get('actor_label') or item.get('actor_name')}",
                            f"Class: {item.get('actor_class') or 'Unknown'}",
                            f"Level: {item.get('level_name') or 'n/a'}",
                            f"Path: {item.get('actor_path') or 'n/a'}",
                            f"Blueprint: {item.get('blueprint_path') or 'n/a'}",
                            f"Components: {_component_preview(item.get('components'))}",
                            f"Transform: {dumps_pretty(item.get('transform') or {})[:260]}",
                        ]
                    )
                )
                continue
            if item.get("kind") == "material_instance":
                params = item.get("parameters") or []
                inventory_lines.append(
                    "\n".join(
                        [
                            f"[I{index}] Material instance: {item.get('material_instance_name') or item.get('material_instance_path')}",
                            f"Path: {item.get('material_instance_path') or 'n/a'}",
                            f"Parent: {item.get('parent_material') or 'Unknown'}",
                            f"Parameters: {_material_parameter_preview(params, include_values=True)}",
                            f"Scalar parameters: {_material_parameter_preview(item.get('scalar_parameters'), include_values=True)}",
                            f"Vector parameters: {_material_parameter_preview(item.get('vector_parameters'), include_values=True)}",
                            f"Texture parameters: {_material_parameter_preview(item.get('texture_parameters'), include_values=True)}",
                            f"Static switches: {_material_parameter_preview(item.get('static_switch_parameters'), include_values=True)}",
                        ]
                    )
                )
                continue
            if item.get("kind") == "code_file":
                inventory_lines.append(
                    "\n".join(
                        [
                            f"[I{index}] Code file: {item.get('file_path')}",
                            f"Module: {item.get('module_name') or 'n/a'}",
                            f"Classes: {', '.join(item.get('classes') or []) or 'n/a'}",
                        ]
                    )
                )
                continue
            blueprint = item.get("blueprint") if isinstance(item.get("blueprint"), dict) else {}
            inventory_lines.append(
                "\n".join(
                    [
                        f"[I{index}] Asset: {item.get('asset_name') or item.get('asset_path')}",
                        f"Type: {item.get('asset_type') or 'Unknown'}",
                        f"Path: {item.get('asset_path') or 'n/a'}",
                        f"Blueprint graphs: {_graph_summary_preview(item.get('graph_summaries') or blueprint.get('graph_summaries'))}",
                        f"Settings: {dumps_pretty(item.get('settings') or {})[:350]}",
                        f"Properties: {dumps_pretty(item.get('properties') or {})[:350]}",
                    ]
                )
            )
        project_file_lines: list[str] = []
        if project_file_result and project_file_result.get("status") == "completed":
            project_file_lines.append(
                "\n".join(
                    [
                        f"[F1] File: {project_file_result.get('file_path')}",
                        f"Resolved: {project_file_result.get('resolved_path')}",
                        f"Excerpt:\n{str(project_file_result.get('text_excerpt') or '')[:1200]}",
                    ]
                )
            )
        inventory_summary = dict(qa_result.get("inventory_summary") or {})
        inventory_freshness = dict(inventory_summary.get("freshness") or {})
        inventory_freshness_line = (
            "Project inventory freshness: "
            f"status={inventory_freshness.get('status', 'unknown')}, "
            f"should_refresh={inventory_freshness.get('should_refresh')}, "
            f"age_minutes={inventory_freshness.get('age_minutes')}, "
            f"stale_after_seconds={inventory_freshness.get('stale_after_seconds')}."
        )
        system_prompt = (
            "You are synthesizing an answer from project knowledge-base evidence. "
            f"Reply in {self._language_label(output_language)}. "
            "Use only the supplied knowledge-base evidence, controlled web evidence, project inventory facts, and explicitly read project file excerpts. "
            "Treat local KB, project inventory, and team rules as higher priority than web search; web evidence is supplemental. "
            "If project inventory freshness is stale, state that the project facts come from the latest submitted snapshot and recommend syncing before final decisions. "
            "If the evidence is insufficient, say so clearly instead of guessing. "
            "Prefer a short answer followed by 2-4 concrete evidence-backed points."
        )
        user_prompt = "\n\n".join(
            [
                f"User question:\n{query.strip()}",
                f"Context bundle:\n{context_bundle_prompt_excerpt(context_bundle) if context_bundle else build_context_summary(request)}",
                "Evidence:",
                "\n\n".join(evidence_lines) if evidence_lines else "No retrieved evidence.",
                "Project inventory facts:",
                inventory_freshness_line,
                "\n\n".join(inventory_lines) if inventory_lines else "No project inventory facts.",
                "Explicit project file excerpts:",
                "\n\n".join(project_file_lines) if project_file_lines else "No project file excerpt.",
            ]
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _direct_answer_fallback_text(self, output_language: str, reason: str) -> str:
        if reason == "missing_openai_api_key":
            return _localized(
                output_language,
                "当前没有可用的 LLM API Key，所以普通对话先走降级回复。请先配置 OPENAI_API_KEY，必要时再配置 OPENAI_BASE_URL 和 CHAT_MODEL。",
                "No live LLM API key is configured yet, so direct chat is using a degraded fallback. Configure OPENAI_API_KEY and, if needed, OPENAI_BASE_URL and CHAT_MODEL.",
            )
        return _localized(
            output_language,
            "当前未能成功调用已配置的 LLM，因此返回了降级回复。请检查 OPENAI_BASE_URL、CHAT_MODEL 和网络连通性。",
            "The backend could not reach the configured LLM, so it returned a degraded fallback. Check OPENAI_BASE_URL, CHAT_MODEL, and network connectivity.",
        )

    def _inventory_project_id(self, request: UnifiedTaskRequest) -> str | None:
        return str(
            request.payload.get("project_id")
            or request.context.project_name
            or request.context.project_root
            or ""
        ).strip() or None

    def _inventory_fallback_answer(
        self,
        *,
        inventory_result: dict[str, Any],
        output_language: str,
    ) -> str:
        items = inventory_result.get("items") or []
        summary = inventory_result.get("summary") or {}
        freshness = dict(summary.get("freshness") or {})
        stale_note = ""
        if freshness.get("status") == "stale":
            age_minutes = freshness.get("age_minutes")
            stale_note = _localized(
                output_language,
                f"提示：当前 Project Inventory 快照可能已过期（约 {age_minutes} 分钟前同步），以下内容代表最近一次快照。建议点击 Sync Inventory Now 后再做最终判断。",
                f"Note: the current Project Inventory snapshot may be stale (synced about {age_minutes} minutes ago). The facts below represent the latest submitted snapshot. Use Sync Inventory Now before making a final decision.",
            )
        if not items:
            if not summary.get("has_snapshot"):
                return _localized(
                    output_language,
                    "当前没有找到可用的 Project Inventory 快照，所以我无法列出当前工程里的资产或代码文件。请先打开 UE 插件等待自动同步，或点击 Sync Inventory Now 手动提交一次项目快照后再询问。",
                    "No Project Inventory snapshot is available yet, so I cannot list assets or code files from the current project. Open the UE plugin and wait for automatic sync, or click Sync Inventory Now to submit a project snapshot, then ask again.",
                )
            no_match = _localized(
                output_language,
                "Project Inventory 已有快照，但本次问题没有命中匹配的资产或代码文件。你可以换一个更具体的资产名、类型、模块名，或重新提交一次最新快照。",
                "A Project Inventory snapshot exists, but no assets or code files matched this question. Try a more specific asset name, asset type, module name, or submit a fresh snapshot.",
            )
            return "\n".join(item for item in (stale_note, no_match) if item)
        lines = [
            *([stale_note] if stale_note else []),
            _localized(
                output_language,
                f"我从 Project Inventory 中找到了 {len(items)} 条相关项目事实：",
                f"I found {len(items)} matching project inventory item(s):",
            )
        ]
        for item in items[:8]:
            if item.get("kind") == "level_actor":
                transform = item.get("transform") if isinstance(item.get("transform"), dict) else {}
                location = transform.get("location") or transform.get("translation") or {}
                location_text = _compact_value(location, max_len=120)
                components = _component_preview(item.get("components"))
                blueprint_path = str(item.get("blueprint_path") or "").strip()
                lines.append(
                    f"- {item.get('actor_label') or item.get('actor_name')} | "
                    f"class={item.get('actor_class') or 'Unknown'} | "
                    f"level={item.get('level_name') or 'n/a'} | location={location_text}"
                    + (f" | blueprint={blueprint_path}" if blueprint_path else "")
                    + (f" | components={components}" if components != "n/a" else "")
                )
                continue
            if item.get("kind") == "material_instance":
                params = item.get("parameters") if isinstance(item.get("parameters"), list) else []
                preview = _material_parameter_preview(params, include_values=True)
                lines.append(
                    f"- {item.get('material_instance_name') or item.get('material_instance_path')} | "
                    f"parent={item.get('parent_material') or 'Unknown'} | "
                    f"parameters={preview if preview != 'n/a' else item.get('parameter_count') or 0}"
                )
                continue
            if item.get("kind") == "code_file":
                classes = ", ".join(item.get("classes") or [])
                lines.append(
                    f"- {item.get('file_path')} | module={item.get('module_name') or 'n/a'}"
                    + (f" | classes={classes}" if classes else "")
                )
                continue
            settings = item.get("settings") if isinstance(item.get("settings"), dict) else {}
            blueprint = item.get("blueprint") if isinstance(item.get("blueprint"), dict) else {}
            setting_bits = []
            for key in (
                "nanite_enabled",
                "lod_count",
                "collision_complexity",
                "parent_class",
                "tick_enabled",
                "blend_mode",
                "srgb",
                "lightmap_resolution",
            ):
                if key in settings:
                    setting_bits.append(f"{key}={settings[key]}")
            parent_class = item.get("parent_class") or blueprint.get("parent_class") or settings.get("parent_class")
            if parent_class and not any(bit.startswith("parent_class=") for bit in setting_bits):
                setting_bits.append(f"parent_class={parent_class}")
            for label, value in (
                ("components", item.get("components") or blueprint.get("components")),
                ("variables", item.get("variables") or blueprint.get("variables")),
                ("functions", item.get("functions") or blueprint.get("functions")),
                ("graphs", item.get("graphs") or blueprint.get("graphs")),
            ):
                if isinstance(value, list) and value:
                    preview = ", ".join(str(entry) for entry in value[:5])
                    setting_bits.append(f"{label}={preview}")
            graph_summary_preview = _graph_summary_preview(item.get("graph_summaries") or blueprint.get("graph_summaries"))
            if graph_summary_preview != "n/a":
                setting_bits.append(f"graph_summaries={graph_summary_preview}")
            lines.append(
                f"- {item.get('asset_name') or item.get('asset_path')} | "
                f"type={item.get('asset_type') or 'Unknown'} | path={item.get('asset_path')}"
                + (f" | {', '.join(setting_bits)}" if setting_bits else "")
            )
        return "\n".join(lines)

    def _inventory_fact_query_requires_snapshot(self, query: str) -> bool:
        """Project-state questions must be grounded in UE inventory, not generic KB notes."""
        query_lower = query.lower()
        project_fact_markers = (
            "current",
            "selected",
            "this project",
            "my project",
            "in project",
            "opened",
            "currently",
            "当前",
            "选中",
            "现在",
            "当前项目",
            "当前工程",
            "我的项目",
            "我们项目",
            "本项目",
            "工程里",
            "工程中",
            "工程是否",
            "项目里",
            "项目中",
            "项目是否",
            "项目规定",
            "这个项目",
            "这个资产",
            "这个蓝图",
            "某个资产",
            "某个蓝图",
            "该资产",
            "该蓝图",
            "团队规定",
            "有哪些",
            "列出",
            "是否打开",
            "是否启用",
            "用了哪些",
            "包含哪些",
        )
        return any(marker in query_lower or marker in query for marker in project_fact_markers)

    def _project_qa_evidence_terms(self, retrieved_docs: list[dict[str, Any]]) -> list[str]:
        highlight_terms = (
            "BeginPlay",
            "Tick",
            "EndPlay",
            "EnhancedInput",
            "UInputAction",
            "InputAction",
            "UInputMappingContext",
            "MappingContext",
            "BindAction",
            "AsyncTask",
            "FRunnable",
            "GameThread",
            "TaskGraph",
            "HTTP",
            "JsonUtilities",
            "Json",
            "FHttpModule",
            "TSoftObjectPtr",
            "SoftObjectPath",
            "StreamableManager",
            "GameplayAbility",
            "AbilitySystemComponent",
            "DataAsset",
            "GameplayTag",
            "增强输入",
            "生命周期",
            "异步加载",
            "软引用",
        )
        blob = "\n".join(
            " ".join(
                str(doc.get(key) or "")
                for key in ("title", "source_path", "section_path", "text")
            )
            for doc in retrieved_docs
        ).lower()
        terms: list[str] = []
        for term in highlight_terms:
            if term.lower() in blob and term not in terms:
                terms.append(term)
        return terms[:12]

    def _empty_project_qa_result(self, *, query: str) -> dict[str, Any]:
        return {
            "answer": "",
            "confidence": 0.0,
            "sources": [],
            "citations": [],
            "retrieved_docs": [],
            "filters_applied": {},
            "local_search": {
                "query": query,
                "mode": "not_used",
                "status": "skipped",
                "reason": "tool_plan_skipped_knowledge_retrieval",
                "items": [],
                "summary": {
                    "result_count": 0,
                    "candidate_count": 0,
                    "searched_file_count": 0,
                    "skipped_file_count": 0,
                    "domain_filters": [],
                    "terms": [],
                },
            },
            "retrieval_quality_gate": {
                "status": "skipped",
                "evidence_sufficient": False,
                "evidence_insufficient": False,
                "reason": "tool_plan_skipped_knowledge_retrieval",
                "selected_round": 0,
                "selected_query": query,
                "retrieved_count": 0,
                "rag_retrieved_count": 0,
                "local_retrieved_count": 0,
            },
            "retrieval_trace": {
                "mode": "not_used",
                "degraded_mode": False,
                "reason": "tool_plan_skipped_knowledge_retrieval",
                "filters_applied": {},
                "retrieved_docs": [],
                "query": query,
                "selected_query": query,
                "retrieval_quality_gate": {
                    "status": "skipped",
                    "evidence_sufficient": False,
                    "evidence_insufficient": False,
                    "reason": "tool_plan_skipped_knowledge_retrieval",
                    "selected_round": 0,
                    "selected_query": query,
                    "retrieved_count": 0,
                    "rag_retrieved_count": 0,
                    "local_retrieved_count": 0,
                },
                "agentic_rag": {
                    "enabled": False,
                    "max_rounds": 0,
                    "attempts": [],
                    "selected_round": 0,
                    "selected_query": query,
                    "evidence_sufficient": False,
                    "evidence_insufficient": False,
                    "final_reason": "tool_plan_skipped_knowledge_retrieval",
                },
            },
            "warnings": [],
        }

    def _empty_inventory_result(self, *, query: str) -> dict[str, Any]:
        return {
            "items": [],
            "summary": {
                "query": query,
                "asset_match_count": 0,
                "code_file_match_count": 0,
                "tool_skipped": True,
            },
        }

    def _agent_chat_route_messages(
        self,
        request: UnifiedTaskRequest,
        *,
        output_language: str,
    ) -> list[dict[str, str]]:
        recent_history: list[str] = []
        for item in request.session.messages[-4:]:
            role = item.role if item.role in {"system", "user", "assistant"} else "user"
            if item.content.strip():
                recent_history.append(f"{role}: {item.content.strip()}")
        user_query = str(
            request.payload.get("user_query")
            or (request.session.messages[-1].content if request.session.messages else "")
        ).strip()
        context_summary = build_context_summary(request) or "(none)"
        system_prompt = (
            "You are a routing judge for UE Agent. "
            "Choose exactly one route for the next backend step: "
            "`direct_answer` or `project_qa`. "
            "Choose `direct_answer` for normal conversation, general coding questions, brainstorming, or questions that do not need repository-specific facts. "
            "Choose `project_qa` only when the user is clearly asking about the current file, current module, current project, project docs, knowledge base, configs, assets, or other project-specific facts that require retrieval. "
            "Do not choose `project_qa` just because editor context exists. "
            "If uncertain, prefer `direct_answer`. "
            f"Write the JSON reason in {self._language_label(output_language)}. "
            'Return JSON only, with this exact schema: {"route_type":"direct_answer","confidence":0.0,"reason":"..."}'
        )
        user_prompt = "\n\n".join(
            [
                f"Latest user query:\n{user_query or '(empty)'}",
                f"Context summary:\n{context_summary}",
                "Recent conversation:",
                "\n".join(recent_history) if recent_history else "(none)",
            ]
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _should_llm_refine_agent_chat_route(
        self,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
    ) -> bool:
        return (
            request.task_type == "agent_chat"
            and routing["intent"]["route_type"] in {"direct_answer", "project_qa"}
            and routing["route"].get("project_signal_strength") == "weak"
        )

    def _llm_route_reason(self, output_language: str, route_type: str) -> str:
        if route_type == "project_qa":
            return _localized(
                output_language,
                "LLM 复核后判断这个问题依赖项目上下文或知识库内容，因此升级为项目问答路径。",
                "The LLM route judge determined that this question depends on project-specific context or knowledge, so it was promoted to project QA.",
            )
        return _localized(
            output_language,
            "LLM 复核后判断这仍然属于普通聊天，上下文本身不足以触发知识检索。",
            "The LLM route judge determined that this is still ordinary chat, and editor context alone is not enough to trigger retrieval.",
        )

    def _apply_llm_route_decision(
        self,
        routing: dict[str, Any],
        *,
        output_language: str,
        decision: dict[str, Any] | None,
    ) -> dict[str, Any]:
        refined = {
            "locale": dict(routing["locale"]),
            "intent": dict(routing["intent"]),
            "route": dict(routing["route"]),
        }
        if not isinstance(decision, dict):
            refined["route"]["llm_route_decision"] = {
                "status": "skipped",
                "route_type": None,
                "confidence": 0.0,
                "reason": "llm_route_decision_missing",
                "error": "LLM route judge returned no structured decision.",
                "provider": None,
                "model": None,
                "profile_id": None,
            }
            return refined

        decision_ok = bool(decision.get("ok"))
        refined["route"]["llm_route_decision"] = {
            "status": "completed" if decision_ok else "skipped",
            "route_type": decision.get("route_type"),
            "confidence": float(decision.get("confidence") or 0.0),
            "reason": decision.get("reason"),
            "error": decision.get("error"),
            "provider": decision.get("provider"),
            "model": decision.get("model"),
            "profile_id": decision.get("profile_id"),
        }
        if not decision_ok or decision.get("route_type") not in {"direct_answer", "project_qa"}:
            return refined

        route_type = str(decision["route_type"])
        reason = self._llm_route_reason(output_language, route_type)
        confidence = max(
            float(refined["route"].get("planner_confidence") or 0.0),
            float(decision.get("confidence") or 0.0),
        )
        refined["route"]["decision_source"] = "llm_route_judge"
        refined["route"]["planner_confidence"] = confidence
        refined["route"]["route_type"] = route_type
        refined["route"]["route_reason"] = reason
        if route_type == "project_qa":
            refined["intent"].update(
                {
                    "intent_type": "project_qa",
                    "knowledge_relevance": "strong",
                    "requires_rag": True,
                    "requires_tool": False,
                    "route_type": "project_qa",
                    "reason": reason,
                }
            )
            refined["route"]["candidate_tool_ids"] = ["retrieve_project_knowledge"]
            refined["route"]["selected_tool_id"] = None
        else:
            knowledge_relevance = "possible" if refined["route"].get("context_present") else "none"
            refined["intent"].update(
                {
                    "intent_type": "casual_chat",
                    "knowledge_relevance": knowledge_relevance,
                    "requires_rag": False,
                    "requires_tool": False,
                    "route_type": "direct_answer",
                    "reason": reason,
                }
            )
            refined["route"]["candidate_tool_ids"] = []
            refined["route"]["selected_tool_id"] = None
        return refined

    def _refine_agent_chat_route(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        chat_config: ChatRuntimeConfig,
    ) -> dict[str, Any]:
        if not self._should_llm_refine_agent_chat_route(request, routing):
            return routing
        decision = self.llm_service.classify_agent_chat(
            messages=self._agent_chat_route_messages(
                request,
                output_language=routing["locale"]["final_output_language"],
            ),
            config=chat_config,
        )
        return self._apply_llm_route_decision(
            routing,
            output_language=routing["locale"]["final_output_language"],
            decision=decision,
        )

    @staticmethod
    def _should_persist_session_history(requested_task_type: str, actual_task_type: str) -> bool:
        return requested_task_type in CHAT_HISTORY_TASK_TYPES and actual_task_type in CHAT_HISTORY_TASK_TYPES

    def _build_context_bundle(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        actual_task_type: str | None = None,
        intent_draft_override: dict[str, Any] | None = None,
        llm_intent_draft_report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        bundle = build_context_bundle(
            db=self.db,
            request=request,
            routing=routing,
            settings=self.settings,
            actual_task_type=actual_task_type,
            intent_draft_override=intent_draft_override,
            llm_intent_draft_report=llm_intent_draft_report,
        )
        active_context = dict(bundle.get("active_context") or {})
        active_context["mcp"] = build_mcp_adapter_status(self.settings)
        blueprint_context = dict(active_context.get("blueprint") or {})
        editor_focus_context = dict(active_context.get("editor_focus") or {})
        level_actor_context = dict(active_context.get("level_actor") or {})
        material_context = dict(active_context.get("material") or {})
        current_blueprint_path = (
            blueprint_context.get("current_blueprint_path")
            or editor_focus_context.get("current_blueprint_path")
            or request.payload.get("current_blueprint_path")
            or request.context.editor_state.get("current_blueprint_path")
        )
        current_graph_name = (
            blueprint_context.get("current_graph_name")
            or editor_focus_context.get("current_graph_name")
            or request.payload.get("current_graph_name")
            or request.context.editor_state.get("current_graph_name")
        )
        current_node_id = (
            blueprint_context.get("selected_node_id")
            or request.payload.get("selected_node_id")
            or request.payload.get("current_node_id")
            or request.context.editor_state.get("selected_node_id")
            or request.context.editor_state.get("current_node_id")
        )
        current_node_name = (
            blueprint_context.get("selected_node_name")
            or request.payload.get("selected_node_name")
            or request.payload.get("current_node_name")
            or request.context.editor_state.get("selected_node_name")
            or request.context.editor_state.get("current_node_name")
        )
        selected_actor_references = [
            str(item or "").strip()
            for item in list(level_actor_context.get("selected_actor_references") or [])
            if str(item or "").strip()
        ]
        current_actor_reference = (
            level_actor_context.get("current_actor_reference")
            or request.payload.get("actor_reference")
            or request.payload.get("current_actor_reference")
            or request.context.editor_state.get("current_actor_reference")
            or request.context.editor_state.get("current_actor_label")
        )
        selected_material_instance_paths = [
            str(item or "").strip()
            for item in list(material_context.get("selected_material_instance_paths") or [])
            if str(item or "").strip()
        ]
        current_material_instance_path = (
            material_context.get("current_material_instance_path")
            or request.payload.get("material_instance_path")
            or request.payload.get("current_material_instance_path")
            or request.context.editor_state.get("material_instance_path")
            or request.context.editor_state.get("current_material_instance_path")
        )
        inventory_context = self.inventory_service.context_snapshot(
            project_id=self._inventory_project_id(request),
            selected_assets=list(request.context.selected_assets or []),
            selected_actor_references=selected_actor_references,
            selected_material_instance_paths=selected_material_instance_paths,
            current_file=request.context.current_file,
            current_blueprint_path=str(current_blueprint_path or "").strip() or None,
            current_graph_name=str(current_graph_name or "").strip() or None,
            current_node_id=str(current_node_id or "").strip() or None,
            current_node_name=str(current_node_name or "").strip() or None,
            current_actor_reference=str(current_actor_reference or "").strip() or None,
            current_material_instance_path=str(current_material_instance_path or "").strip() or None,
        )
        inventory_query = str(
            (bundle.get("input_summary") or {}).get("latest_user_message")
            or request.payload.get("user_query")
            or ""
        ).strip()
        if inventory_context.get("has_snapshot") and inventory_query:
            inventory_matches = self.inventory_service.query(
                query=inventory_query,
                project_id=self._inventory_project_id(request),
                selected_assets=list(request.context.selected_assets or []),
                selected_actor_references=selected_actor_references,
                current_actor_reference=str(current_actor_reference or "").strip() or None,
                selected_material_instance_paths=selected_material_instance_paths,
                current_material_instance_path=str(current_material_instance_path or "").strip() or None,
                limit=10,
            )
            inventory_context["query_candidates"] = list(inventory_matches.get("items") or [])
            inventory_context["query_summary"] = dict(inventory_matches.get("summary") or {})
        else:
            inventory_context["query_candidates"] = []
            inventory_context["query_summary"] = {}
        active_context["inventory"] = {
            "status": inventory_context.get("status"),
            "has_snapshot": inventory_context.get("has_snapshot"),
            "snapshot_id": inventory_context.get("snapshot_id"),
            "project_id": inventory_context.get("project_id"),
            "freshness": inventory_context.get("freshness") or {},
            "asset_count": (inventory_context.get("summary") or {}).get("asset_count", 0),
            "code_file_count": (inventory_context.get("summary") or {}).get("code_file_count", 0),
            "selected_asset_count": len(inventory_context.get("selected_assets") or []),
            "query_candidate_count": len(inventory_context.get("query_candidates") or []),
        }
        asset_context = dict(active_context.get("asset") or {})
        asset_context["selected_asset_details"] = inventory_context.get("selected_assets", [])
        active_context["asset"] = asset_context
        level_actor_context["selected_actor_details"] = inventory_context.get("selected_level_actors", [])
        if inventory_context.get("current_level_actor"):
            level_actor_context["current_actor_inventory"] = inventory_context.get("current_level_actor")
        active_context["level_actor"] = level_actor_context
        material_context["selected_material_instance_details"] = inventory_context.get("selected_material_instances", [])
        if inventory_context.get("current_material_instance"):
            material_context["current_material_instance_inventory"] = inventory_context.get("current_material_instance")
        active_context["material"] = material_context
        if inventory_context.get("current_blueprint"):
            blueprint_context["current_blueprint_inventory"] = inventory_context.get("current_blueprint")
        if inventory_context.get("current_blueprint_graph"):
            blueprint_context["current_graph_summary"] = inventory_context.get("current_blueprint_graph")
        if inventory_context.get("current_blueprint_node"):
            blueprint_context["current_node_summary"] = inventory_context.get("current_blueprint_node")
        active_context["blueprint"] = blueprint_context
        code_context = dict(active_context.get("code") or {})
        code_context["current_file_inventory"] = inventory_context.get("current_file")
        active_context["code"] = code_context
        bundle["active_context"] = active_context
        bundle["project_inventory_context"] = inventory_context
        bundle["context_pack"] = build_context_pack(bundle)
        return bundle

    def _apply_llm_intent_drafter(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        context_bundle: dict[str, Any],
        chat_config: ChatRuntimeConfig,
    ) -> tuple[dict[str, Any], dict[str, Any], str]:
        mode = self.settings.agent_intent_drafter_mode
        if mode == "disabled" or request.task_type not in {"agent_chat", "project_qa"}:
            return (routing, context_bundle, self._actual_task_type(request.task_type, routing))

        llm_result = self.llm_service.complete_json_object(
            messages=build_llm_intent_draft_messages(
                request=request,
                routing=routing,
                context_bundle=context_bundle,
                output_language=routing["locale"]["final_output_language"],
            ),
            config=chat_config,
        )
        outcome = apply_llm_intent_draft(
            deterministic_draft=dict(context_bundle.get("intent_draft") or {}),
            routing=routing,
            llm_result=llm_result,
            mode=mode,
            min_confidence=self.settings.agent_intent_drafter_min_confidence,
            context_resolution=dict(context_bundle.get("context_resolution") or {}),
        )
        refined_routing = outcome["routing"]
        actual_task_type = self._actual_task_type(request.task_type, refined_routing)
        refined_context_bundle = self._build_context_bundle(
            request=request,
            routing=refined_routing,
            actual_task_type=actual_task_type,
            intent_draft_override=outcome["intent_draft"],
            llm_intent_draft_report=outcome["report"],
        )
        return (refined_routing, refined_context_bundle, actual_task_type)

    def _apply_context_route_refinement(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        context_bundle: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], str]:
        refined_routing, report = refine_route_from_resolved_context(
            routing=routing,
            context_bundle=context_bundle,
            free_chat=request.task_type in {"agent_chat", "project_qa"},
        )
        if report.get("status") != "applied":
            context_bundle["context_route_refinement"] = report
            return (routing, context_bundle, self._actual_task_type(request.task_type, routing))

        actual_task_type = self._actual_task_type(request.task_type, refined_routing)
        refined_context_bundle = self._build_context_bundle(
            request=request,
            routing=refined_routing,
            actual_task_type=actual_task_type,
        )
        refined_context_bundle["context_route_refinement"] = report
        return (refined_routing, refined_context_bundle, actual_task_type)

    def create_task(
        self,
        request: UnifiedTaskRequest,
        stream_sink: StreamEventSink | None = None,
    ) -> UnifiedTaskResponse:
        session_model = get_or_create_session(
            self.db,
            request.session.session_id,
            project_name=request.context.project_name,
            preferred_output_language=None,
            profile_id=request.runtime_options.profile_id,
        )
        chat_config = self._resolve_chat_config(request)
        routing = classify_request(
            request,
            session_preference=session_model.preferred_output_language,
            signal_mode=self.settings.router_signal_mode,
            signal_min_confidence=self.settings.router_signal_min_confidence,
            signal_min_margin=self.settings.router_signal_min_margin,
        )
        routing = self._refine_agent_chat_route(request=request, routing=routing, chat_config=chat_config)
        preferred_language_to_store = (
            None
            if routing["locale"].get("language_source") == "message_override"
            else routing["locale"]["final_output_language"]
        )
        get_or_create_session(
            self.db,
            request.session.session_id,
            project_name=request.context.project_name,
            preferred_output_language=preferred_language_to_store,
            profile_id=request.runtime_options.profile_id,
        )
        actual_task_type = self._actual_task_type(request.task_type, routing)
        context_bundle = self._build_context_bundle(
            request=request,
            routing=routing,
            actual_task_type=actual_task_type,
        )
        routing, context_bundle, actual_task_type = self._apply_llm_intent_drafter(
            request=request,
            routing=routing,
            context_bundle=context_bundle,
            chat_config=chat_config,
        )
        routing, context_bundle, actual_task_type = self._apply_context_route_refinement(
            request=request,
            routing=routing,
            context_bundle=context_bundle,
        )
        persist_session_history = self._should_persist_session_history(
            request.task_type,
            actual_task_type,
        )
        if persist_session_history:
            append_messages(
                self.db,
                request.session.session_id,
                [message.model_dump(mode="json") for message in request.session.messages],
            )

        task_id = f"task_{uuid.uuid4().hex}"
        run_id = f"run_{uuid.uuid4().hex}"
        trace_id = f"trace_{uuid.uuid4().hex}"
        self._emit_stream_event(
            stream_sink,
            "run_started",
            {
                "task_type": actual_task_type,
                "route_type": routing["intent"]["route_type"],
                "trace_id": trace_id,
                "streaming_mode": "sse",
            },
            run_id=run_id,
            task_id=task_id,
        )

        started = time.perf_counter()
        execution = self._execute_route(
            request=request,
            routing=routing,
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            actual_task_type=actual_task_type,
            chat_config=chat_config,
            context_bundle=context_bundle,
            stream_sink=stream_sink,
        )
        execution["debug_view"]["active_context"] = context_bundle.get("active_context", {})
        execution["debug_view"]["context_pack"] = context_bundle.get("context_pack", {})
        execution["debug_view"]["agent_turn_context"] = context_bundle.get("agent_turn_context", {})
        execution["debug_view"]["context_budget_report"] = context_bundle.get("context_budget_report", {})
        execution["debug_view"]["intent_draft"] = context_bundle.get("intent_draft", {})
        execution["debug_view"]["llm_intent_draft"] = context_bundle.get("llm_intent_draft", {})
        execution["debug_view"]["context_resolution"] = context_bundle.get("context_resolution", {})
        execution["debug_view"]["context_route_refinement"] = context_bundle.get("context_route_refinement", {})
        execution["debug_view"]["verified_intent"] = context_bundle.get("verified_intent", {})
        execution["debug_view"]["tool_plan_v1"] = context_bundle.get("tool_plan_v1", {})
        execution["debug_view"]["tool_plan_self_check"] = context_bundle.get("tool_plan_self_check", {})
        execution["debug_view"]["tool_registry_protocol"] = tool_protocol_summary()
        execution["debug_view"]["tool_execution_policy"] = TOOL_EXECUTION_POLICY
        execution["debug_view"]["tools"] = enrich_tool_debug_entries(
            list(execution["debug_view"].get("tools") or [])
        )
        skill_runtime = build_skill_runtime_descriptor(
            requested_task_type=request.task_type,
            actual_task_type=actual_task_type,
            routing=routing,
            retrieval_trace=execution["retrieval_trace"],
            execution_data=execution["data"],
        )
        execution["debug_view"]["skill"] = skill_runtime
        execution["data"] = {**dict(execution.get("data") or {}), "skill": skill_runtime}
        execution["data"]["context_pack"] = context_bundle.get("context_pack", {})
        execution["data"]["agent_turn_context"] = context_bundle.get("agent_turn_context", {})
        execution["data"]["context_budget_report"] = context_bundle.get("context_budget_report", {})
        execution["data"]["intent_draft"] = context_bundle.get("intent_draft", {})
        execution["data"]["llm_intent_draft"] = context_bundle.get("llm_intent_draft", {})
        execution["data"]["context_resolution"] = context_bundle.get("context_resolution", {})
        execution["data"]["context_route_refinement"] = context_bundle.get("context_route_refinement", {})
        execution["data"]["verified_intent"] = context_bundle.get("verified_intent", {})
        execution["data"]["tool_plan_v1"] = context_bundle.get("tool_plan_v1", {})
        execution["data"]["tool_plan_self_check"] = context_bundle.get("tool_plan_self_check", {})
        execution["planner_diagnostics"] = {
            **dict(execution.get("planner_diagnostics") or {}),
            "skill": skill_runtime,
        }
        execution["action_proposals"] = self._normalize_action_proposals(execution["action_proposals"])
        artifact_payloads = self._materialize_artifacts(task_id, execution.get("artifacts", []))
        execution["debug_view"]["artifacts"] = artifact_payloads
        latency_ms = int((time.perf_counter() - started) * 1000)
        usage_payload = dict(execution.get("usage") or {})
        usage_payload["latency_ms"] = latency_ms
        usage = summarize_usage(usage_payload)
        task_status, finish_reason, output_complete = self._derive_task_outcome(
            execution["action_proposals"],
            execution["errors"],
        )
        execution["debug_view"].update(
            {
                "metrics": {
                    "latency_ms": usage["latency_ms"],
                    "estimated_cost_usd": usage["estimated_cost_usd"],
                    "input_tokens": usage["input_tokens"],
                    "output_tokens": usage["output_tokens"],
                },
                "session_summary": {
                    "session_id": request.session.session_id,
                    "message_count": len(request.session.messages),
                    "project_name": request.context.project_name,
                    "active_panel": request.context.active_panel,
                    "profile_id": chat_config.profile_id,
                    "profile_name": chat_config.profile_name,
                    "chat_model": chat_config.model,
                },
                "retrieval_summary": {
                    "mode": execution["retrieval_trace"].get("mode", "not_used"),
                    "retrieved_count": len(execution["retrieval_trace"].get("retrieved_docs", [])),
                    "degraded_mode": execution["retrieval_trace"].get("degraded_mode", False),
                },
                "memory_summary": {
                    "artifact_count": len(artifact_payloads),
                    "step_count": len(execution["step_results"]),
                    "session_memory": context_bundle.get("session_summary", {}),
                    "long_term_memory": context_bundle.get("long_term_memory", {}),
                    "file_memory": context_bundle.get("file_memory", {}),
                    "web_memory": context_bundle.get("web_memory", {}),
                    "memory": context_bundle.get("memory", {}),
                    "context_budget": context_bundle.get("budget", {}),
                    "context_budget_report": context_bundle.get("context_budget_report", {}),
                },
                "output_complete": output_complete,
                "finish_reason": finish_reason,
            }
        )
        execution = synthesize_execution_response(
            execution,
            output_language=routing["locale"]["final_output_language"],
            route_type=routing["intent"]["route_type"],
            selected_tool_id=routing["route"].get("selected_tool_id"),
        )
        execution = apply_response_critic(
            execution,
            output_language=routing["locale"]["final_output_language"],
        )
        active_target_memory_update = update_active_target_memory(
            self.db,
            request.session.session_id,
            context_bundle=context_bundle,
            task_id=task_id,
        )
        execution["debug_view"]["memory_summary"] = {
            **dict(execution["debug_view"].get("memory_summary") or {}),
            "updated_active_target_memory": active_target_memory_update,
        }
        conversation_focus_memory_update = update_conversation_focus_memory(
            self.db,
            request.session.session_id,
            context_bundle=context_bundle,
            execution=execution,
            task_id=task_id,
        )
        execution["debug_view"]["memory_summary"] = {
            **dict(execution["debug_view"].get("memory_summary") or {}),
            "updated_conversation_focus_memory": conversation_focus_memory_update,
        }
        if persist_session_history and execution["assistant_message"].strip():
            append_messages(
                self.db,
                request.session.session_id,
                [
                    {
                        "role": "assistant",
                        "content": execution["assistant_message"],
                        "language": routing["locale"]["final_output_language"],
                        "metadata": {
                            "task_id": task_id,
                            "run_id": run_id,
                            "task_type": actual_task_type,
                        },
                    }
                ],
            )
            memory_update = update_session_memory(self.db, request.session.session_id)
            execution["debug_view"]["memory_summary"] = {
                **dict(execution["debug_view"].get("memory_summary") or {}),
                "updated_session_memory": memory_update,
            }
        execution["debug_view"]["agent_decision_trace"] = build_agent_decision_trace(
            request=request,
            routing=routing,
            context_bundle=context_bundle,
            skill_runtime=skill_runtime,
            retrieval_trace=execution["retrieval_trace"],
            user_view_payload=execution["user_view"],
            debug_view=execution["debug_view"],
            data=execution["data"],
            task_status=task_status,
            finish_reason=finish_reason,
            output_complete=output_complete,
        )
        multi_agent_lite_trace = build_multi_agent_lite_trace(
            request=request,
            routing=routing,
            context_pack=context_bundle.get("context_pack", {}),
            skill_runtime=skill_runtime,
            retrieval_trace=execution["retrieval_trace"],
            data=execution["data"],
            debug_view=execution["debug_view"],
            action_proposals=execution["action_proposals"],
        )
        execution["debug_view"]["multi_agent_lite"] = multi_agent_lite_trace
        execution["data"]["multi_agent_lite"] = multi_agent_lite_trace
        react_v2_trace = build_react_v2_trace(
            request=request,
            routing=routing,
            context_pack=context_bundle.get("context_pack", {}),
            skill_runtime=skill_runtime,
            retrieval_trace=execution["retrieval_trace"],
            data=execution["data"],
            debug_view=execution["debug_view"],
            action_proposals=execution["action_proposals"],
            task_status=task_status,
            finish_reason=finish_reason,
            output_complete=output_complete,
        )
        execution["debug_view"]["react_trace"] = react_v2_trace
        execution["data"]["react_trace"] = react_v2_trace
        agent_dag = build_agent_dag_projection(
            request=request,
            routing=routing,
            context_bundle=context_bundle,
            skill_runtime=skill_runtime,
            retrieval_trace=execution["retrieval_trace"],
            data=execution["data"],
            debug_view=execution["debug_view"],
            action_proposals=execution["action_proposals"],
            task_status=task_status,
            finish_reason=finish_reason,
        )
        execution["debug_view"]["agent_dag"] = agent_dag
        execution["data"]["agent_dag"] = agent_dag
        subagent_runtime = build_subagent_runtime(agent_dag)
        execution["debug_view"]["subagent_runtime"] = subagent_runtime
        execution["data"]["subagent_runtime"] = subagent_runtime
        trace_summary = build_trace_summary(
            trace_id,
            routing["intent"]["route_type"],
            task_status,
            finish_reason=finish_reason,
            settings=self.settings,
        )
        trace_summary["skill_id"] = skill_runtime.get("skill_id")
        trace_summary["skill_task_type"] = skill_runtime.get("task_type")

        response = compose_unified_response(
            task={
                "task_id": task_id,
                "run_id": run_id,
                "task_type": actual_task_type,
                "status": task_status,
                "trace_id": trace_id,
                "output_complete": output_complete,
                "finish_reason": finish_reason,
            },
            intent=routing["intent"],
            locale=routing["locale"],
            user_view_payload=execution["user_view"],
            debug_payload=execution["debug_view"],
            data=execution["data"],
            usage=usage,
            trace_summary=trace_summary,
            retrieval_trace=execution["retrieval_trace"],
            planner_diagnostics=execution["planner_diagnostics"],
            step_results=execution["step_results"],
            action_proposals=execution["action_proposals"],
            errors=execution["errors"],
            assistant_message=execution["assistant_message"],
        )
        snapshot_path = self._write_snapshot(task_id, response.model_dump(mode="json"))
        event_payloads = build_persisted_event_payloads(
            task_id=task_id,
            run_id=run_id,
            response=response,
        )
        self._persist_task(
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            request=request,
            routing=routing,
            response=response,
            snapshot_path=snapshot_path,
            event_payloads=event_payloads,
            artifact_payloads=artifact_payloads,
        )
        self._emit_stream_event(
            stream_sink,
            "final",
            {
                "status": response.task.status,
                "finish_reason": response.task.finish_reason,
                "assistant_message": response.assistant_message,
                "response": response.model_dump(mode="json"),
            },
            run_id=run_id,
            task_id=task_id,
        )
        return response

    def list_recent(self) -> list[UnifiedTaskResponse]:
        return [self._to_response(task) for task in list_recent_tasks(self.db)]

    def get_task_response(self, task_id: str) -> UnifiedTaskResponse | None:
        task = get_task(self.db, task_id)
        return self._to_response(task) if task else None

    def get_run_response(self, run_id: str) -> UnifiedTaskResponse | None:
        task = get_task_by_run_id(self.db, run_id)
        return self._to_response(task) if task else None

    def get_task_events(self, task_id: str) -> list[dict[str, Any]]:
        return [item.payload_json for item in list_task_events(self.db, task_id)]

    def get_run_events(self, run_id: str) -> list[dict[str, Any]] | None:
        task = get_task_by_run_id(self.db, run_id)
        if not task:
            return None
        return self.get_task_events(task.task_id)

    def get_task_artifacts(self, task_id: str) -> list[ArtifactDescriptor]:
        return [
            ArtifactDescriptor(
                artifact_id=item.artifact_id,
                artifact_type=item.artifact_type,
                label=item.label,
                path=item.path,
                metadata=item.metadata_json,
            )
            for item in list_task_artifacts(self.db, task_id)
        ]

    def cancel_run(self, run_id: str) -> UnifiedTaskResponse | None:
        task = get_task_by_run_id(self.db, run_id)
        if not task:
            return None
        if task.status not in {"accepted", "running", "waiting_confirmation"}:
            return self._to_response(task)

        mark_task_cancelled(self.db, task)
        task.action_proposals_json = [
            {
                **item,
                "confirmation": {
                    **dict(item.get("confirmation") or {}),
                    "state": "rejected",
                },
            }
            for item in task.action_proposals_json
        ]
        raw_response = dict(task.raw_response_json or {})
        raw_response["task"] = {
            **dict(raw_response.get("task") or {}),
            "status": "cancelled",
            "finish_reason": task.finish_reason,
            "output_complete": True,
        }
        raw_response["trace_summary"] = {
            **dict(raw_response.get("trace_summary") or {}),
            "final_status": "cancelled",
            "finish_reason": task.finish_reason,
        }
        raw_response["action_proposals"] = task.action_proposals_json
        raw_response["debug_view"] = {
            **dict(raw_response.get("debug_view") or {}),
            "output_complete": True,
            "finish_reason": task.finish_reason,
        }
        task.raw_response_json = raw_response
        task.trace_summary_json = raw_response["trace_summary"]
        task.debug_view_json = raw_response["debug_view"]
        save_task(self.db, task)

        event_payload = build_run_cancelled_event_payload(
            run_id=run_id,
            task_id=task.task_id,
            finish_reason=task.finish_reason,
            seq=len(list_task_events(self.db, task.task_id)) + 1,
        )
        add_task_event(
            self.db,
            TaskEventModel(
                event_id=f"evt_{uuid.uuid4().hex}",
                task_id=task.task_id,
                event_type="run_cancelled",
                payload_json=event_payload,
            ),
        )
        audit_entry = build_audit_entry(
            "run_cancelled",
            {"run_id": run_id, "finish_reason": task.finish_reason},
            task_id=task.task_id,
            session_id=task.session_id,
        )
        create_audit_log(
            self.db,
            AuditLogModel(
                audit_id=f"audit_{uuid.uuid4().hex}",
                task_id=task.task_id,
                session_id=task.session_id,
                event_type=audit_entry["event_type"],
                payload_json=audit_entry["payload"],
            ),
        )
        return self._to_response(task)

    def _normalize_action_proposals(self, proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in proposals:
            proposal_id = item.get("proposal_id") or f"proposal_{uuid.uuid4().hex}"
            requires_confirmation = bool(item.get("requires_confirmation", True))
            confirmation = dict(item.get("confirmation") or {})
            if requires_confirmation:
                confirmation.setdefault("state", "pending")
                confirmation.setdefault("decision_endpoint", f"/api/v1/proposals/{proposal_id}/decision")
            else:
                confirmation.setdefault("state", "not_required")
                confirmation.setdefault("decision_endpoint", None)
            normalized.append(
                {
                    **item,
                    "proposal_id": proposal_id,
                    "confirmation": confirmation,
                }
            )
        return normalized

    def _derive_task_outcome(
        self,
        proposals: list[dict[str, Any]],
        errors: list[dict[str, Any]],
    ) -> tuple[str, str, bool]:
        if errors:
            return ("failed", "execution_error", True)
        if any(
            item.get("requires_confirmation")
            and (item.get("confirmation") or {}).get("state") == "pending"
            for item in proposals
        ):
            return ("waiting_confirmation", "waiting_confirmation", True)
        return ("completed", "completed", True)

    def _actual_task_type(self, request_task_type: str, routing: dict[str, Any]) -> str:
        if request_task_type != "agent_chat":
            return request_task_type
        route_type = routing["intent"]["route_type"]
        if route_type == "project_qa":
            return "project_qa"
        selected_tool_id = routing["route"].get("selected_tool_id")
        if selected_tool_id and selected_tool_id in TOOL_ID_TO_TASK_TYPE:
            return TOOL_ID_TO_TASK_TYPE[selected_tool_id]
        if route_type in {"single_tool", "workflow"}:
            return "task_request"
        return "agent_chat"

    def _base_debug(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        trace_id: str,
        context_bundle: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_context_bundle = context_bundle or self._build_context_bundle(
            request=request,
            routing=routing,
        )
        return {
            "raw_request": redact_payload(request.model_dump(mode="json")),
            "normalized_request": request.model_dump(mode="json"),
            "intent": routing["intent"],
            "route": routing["route"],
            "context_bundle": resolved_context_bundle,
            "context_pack": resolved_context_bundle.get("context_pack", {}),
            "agent_turn_context": resolved_context_bundle.get("agent_turn_context", {}),
            "context_budget_report": resolved_context_bundle.get("context_budget_report", {}),
            "intent_draft": resolved_context_bundle.get("intent_draft", {}),
            "context_resolution": resolved_context_bundle.get("context_resolution", {}),
            "context_route_refinement": resolved_context_bundle.get("context_route_refinement", {}),
            "verified_intent": resolved_context_bundle.get("verified_intent", {}),
            "tool_plan_v1": resolved_context_bundle.get("tool_plan_v1", {}),
            "active_context": resolved_context_bundle.get("active_context", {}),
            "graph_framework": graph_framework_readiness_report(
                review_fix_validate_graph_spec(),
                requested_framework=self.settings.agent_graph_framework,
            ),
            "tool_registry_protocol": tool_protocol_summary(),
            "tool_execution_policy": TOOL_EXECUTION_POLICY,
            "retrieval": {},
            "retrieval_summary": {},
            "tools": [],
            "step_results": [],
            "raw_result": {},
            "artifacts": [],
            "trace_links": [{"type": "local_trace", "trace_id": trace_id}],
            "metrics": {},
            "session_summary": {},
            "memory_summary": {
                "session_memory": resolved_context_bundle.get("session_summary", {}),
                "long_term_memory": resolved_context_bundle.get("long_term_memory", {}),
                "file_memory": resolved_context_bundle.get("file_memory", {}),
                "context_budget": resolved_context_bundle.get("budget", {}),
                "context_budget_report": resolved_context_bundle.get("context_budget_report", {}),
            },
            "output_complete": True,
            "finish_reason": "completed",
            "warnings": [],
        }

    def _handler_dependencies(self) -> TaskHandlerDependencies:
        return TaskHandlerDependencies(
            db=self.db,
            settings=self.settings,
            kb_service=self.kb_service,
            llm_service=self.llm_service,
            inventory_service=self.inventory_service,
            base_debug_builder=self._base_debug,
            stream_event_emitter=self._emit_stream_event,
        )

    def _execute_route(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        task_id: str,
        run_id: str,
        trace_id: str,
        actual_task_type: str,
        chat_config: ChatRuntimeConfig,
        context_bundle: dict[str, Any],
        stream_sink: StreamEventSink | None = None,
    ) -> dict[str, Any]:
        return self.route_dispatcher.execute(
            self,
            TaskExecutionContext(
                request=request,
                routing=routing,
                task_id=task_id,
                run_id=run_id,
                trace_id=trace_id,
                actual_task_type=actual_task_type,
                output_language=routing["locale"]["final_output_language"],
                chat_config=chat_config,
                context_bundle=context_bundle,
                stream_sink=stream_sink,
                dependencies=self._handler_dependencies(),
            ),
        )

    def _query_text(self, request: UnifiedTaskRequest) -> str:
        return str(
            request.payload.get("user_query")
            or request.payload.get("requirement_description")
            or (request.session.messages[-1].content if request.session.messages else "")
            or ""
        ).strip()

    def _multi_agent_requested(self, *, request: UnifiedTaskRequest, routing: dict[str, Any]) -> bool:
        payload = request.payload or {}
        workflow_mode = str(payload.get("workflow_mode") or payload.get("agent_chain") or "").strip().lower()
        if workflow_mode in {"review_fix_validate", "multi_agent_review_fix", "code_review_fix_validate"}:
            return True
        enable_multi_agent = payload.get("enable_multi_agent")
        if enable_multi_agent is True or str(enable_multi_agent or "").strip().lower() in {"1", "true", "yes", "on"}:
            return True
        selected_tool_id = str((routing.get("route") or {}).get("selected_tool_id") or "")
        if selected_tool_id == "multi_agent_code_review_and_fix":
            return True
        text = self._query_text(request).lower()
        trigger_phrases = (
            "review and fix",
            "fix after review",
            "fix review issues",
            "auto fix",
            "review fix validate",
            "审查并修复",
            "检查并修复",
            "自动修复",
            "修复这些问题",
        )
        return any(phrase in text for phrase in trigger_phrases)

    def _materialize_artifacts(
        self,
        task_id: str,
        artifact_specs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        artifact_dir = task_artifact_dir(self.settings, task_id)
        materialized: list[dict[str, Any]] = []
        for spec in artifact_specs:
            artifact_id = f"artifact_{uuid.uuid4().hex}"
            filename = spec["filename"]
            path = artifact_dir / filename
            content = spec.get("content")
            if isinstance(content, (dict, list)):
                path.write_text(dumps_pretty(content), encoding="utf-8")
            else:
                path.write_text(str(content or ""), encoding="utf-8")
            materialized.append(
                {
                    "artifact_id": artifact_id,
                    "artifact_type": spec["artifact_type"],
                    "label": spec["label"],
                    "path": str(path),
                    "metadata": spec.get("metadata", {}),
                }
            )
        return materialized

    def _persist_task(
        self,
        *,
        task_id: str,
        run_id: str,
        trace_id: str,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        response: UnifiedTaskResponse,
        snapshot_path: Path,
        event_payloads: list[dict[str, Any]],
        artifact_payloads: list[dict[str, Any]],
    ) -> None:
        db_task = TaskModel(
            task_id=task_id,
            run_id=run_id,
            session_id=request.session.session_id,
            task_type=response.task.task_type,
            status=response.task.status,
            trace_id=trace_id,
            intent_type=response.intent.intent_type,
            knowledge_relevance=response.intent.knowledge_relevance,
            route_type=response.intent.route_type,
            route_reason=response.intent.reason,
            selected_tool_id=routing["route"].get("selected_tool_id"),
            candidate_tool_ids=routing["route"].get("candidate_tool_ids", []),
            planner_confidence=routing["route"].get("planner_confidence", 0.0),
            locale_json=response.locale.model_dump(mode="json"),
            user_view_json=response.user_view.model_dump(mode="json"),
            debug_view_json=response.debug_view.model_dump(mode="json"),
            presentation_json=response.presentation.model_dump(mode="json"),
            assistant_message=response.assistant_message,
            data_json=response.data,
            usage_json=response.usage.model_dump(mode="json"),
            trace_summary_json=response.trace_summary,
            retrieval_trace_json=response.retrieval_trace,
            planner_diagnostics_json=response.planner_diagnostics,
            step_results_json=[item.model_dump(mode="json") for item in response.step_results],
            action_proposals_json=[item.model_dump(mode="json") for item in response.action_proposals],
            errors_json=[item.model_dump(mode="json") for item in response.errors],
            raw_request_json=response.debug_view.raw_request,
            raw_response_json=response.model_dump(mode="json"),
            snapshot_path=str(snapshot_path),
            output_complete=response.task.output_complete,
            finish_reason=response.task.finish_reason,
            completed_at=(
                now_utc()
                if response.task.status in {"completed", "failed", "cancelled"}
                else None
            ),
        )
        create_task(self.db, db_task)

        for payload in event_payloads:
            add_task_event(
                self.db,
                TaskEventModel(
                    event_id=f"evt_{uuid.uuid4().hex}",
                    task_id=task_id,
                    event_type=payload["event"],
                    payload_json=payload,
                ),
            )

        for item in artifact_payloads:
            add_task_artifact(
                self.db,
                TaskArtifactModel(
                    artifact_id=item["artifact_id"],
                    task_id=task_id,
                    artifact_type=item["artifact_type"],
                    label=item["label"],
                    path=item["path"],
                    metadata_json=item["metadata"],
                ),
            )

        for proposal in response.action_proposals:
            create_proposal(
                self.db,
                ProposalModel(
                    proposal_id=proposal.proposal_id,
                    task_id=task_id,
                    title=proposal.title,
                    proposal_type=proposal.proposal_type,
                    before_summary=proposal.before_summary,
                    after_summary=proposal.after_summary,
                    rationale=proposal.rationale,
                    risk_flags=proposal.risk_flags,
                    dry_run_preview_json=proposal.dry_run_preview,
                    display_hints_json=proposal.display_hints,
                    requires_confirmation=proposal.requires_confirmation,
                    confirmation_state=proposal.confirmation.get("state", "pending"),
                    decision_endpoint=proposal.confirmation.get("decision_endpoint"),
                ),
            )
            proposal_audit = build_audit_entry(
                "proposal_emitted",
                {
                    "proposal_id": proposal.proposal_id,
                    "proposal_type": proposal.proposal_type,
                    "confirmation_state": proposal.confirmation.get("state"),
                },
                task_id=task_id,
                session_id=request.session.session_id,
            )
            create_audit_log(
                self.db,
                AuditLogModel(
                    audit_id=f"audit_{uuid.uuid4().hex}",
                    task_id=task_id,
                    session_id=request.session.session_id,
                    event_type=proposal_audit["event_type"],
                    payload_json=proposal_audit["payload"],
                ),
            )

        audit_entry = build_audit_entry(
            "task_persisted",
            {
                "run_id": run_id,
                "task_type": response.task.task_type,
                "status": response.task.status,
                "finish_reason": response.task.finish_reason,
                "proposal_count": len(response.action_proposals),
            },
            task_id=task_id,
            session_id=request.session.session_id,
        )
        create_audit_log(
            self.db,
            AuditLogModel(
                audit_id=f"audit_{uuid.uuid4().hex}",
                task_id=task_id,
                session_id=request.session.session_id,
                event_type=audit_entry["event_type"],
                payload_json=audit_entry["payload"],
            ),
        )

    def _to_response(self, task: TaskModel | None) -> UnifiedTaskResponse | None:
        if not task:
            return None
        response = UnifiedTaskResponse.model_validate(task.raw_response_json)
        response.task.status = task.status
        response.task.output_complete = task.output_complete
        response.task.finish_reason = task.finish_reason
        response.action_proposals = [ActionProposal.model_validate(item) for item in task.action_proposals_json]
        response.trace_summary["final_status"] = task.status
        response.trace_summary["finish_reason"] = task.finish_reason
        response.debug_view.output_complete = task.output_complete
        response.debug_view.finish_reason = task.finish_reason
        return response

    def _write_snapshot(self, task_id: str, payload: dict[str, Any]) -> Path:
        artifact_dir = task_artifact_dir(self.settings, task_id)
        snapshot_path = artifact_dir / "debug_snapshot.json"
        snapshot_path.write_text(dumps_pretty(payload), encoding="utf-8")
        return snapshot_path
