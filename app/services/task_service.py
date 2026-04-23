from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.agent.context_builder import build_context_summary
from app.agent.response_composer import compose_unified_response
from app.agent.router import classify_request
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
from app.schemas.requests import UnifiedTaskRequest
from app.schemas.responses import UnifiedTaskResponse
from app.services.kb_service import KnowledgeBaseService
from app.services.llm_service import ChatRuntimeConfig, LLMService, chat_runtime_config
from app.services.project_inventory_service import ProjectInventoryService
from app.skills.executors import (
    AssetsInspectSkillExecutor,
    CodeGenerateSkillExecutor,
    CodeReviewSkillExecutor,
    LogsAnalyzeSkillExecutor,
)
from app.skills.runtime import build_skill_runtime_descriptor
from app.tools.config_validate import validate_design_config
from app.tools.registry import TOOL_ID_TO_TASK_TYPE
from app.utils.json_tools import dumps_pretty
from app.utils.paths import task_artifact_dir
from app.utils.time import now_utc
from app.workflows.graphs import (
    run_config_generate_workflow,
    run_perf_analyze_workflow,
)


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
    ) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": system_prompt}]
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
    ) -> list[dict[str, str]]:
        context_summary = build_context_summary(request)
        system_prompt = (
            "You are UE Agent, a backend assistant for Unreal Engine development and general software questions. "
            f"Reply in {self._language_label(output_language)} unless the user explicitly requests another language. "
            "Be concise, accurate, and honest about uncertainty. "
            "Do not invent project-specific facts. "
            "If editor context is included, use it only when it is relevant to the user request."
        )
        if context_summary:
            system_prompt += f"\n\nEditor context summary:\n{context_summary}"
        fallback_user_text = str(request.payload.get("user_query") or "")
        return self._session_messages(
            request,
            system_prompt=system_prompt,
            fallback_user_text=fallback_user_text,
        )

    def _project_qa_messages(
        self,
        *,
        request: UnifiedTaskRequest,
        query: str,
        qa_result: dict[str, Any],
        output_language: str,
    ) -> list[dict[str, str]]:
        evidence_lines: list[str] = []
        for index, item in enumerate(qa_result["retrieved_docs"][:4], start=1):
            snippet = str(item.get("source_path") or item.get("title") or "").strip()
            evidence_lines.append(
                "\n".join(
                    [
                        f"[S{index}] {item['title']}",
                        f"Source: {snippet}",
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
        system_prompt = (
            "You are synthesizing an answer from project knowledge-base evidence. "
            f"Reply in {self._language_label(output_language)}. "
            "Use only the supplied knowledge-base evidence and project inventory facts. "
            "If the evidence is insufficient, say so clearly instead of guessing. "
            "Prefer a short answer followed by 2-4 concrete evidence-backed points."
        )
        user_prompt = "\n\n".join(
            [
                f"User question:\n{query.strip()}",
                f"Context summary:\n{build_context_summary(request)}",
                "Evidence:",
                "\n\n".join(evidence_lines) if evidence_lines else "No retrieved evidence.",
                "Project inventory facts:",
                "\n\n".join(inventory_lines) if inventory_lines else "No project inventory facts.",
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
        if not items:
            return _localized(
                output_language,
                "当前没有命中项目快照信息。请先让 UE 插件提交 Project Inventory 快照，或补充更具体的资产/代码名称。",
                "No project inventory facts matched. Submit a Project Inventory snapshot from the UE plugin or ask with a more specific asset/code name.",
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
            setting_bits = []
            for key in ("nanite_enabled", "lod_count", "parent_class", "tick_enabled", "blend_mode", "srgb"):
                if key in settings:
                    setting_bits.append(f"{key}={settings[key]}")
            lines.append(
                f"- {item.get('asset_name') or item.get('asset_path')} | "
                f"type={item.get('asset_type') or 'Unknown'} | path={item.get('asset_path')}"
                + (f" | {', '.join(setting_bits)}" if setting_bits else "")
            )
        return "\n".join(lines)

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

    def create_task(self, request: UnifiedTaskRequest) -> UnifiedTaskResponse:
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
        get_or_create_session(
            self.db,
            request.session.session_id,
            project_name=request.context.project_name,
            preferred_output_language=routing["locale"]["final_output_language"],
            profile_id=request.runtime_options.profile_id,
        )
        append_messages(
            self.db,
            request.session.session_id,
            [message.model_dump(mode="json") for message in request.session.messages],
        )

        task_id = f"task_{uuid.uuid4().hex}"
        run_id = f"run_{uuid.uuid4().hex}"
        trace_id = f"trace_{uuid.uuid4().hex}"
        actual_task_type = self._actual_task_type(request.task_type, routing)

        started = time.perf_counter()
        execution = self._execute_route(
            request=request,
            routing=routing,
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            actual_task_type=actual_task_type,
            chat_config=chat_config,
        )
        skill_runtime = build_skill_runtime_descriptor(
            requested_task_type=request.task_type,
            actual_task_type=actual_task_type,
            routing=routing,
            retrieval_trace=execution["retrieval_trace"],
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
                },
                "output_complete": output_complete,
                "finish_reason": finish_reason,
            }
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
    ) -> dict[str, Any]:
        return {
            "raw_request": redact_payload(request.model_dump(mode="json")),
            "normalized_request": request.model_dump(mode="json"),
            "intent": routing["intent"],
            "route": routing["route"],
            "retrieval": {},
            "retrieval_summary": {},
            "tools": [],
            "step_results": [],
            "raw_result": {},
            "artifacts": [],
            "trace_links": [{"type": "local_trace", "trace_id": trace_id}],
            "metrics": {},
            "session_summary": {},
            "memory_summary": {},
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
    ) -> dict[str, Any]:
        route_type = routing["intent"]["route_type"]
        output_language = routing["locale"]["final_output_language"]
        if route_type == "project_qa":
            return self._execute_project_qa_live(
                request=request,
                routing=routing,
                trace_id=trace_id,
                output_language=output_language,
                chat_config=chat_config,
            )
        if route_type == "direct_answer":
            return self._execute_direct_answer_live(
                request=request,
                routing=routing,
                trace_id=trace_id,
                output_language=output_language,
                chat_config=chat_config,
            )
        if actual_task_type == "code_review":
            return self._execute_code_review(
                request=request,
                routing=routing,
                task_id=task_id,
                run_id=run_id,
                trace_id=trace_id,
                output_language=output_language,
                chat_config=chat_config,
            )
        if actual_task_type == "logs_analyze":
            return self._execute_logs_analyze(
                request=request,
                routing=routing,
                task_id=task_id,
                run_id=run_id,
                trace_id=trace_id,
                output_language=output_language,
            )
        if actual_task_type == "config_generate":
            return self._execute_config_generate(
                request=request,
                routing=routing,
                task_id=task_id,
                run_id=run_id,
                trace_id=trace_id,
                output_language=output_language,
            )
        if actual_task_type == "perf_analyze":
            return self._execute_perf_analyze(
                request=request,
                routing=routing,
                task_id=task_id,
                run_id=run_id,
                trace_id=trace_id,
                output_language=output_language,
            )
        if actual_task_type == "config_validate":
            return self._execute_config_validate(
                request=request,
                routing=routing,
                trace_id=trace_id,
                output_language=output_language,
            )
        if actual_task_type == "assets_inspect":
            return self._execute_assets_inspect(
                request=request,
                routing=routing,
                trace_id=trace_id,
                output_language=output_language,
                chat_config=chat_config,
            )
        if actual_task_type == "code_generate":
            return self._execute_code_generate_v2(
                request=request,
                routing=routing,
                trace_id=trace_id,
                output_language=output_language,
                chat_config=chat_config,
            )
        return self._execute_task_placeholder(
            request=request,
            routing=routing,
            trace_id=trace_id,
            output_language=output_language,
        )

    def _execute_project_qa_live(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        trace_id: str,
        output_language: str,
        chat_config: ChatRuntimeConfig,
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
        inventory_result = self.inventory_service.query(
            query=str(query),
            project_id=self._inventory_project_id(request),
            limit=8,
        )
        qa_result["inventory_items"] = inventory_result["items"]
        qa_result["inventory_summary"] = inventory_result["summary"]
        base_debug = self._base_debug(request=request, routing=routing, trace_id=trace_id)
        llm_result = {
            "ok": False,
            "reason": "not_attempted",
            "error": "",
            "provider": "openai_compatible",
            "model": chat_config.model,
            "profile_id": chat_config.profile_id,
            "usage": {},
        }
        answer_generation_mode = "retrieval_summary_fallback"
        if inventory_result["items"]:
            qa_result["answer"] = self._inventory_fallback_answer(
                inventory_result=inventory_result,
                output_language=output_language,
            )
            qa_result["confidence"] = max(float(qa_result["confidence"]), 0.72)
            answer_generation_mode = "inventory_summary_fallback"
        if qa_result["retrieved_docs"] or inventory_result["items"]:
            llm_result = self.llm_service.complete(
                messages=self._project_qa_messages(
                    request=request,
                    query=str(query),
                    qa_result=qa_result,
                    output_language=output_language,
                ),
                config=chat_config,
            )
            if llm_result["ok"]:
                qa_result["answer"] = llm_result["text"]
                answer_generation_mode = "llm_synthesized"

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
                "step_id": "query_project_inventory",
                "title": "Project Inventory Query",
                "status": "completed",
                "summary": _localized(
                    output_language,
                    f"命中 {len(inventory_result['items'])} 条项目快照记录。",
                    f"Matched {len(inventory_result['items'])} project inventory item(s).",
                ),
                "details": inventory_result["summary"],
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
        user_view = {
            "title": _localized(output_language, "项目问答结果", "Project QA Result"),
            "text": qa_result["answer"],
            "blocks": [
                UserViewBlock(
                    block_type="summary",
                    title=_localized(output_language, "检索摘要", "Retrieval Summary"),
                    text=_localized(
                        output_language,
                        f"命中 {len(qa_result['retrieved_docs'])} 个知识库片段、{len(inventory_result['items'])} 条项目快照记录，当前置信度 {confidence:.2f}。",
                        f"Retrieved {len(qa_result['retrieved_docs'])} KB chunk(s) and {len(inventory_result['items'])} inventory item(s) with confidence {confidence:.2f}.",
                    ),
                    data={
                        "confidence": confidence,
                        "kb_chunk_count": len(qa_result["retrieved_docs"]),
                        "inventory_item_count": len(inventory_result["items"]),
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
            "inventory": inventory_result,
            "answer_generation": {
                "mode": answer_generation_mode,
                "provider": llm_result["provider"],
                "model": llm_result["model"],
                "profile_id": chat_config.profile_id,
            },
            "context_summary": build_context_summary(request),
        }
        base_debug["retrieval"] = qa_result["retrieval_trace"]
        base_debug["inventory"] = inventory_result
        base_debug["tools"] = [
            {
                "tool_id": "retrieve_project_knowledge",
                "status": "completed",
                "summary": f"Retrieved {len(qa_result['retrieved_docs'])} relevant chunk(s).",
            },
            {
                "tool_id": "query_project_inventory",
                "status": "completed",
                "summary": f"Matched {len(inventory_result['items'])} project inventory item(s).",
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
        base_debug["step_results"] = step_results
        base_debug["raw_result"] = data
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

    def _execute_direct_answer_live(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        trace_id: str,
        output_language: str,
        chat_config: ChatRuntimeConfig,
    ) -> dict[str, Any]:
        base_debug = self._base_debug(request=request, routing=routing, trace_id=trace_id)
        llm_result = self.llm_service.complete(
            messages=self._direct_answer_messages(request, output_language=output_language),
            config=chat_config,
        )
        used_live_llm = llm_result["ok"]
        answer_text = (
            llm_result["text"]
            if used_live_llm
            else self._direct_answer_fallback_text(output_language, llm_result["reason"])
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
                "summary": (
                    _localized(
                        output_language,
                        "已使用配置好的聊天模型完成普通对话回复。",
                        "Completed the direct-chat response with the configured live model.",
                    )
                    if used_live_llm
                    else _localized(
                        output_language,
                        "当前无法调用在线聊天模型，因此返回了降级回复。",
                        "The live chat model was unavailable, so the backend returned a degraded fallback.",
                    )
                ),
                "details": {
                    "route_type": "direct_answer",
                    "live_llm_used": used_live_llm,
                    "reason": llm_result["reason"],
                    "model": llm_result["model"],
                },
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
            "confidence": 0.85 if used_live_llm else 0.0,
            "warnings": [] if used_live_llm else [llm_result["reason"]],
            "answer_generation": {
                "mode": "live_llm" if used_live_llm else "degraded_fallback",
                "provider": llm_result["provider"],
                "model": llm_result["model"],
                "profile_id": chat_config.profile_id,
            },
            "context_summary": build_context_summary(request),
        }
        base_debug["retrieval"] = retrieval_trace
        base_debug["tools"] = [
            {
                "tool_id": "llm_direct_answer",
                "status": "completed" if used_live_llm else "degraded",
                "summary": (
                    f"Used model {llm_result['model']} for direct chat."
                    if used_live_llm
                    else f"Live chat unavailable ({llm_result['reason']})."
                ),
            }
        ]
        base_debug["step_results"] = step_results
        base_debug["raw_result"] = data
        base_debug["warnings"] = data["warnings"]
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
            "context_summary": build_context_summary(request),
        }
        base_debug["retrieval"] = qa_result["retrieval_trace"]
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
    ) -> dict[str, Any]:
        executor = LogsAnalyzeSkillExecutor(
            kb_service=self.kb_service,
            base_debug_builder=self._base_debug,
        )
        return executor.execute(
            request=request,
            routing=routing,
            task_id=task_id,
            run_id=run_id,
            trace_id=trace_id,
            output_language=output_language,
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
        )

    def _execute_config_validate(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        trace_id: str,
        output_language: str,
    ) -> dict[str, Any]:
        base_debug = self._base_debug(request=request, routing=routing, trace_id=trace_id)
        result = validate_design_config(request.payload)
        step_results = [
            {
                "step_id": "validate_config",
                "title": "Validate Config",
                "status": "completed",
                "summary": _localized(
                    output_language,
                    f"发现 {len(result['errors'])} 个错误和 {len(result['warnings'])} 个告警。",
                    f"Found {len(result['errors'])} error(s) and {len(result['warnings'])} warning(s).",
                ),
                "details": result["validation_summary"],
            }
        ]
        is_valid = result["validation_summary"]["is_valid"]
        user_text = _localized(
            output_language,
            "配置结构有效。" if is_valid else "配置结构存在问题，请先修正错误项。",
            "The config structure is valid." if is_valid else "The config structure contains problems that should be fixed first.",
        )
        user_view = {
            "title": _localized(output_language, "配置校验结果", "Config Validation Result"),
            "text": user_text,
            "blocks": [
                UserViewBlock(
                    block_type="summary",
                    title=_localized(output_language, "校验摘要", "Validation Summary"),
                    text=_localized(
                        output_language,
                        f"错误 {len(result['errors'])} 条，告警 {len(result['warnings'])} 条。",
                        f"Errors: {len(result['errors'])}, warnings: {len(result['warnings'])}.",
                    ),
                    data=result["validation_summary"],
                ).model_dump(mode="json")
            ],
            "citations_preview": [],
            "quick_actions": [],
            "status_hint": "valid" if is_valid else "invalid",
        }
        data = {
            **result,
            "sources": [],
            "citations": [],
            "context_summary": build_context_summary(request),
        }
        base_debug["retrieval"] = {"mode": "not_used", "degraded_mode": False, "reason": "route_config_validate", "filters_applied": {}, "retrieved_docs": []}
        base_debug["tools"] = [{"tool_id": "validate_design_config", "status": "completed", "summary": user_text}]
        base_debug["step_results"] = step_results
        base_debug["raw_result"] = data
        base_debug["warnings"] = [item["message"] for item in result["warnings"]]
        return {
            "user_view": user_view,
            "debug_view": base_debug,
            "data": data,
            "retrieval_trace": base_debug["retrieval"],
            "planner_diagnostics": routing["route"],
            "step_results": step_results,
            "action_proposals": [],
            "errors": [],
            "assistant_message": user_text,
            "artifacts": [
                {
                    "artifact_type": "config_validation_report",
                    "label": "Config Validation Report",
                    "filename": "config_validation_report.json",
                    "content": result,
                }
            ],
        }

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
        return executor.execute(
            request=request,
            routing=routing,
            trace_id=trace_id,
            output_language=output_language,
            chat_config=chat_config,
        )

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
