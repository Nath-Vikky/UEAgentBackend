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
from app.services.code_generation_service import CodeGenerationService
from app.services.kb_service import KnowledgeBaseService
from app.services.llm_service import ChatRuntimeConfig, LLMService, chat_runtime_config
from app.tools.asset_inspect import inspect_asset_metadata
from app.tools.config_validate import validate_design_config
from app.tools.registry import TOOL_ID_TO_TASK_TYPE
from app.tools.retrieval import retrieve_support_notes
from app.utils.json_tools import dumps_pretty
from app.utils.paths import task_artifact_dir
from app.utils.time import now_utc
from app.workflows.graphs import (
    run_code_review_workflow,
    run_config_generate_workflow,
    run_log_analysis_workflow,
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
        system_prompt = (
            "You are synthesizing an answer from project knowledge-base evidence. "
            f"Reply in {self._language_label(output_language)}. "
            "Use only the supplied evidence. "
            "If the evidence is insufficient, say so clearly instead of guessing. "
            "Prefer a short answer followed by 2-4 concrete evidence-backed points."
        )
        user_prompt = "\n\n".join(
            [
                f"User question:\n{query.strip()}",
                f"Context summary:\n{build_context_summary(request)}",
                "Evidence:",
                "\n\n".join(evidence_lines) if evidence_lines else "No retrieved evidence.",
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
        if qa_result["retrieved_docs"]:
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
            "answer_generation": {
                "mode": answer_generation_mode,
                "provider": llm_result["provider"],
                "model": llm_result["model"],
                "profile_id": chat_config.profile_id,
            },
            "context_summary": build_context_summary(request),
        }
        base_debug["retrieval"] = qa_result["retrieval_trace"]
        base_debug["tools"] = [
            {
                "tool_id": "retrieve_project_knowledge",
                "status": "completed",
                "summary": f"Retrieved {len(qa_result['retrieved_docs'])} relevant chunk(s).",
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

    def _review_issue_reason(self, rule_id: str, output_language: str) -> str:
        zh_reasons = {
            "raw_pointer_ownership": "代码中出现裸 UObject 指针，当前片段里没有看到 UPROPERTY、TObjectPtr 或明确的所有权说明。",
            "tick_hot_path": "代码启用了 Tick 路径，若其中包含同步加载或复杂逻辑，可能造成帧时间抖动。",
            "thread_context": "代码涉及线程或异步执行，需要确认是否在非游戏线程访问 UObject、World 或编辑器对象。",
            "hardcoded_asset_path": "代码中硬编码了 /Game/ 资产路径，后续重命名、迁移或打包时容易失效。",
            "sync_load_usage": "代码使用同步加载 API，运行时可能阻塞游戏线程或编辑器交互。",
            "blueprint_surface": "代码暴露了 Blueprint API，需要确认这确实是稳定的蓝图调用边界。",
            "include_pollution": "include 数量偏多，可能扩大编译依赖和模块耦合。",
        }
        en_reasons = {
            "raw_pointer_ownership": "The code uses a raw UObject pointer without visible UPROPERTY, TObjectPtr, or ownership notes.",
            "tick_hot_path": "The code enables Tick, which can create frame-time pressure if expensive work runs there.",
            "thread_context": "The code uses threading or async execution and should be checked for UObject or World access off the game thread.",
            "hardcoded_asset_path": "The code hard-codes a /Game/ asset path, which can break after rename, migration, or packaging changes.",
            "sync_load_usage": "The code uses synchronous loading APIs that may block the game thread or editor interaction.",
            "blueprint_surface": "The code exposes Blueprint-facing API and should be checked against the intended public surface.",
            "include_pollution": "The file has a large include surface, which may increase build cost and module coupling.",
        }
        return _localized(
            output_language,
            zh_reasons.get(rule_id, "该问题由通用 Unreal/C++/C# 规则扫描发现，需要结合项目语境复核。"),
            en_reasons.get(rule_id, "This finding was produced by the general Unreal/C++/C# rule scan and should be reviewed in context."),
        )

    def _review_issue_suggestion(self, issue: dict[str, Any], output_language: str) -> str:
        rule_id = str(issue.get("rule_id") or "")
        zh_suggestions = {
            "raw_pointer_ownership": "优先改为 TObjectPtr/TWeakObjectPtr，或补充 UPROPERTY 与生命周期说明。",
            "tick_hot_path": "确认 Tick 内工作量足够轻；如存在加载、查询或复杂计算，考虑改为事件驱动或异步流程。",
            "thread_context": "确认 UObject/World 访问发生在游戏线程；必要时用 AsyncTask(ENamedThreads::GameThread, ...) 切回主线程。",
            "hardcoded_asset_path": "优先改为软引用、配置项或数据资产引用，并在注释中说明依赖原因。",
            "sync_load_usage": "确认同步加载不会发生在高频路径；能延迟加载时优先使用软引用或异步加载。",
            "blueprint_surface": "复核 BlueprintCallable/BlueprintReadWrite 是否必须公开；内部能力尽量保持 C++ 私有边界。",
            "include_pollution": "尝试使用前向声明、拆分头文件依赖，或把重依赖移动到 .cpp。",
        }
        fallback = str(issue.get("suggestion") or "").strip()
        return _localized(
            output_language,
            zh_suggestions.get(rule_id, fallback or "建议结合上下文进行人工复核，并补充必要测试。"),
            fallback or "Review this in context and add focused tests where needed.",
        )

    def _localized_review_issues(
        self,
        issues: list[dict[str, Any]],
        *,
        output_language: str,
    ) -> list[dict[str, Any]]:
        localized: list[dict[str, Any]] = []
        for issue in issues:
            item = dict(issue)
            rule_id = str(item.get("rule_id") or "")
            item["reason"] = self._review_issue_reason(rule_id, output_language)
            item["suggestion"] = self._review_issue_suggestion(item, output_language)
            item["impact"] = _localized(
                output_language,
                "可能影响运行稳定性、维护成本或编辑器/打包流程，建议按严重度优先级处理。",
                "This may affect runtime stability, maintenance cost, or editor/packaging workflows.",
            )
            if output_language.startswith("zh"):
                title_map = {
                    "raw_pointer_ownership": "潜在裸指针所有权风险",
                    "tick_hot_path": "Tick 路径需要确认合理性",
                    "thread_context": "潜在线程上下文风险",
                    "hardcoded_asset_path": "检测到硬编码资产路径",
                    "sync_load_usage": "检测到同步资产加载",
                    "blueprint_surface": "Blueprint 暴露边界需要复核",
                    "include_pollution": "include 依赖面偏大",
                }
                item["title"] = title_map.get(rule_id, str(item.get("title") or "代码审查发现"))
            localized.append(item)
        return localized

    def _review_no_issue_item(self, result: dict[str, Any], output_language: str) -> dict[str, Any]:
        dimensions = [
            "UObject 生命周期",
            "Tick / 高频路径",
            "线程上下文",
            "资产加载与硬编码路径",
            "Blueprint 暴露边界",
            "include 依赖面",
        ]
        return {
            "rule_id": "no_high_risk_findings",
            "severity": "info",
            "title": _localized(
                output_language,
                "未发现高风险规则命中",
                "No high-risk rule hits detected",
            ),
            "line": None,
            "reason": _localized(
                output_language,
                f"本次规则扫描覆盖了 {', '.join(dimensions)}，没有发现明确的高风险问题。",
                "The rule scan covered UObject lifetime, Tick paths, thread context, asset loading, Blueprint API surface, and include dependencies without obvious high-risk hits.",
            ),
            "suggestion": _localized(
                output_language,
                "如果仍需更深入审查，请补充设计意图、调用路径或项目编码规范到知识库后再次分析。",
                "For deeper review, add design intent, call flow, or project coding rules to the knowledge base and run the analysis again.",
            ),
            "checked_dimensions": dimensions,
            "review_scope": result.get("review_scope") or {},
        }

    def _review_recommendation_items(
        self,
        result: dict[str, Any],
        *,
        output_language: str,
    ) -> list[dict[str, Any]]:
        issues = self._localized_review_issues(result["issue_list"], output_language=output_language)
        if issues:
            return [
                {
                    "priority": index,
                    "severity": item.get("severity"),
                    "rule_id": item.get("rule_id"),
                    "suggestion": item.get("suggestion"),
                    "line": item.get("line"),
                }
                for index, item in enumerate(issues[:5], start=1)
            ]
        return [
            {
                "priority": 1,
                "severity": "info",
                "suggestion": _localized(
                    output_language,
                    "当前没有明显规则命中；建议把人工审查重点放在架构意图、命名一致性和测试覆盖上。",
                    "No obvious rule hits were detected; focus human review on architecture intent, naming consistency, and test coverage.",
                ),
            }
        ]

    def _review_reference_items(
        self,
        result: dict[str, Any],
        *,
        output_language: str,
    ) -> list[dict[str, Any]]:
        references = [
            {
                "title": item.get("title"),
                "source": item.get("source"),
                "reason": _localized(
                    output_language,
                    "该片段作为项目知识库或规范参考参与了审查。",
                    "This chunk was used as project knowledge-base or guideline evidence.",
                ),
            }
            for item in result.get("retrieved_references", [])[:5]
        ]
        if references:
            return references
        return [
            {
                "title": _localized(output_language, "未命中足够项目知识库证据", "No project KB evidence matched"),
                "source": "local_rule_fallback",
                "reason": _localized(
                    output_language,
                    "以下审查基于当前文件内容和通用 Unreal/C++/C# 规则，仅供参考。",
                    "The review below is based on the current file content and general Unreal/C++/C# rules.",
                ),
            }
        ]

    def _review_next_step_items(
        self,
        result: dict[str, Any],
        *,
        output_language: str,
    ) -> list[dict[str, Any]]:
        has_issues = bool(result["issue_list"])
        return [
            {
                "step": "fix_or_confirm_findings",
                "text": _localized(
                    output_language,
                    "优先处理 high / medium 问题；如果判断为误报，请在代码注释或知识库中补充项目约束。",
                    "Prioritize high and medium findings; if a finding is expected, document the project constraint in code comments or the knowledge base.",
                )
                if has_issues
                else _localized(
                    output_language,
                    "如果本次审查结论符合预期，可以继续做人工架构审查或补充更具体的审查 focus。",
                    "If this result looks reasonable, continue with human architecture review or provide a more specific review focus.",
                ),
            },
            {
                "step": "run_editor_validation",
                "text": _localized(
                    output_language,
                    "在 UE 编辑器或本地构建环境中运行编译、相关自动化测试或打开目标资产验证行为。",
                    "Run compilation, relevant automated tests, or editor validation for the touched assets/classes.",
                ),
            },
            {
                "step": "improve_kb",
                "text": _localized(
                    output_language,
                    "如果需要更贴合项目风格的审查，把团队编码规范、模块约束或示例代码导入知识库。",
                    "For more project-specific review, import team coding rules, module constraints, or example code into the knowledge base.",
                ),
            },
        ]

    def _code_review_llm_messages(
        self,
        *,
        request: UnifiedTaskRequest,
        result: dict[str, Any],
        output_language: str,
    ) -> list[dict[str, str]]:
        analysis_input = result.get("analysis_input") or {}
        source_excerpt = str(analysis_input.get("source_excerpt") or "")
        review_scope = result.get("review_scope") or {}
        static_findings = [
            {
                "rule_id": item.get("rule_id"),
                "severity": item.get("severity"),
                "line": item.get("line"),
                "title": item.get("title"),
                "evidence": item.get("evidence"),
            }
            for item in result.get("issue_list", [])[:8]
        ]
        system_prompt = (
            "You are a senior Unreal Engine code reviewer. "
            f"Return natural language fields in {self._language_label(output_language)}. "
            "Use the provided source excerpt, static rule findings, editor context, and retrieved guidance. "
            "If project KB evidence is insufficient, say that explicitly and still review from the file content and general Unreal/C++/C# rules. "
            "Return JSON only with keys: summary, issues, recommendations, next_steps. "
            "Each issue must include severity, line, title, reason, impact, suggestion."
        )
        user_prompt = "\n\n".join(
            [
                f"Review scope:\n{dumps_pretty(review_scope)}",
                f"Editor context:\n{build_context_summary(request)}",
                f"Static findings:\n{dumps_pretty(static_findings)}",
                f"Retrieved guidance count: {len(result.get('retrieved_references', []))}",
                f"Source excerpt:\n{source_excerpt}",
            ]
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _run_code_review_llm(
        self,
        *,
        request: UnifiedTaskRequest,
        result: dict[str, Any],
        output_language: str,
        chat_config: ChatRuntimeConfig,
    ) -> dict[str, Any]:
        review_scope = result.get("review_scope") or {}
        analysis_input = result.get("analysis_input") or {}
        if review_scope.get("load_error") or not analysis_input.get("source_excerpt"):
            return {
                "ok": False,
                "payload": None,
                "reason": "not_attempted",
                "error": "file_read_failed_or_empty_source",
                "provider": "openai_compatible",
                "model": chat_config.model,
                "profile_id": chat_config.profile_id,
                "usage": {},
            }
        return self.llm_service.complete_json_object(
            messages=self._code_review_llm_messages(
                request=request,
                result=result,
                output_language=output_language,
            ),
            config=chat_config,
        )

    def _localized_asset_issue_items(
        self,
        issues: list[dict[str, Any]],
        *,
        output_language: str,
    ) -> list[dict[str, Any]]:
        localized: list[dict[str, Any]] = []
        for issue in issues:
            item = dict(issue)
            asset_name = str(item.get("asset_name") or item.get("asset_path") or "")
            asset_type = str(item.get("asset_type") or "")
            rule_id = str(item.get("rule_id") or "")
            if output_language.startswith("zh"):
                if rule_id == "placeholder_asset_name":
                    item["message"] = f"资产名称 `{asset_name}` 看起来是默认或占位名称。"
                    item["reason"] = f"`{asset_name}` 属于默认/占位命名，进入正式项目后会降低资产可读性和可维护性。"
                    item["suggestion"] = (
                        "改成带项目语义的名称；地图资产建议使用 `L_项目语义名` 或 `Map_项目语义名`。"
                        if asset_type == "World"
                        else "改成带项目语义的稳定名称，并保留类型前缀。"
                    )
                elif rule_id == "asset_name_spaces":
                    item["message"] = "资产名称不应包含空格。"
                    item["reason"] = "空格会降低引用、搜索和批量处理时的一致性。"
                    item["suggestion"] = "移除空格，并使用稳定的 PascalCase 或团队约定命名。"
                elif rule_id == "content_root":
                    item["message"] = "资产路径不在 `/Game/` 项目内容根下。"
                    item["reason"] = "项目内容资产应稳定归档在 `/Game/` 下，方便打包、迁移和引用追踪。"
                    item["suggestion"] = "将资产移动或引用到项目内容根目录下。"
                elif rule_id == "duplicate_candidate":
                    item["message"] = "存在疑似重复或高度相似的资产名称。"
                    item["reason"] = "多个资产在去掉分隔符或数字后名称高度相似，后续维护时容易混淆。"
                    item["suggestion"] = "确认它们是否是有意变体；如果不是，请用更明确的语义区分命名。"
            localized.append(item)
        return localized

    def _localized_asset_recommendation_items(
        self,
        items: list[dict[str, Any]],
        *,
        output_language: str,
    ) -> list[dict[str, Any]]:
        localized: list[dict[str, Any]] = []
        for item in items:
            payload = dict(item)
            asset_name = str(payload.get("asset_name") or "")
            suggested_name = str(payload.get("suggested_name") or "")
            if output_language.startswith("zh"):
                reason = str(payload.get("reason") or "")
                if "placeholder" in reason.lower() or "default" in reason.lower():
                    payload["reason"] = f"`{asset_name}` 是默认/占位命名，建议在进入正式内容前替换。"
                elif "prefix" in reason.lower():
                    payload["reason"] = "按资产类型补充前缀，方便 Content Browser 中快速识别。"
                elif "spaces" in reason.lower():
                    payload["reason"] = "移除空格，保持 UE 资产引用和批处理的一致性。"
                elif "PascalCase" in reason:
                    payload["reason"] = "使用稳定的 PascalCase 风格名称。"
                payload["suggestion"] = (
                    f"建议重命名为 `{suggested_name}`。"
                    if suggested_name
                    else "建议改成带项目语义的稳定名称。"
                )
            localized.append(payload)
        return localized

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
        workflow = run_code_review_workflow(
            request=request,
            kb_service=self.kb_service,
            task_id=task_id,
            run_id=run_id,
            output_language=output_language,
        )
        result = workflow["result"]
        base_debug = self._base_debug(request=request, routing=routing, trace_id=trace_id)
        severity_summary = result["severity_summary"]
        total_issues = len(result["issue_list"])
        load_error = (result.get("review_scope") or {}).get("load_error")
        llm_review = self._run_code_review_llm(
            request=request,
            result=result,
            output_language=output_language,
            chat_config=chat_config,
        )
        llm_payload = llm_review.get("payload") if llm_review.get("ok") else None
        llm_payload = llm_payload if isinstance(llm_payload, dict) else {}
        localized_issues = self._localized_review_issues(
            result["issue_list"],
            output_language=output_language,
        )
        issue_items = localized_issues or [self._review_no_issue_item(result, output_language)]
        recommendation_items = self._review_recommendation_items(
            result,
            output_language=output_language,
        )
        reference_items = self._review_reference_items(result, output_language=output_language)
        next_step_items = self._review_next_step_items(result, output_language=output_language)
        review_scope = result.get("review_scope") or {}
        kb_reference_count = len(result.get("retrieved_references", []))
        evidence_note = _localized(
            output_language,
            "已结合项目知识库证据。" if kb_reference_count else "未命中足够项目知识库证据；以下审查基于当前文件内容和通用 Unreal/C++/C# 规则，仅供参考。",
            "Project KB evidence was used." if kb_reference_count else "No sufficient project KB evidence matched; this review is based on the current file content and general Unreal/C++/C# rules.",
        )
        llm_note = ""
        if llm_review.get("ok") and llm_payload.get("summary"):
            llm_note = str(llm_payload["summary"]).strip()
        elif llm_review.get("reason") not in {"not_attempted", "missing_openai_api_key"}:
            llm_note = _localized(
                output_language,
                "LLM 综合审查未成功，本次结果使用确定性规则扫描与知识库检索降级生成。",
                "LLM synthesis did not complete; this result falls back to deterministic rule scan and retrieval.",
            )
        user_text = _localized(
            output_language,
            f"已完成代码审查，共发现 {total_issues} 个潜在问题，其中高风险 {severity_summary['high']} 个。{evidence_note}",
            f"Code review completed with {total_issues} potential findings, including {severity_summary['high']} high-severity item(s).",
        )
        summary_lines = [
            user_text,
            _localized(
                output_language,
                f"审查范围：{review_scope.get('file_path') or 'inline input'}，共 {review_scope.get('line_count')} 行，读取状态 {review_scope.get('read_status') or 'unknown'}。",
                f"Scope: {review_scope.get('file_path') or 'inline input'}, {review_scope.get('line_count')} line(s), read status {review_scope.get('read_status') or 'unknown'}.",
            ),
        ]
        if llm_note:
            summary_lines.append(llm_note)
        user_view = {
            "title": _localized(output_language, "代码审查结果", "Code Review Result"),
            "text": user_text,
            "blocks": [
                UserViewBlock(
                    block_type="summary",
                    title=_localized(output_language, "审查摘要", "Review Summary"),
                    text="\n".join(summary_lines),
                    data={
                        "severity_summary": severity_summary,
                        "review_scope": review_scope,
                        "kb_reference_count": kb_reference_count,
                        "llm_review_status": "completed" if llm_review.get("ok") else "skipped",
                    },
                ).model_dump(mode="json"),
                UserViewBlock(
                    block_type="issues",
                    title=_localized(output_language, "具体问题", "Findings"),
                    text="\n".join(
                        f"[{item.get('severity')}] {item.get('title')} - {item.get('reason')}"
                        for item in issue_items[:6]
                    ),
                    data={"items": issue_items[:8]},
                ).model_dump(mode="json"),
                UserViewBlock(
                    block_type="recommendations",
                    title=_localized(output_language, "修改建议", "Recommendations"),
                    text="\n".join(str(item.get("suggestion") or "") for item in recommendation_items[:5]),
                    data={"items": recommendation_items[:5]},
                ).model_dump(mode="json"),
                UserViewBlock(
                    block_type="references",
                    title=_localized(output_language, "证据与依据", "Evidence And References"),
                    text="\n".join(str(item.get("reason") or item.get("title") or "") for item in reference_items[:5]),
                    data={"items": reference_items[:5]},
                ).model_dump(mode="json"),
                UserViewBlock(
                    block_type="next_steps",
                    title=_localized(output_language, "下一步", "Next Steps"),
                    text="\n".join(str(item.get("text") or "") for item in next_step_items),
                    data={"items": next_step_items},
                ).model_dump(mode="json"),
            ],
            "citations_preview": _citation_previews(result["retrieved_references"]),
            "quick_actions": [
                QuickAction(
                    action_id="open_debug_view",
                    label=_localized(output_language, "查看调试信息", "Open debug view"),
                ).model_dump(mode="json")
            ],
            "status_hint": "needs_human_followup" if result["need_human_followup"] else "review_complete",
        }
        if load_error:
            user_text = _localized(
                output_language,
                "代码审查未能读取选中的文件，请检查 project_root、file_path 和允许扫描的源码目录。",
                "Code review could not read the selected file. Check project_root, file_path, and the allowed source roots.",
            )
            user_view["text"] = user_text
            user_view["blocks"][0]["text"] = user_text
            user_view["blocks"][1]["text"] = load_error
            user_view["status_hint"] = "read_error"
        data = {
            **result,
            "llm_review": llm_review,
            "localized_review": {
                "issues": issue_items,
                "recommendations": recommendation_items,
                "references": reference_items,
                "next_steps": next_step_items,
            },
            "sources": [{"title": item["title"], "source": item["source"]} for item in result["retrieved_references"]],
            "citations": result["retrieved_references"],
            "context_summary": build_context_summary(request),
            "warnings": workflow["warnings"],
        }
        if load_error:
            data["warnings"] = [*workflow["warnings"], load_error]
        base_debug["retrieval"] = workflow["retrieval_trace"]
        base_debug["tools"] = [
            *workflow["tools"],
            {
                "tool_id": "llm_code_review_synthesis",
                "status": "completed" if llm_review.get("ok") else "skipped",
                "summary": llm_review.get("reason") or "not_attempted",
            },
        ]
        base_debug["step_results"] = workflow["step_results"]
        base_debug["raw_result"] = data
        base_debug["warnings"] = workflow["warnings"]
        if load_error:
            base_debug["warnings"] = [*workflow["warnings"], load_error]
        return {
            "user_view": user_view,
            "debug_view": base_debug,
            "data": data,
            "retrieval_trace": workflow["retrieval_trace"],
            "planner_diagnostics": routing["route"],
            "step_results": workflow["step_results"],
            "action_proposals": workflow["action_proposals"],
            "errors": (
                [
                    {
                        "code": "code_review_file_read_failed",
                        "message": user_text,
                        "details": {
                            "file_path": (result.get("review_scope") or {}).get("file_path"),
                            "load_error": load_error,
                        },
                    }
                ]
                if load_error
                else []
            ),
            "assistant_message": user_text,
            "artifacts": workflow["artifacts"],
            "usage": llm_review.get("usage") or {},
        }

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
        workflow = run_log_analysis_workflow(
            request=request,
            kb_service=self.kb_service,
            task_id=task_id,
            run_id=run_id,
            output_language=output_language,
        )
        result = workflow["result"]
        base_debug = self._base_debug(request=request, routing=routing, trace_id=trace_id)
        issue_family_labels = [
            item.replace("_", " ").title() for item in result["issue_families"][:5]
        ]
        parser_diagnostics = result["parser_diagnostics"]
        input_context = result.get("input_context") or {}
        modules = parser_diagnostics.get("modules") or []
        resource_paths = parser_diagnostics.get("resource_paths") or []
        suggestions = result["suggestions"][:4]
        user_text = _localized(
            output_language,
            f"已完成日志分析，识别到 {len(result['issue_families']) or 1} 组问题特征。",
            f"Log analysis completed and identified {len(result['issue_families']) or 1} issue-family candidate(s).",
        )
        user_view = {
            "title": _localized(output_language, "日志分析结果", "Log Analysis Result"),
            "text": user_text,
            "blocks": [
                UserViewBlock(
                    block_type="summary",
                    title=_localized(output_language, "日志摘要", "Log Summary"),
                    text=result["summary"],
                    data={
                        **result["log_summary"],
                        "issue_family_count": len(result["issue_families"]),
                    },
                ).model_dump(mode="json"),
                UserViewBlock(
                    block_type="issues",
                    title=_localized(output_language, "问题类型", "Issue Families"),
                    text="\n".join(issue_family_labels or result["findings"][:3]),
                    data={
                        "items": [
                            {"issue_family": item}
                            for item in (result["issue_families"][:5] or result["findings"][:5])
                        ],
                        "issue_families": result["issue_families"],
                        "findings": result["findings"][:5],
                    },
                ).model_dump(mode="json"),
                UserViewBlock(
                    block_type="recommendations",
                    title=_localized(output_language, "建议动作", "Suggested Actions"),
                    text="\n".join(suggestions),
                    data={
                        "items": [{"suggestion": item} for item in suggestions],
                        "suggestions": suggestions,
                        "suspected_causes": result["suspected_causes"][:5],
                    },
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
        if any(input_context.values()):
            user_view["blocks"].append(
                UserViewBlock(
                    block_type="summary",
                    title=_localized(output_language, "日志范围", "Captured Log Window"),
                    text=str(input_context.get("log_source") or "clipboard_or_editor"),
                    data=input_context,
                ).model_dump(mode="json")
            )
        if modules or resource_paths:
            details: list[str] = []
            if modules:
                details.append("Modules: " + ", ".join(modules[:5]))
            if resource_paths:
                details.append("Resources: " + ", ".join(resource_paths[:3]))
            user_view["blocks"].append(
                UserViewBlock(
                    block_type="references",
                    title=_localized(output_language, "关键上下文", "Affected Modules / Resources"),
                    text="\n".join(details),
                    data={
                        "items": [
                            *[{"kind": "module", "value": item} for item in modules[:8]],
                            *[{"kind": "resource_path", "value": item} for item in resource_paths[:8]],
                        ],
                        "modules": modules[:8],
                        "resource_paths": resource_paths[:8],
                    },
                ).model_dump(mode="json")
            )
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
        base_debug = self._base_debug(request=request, routing=routing, trace_id=trace_id)
        execution = CodeGenerationService(
            kb_service=self.kb_service,
            llm_service=self.llm_service,
        ).execute(
            request=request,
            output_language=output_language,
            chat_config=chat_config,
        )
        result = execution["result"]
        user_text = _localized(
            output_language,
            "已生成代码结果草稿，当前只返回非破坏性的结果，不会直接写入工程。",
            "Generated code results in a non-destructive way and did not write anything into the project.",
        )
        user_view = {
            "title": _localized(output_language, "代码生成结果", "Code Generation Result"),
            "text": user_text,
            "blocks": [
                UserViewBlock(
                    block_type="summary",
                    title=_localized(output_language, "生成摘要", "Generation Summary"),
                    text=result["summary"],
                    data={
                        "generation_mode": result["generation_mode"],
                        "reference_count": result["reference_lookup"]["reference_count"],
                    },
                ).model_dump(mode="json"),
                UserViewBlock(
                    block_type="list",
                    title=_localized(output_language, "生成文件", "Generated Files"),
                    text="\n".join(item["label"] for item in result["generated_items"]),
                    data={"generated_items": result["generated_items"]},
                ).model_dump(mode="json"),
            ],
            "citations_preview": _citation_previews(result["retrieved_references"]),
            "quick_actions": [
                QuickAction(
                    action_id="review_generated_items",
                    label=_localized(output_language, "查看生成结果", "Review generated items"),
                ).model_dump(mode="json")
            ],
            "status_hint": "draft_generated",
        }
        data = {
            **result,
            "sources": result["reference_lookup"]["sources"],
            "citations": result["retrieved_references"],
            "context_summary": build_context_summary(request),
            "warnings": execution["warnings"],
        }
        base_debug["retrieval"] = execution["retrieval_trace"]
        base_debug["tools"] = execution["tools"]
        base_debug["step_results"] = execution["step_results"]
        base_debug["raw_result"] = data
        base_debug["warnings"] = execution["warnings"]
        return {
            "user_view": user_view,
            "debug_view": base_debug,
            "data": data,
            "retrieval_trace": execution["retrieval_trace"],
            "planner_diagnostics": routing["route"],
            "step_results": execution["step_results"],
            "action_proposals": execution["action_proposals"],
            "errors": [],
            "assistant_message": user_text,
            "artifacts": execution["artifacts"],
            "usage": execution["usage"],
        }

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
    ) -> dict[str, Any]:
        base_debug = self._base_debug(request=request, routing=routing, trace_id=trace_id)
        result = inspect_asset_metadata(request.payload, request.context)
        localized_violations = self._localized_asset_issue_items(
            result["violations"],
            output_language=output_language,
        )
        localized_rename_suggestions = self._localized_asset_recommendation_items(
            result["rename_suggestions"],
            output_language=output_language,
        )
        support = retrieve_support_notes(
            self.kb_service,
            query=request.payload.get("user_query") or "asset naming and folder rules",
            context=request.context,
            output_language=output_language,
            domain_filters=["asset_rules", "team_rules", "project_docs"],
        )
        step_results = [
            {
                "step_id": "inspect_assets",
                "title": "Inspect Assets",
                "status": "completed",
                "summary": _localized(
                    output_language,
                    f"已检查 {result['summary']['asset_count']} 个资产，发现 {result['summary']['violation_count']} 个问题。",
                    f"Inspected {result['summary']['asset_count']} asset(s) and found {result['summary']['violation_count']} issue(s).",
                ),
                "details": result["summary"],
            },
            {
                "step_id": "retrieve_asset_rules",
                "title": "Retrieve Asset Rules",
                "status": "completed",
                "summary": _localized(
                    output_language,
                    f"补充检索到 {len(support['retrieved_docs'])} 个资产规则片段。",
                    f"Retrieved {len(support['retrieved_docs'])} supporting asset-rule chunk(s).",
                ),
                "details": support["retrieval_trace"],
            },
        ]
        user_text = _localized(
            output_language,
            f"已完成资产检查，共发现 {result['summary']['violation_count']} 个规则问题。",
            f"Asset inspection completed with {result['summary']['violation_count']} rule issue(s).",
        )
        user_view = {
            "title": _localized(output_language, "资产检查结果", "Asset Inspection Result"),
            "text": user_text,
            "blocks": [
                UserViewBlock(
                    block_type="summary",
                    title=_localized(output_language, "检查摘要", "Inspection Summary"),
                    text=user_text,
                    data=result["summary"],
                ).model_dump(mode="json")
            ],
            "citations_preview": _citation_previews(support["citations"]),
            "quick_actions": [],
            "status_hint": "inspection_complete",
        }
        if result["violations"]:
            user_view["blocks"].append(
                UserViewBlock(
                    block_type="issues",
                    title=_localized(output_language, "规则问题", "Rule Findings"),
                    text="\n".join(
                        f"[{item['severity']}] {item.get('message') or item.get('reason')}"
                        for item in localized_violations[:5]
                    ),
                    data={
                        "items": localized_violations[:5],
                        "violations": localized_violations[:5],
                    },
                ).model_dump(mode="json")
            )
        user_view["blocks"].append(
            UserViewBlock(
                block_type="recommendations",
                title=_localized(output_language, "重命名建议", "Rename Suggestions"),
                text="\n".join(
                    item.get("suggestion") or item.get("suggested_name") or ""
                    for item in localized_rename_suggestions[:5]
                )
                or _localized(output_language, "暂无。", "None."),
                data={
                    "items": localized_rename_suggestions[:5],
                    "rename_suggestions": localized_rename_suggestions[:5],
                },
            ).model_dump(mode="json")
        )
        user_view["blocks"].append(
            UserViewBlock(
                block_type="references",
                title=_localized(output_language, "资产类型", "Asset Types"),
                text="\n".join(
                    f"{item['asset_path']} -> {item['asset_type']}"
                    for item in result["type_insights"][:5]
                )
                or _localized(output_language, "暂无。", "None."),
                data={"items": result["type_insights"][:5], "type_insights": result["type_insights"][:5]},
            ).model_dump(mode="json")
        )
        user_view["blocks"].append(
            UserViewBlock(
                block_type="references",
                title=_localized(output_language, "关系摘要", "Relationship Summary"),
                text="\n".join(
                    f"{item['asset_path']} | deps {item['dependency_count']} | refs {item['referencer_count']}"
                    for item in result["relationship_summary"][:5]
                )
                or _localized(output_language, "暂无。", "None."),
                data={
                    "items": result["relationship_summary"][:5],
                    "relationship_summary": result["relationship_summary"][:5],
                },
            ).model_dump(mode="json")
        )
        if support["answer"]:
            user_view["blocks"].append(
                UserViewBlock(
                    block_type="summary",
                    title=_localized(output_language, "参考规则摘要", "Supporting Rules Summary"),
                    text=support["answer"][:400],
                    data={"citation_count": len(support["citations"])},
                ).model_dump(mode="json")
            )
        data = {
            **result,
            "retrieved_references": support["citations"],
            "supporting_notes": support["answer"],
            "sources": [{"title": item["title"], "source": item["source"]} for item in support["citations"]],
            "citations": support["citations"],
            "context_summary": build_context_summary(request),
            "warnings": support["warnings"],
            "localized_asset_view": {
                "violations": localized_violations,
                "rename_suggestions": localized_rename_suggestions,
            },
        }
        base_debug["retrieval"] = support["retrieval_trace"]
        base_debug["tools"] = [
            {"tool_id": "inspect_asset_metadata", "status": "completed", "summary": user_text},
            {
                "tool_id": "retrieve_project_knowledge",
                "status": "completed",
                "summary": f"Retrieved {len(support['retrieved_docs'])} asset-rule chunk(s).",
            },
        ]
        base_debug["step_results"] = step_results
        base_debug["raw_result"] = data
        base_debug["warnings"] = support["warnings"]
        return {
            "user_view": user_view,
            "debug_view": base_debug,
            "data": data,
            "retrieval_trace": support["retrieval_trace"],
            "planner_diagnostics": routing["route"],
            "step_results": step_results,
            "action_proposals": [],
            "errors": [],
            "assistant_message": user_text,
            "artifacts": [
                {
                    "artifact_type": "asset_inspection_report",
                    "label": "Asset Inspection Report",
                    "filename": "asset_inspection_report.json",
                    "content": {
                        "inspection": result,
                        "support": support,
                    },
                }
            ],
        }

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
