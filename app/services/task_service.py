from __future__ import annotations

import os
import re
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.agent.context_builder import build_context_summary
from app.agent.context_manager import build_context_bundle, context_bundle_prompt_excerpt
from app.agent.decision_trace import build_agent_decision_trace
from app.agent.memory_manager import update_session_memory
from app.agent.multi_agent import ReviewFixValidateChain
from app.agent.response_composer import compose_unified_response
from app.agent.router import classify_request
from app.agent.self_reflection import build_self_reflection
from app.agent.tool_planner import (
    build_project_qa_tool_calls,
    build_react_planner_messages,
    sanitize_react_planner_payload,
    tool_call_sequence,
)
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
from app.schemas.common import ActionProposal, ArtifactDescriptor, CitationPreview, QuickAction, UserViewBlock
from app.schemas.requests import EditorOperationProposalRequest, UnifiedTaskRequest
from app.schemas.responses import UnifiedTaskResponse
from app.services.kb_service import KnowledgeBaseService
from app.services.llm_service import ChatRuntimeConfig, LLMService, chat_runtime_config
from app.services.editor_operation_service import (
    EDITOR_OPERATION_PROTOCOL_VERSION,
    OPERATION_SPECS,
    EditorOperationService,
    EditorOperationValidationError,
)
from app.services.mcp_tool_adapter import build_mcp_adapter_status
from app.services.project_inventory_service import ProjectInventoryService
from app.services.task_handlers import RouteExecutionDispatcher, TaskExecutionContext
from app.skills.executors import (
    AssetsInspectSkillExecutor,
    CodeGenerateSkillExecutor,
    CodeReviewSkillExecutor,
    LogsAnalyzeSkillExecutor,
)
from app.skills.runtime import build_skill_runtime_descriptor
from app.tools.contracts import validate_tool_call_input, validate_tool_result
from app.tools.registry import (
    TOOL_EXECUTION_POLICY,
    TOOL_ID_TO_TASK_TYPE,
    enrich_tool_debug_entries,
    free_chat_tool_ids,
    tool_capability_cards,
    tool_protocol_summary,
)
from app.utils.json_tools import dumps_pretty
from app.utils.paths import task_artifact_dir
from app.utils.time import now_utc
from app.workflows.graphs import (
    run_config_generate_workflow,
    run_perf_analyze_workflow,
)

CHAT_HISTORY_TASK_TYPES = {"agent_chat", "project_qa"}
StreamEventSink = Callable[[dict[str, Any]], None]


def _localized(language: str, zh_text: str, en_text: str) -> str:
    return zh_text if language.startswith("zh") else en_text


def _citation_previews(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        CitationPreview(
            title=item["title"],
            source=item["source"],
            snippet=item.get("snippet"),
        ).model_dump(mode="json")
        for item in citations[:3]
    ]


class TaskService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings
        self.kb_service = KnowledgeBaseService(db, settings)
        self.llm_service = LLMService(settings)
        self.inventory_service = ProjectInventoryService(settings)
        self.route_dispatcher = RouteExecutionDispatcher()
        self._stream_sequence = 0

    def _emit_stream_event(
        self,
        sink: StreamEventSink | None,
        event: str,
        payload: dict[str, Any],
        *,
        run_id: str | None = None,
        task_id: str | None = None,
    ) -> None:
        if not sink:
            return
        self._stream_sequence += 1
        sink(
            {
                "event": event,
                "seq": self._stream_sequence,
                "timestamp": now_utc().isoformat(),
                "run_id": run_id,
                "task_id": task_id,
                "payload": payload,
            }
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
            inventory_lines.append(
                "\n".join(
                    [
                        f"[I{index}] Asset: {item.get('asset_name') or item.get('asset_path')}",
                        f"Type: {item.get('asset_type') or 'Unknown'}",
                        f"Path: {item.get('asset_path') or 'n/a'}",
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
        system_prompt = (
            "You are synthesizing an answer from project knowledge-base evidence. "
            f"Reply in {self._language_label(output_language)}. "
            "Use only the supplied knowledge-base evidence, controlled web evidence, project inventory facts, and explicitly read project file excerpts. "
            "Treat local KB, project inventory, and team rules as higher priority than web search; web evidence is supplemental. "
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
        if not items:
            if not summary.get("has_snapshot"):
                return _localized(
                    output_language,
                    "当前没有找到可用的 Project Inventory 快照，所以我无法列出当前工程里的资产或代码文件。请先在 UE 插件 Debug View 点击 Submit Inventory，提交一次项目快照后再询问。",
                    "No Project Inventory snapshot is available yet, so I cannot list assets or code files from the current project. Submit a Project Inventory snapshot from the UE plugin Debug View first, then ask again.",
                )
            return _localized(
                output_language,
                "Project Inventory 已有快照，但本次问题没有命中匹配的资产或代码文件。你可以换一个更具体的资产名、类型、模块名，或重新提交一次最新快照。",
                "A Project Inventory snapshot exists, but no assets or code files matched this question. Try a more specific asset name, asset type, module name, or submit a fresh snapshot.",
            )
        lines = [
            _localized(
                output_language,
                f"我从 Project Inventory 中找到了 {len(items)} 条相关项目事实：",
                f"I found {len(items)} matching project inventory item(s):",
            )
        ]
        for item in items[:8]:
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
            lines.append(
                f"- {item.get('asset_name') or item.get('asset_path')} | "
                f"type={item.get('asset_type') or 'Unknown'} | path={item.get('asset_path')}"
                + (f" | {', '.join(setting_bits)}" if setting_bits else "")
            )
        return "\n".join(lines)

    def _project_qa_tool_plan(self, *, query: str, routing: dict[str, Any]) -> dict[str, Any]:
        selected_tool_id = routing["route"].get("selected_tool_id")
        query_lower = query.lower()
        inventory_tokens = (
            "asset",
            "assets",
            "blueprint",
            "staticmesh",
            "static mesh",
            "skeletal",
            "material",
            "texture",
            "nanite",
            "lod",
            "code file",
            ".cpp",
            ".h",
            "module",
            "settings",
            "properties",
            "component",
            "components",
            "variable",
            "variables",
            "function",
            "functions",
            "graph",
            "graphs",
            "event graph",
            "selected asset",
            "current asset",
            "资产",
            "蓝图",
            "静态网格体",
            "材质",
            "贴图",
            "代码文件",
            "模块",
            "属性",
            "设置",
        )
        knowledge_tokens = (
            "why",
            "how",
            "should",
            "best practice",
            "rule",
            "guideline",
            "explain",
            "risk",
            "为什么",
            "怎么",
            "如何",
            "应该",
            "规范",
            "规则",
            "建议",
            "风险",
            "解释",
        )
        use_inventory = selected_tool_id == "query_project_inventory" or any(
            token in query_lower or token in query for token in inventory_tokens
        )
        needs_knowledge = selected_tool_id != "query_project_inventory" or any(
            token in query_lower or token in query for token in knowledge_tokens
        )
        return {
            "selected_tool_id": selected_tool_id,
            "use_inventory": use_inventory,
            "use_knowledge": needs_knowledge,
            "reason": (
                "inventory_first"
                if selected_tool_id == "query_project_inventory"
                else "retrieval_backed_project_qa"
            ),
        }

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

    def _project_file_candidate(self, request: UnifiedTaskRequest) -> dict[str, Any]:
        project_root = str(
            request.payload.get("project_root")
            or request.context.project_root
            or ""
        ).strip()
        file_path = str(
            request.payload.get("read_file_path")
            or request.payload.get("file_path")
            or request.payload.get("current_file")
            or request.context.current_file
            or ""
        ).strip()
        try:
            max_bytes = int(request.payload.get("max_file_read_bytes") or 40_000)
        except (TypeError, ValueError):
            max_bytes = 40_000
        return {
            "project_root": project_root,
            "file_path": file_path,
            "max_bytes": max(1024, min(max_bytes, 120_000)),
        }

    def _should_read_project_file(self, *, request: UnifiedTaskRequest, query: str) -> bool:
        candidate = self._project_file_candidate(request)
        if not candidate["project_root"] or not candidate["file_path"]:
            return False
        lowered = query.lower()
        file_reference_tokens = (
            "this file",
            "current file",
            "that file",
            "read file",
            "open file",
            "explain file",
            "这个文件",
            "当前文件",
            "该文件",
            "读取文件",
            "查看文件",
            "解释文件",
        )
        return any(token in lowered or token in query for token in file_reference_tokens)

    def _read_project_file_tool(self, request: UnifiedTaskRequest) -> dict[str, Any]:
        candidate = self._project_file_candidate(request)
        project_root = candidate["project_root"]
        file_path = candidate["file_path"]
        max_bytes = int(candidate["max_bytes"])
        if not project_root or not file_path:
            return {
                "status": "skipped",
                "reason": "missing_project_root_or_file_path",
                "file_path": file_path,
            }

        root = Path(project_root).resolve()
        requested = Path(file_path)
        resolved = requested.resolve() if requested.is_absolute() else (root / requested).resolve()
        try:
            is_inside_root = os.path.commonpath([str(root), str(resolved)]) == str(root)
        except ValueError:
            is_inside_root = False
        if not is_inside_root:
            return {
                "status": "blocked",
                "reason": "file_outside_project_root",
                "file_path": file_path,
                "project_root": str(root),
                "resolved_path": str(resolved),
            }

        allowed_suffixes = {
            ".h",
            ".hpp",
            ".hh",
            ".inl",
            ".c",
            ".cc",
            ".cpp",
            ".cxx",
            ".cs",
            ".md",
            ".txt",
            ".json",
            ".ini",
            ".yaml",
            ".yml",
            ".uproject",
            ".uplugin",
        }
        if resolved.suffix.lower() not in allowed_suffixes:
            return {
                "status": "blocked",
                "reason": "unsupported_file_extension",
                "file_path": file_path,
                "resolved_path": str(resolved),
                "allowed_suffixes": sorted(allowed_suffixes),
            }
        if not resolved.exists() or not resolved.is_file():
            return {
                "status": "error",
                "reason": "file_not_found",
                "file_path": file_path,
                "resolved_path": str(resolved),
            }

        with resolved.open("rb") as handle:
            raw = handle.read(max_bytes + 1)
        truncated = len(raw) > max_bytes
        text = raw[:max_bytes].decode("utf-8", errors="replace")
        return {
            "status": "completed",
            "reason": "read_completed",
            "file_path": file_path,
            "resolved_path": str(resolved),
            "bytes_read": min(len(raw), max_bytes),
            "max_bytes": max_bytes,
            "truncated": truncated,
            "text_excerpt": text,
        }

    def _project_file_fallback_answer(
        self,
        *,
        project_file_result: dict[str, Any],
        output_language: str,
    ) -> str:
        if project_file_result.get("status") == "completed":
            excerpt = str(project_file_result.get("text_excerpt") or "").strip()
            preview = excerpt[:500] + ("..." if len(excerpt) > 500 else "")
            return _localized(
                output_language,
                f"我已读取当前项目文件 `{project_file_result.get('file_path')}`。当前没有可用 LLM 综合解释，因此先返回文件片段供你确认：\n\n{preview}",
                f"I read project file `{project_file_result.get('file_path')}`. No live LLM synthesis is available, so here is the file excerpt for confirmation:\n\n{preview}",
            )
        return _localized(
            output_language,
            f"我尝试读取当前项目文件，但未成功：{project_file_result.get('reason') or 'unknown_reason'}。",
            f"I tried to read the current project file, but it did not succeed: {project_file_result.get('reason') or 'unknown_reason'}.",
        )

    def _react_planner_messages(
        self,
        *,
        request: UnifiedTaskRequest,
        query: str,
        deterministic_plan: dict[str, Any],
        output_language: str,
    ) -> list[dict[str, str]]:
        allowed_tool_ids = free_chat_tool_ids()
        allowed_tools = [
            card
            for card in tool_capability_cards()
            if card["tool_id"] in allowed_tool_ids
        ]
        return build_react_planner_messages(
            query=query,
            context_summary=build_context_summary(request) or "(none)",
            deterministic_plan=deterministic_plan,
            allowed_tools=allowed_tools,
            output_language_label=self._language_label(output_language),
        )

    def _react_lite_tool_plan(
        self,
        *,
        request: UnifiedTaskRequest,
        query: str,
        deterministic_plan: dict[str, Any],
        chat_config: ChatRuntimeConfig,
        output_language: str,
    ) -> dict[str, Any]:
        allowed_tool_ids = free_chat_tool_ids()
        planner_decision = {
            "status": "skipped",
            "reason": "llm_unavailable_or_not_attempted",
            "requested_tool_ids": [],
            "confidence": 0.0,
            "error": "",
            "provider": "openai_compatible",
            "model": chat_config.model,
            "profile_id": chat_config.profile_id,
        }
        use_inventory = bool(deterministic_plan.get("use_inventory"))
        use_knowledge = bool(deterministic_plan.get("use_knowledge"))
        use_project_file = self._should_read_project_file(request=request, query=query)
        planner_inputs: dict[str, dict[str, Any]] = {}

        llm_available, _ = self.llm_service.availability(chat_config)
        if llm_available:
            decision = self.llm_service.complete_json_object(
                messages=self._react_planner_messages(
                    request=request,
                    query=query,
                    deterministic_plan=deterministic_plan,
                    output_language=output_language,
                ),
                config=chat_config,
            )
            planner_decision.update(
                {
                    "status": "completed" if decision.get("ok") else "skipped",
                    "reason": decision.get("reason"),
                    "error": decision.get("error") or "",
                    "provider": decision.get("provider"),
                    "model": decision.get("model"),
                    "profile_id": decision.get("profile_id"),
                }
            )
            payload = decision.get("payload") if decision.get("ok") else None
            if isinstance(payload, dict):
                sanitized = sanitize_react_planner_payload(
                    payload,
                    allowed_tool_ids=set(allowed_tool_ids),
                )
                requested_tool_ids = sanitized["requested_tool_ids"]
                planner_inputs = sanitized["tool_inputs_by_id"]
                planner_decision["requested_tool_ids"] = requested_tool_ids
                planner_decision["tool_inputs_by_id"] = planner_inputs
                planner_decision["confidence"] = sanitized["confidence"]
                use_inventory = use_inventory or "query_project_inventory" in requested_tool_ids
                use_knowledge = use_knowledge or "retrieve_project_knowledge" in requested_tool_ids
                use_project_file = use_project_file or "read_project_file" in requested_tool_ids

        candidate = self._project_file_candidate(request) if use_project_file else {}
        project_file_input = (
            {
                "project_root": candidate["project_root"],
                "file_path": candidate["file_path"],
                "max_bytes": candidate["max_bytes"],
            }
            if candidate
            else None
        )
        tool_calls = build_project_qa_tool_calls(
            query=query,
            use_inventory=use_inventory,
            use_knowledge=use_knowledge,
            use_project_file=use_project_file,
            rag_top_k=self.settings.rag_top_k,
            planner_inputs=planner_inputs,
            project_file_input=project_file_input,
        )
        input_contracts = [
            validate_tool_call_input(str(call.get("tool_id") or ""), dict(call.get("input") or {}))
            for call in tool_calls
        ]
        return {
            **deterministic_plan,
            "use_inventory": use_inventory,
            "use_knowledge": use_knowledge,
            "use_project_file": use_project_file,
            "tool_calls": tool_calls,
            "tool_call_sequence": tool_call_sequence(tool_calls),
            "input_contracts": input_contracts,
            "planner_decision": planner_decision,
            "reason": (
                "react_lite_llm_augmented"
                if planner_decision["status"] == "completed"
                else deterministic_plan.get("reason", "deterministic_fallback")
            ),
        }

    def _build_react_lite_trace(
        self,
        *,
        query: str,
        tool_plan: dict[str, Any],
        qa_result: dict[str, Any],
        inventory_result: dict[str, Any],
        project_file_result: dict[str, Any],
        answer_generation_mode: str,
    ) -> dict[str, Any]:
        steps: list[dict[str, Any]] = [
            {
                "phase": "thought",
                "text": "Decide whether the user needs current project facts, knowledge evidence, an explicit file read, or a direct answer.",
                "details": {
                    "query": query,
                    "selected_tool_id": tool_plan.get("selected_tool_id"),
                    "use_inventory": tool_plan.get("use_inventory"),
                    "use_knowledge": tool_plan.get("use_knowledge"),
                    "use_project_file": tool_plan.get("use_project_file"),
                    "planner_decision": tool_plan.get("planner_decision", {}),
                },
            }
        ]
        if tool_plan.get("use_inventory"):
            steps.extend(
                [
                    {
                        "phase": "action",
                        "tool_id": "query_project_inventory",
                        "input": {"query": query, "limit": 8},
                    },
                    {
                        "phase": "observation",
                        "tool_id": "query_project_inventory",
                        "summary": f"Matched {len(inventory_result.get('items') or [])} project inventory item(s).",
                        "details": inventory_result.get("summary", {}),
                    },
                ]
            )
        if tool_plan.get("use_knowledge"):
            steps.extend(
                [
                    {
                        "phase": "action",
                        "tool_id": "retrieve_project_knowledge",
                        "input": {"query": query, "top_k": self.settings.rag_top_k},
                    },
                    {
                        "phase": "observation",
                        "tool_id": "retrieve_project_knowledge",
                        "summary": f"Retrieved {len(qa_result.get('retrieved_docs') or [])} knowledge chunk(s).",
                        "details": {
                            "confidence": qa_result.get("confidence"),
                            "sources": qa_result.get("sources", []),
                        },
                    },
                ]
            )
        if tool_plan.get("use_project_file"):
            steps.extend(
                [
                    {
                        "phase": "action",
                        "tool_id": "read_project_file",
                        "input": self._project_file_candidate_from_result(project_file_result),
                    },
                    {
                        "phase": "observation",
                        "tool_id": "read_project_file",
                        "summary": f"Read project file status: {project_file_result.get('status')}.",
                        "details": {
                            "status": project_file_result.get("status"),
                            "reason": project_file_result.get("reason"),
                            "file_path": project_file_result.get("file_path"),
                            "resolved_path": project_file_result.get("resolved_path"),
                            "bytes_read": project_file_result.get("bytes_read"),
                            "truncated": project_file_result.get("truncated"),
                        },
                    },
                ]
            )
        steps.append(
            {
                "phase": "final",
                "text": "Compose the final answer from the collected observations.",
                "details": {"answer_generation_mode": answer_generation_mode},
            }
        )
        return {
            "mode": "react_lite",
            "max_iterations": 3,
            "iterations_used": sum(1 for item in steps if item.get("phase") == "action"),
            "stop_reason": "agent_decided_done",
            "planner_status": tool_plan.get("planner_decision", {}).get("status", "skipped"),
            "tool_call_sequence": tool_call_sequence(list(tool_plan.get("tool_calls") or [])),
            "steps": steps,
        }

    @staticmethod
    def _project_file_candidate_from_result(project_file_result: dict[str, Any]) -> dict[str, Any]:
        return {
            "file_path": project_file_result.get("file_path"),
            "max_bytes": project_file_result.get("max_bytes"),
        }

    def _project_qa_result_contracts(
        self,
        *,
        tool_plan: dict[str, Any],
        qa_result: dict[str, Any],
        inventory_result: dict[str, Any],
        project_file_result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        contracts: list[dict[str, Any]] = []
        if tool_plan.get("use_knowledge"):
            contracts.append(validate_tool_result("retrieve_project_knowledge", qa_result))
        if qa_result.get("web_search"):
            contracts.append(validate_tool_result("web_search_knowledge", qa_result["web_search"]))
        if tool_plan.get("use_inventory"):
            contracts.append(validate_tool_result("query_project_inventory", inventory_result))
        if tool_plan.get("use_project_file"):
            contracts.append(validate_tool_result("read_project_file", project_file_result))
        return contracts

    @staticmethod
    def _tool_call_input(tool_plan: dict[str, Any], tool_id: str) -> dict[str, Any]:
        for call in list(tool_plan.get("tool_calls") or []):
            if call.get("tool_id") == tool_id and isinstance(call.get("input"), dict):
                return dict(call["input"])
        return {}

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
    ) -> dict[str, Any]:
        bundle = build_context_bundle(
            db=self.db,
            request=request,
            routing=routing,
            actual_task_type=actual_task_type,
        )
        active_context = dict(bundle.get("active_context") or {})
        active_context["mcp"] = build_mcp_adapter_status(self.settings)
        inventory_context = self.inventory_service.context_snapshot(
            project_id=self._inventory_project_id(request),
            selected_assets=list(request.context.selected_assets or []),
            current_file=request.context.current_file,
        )
        active_context["inventory"] = {
            "status": inventory_context.get("status"),
            "has_snapshot": inventory_context.get("has_snapshot"),
            "snapshot_id": inventory_context.get("snapshot_id"),
            "project_id": inventory_context.get("project_id"),
            "asset_count": (inventory_context.get("summary") or {}).get("asset_count", 0),
            "code_file_count": (inventory_context.get("summary") or {}).get("code_file_count", 0),
            "selected_asset_count": len(inventory_context.get("selected_assets") or []),
        }
        asset_context = dict(active_context.get("asset") or {})
        asset_context["selected_asset_details"] = inventory_context.get("selected_assets", [])
        active_context["asset"] = asset_context
        code_context = dict(active_context.get("code") or {})
        code_context["current_file_inventory"] = inventory_context.get("current_file")
        active_context["code"] = code_context
        bundle["active_context"] = active_context
        bundle["project_inventory_context"] = inventory_context
        return bundle

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
        routing = classify_request(request, session_preference=session_model.preferred_output_language)
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
                    "context_budget": context_bundle.get("budget", {}),
                },
                "output_complete": output_complete,
                "finish_reason": finish_reason,
            }
        )
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
        event_payloads = self._build_event_payloads(task_id, run_id, response)
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

        event_payload = {
            "event": "run_cancelled",
            "run_id": run_id,
            "task_id": task.task_id,
            "seq": len(list_task_events(self.db, task.task_id)) + 1,
            "timestamp": now_utc().isoformat(),
            "payload": {"status": "cancelled", "finish_reason": task.finish_reason},
        }
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
            "active_context": resolved_context_bundle.get("active_context", {}),
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
                "context_budget": resolved_context_bundle.get("budget", {}),
            },
            "output_complete": True,
            "finish_reason": "completed",
            "warnings": [],
        }

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

    @staticmethod
    def _extract_asset_name_from_text(text: str, default_name: str) -> str:
        for pattern in (
            r"\b(BP_[A-Za-z][A-Za-z0-9_]{1,63})\b",
            r"\b(SM_[A-Za-z][A-Za-z0-9_]{1,63})\b",
            r"\b(L_[A-Za-z][A-Za-z0-9_]{1,63})\b",
            r"(?:命名为|改成|改为|叫做|叫|named|name it|rename to|to)\s*([A-Za-z][A-Za-z0-9_]{1,63})",
        ):
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return default_name

    @staticmethod
    def _selected_asset_path(request: UnifiedTaskRequest) -> str | None:
        selected_assets = list(request.context.selected_assets or [])
        if selected_assets:
            return str(selected_assets[0])
        asset_items = request.payload.get("asset_items") or request.payload.get("assets") or []
        if isinstance(asset_items, list) and asset_items:
            first = asset_items[0]
            if isinstance(first, dict):
                return str(first.get("asset_path") or first.get("package_path") or "")
            return str(first)
        return None

    def _detect_editor_operation_request(
        self,
        request: UnifiedTaskRequest,
    ) -> EditorOperationProposalRequest | None:
        explicit_operation = request.payload.get("operation_type")
        if explicit_operation in OPERATION_SPECS:
            payload = request.payload.get("operation_payload")
            if not isinstance(payload, dict):
                payload = request.payload.get("payload") if isinstance(request.payload.get("payload"), dict) else request.payload
            return EditorOperationProposalRequest(
                operation_type=explicit_operation,
                payload=dict(payload or {}),
                reason=str(request.payload.get("reason") or request.payload.get("user_query") or ""),
                source_task_id=request.payload.get("source_task_id"),
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        query_text = self._query_text(request)
        if not query_text:
            return None
        query_lower = query_text.lower()

        wants_blueprint = (
            ("蓝图" in query_text or "blueprint" in query_lower or "bp_" in query_lower)
            and any(token in query_lower or token in query_text for token in ("创建", "新建", "生成", "create", "make"))
        )
        if wants_blueprint:
            parent_class = "/Script/Engine.Actor"
            if "character" in query_lower or "角色" in query_text:
                parent_class = "/Script/Engine.Character"
            elif "pawn" in query_lower:
                parent_class = "/Script/Engine.Pawn"
            asset_name = self._extract_asset_name_from_text(query_text, "BP_AgentCreatedActor")
            if not asset_name.startswith("BP_"):
                asset_name = f"BP_{asset_name}"
            return EditorOperationProposalRequest(
                operation_type="create_blueprint_asset",
                payload={
                    "parent_class": request.payload.get("parent_class") or parent_class,
                    "target_folder": request.payload.get("target_folder") or "/Game/Blueprints",
                    "asset_name": request.payload.get("asset_name") or asset_name,
                },
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        selected_asset = self._selected_asset_path(request)
        wants_rename = selected_asset and any(
            token in query_lower or token in query_text
            for token in ("rename", "重命名", "改名", "改成", "改为")
        )
        if wants_rename:
            default_name = str(selected_asset).rstrip("/").rsplit("/", 1)[-1].split(".")[-1]
            new_name = request.payload.get("new_name") or self._extract_asset_name_from_text(query_text, default_name)
            return EditorOperationProposalRequest(
                operation_type="rename_selected_asset",
                payload={"asset_path": selected_asset, "new_name": new_name},
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )

        wants_static_mesh_settings = selected_asset and (
            "nanite" in query_lower
            or "碰撞" in query_text
            or "collision" in query_lower
            or "lightmap" in query_lower
            or "lod" in query_lower
        )
        if wants_static_mesh_settings:
            settings: dict[str, Any] = {}
            if "nanite" in query_lower:
                settings["nanite_enabled"] = not any(
                    token in query_lower or token in query_text for token in ("disable", "off", "关闭", "禁用")
                )
            if "use_complex_as_simple" in query_lower or "复杂碰撞作为简单" in query_text:
                settings["collision_complexity"] = "use_complex_as_simple"
            elif "use_simple_as_complex" in query_lower or "简单碰撞作为复杂" in query_text:
                settings["collision_complexity"] = "use_simple_as_complex"
            elif "simple_and_complex" in query_lower or "简单和复杂" in query_text:
                settings["collision_complexity"] = "simple_and_complex"
            lightmap_match = re.search(r"lightmap(?:\s+resolution)?\s*(\d{1,4})|光照贴图(?:分辨率)?\s*(\d{1,4})", query_text, flags=re.IGNORECASE)
            if lightmap_match:
                settings["lightmap_resolution"] = int(lightmap_match.group(1) or lightmap_match.group(2))
            if not settings:
                return None
            return EditorOperationProposalRequest(
                operation_type="apply_static_mesh_basic_settings",
                payload={"asset_path": selected_asset, "settings": settings},
                reason=query_text,
                requested_by="agent_chat",
                context=request.context.model_dump(mode="json"),
            )
        return None

    def _build_editor_operation_action_proposal(
        self,
        *,
        request: EditorOperationProposalRequest,
        output_language: str,
    ) -> dict[str, Any] | None:
        proposal_id = f"proposal_{uuid.uuid4().hex}"
        service = EditorOperationService(self.db)
        try:
            normalized_payload = service._normalize_payload(request.operation_type, dict(request.payload or {}))
            before_summary, after_summary = service._build_summaries(request.operation_type, normalized_payload)
        except EditorOperationValidationError:
            return None
        spec = OPERATION_SPECS[request.operation_type]
        dry_run_preview = {
            "protocol_version": EDITOR_OPERATION_PROTOCOL_VERSION,
            "proposal_kind": "editor_operation",
            "operation_type": request.operation_type,
            "tool_id": spec["tool_id"],
            "transport": "http",
            "mcp_like": True,
            "side_effect_level": "confirmed_write",
            "approval_state": "pending",
            "operation_payload": normalized_payload,
            "source_task_id": request.source_task_id,
            "context": dict(request.context or {}),
            "execution_contract": {
                "executor": "ue_plugin",
                "execute_after_confirmation": True,
                "result_endpoint": "POST /api/v1/editor-operations/results",
                "llm_direct_execution": False,
            },
        }
        return ActionProposal(
            proposal_id=proposal_id,
            title=_localized(output_language, f"编辑器操作：{spec['title']}", spec["title"]),
            proposal_type="editor_operation",
            before_summary=before_summary,
            after_summary=after_summary,
            rationale=request.reason or spec["summary"],
            risk_flags=spec["risk_flags"],
            dry_run_preview=dry_run_preview,
            display_hints={
                "ui": "editor_operation_confirmation",
                "operation_type": request.operation_type,
                "tool_id": spec["tool_id"],
                "requires_ue_plugin_execution": True,
                "confirm_endpoint": f"/api/v1/editor-operations/proposals/{proposal_id}/confirm",
                "reject_endpoint": f"/api/v1/editor-operations/proposals/{proposal_id}/reject",
                "generic_decision_endpoint": f"/api/v1/proposals/{proposal_id}/decision",
                "result_endpoint": "/api/v1/editor-operations/results",
                "confirmation_labels": {
                    "confirm": "Confirm & Execute in UE",
                    "reject": "Cancel",
                },
            },
            requires_confirmation=True,
            confirmation={
                "state": "pending",
                "decision_endpoint": f"/api/v1/proposals/{proposal_id}/decision",
            },
        ).model_dump(mode="json")

    def _execute_editor_operation_proposal(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        trace_id: str,
        output_language: str,
        editor_operation_request: EditorOperationProposalRequest,
        context_bundle: dict[str, Any],
    ) -> dict[str, Any]:
        base_debug = self._base_debug(
            request=request,
            routing=routing,
            trace_id=trace_id,
            context_bundle=context_bundle,
        )
        proposal = self._build_editor_operation_action_proposal(
            request=editor_operation_request,
            output_language=output_language,
        )
        if not proposal:
            text = _localized(
                output_language,
                "已识别到编辑器操作意图，但参数未通过安全校验，因此没有生成执行提案。",
                "An editor operation intent was detected, but the parameters failed safety validation, so no proposal was created.",
            )
            status = "blocked"
            proposals: list[dict[str, Any]] = []
        else:
            text = _localized(
                output_language,
                "已生成编辑器操作 Proposal。后端不会直接操作 UE 编辑器，请在 UE 插件中确认后执行。",
                "Created an editor operation proposal. The backend will not operate Unreal Editor directly; confirm it in the UE plugin before execution.",
            )
            status = "waiting_confirmation"
            proposals = [proposal]
        step_results = [
            {
                "step_id": "plan_editor_operation",
                "title": "Plan Editor Operation",
                "status": "completed" if proposals else "blocked",
                "summary": text,
                "details": {
                    "operation_type": editor_operation_request.operation_type,
                    "proposal_count": len(proposals),
                },
            }
        ]
        user_view = {
            "title": _localized(output_language, "编辑器操作提案", "Editor Operation Proposal"),
            "text": text,
            "blocks": [
                UserViewBlock(
                    block_type="summary",
                    title=_localized(output_language, "安全确认", "Safety Confirmation"),
                    text=text,
                    data={
                        "operation_type": editor_operation_request.operation_type,
                        "proposal": proposal or {},
                    },
                ).model_dump(mode="json")
            ],
            "citations_preview": [],
            "quick_actions": [
                QuickAction(
                    action_id="open_proposal",
                    label=_localized(output_language, "查看确认提案", "Open proposal"),
                    payload={"proposal_id": proposal.get("proposal_id") if proposal else None},
                ).model_dump(mode="json")
            ]
            if proposal
            else [],
            "status_hint": status,
        }
        data = {
            "answer": text,
            "editor_operation": {
                "operation_type": editor_operation_request.operation_type,
                "proposal": proposal or {},
                "proposal_created": bool(proposal),
                "safety_policy": {
                    "llm_direct_execution": False,
                    "requires_frontend_confirmation": True,
                    "ue_plugin_executes_editor_api": True,
                },
            },
            "context_summary": build_context_summary(request),
            "context_bundle": context_bundle,
            "warnings": [],
        }
        retrieval_trace = {
            "mode": "not_used",
            "degraded_mode": False,
            "reason": "editor_operation_proposal",
            "filters_applied": {},
            "retrieved_docs": [],
        }
        base_debug["tools"] = [
            {
                "tool_id": proposal["dry_run_preview"]["tool_id"] if proposal else "editor_operation_proposal",
                "status": "waiting_confirmation" if proposal else "blocked",
                "summary": text,
                "approval_state": "required" if proposal else "blocked",
            }
        ]
        base_debug["side_effects"] = [
            {
                "proposal_id": proposal.get("proposal_id") if proposal else None,
                "proposal_type": "editor_operation",
                "operation_type": editor_operation_request.operation_type,
                "side_effect_level": "confirmed_write",
                "execution_state": "not_executed_without_confirmation",
                "written_by_backend": False,
            }
        ]
        base_debug["step_results"] = step_results
        base_debug["raw_result"] = data
        return {
            "user_view": user_view,
            "debug_view": base_debug,
            "data": data,
            "retrieval_trace": retrieval_trace,
            "planner_diagnostics": routing["route"],
            "step_results": step_results,
            "action_proposals": proposals,
            "errors": [],
            "assistant_message": text,
            "artifacts": [],
            "usage": {},
        }

    def _execute_project_qa_live(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        trace_id: str,
        output_language: str,
        chat_config: ChatRuntimeConfig,
        context_bundle: dict[str, Any],
        stream_sink: StreamEventSink | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        query = request.payload.get("user_query") or (
            request.session.messages[-1].content if request.session.messages else ""
        )
        query_text = str(query)
        deterministic_tool_plan = self._project_qa_tool_plan(query=query_text, routing=routing)
        tool_plan = self._react_lite_tool_plan(
            request=request,
            query=query_text,
            deterministic_plan=deterministic_tool_plan,
            chat_config=chat_config,
            output_language=output_language,
        )
        if tool_plan["use_knowledge"]:
            self._emit_stream_event(
                stream_sink,
                "tool_call",
                {"tool_id": "retrieve_project_knowledge", "query": query_text},
                run_id=run_id,
                task_id=task_id,
            )
        qa_result = (
            self.kb_service.project_qa(
                query=query_text,
                context=request.context,
                payload=request.payload,
                output_language=output_language,
                source_task_id=task_id,
            )
            if tool_plan["use_knowledge"]
            else self._empty_project_qa_result(query=query_text)
        )
        if tool_plan["use_knowledge"]:
            self._emit_stream_event(
                stream_sink,
                "tool_result",
                {
                    "tool_id": "retrieve_project_knowledge",
                    "status": "completed",
                    "matched_count": len(qa_result.get("retrieved_docs", [])),
                },
                run_id=run_id,
                task_id=task_id,
            )
        if tool_plan["use_inventory"]:
            self._emit_stream_event(
                stream_sink,
                "tool_call",
                {"tool_id": "query_project_inventory", "query": query_text},
                run_id=run_id,
                task_id=task_id,
            )
        inventory_tool_input = self._tool_call_input(tool_plan, "query_project_inventory")
        inventory_fields = inventory_tool_input.get("fields")
        if not isinstance(inventory_fields, list):
            inventory_fields = []
        inventory_result = (
            self.inventory_service.query(
                query=str(inventory_tool_input.get("query") or query_text),
                project_id=str(inventory_tool_input.get("project_id") or self._inventory_project_id(request) or ""),
                asset_path=str(inventory_tool_input.get("asset_path") or ""),
                asset_type=str(inventory_tool_input.get("asset_type") or "") or None,
                fields=[str(item) for item in inventory_fields],
                selected_assets=list(request.context.selected_assets or []),
                limit=int(inventory_tool_input.get("limit") or 8),
            )
            if tool_plan["use_inventory"]
            else self._empty_inventory_result(query=query_text)
        )
        if tool_plan["use_inventory"]:
            self._emit_stream_event(
                stream_sink,
                "tool_result",
                {
                    "tool_id": "query_project_inventory",
                    "status": "completed",
                    "matched_count": len(inventory_result.get("items", [])),
                },
                run_id=run_id,
                task_id=task_id,
            )
        if tool_plan["use_project_file"]:
            self._emit_stream_event(
                stream_sink,
                "tool_call",
                {
                    "tool_id": "read_project_file",
                    "file_path": self._project_file_candidate(request)["file_path"],
                },
                run_id=run_id,
                task_id=task_id,
            )
        project_file_result = (
            self._read_project_file_tool(request)
            if tool_plan["use_project_file"]
            else {
                "status": "skipped",
                "reason": "tool_plan_skipped_project_file_read",
                "file_path": self._project_file_candidate(request)["file_path"],
            }
        )
        if tool_plan["use_project_file"]:
            self._emit_stream_event(
                stream_sink,
                "tool_result",
                {
                    "tool_id": "read_project_file",
                    "status": project_file_result.get("status", "skipped"),
                    "file_path": project_file_result.get("file_path"),
                    "bytes_read": project_file_result.get("bytes_read"),
                },
                run_id=run_id,
                task_id=task_id,
            )
        qa_result["inventory_items"] = inventory_result["items"]
        qa_result["inventory_summary"] = inventory_result["summary"]
        qa_result["project_file"] = project_file_result
        base_debug = self._base_debug(
            request=request,
            routing=routing,
            trace_id=trace_id,
            context_bundle=context_bundle,
        )
        llm_result = {
            "ok": False,
            "reason": "not_attempted",
            "error": "",
            "provider": "openai_compatible",
            "model": chat_config.model,
            "profile_id": chat_config.profile_id,
            "usage": {},
        }
        answer_generation_mode = qa_result.get("answer_mode") or "retrieval_summary_fallback"
        if tool_plan["use_inventory"]:
            inventory_requires_snapshot = self._inventory_fact_query_requires_snapshot(query_text)
            if inventory_result["items"]:
                qa_result["answer"] = self._inventory_fallback_answer(
                    inventory_result=inventory_result,
                    output_language=output_language,
                )
                qa_result["confidence"] = max(float(qa_result["confidence"]), 0.72)
                answer_generation_mode = "inventory_summary_fallback"
            elif inventory_requires_snapshot:
                qa_result["answer"] = self._inventory_fallback_answer(
                    inventory_result=inventory_result,
                    output_language=output_language,
                )
                fallback_confidence = 0.25 if inventory_result["summary"].get("has_snapshot") else 0.12
                qa_result["confidence"] = fallback_confidence
                qa_result["sources"] = []
                qa_result["citations"] = []
                qa_result["retrieved_docs"] = []
                qa_result["warnings"] = list(qa_result.get("warnings") or [])
                qa_result["warnings"].append(
                    "inventory_no_matching_items"
                    if inventory_result["summary"].get("has_snapshot")
                    else "inventory_snapshot_required"
                )
                quality_gate = dict(qa_result.get("retrieval_quality_gate") or {})
                quality_gate.update(
                    {
                        "status": "warning",
                        "evidence_sufficient": False,
                        "evidence_insufficient": True,
                        "reason": "inventory_snapshot_required",
                        "retrieved_count": 0,
                        "rag_retrieved_count": 0,
                        "local_retrieved_count": 0,
                    }
                )
                qa_result["retrieval_quality_gate"] = quality_gate
                retrieval_trace = dict(qa_result.get("retrieval_trace") or {})
                retrieval_trace["retrieved_docs"] = []
                retrieval_trace["reason"] = "inventory_snapshot_required"
                retrieval_trace["retrieval_quality_gate"] = quality_gate
                qa_result["retrieval_trace"] = retrieval_trace
                answer_generation_mode = "inventory_summary_fallback"
        if (
            answer_generation_mode == "retrieval_summary_fallback"
            and not qa_result.get("answer")
            and project_file_result.get("status") != "skipped"
        ):
            qa_result["answer"] = self._project_file_fallback_answer(
                project_file_result=project_file_result,
                output_language=output_language,
            )
            answer_generation_mode = "project_file_fallback"
            qa_result["confidence"] = max(
                float(qa_result["confidence"]),
                0.55 if project_file_result.get("status") == "completed" else 0.25,
            )
        has_project_file_context = project_file_result.get("status") == "completed"
        if answer_generation_mode != "knowledge_catalog" and (
            qa_result["retrieved_docs"] or inventory_result["items"] or has_project_file_context
        ):
            complete_kwargs: dict[str, Any] = {
                "messages": self._project_qa_messages(
                    request=request,
                    query=query_text,
                    qa_result=qa_result,
                    project_file_result=project_file_result,
                    output_language=output_language,
                    context_bundle=context_bundle,
                ),
                "config": chat_config,
            }
            if stream_sink:
                complete_kwargs["stream_sink"] = (
                    lambda text_delta: self._emit_stream_event(
                        stream_sink,
                        "assistant_delta",
                        {"text": text_delta},
                        run_id=run_id,
                        task_id=task_id,
                    )
                )
            llm_result = self.llm_service.complete(**complete_kwargs)
            if llm_result["ok"]:
                qa_result["answer"] = llm_result["text"]
                answer_generation_mode = "llm_synthesized"

        react_loop = self._build_react_lite_trace(
            query=query_text,
            tool_plan=tool_plan,
            qa_result=qa_result,
            inventory_result=inventory_result,
            project_file_result=project_file_result,
            answer_generation_mode=answer_generation_mode,
        )
        result_contracts = self._project_qa_result_contracts(
            tool_plan=tool_plan,
            qa_result=qa_result,
            inventory_result=inventory_result,
            project_file_result=project_file_result,
        )
        self_reflection = build_self_reflection(
            route_type="project_qa",
            output_language=output_language,
            answer_text=str(qa_result.get("answer") or ""),
            confidence=float(qa_result.get("confidence") or 0.0),
            answer_generation_mode=answer_generation_mode,
            retrieved_docs=qa_result.get("retrieved_docs", []),
            inventory_items=inventory_result.get("items", []),
            project_file_result=project_file_result,
            live_llm_used=bool(llm_result.get("ok")),
            warnings=qa_result.get("warnings", []),
        )

        confidence = qa_result["confidence"]
        step_results = [
            {
                "step_id": "classify_intent",
                "title": "Intent Classification",
                "status": "completed",
                "summary": routing["intent"]["reason"],
                "details": routing["intent"],
            },
            {
                "step_id": "retrieve_knowledge",
                "title": "Knowledge Retrieval",
                "status": "completed" if tool_plan["use_knowledge"] else "skipped",
                "summary": _localized(
                    output_language,
                    (
                        f"检索到 {len(qa_result['retrieved_docs'])} 个相关片段。"
                        if tool_plan["use_knowledge"]
                        else "本次问题优先查询项目快照，未触发知识库检索。"
                    ),
                    (
                        f"Retrieved {len(qa_result['retrieved_docs'])} relevant chunks."
                        if tool_plan["use_knowledge"]
                        else "This question used project inventory first, so knowledge retrieval was not triggered."
                    ),
                ),
                "details": qa_result["retrieval_trace"],
            },
            {
                "step_id": "query_project_inventory",
                "title": "Project Inventory Query",
                "status": "completed" if tool_plan["use_inventory"] else "skipped",
                "summary": _localized(
                    output_language,
                    (
                        f"命中 {len(inventory_result['items'])} 条项目快照记录。"
                        if tool_plan["use_inventory"]
                        else "本次问题未选择 Project Inventory 工具。"
                    ),
                    (
                        f"Matched {len(inventory_result['items'])} project inventory item(s)."
                        if tool_plan["use_inventory"]
                        else "Project Inventory was not selected for this question."
                    ),
                ),
                "details": inventory_result["summary"],
            },
            {
                "step_id": "read_project_file",
                "title": "Read Project File",
                "status": project_file_result.get("status", "skipped")
                if tool_plan["use_project_file"]
                else "skipped",
                "summary": _localized(
                    output_language,
                    (
                        f"读取项目文件：{project_file_result.get('file_path')}。"
                        if project_file_result.get("status") == "completed"
                        else f"未读取项目文件：{project_file_result.get('reason') or 'not_selected'}。"
                    ),
                    (
                        f"Read project file: {project_file_result.get('file_path')}."
                        if project_file_result.get("status") == "completed"
                        else f"Did not read a project file: {project_file_result.get('reason') or 'not_selected'}."
                    ),
                ),
                "details": {
                    key: value
                    for key, value in project_file_result.items()
                    if key != "text_excerpt"
                },
            },
            {
                "step_id": "compose_answer",
                "title": "Answer Composition",
                "status": "completed",
                "summary": (
                    _localized(
                        output_language,
                        "已使用配置好的聊天模型整合检索证据并生成回答。",
                        "Synthesized the answer from retrieved evidence with the configured chat model.",
                    )
                    if llm_result["ok"]
                    else _localized(
                        output_language,
                        "当前未使用在线聊天模型，直接返回检索摘要作为项目问答结果。",
                        "Returned the retrieval summary directly because no live chat model was used.",
                    )
                ),
                "details": {
                    "confidence": qa_result["confidence"],
                    "sources": qa_result["sources"],
                    "answer_generation_mode": answer_generation_mode,
                    "llm_reason": llm_result["reason"],
                    "model": llm_result["model"],
                    "retrieval_quality_gate": qa_result.get("retrieval_quality_gate", {}),
                },
            },
        ]
        quick_actions = [
            QuickAction(
                action_id="refresh_kb" if confidence < 0.4 else "inspect_debug_view",
                label=_localized(
                    output_language,
                    "刷新知识库" if confidence < 0.4 else "查看调试信息",
                    "Refresh knowledge base" if confidence < 0.4 else "Open debug view",
                ),
            ).model_dump(mode="json")
        ]
        evidence_terms = self._project_qa_evidence_terms(qa_result.get("retrieved_docs", []))
        if evidence_terms and answer_generation_mode != "llm_synthesized":
            evidence_text = _localized(
                output_language,
                "证据关键词：" + ", ".join(evidence_terms),
                "Evidence highlights: " + ", ".join(evidence_terms),
            )
            if evidence_text not in str(qa_result.get("answer") or ""):
                qa_result["answer"] = f"{qa_result['answer']}\n\n{evidence_text}"
        user_view = {
            "title": _localized(output_language, "项目问答结果", "Project QA Result"),
            "text": qa_result["answer"],
            "blocks": [
                UserViewBlock(
                    block_type="summary",
                    title=_localized(output_language, "检索摘要", "Retrieval Summary"),
                    text=_localized(
                        output_language,
                        f"命中 {len(qa_result['retrieved_docs'])} 个知识库片段、{len(inventory_result['items'])} 条项目快照记录、项目文件读取状态 {project_file_result.get('status')}，当前置信度 {confidence:.2f}。",
                        f"Retrieved {len(qa_result['retrieved_docs'])} KB chunk(s), {len(inventory_result['items'])} inventory item(s), project file status {project_file_result.get('status')}, with confidence {confidence:.2f}.",
                    ),
                    data={
                        "confidence": confidence,
                        "kb_chunk_count": len(qa_result["retrieved_docs"]),
                        "inventory_item_count": len(inventory_result["items"]),
                        "project_file_status": project_file_result.get("status"),
                        "retrieval_quality_gate": qa_result.get("retrieval_quality_gate", {}),
                    },
                ).model_dump(mode="json")
            ],
            "citations_preview": _citation_previews(qa_result["citations"]),
            "quick_actions": quick_actions,
            "status_hint": "low_confidence" if confidence < 0.4 else "evidence_retrieved",
        }
        data = {
            "answer": qa_result["answer"],
            "sources": qa_result["sources"],
            "confidence": qa_result["confidence"],
            "retrieved_docs": qa_result["retrieved_docs"],
            "filters_applied": qa_result["filters_applied"],
            "citations": qa_result["citations"],
            "warnings": qa_result["warnings"],
            "answer_mode": qa_result.get("answer_mode", answer_generation_mode),
            "catalog": qa_result.get("catalog", {}),
            "local_search": qa_result.get("local_search", {}),
            "web_memory": qa_result.get("web_memory", {}),
            "web_memory_store": qa_result.get("web_memory_store", {}),
            "web_search": qa_result.get("web_search", {}),
            "source_arbitration": qa_result.get("source_arbitration", {}),
            "retrieval_quality_gate": qa_result.get("retrieval_quality_gate", {}),
            "inventory": inventory_result,
            "project_file": project_file_result,
            "answer_generation": {
                "mode": answer_generation_mode,
                "provider": llm_result["provider"],
                "model": llm_result["model"],
                "profile_id": chat_config.profile_id,
            },
            "react_loop": react_loop,
            "tool_plan": tool_plan,
            "tool_contracts": {
                "input_contracts": tool_plan.get("input_contracts", []),
                "result_contracts": result_contracts,
            },
            "self_reflection": self_reflection,
            "context_summary": build_context_summary(request),
            "context_bundle": context_bundle,
        }
        base_debug["retrieval"] = qa_result["retrieval_trace"]
        base_debug["local_search"] = qa_result.get("local_search", {})
        base_debug["web_memory"] = qa_result.get("web_memory", {})
        base_debug["web_memory_store"] = qa_result.get("web_memory_store", {})
        base_debug["web_search"] = qa_result.get("web_search", {})
        base_debug["source_arbitration"] = qa_result.get("source_arbitration", {})
        base_debug["retrieval_quality_gate"] = qa_result.get("retrieval_quality_gate", {})
        base_debug["inventory"] = inventory_result
        base_debug["project_file"] = {
            key: value for key, value in project_file_result.items() if key != "text_excerpt"
        }
        base_debug["tools"] = [
            {
                "tool_id": "retrieve_project_knowledge",
                "status": "completed" if tool_plan["use_knowledge"] else "skipped",
                "summary": (
                    f"Retrieved {len(qa_result['retrieved_docs'])} relevant chunk(s)."
                    if tool_plan["use_knowledge"]
                    else "Skipped by Project QA tool plan."
                ),
            },
            {
                "tool_id": "query_project_inventory",
                "status": "completed" if tool_plan["use_inventory"] else "skipped",
                "summary": (
                    f"Matched {len(inventory_result['items'])} project inventory item(s)."
                    if tool_plan["use_inventory"]
                    else "Skipped by Project QA tool plan."
                ),
            },
            {
                "tool_id": "read_project_file",
                "status": (
                    project_file_result.get("status", "skipped")
                    if tool_plan["use_project_file"]
                    else "skipped"
                ),
                "summary": (
                    f"Read project file {project_file_result.get('file_path')}."
                    if project_file_result.get("status") == "completed"
                    else f"Skipped or blocked project file read ({project_file_result.get('reason')})."
                ),
            },
            {
                "tool_id": "llm_answer_synthesis",
                "status": "completed" if llm_result["ok"] else "skipped",
                "summary": (
                    f"Used model {llm_result['model']} for final answer synthesis."
                    if llm_result["ok"]
                    else f"Skipped live answer synthesis ({llm_result['reason']})."
                ),
            },
        ]
        web_search_result = qa_result.get("web_search") or {}
        if web_search_result.get("status") != "skipped":
            base_debug["tools"].append(
                {
                    "tool_id": "web_search_knowledge",
                    "status": web_search_result.get("status", "skipped"),
                    "summary": (
                        f"Controlled Web Search returned {len(web_search_result.get('items', []))} result(s)."
                        if web_search_result.get("status") == "completed"
                        else f"Controlled Web Search failed or degraded ({web_search_result.get('reason', 'unknown')})."
                    ),
                }
            )
        base_debug["step_results"] = step_results
        base_debug["raw_result"] = data
        base_debug["tool_plan"] = tool_plan
        base_debug["tool_contracts"] = {
            "input_contracts": tool_plan.get("input_contracts", []),
            "result_contracts": result_contracts,
        }
        base_debug["react_loop"] = react_loop
        base_debug["self_reflection"] = self_reflection
        base_debug["warnings"] = qa_result["warnings"] + (
            [] if llm_result["ok"] or llm_result["reason"] == "not_attempted" else [llm_result["reason"]]
        )
        return {
            "user_view": user_view,
            "debug_view": base_debug,
            "data": data,
            "retrieval_trace": qa_result["retrieval_trace"],
            "planner_diagnostics": routing["route"],
            "step_results": step_results,
            "action_proposals": [],
            "errors": [],
            "assistant_message": qa_result["answer"],
            "artifacts": [],
            "usage": llm_result["usage"],
        }

    def _execute_project_qa(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        trace_id: str,
        output_language: str,
    ) -> dict[str, Any]:
        query = request.payload.get("user_query") or (
            request.session.messages[-1].content if request.session.messages else ""
        )
        qa_result = self.kb_service.project_qa(
            query=query,
            context=request.context,
            payload=request.payload,
            output_language=output_language,
        )
        base_debug = self._base_debug(request=request, routing=routing, trace_id=trace_id)
        confidence = qa_result["confidence"]
        step_results = [
            {
                "step_id": "classify_intent",
                "title": "Intent Classification",
                "status": "completed",
                "summary": routing["intent"]["reason"],
                "details": routing["intent"],
            },
            {
                "step_id": "retrieve_knowledge",
                "title": "Knowledge Retrieval",
                "status": "completed",
                "summary": _localized(
                    output_language,
                    f"检索到 {len(qa_result['retrieved_docs'])} 个相关片段。",
                    f"Retrieved {len(qa_result['retrieved_docs'])} relevant chunks.",
                ),
                "details": qa_result["retrieval_trace"],
            },
            {
                "step_id": "compose_answer",
                "title": "Answer Composition",
                "status": "completed",
                "summary": _localized(
                    output_language,
                    "已生成带引用预览和置信度的项目问答结果。",
                    "Built a project QA answer with citation preview and confidence.",
                ),
                "details": {"confidence": qa_result["confidence"], "sources": qa_result["sources"]},
            },
        ]
        quick_actions = [
            QuickAction(
                action_id="refresh_kb" if confidence < 0.4 else "inspect_debug_view",
                label=_localized(
                    output_language,
                    "刷新知识库" if confidence < 0.4 else "查看调试信息",
                    "Refresh knowledge base" if confidence < 0.4 else "Open debug view",
                ),
            ).model_dump(mode="json")
        ]
        user_view = {
            "title": _localized(output_language, "项目问答结果", "Project QA Result"),
            "text": qa_result["answer"],
            "blocks": [
                UserViewBlock(
                    block_type="summary",
                    title=_localized(output_language, "检索摘要", "Retrieval Summary"),
                    text=_localized(
                        output_language,
                        f"命中 {len(qa_result['retrieved_docs'])} 个片段，当前置信度 {confidence:.2f}。",
                        f"Retrieved {len(qa_result['retrieved_docs'])} chunks with confidence {confidence:.2f}.",
                    ),
                    data={"confidence": confidence},
                ).model_dump(mode="json")
            ],
            "citations_preview": _citation_previews(qa_result["citations"]),
            "quick_actions": quick_actions,
            "status_hint": "low_confidence" if confidence < 0.4 else "evidence_retrieved",
        }
        data = {
            "answer": qa_result["answer"],
            "sources": qa_result["sources"],
            "confidence": qa_result["confidence"],
            "retrieved_docs": qa_result["retrieved_docs"],
            "filters_applied": qa_result["filters_applied"],
            "citations": qa_result["citations"],
            "warnings": qa_result["warnings"],
            "local_search": qa_result.get("local_search", {}),
            "web_memory": qa_result.get("web_memory", {}),
            "web_memory_store": qa_result.get("web_memory_store", {}),
            "web_search": qa_result.get("web_search", {}),
            "source_arbitration": qa_result.get("source_arbitration", {}),
            "retrieval_quality_gate": qa_result.get("retrieval_quality_gate", {}),
            "context_summary": build_context_summary(request),
        }
        base_debug["retrieval"] = qa_result["retrieval_trace"]
        base_debug["local_search"] = qa_result.get("local_search", {})
        base_debug["web_memory"] = qa_result.get("web_memory", {})
        base_debug["web_memory_store"] = qa_result.get("web_memory_store", {})
        base_debug["web_search"] = qa_result.get("web_search", {})
        base_debug["source_arbitration"] = qa_result.get("source_arbitration", {})
        base_debug["retrieval_quality_gate"] = qa_result.get("retrieval_quality_gate", {})
        base_debug["step_results"] = step_results
        base_debug["raw_result"] = data
        base_debug["warnings"] = qa_result["warnings"]
        return {
            "user_view": user_view,
            "debug_view": base_debug,
            "data": data,
            "retrieval_trace": qa_result["retrieval_trace"],
            "planner_diagnostics": routing["route"],
            "step_results": step_results,
            "action_proposals": [],
            "errors": [],
            "assistant_message": qa_result["answer"],
            "artifacts": [],
        }

    def _execute_direct_answer(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        trace_id: str,
        output_language: str,
    ) -> dict[str, Any]:
        base_debug = self._base_debug(request=request, routing=routing, trace_id=trace_id)
        answer_text = _localized(
            output_language,
            "当前请求没有进入项目知识检索路径，系统按普通对话处理。当前阶段仍使用安全占位回答，而不是实时大模型直答。",
            "This request was not routed into project knowledge retrieval, so the system handled it as direct chat. The current phase still uses a safe placeholder instead of a live LLM answer.",
        )
        step_results = [
            {
                "step_id": "classify_intent",
                "title": "Intent Classification",
                "status": "completed",
                "summary": routing["intent"]["reason"],
                "details": routing["intent"],
            },
            {
                "step_id": "direct_answer",
                "title": "Direct Answer",
                "status": "completed",
                "summary": _localized(
                    output_language,
                    "未调用知识库，返回普通对话占位结果。",
                    "Skipped the knowledge base and returned a direct-chat placeholder.",
                ),
                "details": {"route_type": "direct_answer"},
            },
        ]
        user_view = {
            "title": _localized(output_language, "对话结果", "Chat Result"),
            "text": answer_text,
            "blocks": [
                UserViewBlock(
                    block_type="summary",
                    title=_localized(output_language, "路由结果", "Route Result"),
                    text=routing["intent"]["reason"],
                    data={"route_type": "direct_answer"},
                ).model_dump(mode="json")
            ],
            "citations_preview": [],
            "quick_actions": [
                QuickAction(
                    action_id="ask_project_question",
                    label=_localized(output_language, "改为项目问答", "Ask as project QA"),
                ).model_dump(mode="json")
            ],
            "status_hint": "direct_answer",
        }
        retrieval_trace = {
            "mode": "not_used",
            "degraded_mode": False,
            "reason": "route_direct_answer",
            "filters_applied": {},
            "retrieved_docs": [],
        }
        data = {
            "answer": answer_text,
            "sources": [],
            "confidence": 0.0,
            "warnings": [],
            "context_summary": build_context_summary(request),
        }
        base_debug["retrieval"] = retrieval_trace
        base_debug["step_results"] = step_results
        base_debug["raw_result"] = data
        return {
            "user_view": user_view,
            "debug_view": base_debug,
            "data": data,
            "retrieval_trace": retrieval_trace,
            "planner_diagnostics": routing["route"],
            "step_results": step_results,
            "action_proposals": [],
            "errors": [],
            "assistant_message": answer_text,
            "artifacts": [],
        }

    def _execute_code_review(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        task_id: str,
        run_id: str,
        trace_id: str,
        output_language: str,
        chat_config: ChatRuntimeConfig,
        context_bundle: dict[str, Any],
    ) -> dict[str, Any]:
        executor = CodeReviewSkillExecutor(
            kb_service=self.kb_service,
            llm_service=self.llm_service,
            base_debug_builder=self._base_debug,
        )
        return executor.execute(
            request=request,
            routing=routing,
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            output_language=output_language,
            chat_config=chat_config,
            context_bundle=context_bundle,
        )

    def _execute_code_review_multi_agent(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        task_id: str,
        run_id: str,
        trace_id: str,
        output_language: str,
        chat_config: ChatRuntimeConfig,
        context_bundle: dict[str, Any],
    ) -> dict[str, Any]:
        chain = ReviewFixValidateChain(
            kb_service=self.kb_service,
            llm_service=self.llm_service,
            base_debug_builder=self._base_debug,
        )
        return chain.run(
            request=request,
            routing=routing,
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            output_language=output_language,
            chat_config=chat_config,
            context_bundle=context_bundle,
        )

    def _execute_logs_analyze(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        task_id: str,
        run_id: str,
        trace_id: str,
        output_language: str,
        chat_config: ChatRuntimeConfig,
    ) -> dict[str, Any]:
        executor = LogsAnalyzeSkillExecutor(
            kb_service=self.kb_service,
            llm_service=self.llm_service,
            base_debug_builder=self._base_debug,
        )
        return executor.execute(
            request=request,
            routing=routing,
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            output_language=output_language,
            chat_config=chat_config,
        )

    def _execute_config_generate(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        task_id: str,
        run_id: str,
        trace_id: str,
        output_language: str,
    ) -> dict[str, Any]:
        workflow = run_config_generate_workflow(
            request=request,
            kb_service=self.kb_service,
            task_id=task_id,
            run_id=run_id,
            output_language=output_language,
        )
        result = workflow["result"]
        base_debug = self._base_debug(request=request, routing=routing, trace_id=trace_id)
        validation = result["validation_results"]["validation_summary"]
        user_text = _localized(
            output_language,
            "已生成配置草稿并完成基础结构校验，当前等待人工确认后再进入后续采用流程。",
            "Generated a config draft and completed baseline structural validation. The run is now waiting for human confirmation before downstream adoption.",
        )
        user_view = {
            "title": _localized(output_language, "配置生成结果", "Config Generation Result"),
            "text": user_text,
            "blocks": [
                UserViewBlock(
                    block_type="summary",
                    title=_localized(output_language, "校验摘要", "Validation Summary"),
                    text=_localized(
                        output_language,
                        f"错误 {validation['error_count']} 条，告警 {validation['warning_count']} 条。",
                        f"Errors: {validation['error_count']}, warnings: {validation['warning_count']}.",
                    ),
                    data=validation,
                ).model_dump(mode="json"),
                UserViewBlock(
                    block_type="json_preview",
                    title=_localized(output_language, "草稿预览", "Draft Preview"),
                    text=str(result["draft_config"])[:400],
                    data={"draft_config": result["draft_config"]},
                ).model_dump(mode="json"),
            ],
            "citations_preview": _citation_previews(result["retrieved_references"]),
            "quick_actions": [
                QuickAction(
                    action_id="open_proposal_panel",
                    label=_localized(output_language, "查看待确认 Proposal", "Open pending proposal"),
                ).model_dump(mode="json")
            ],
            "status_hint": "waiting_confirmation",
        }
        data = {
            **result,
            "sources": [{"title": item["title"], "source": item["source"]} for item in result["retrieved_references"]],
            "citations": result["retrieved_references"],
            "context_summary": build_context_summary(request),
            "warnings": workflow["warnings"],
        }
        base_debug["retrieval"] = workflow["retrieval_trace"]
        base_debug["tools"] = workflow["tools"]
        base_debug["step_results"] = workflow["step_results"]
        base_debug["raw_result"] = data
        base_debug["warnings"] = workflow["warnings"]
        return {
            "user_view": user_view,
            "debug_view": base_debug,
            "data": data,
            "retrieval_trace": workflow["retrieval_trace"],
            "planner_diagnostics": routing["route"],
            "step_results": workflow["step_results"],
            "action_proposals": workflow["action_proposals"],
            "errors": [],
            "assistant_message": user_text,
            "artifacts": workflow["artifacts"],
        }

    def _execute_perf_analyze(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        task_id: str,
        run_id: str,
        trace_id: str,
        output_language: str,
    ) -> dict[str, Any]:
        workflow = run_perf_analyze_workflow(
            request=request,
            kb_service=self.kb_service,
            task_id=task_id,
            run_id=run_id,
            output_language=output_language,
        )
        result = workflow["result"]
        base_debug = self._base_debug(request=request, routing=routing, trace_id=trace_id)
        user_text = _localized(
            output_language,
            f"已完成性能分析，识别到 {len(result['suspicious_points'])} 个可疑瓶颈信号。",
            f"Performance analysis completed and identified {len(result['suspicious_points'])} suspicious bottleneck signal(s).",
        )
        user_view = {
            "title": _localized(output_language, "性能分析结果", "Performance Analysis Result"),
            "text": user_text,
            "blocks": [
                UserViewBlock(
                    block_type="summary",
                    title=_localized(output_language, "指标摘要", "Metric Summary"),
                    text=result["summary"],
                    data=result["metric_summary"],
                ).model_dump(mode="json"),
                UserViewBlock(
                    block_type="list",
                    title=_localized(output_language, "优化建议", "Optimization Suggestions"),
                    text="\n".join(result["optimization_suggestions"][:4]),
                    data={"suspicious_points": result["suspicious_points"][:6]},
                ).model_dump(mode="json"),
            ],
            "citations_preview": _citation_previews(result["retrieved_references"]),
            "quick_actions": [
                QuickAction(
                    action_id="open_debug_view",
                    label=_localized(output_language, "查看调试信息", "Open debug view"),
                ).model_dump(mode="json")
            ],
            "status_hint": "analysis_complete",
        }
        data = {
            **result,
            "sources": [{"title": item["title"], "source": item["source"]} for item in result["retrieved_references"]],
            "citations": result["retrieved_references"],
            "context_summary": build_context_summary(request),
            "warnings": workflow["warnings"],
        }
        base_debug["retrieval"] = workflow["retrieval_trace"]
        base_debug["tools"] = workflow["tools"]
        base_debug["step_results"] = workflow["step_results"]
        base_debug["raw_result"] = data
        base_debug["warnings"] = workflow["warnings"]
        return {
            "user_view": user_view,
            "debug_view": base_debug,
            "data": data,
            "retrieval_trace": workflow["retrieval_trace"],
            "planner_diagnostics": routing["route"],
            "step_results": workflow["step_results"],
            "action_proposals": workflow["action_proposals"],
            "errors": [],
            "assistant_message": user_text,
            "artifacts": workflow["artifacts"],
        }

    def _execute_code_generate_v2(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        trace_id: str,
        output_language: str,
        chat_config: ChatRuntimeConfig,
        context_bundle: dict[str, Any],
    ) -> dict[str, Any]:
        executor = CodeGenerateSkillExecutor(
            kb_service=self.kb_service,
            llm_service=self.llm_service,
            base_debug_builder=self._base_debug,
        )
        return executor.execute(
            request=request,
            routing=routing,
            trace_id=trace_id,
            output_language=output_language,
            chat_config=chat_config,
            context_bundle=context_bundle,
        )

    def _execute_assets_inspect(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        trace_id: str,
        output_language: str,
        chat_config: ChatRuntimeConfig,
    ) -> dict[str, Any]:
        executor = AssetsInspectSkillExecutor(
            kb_service=self.kb_service,
            llm_service=self.llm_service,
            base_debug_builder=self._base_debug,
        )
        execution = executor.execute(
            request=request,
            routing=routing,
            trace_id=trace_id,
            output_language=output_language,
            chat_config=chat_config,
        )
        proposal = self._asset_inspect_rename_operation_proposal(
            execution=execution,
            request=request,
            output_language=output_language,
        )
        if proposal:
            execution["action_proposals"] = list(execution.get("action_proposals") or []) + [proposal]
            execution["data"]["editor_operation_proposals"] = [proposal]
            execution["user_view"]["blocks"] = list(execution["user_view"].get("blocks") or []) + [
                UserViewBlock(
                    block_type="editor_operation_proposal",
                    title=_localized(output_language, "可确认的编辑器操作", "Confirmable Editor Operation"),
                    text=_localized(
                        output_language,
                        "已根据资产检查结果生成重命名提案。确认后由 UE 插件执行，后端不会直接修改编辑器资产。",
                        "A rename proposal was generated from the asset inspection result. The UE plugin executes it after confirmation; the backend does not directly modify editor assets.",
                    ),
                    data={"proposal": proposal},
                ).model_dump(mode="json")
            ]
            execution["debug_view"]["side_effects"] = list(execution["debug_view"].get("side_effects") or []) + [
                {
                    "proposal_id": proposal["proposal_id"],
                    "proposal_type": "editor_operation",
                    "operation_type": "rename_selected_asset",
                    "tool_id": "editor_rename_asset",
                    "side_effect_level": "confirmed_write",
                    "execution_state": "not_executed_without_confirmation",
                    "written_by_backend": False,
                }
            ]
        return execution

    def _asset_inspect_rename_operation_proposal(
        self,
        *,
        execution: dict[str, Any],
        request: UnifiedTaskRequest,
        output_language: str,
    ) -> dict[str, Any] | None:
        data = dict(execution.get("data") or {})
        summary = dict(data.get("summary") or {})
        if int(summary.get("asset_count") or 0) != 1:
            return None
        suggestions = list(data.get("rename_suggestions") or [])
        if not suggestions:
            suggestions = list(
                dict(data.get("localized_asset_view") or {}).get("rename_suggestions") or []
            )
        if not suggestions:
            return None
        for raw_suggestion in suggestions:
            suggestion = dict(raw_suggestion)
            asset_path = str(suggestion.get("asset_path") or "").strip()
            new_name = str(suggestion.get("suggested_name") or "").strip()
            if not asset_path or not new_name:
                continue
            proposal = self._build_editor_operation_action_proposal(
                request=EditorOperationProposalRequest(
                    operation_type="rename_selected_asset",
                    payload={"asset_path": asset_path, "new_name": new_name},
                    reason=str(suggestion.get("reason") or "Asset inspection generated a rename suggestion."),
                    requested_by="assets_inspect",
                    context=request.context.model_dump(mode="json"),
                ),
                output_language=output_language,
            )
            if proposal:
                return proposal
        return None

    def _execute_task_placeholder(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        trace_id: str,
        output_language: str,
    ) -> dict[str, Any]:
        base_debug = self._base_debug(request=request, routing=routing, trace_id=trace_id)
        placeholder_text = _localized(
            output_language,
            "系统已经识别到这是工程任务请求，但当前任务类型还未接入具体执行器，因此先返回任务路由和调试诊断。",
            "The system recognized this as an engineering task request, but this task type does not have a concrete executor yet, so it is returning routing diagnostics for now.",
        )
        step_results = [
            {
                "step_id": "classify_intent",
                "title": "Intent Classification",
                "status": "completed",
                "summary": routing["intent"]["reason"],
                "details": routing["intent"],
            }
        ]
        user_view = {
            "title": _localized(output_language, "任务路由结果", "Task Routing Result"),
            "text": placeholder_text,
            "blocks": [
                UserViewBlock(
                    block_type="summary",
                    title=_localized(output_language, "候选工具", "Candidate Tools"),
                    text=", ".join(routing["route"]["candidate_tool_ids"]) or "tool_registry_pending",
                ).model_dump(mode="json")
            ],
            "citations_preview": [],
            "quick_actions": [
                QuickAction(
                    action_id="open_debug_view",
                    label=_localized(output_language, "查看调试信息", "Open debug view"),
                ).model_dump(mode="json")
            ],
            "status_hint": "tool_placeholder",
        }
        retrieval_trace = {
            "mode": "not_used",
            "degraded_mode": False,
            "reason": "route_task_placeholder",
            "filters_applied": {},
            "retrieved_docs": [],
        }
        data = {
            "answer": placeholder_text,
            "sources": [],
            "citations": [],
            "confidence": 0.0,
            "context_summary": build_context_summary(request),
            "warnings": [],
        }
        base_debug["retrieval"] = retrieval_trace
        base_debug["step_results"] = step_results
        base_debug["raw_result"] = data
        return {
            "user_view": user_view,
            "debug_view": base_debug,
            "data": data,
            "retrieval_trace": retrieval_trace,
            "planner_diagnostics": routing["route"],
            "step_results": step_results,
            "action_proposals": [],
            "errors": [],
            "assistant_message": placeholder_text,
            "artifacts": [],
        }

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

    def _build_event_payloads(
        self,
        task_id: str,
        run_id: str,
        response: UnifiedTaskResponse,
    ) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []

        def append(event: str, payload: dict[str, Any]) -> None:
            payloads.append(
                {
                    "event": event,
                    "run_id": run_id,
                    "task_id": task_id,
                    "seq": len(payloads) + 1,
                    "timestamp": now_utc().isoformat(),
                    "payload": payload,
                }
            )

        append("run_started", {"task_type": response.task.task_type})
        append("route_selected", response.planner_diagnostics)

        if response.retrieval_trace.get("mode") not in {None, "", "not_used"}:
            append("retrieval_started", {"mode": response.retrieval_trace.get("mode")})
            append(
                "retrieval_completed",
                {
                    "mode": response.retrieval_trace.get("mode"),
                    "retrieved_docs": response.retrieval_trace.get("retrieved_docs", []),
                },
            )

        for step in response.step_results:
            step_payload = step.model_dump(mode="json")
            append("step_started", {"step_id": step.step_id, "title": step.title})
            append("step_completed", step_payload)

        if response.assistant_message:
            append("text_delta", {"text": response.assistant_message})

        for proposal in response.action_proposals:
            append("proposal_emitted", proposal.model_dump(mode="json"))

        append(
            "run_completed",
            {
                "status": response.task.status,
                "finish_reason": response.task.finish_reason,
            },
        )
        return payloads

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
