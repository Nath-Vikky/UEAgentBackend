from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from app.agent.context_builder import build_context_summary
from app.agent.validation_advisor import build_log_validation_plan
from app.schemas.common import CitationPreview, QuickAction, UserViewBlock
from app.schemas.requests import UnifiedTaskRequest
from app.services.kb_service import KnowledgeBaseService
from app.services.llm_service import ChatRuntimeConfig, LLMService
from app.utils.json_tools import dumps_pretty
from app.workflows.graphs import run_log_analysis_workflow


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


def _llm_skip_reason_code(result: dict[str, Any]) -> str:
    reason = str(result.get("reason") or "").strip()
    error = str(result.get("error") or "").strip()
    if reason == "not_attempted" and error:
        return error
    return reason or error or "not_attempted"


def _localized_llm_skip_reason(reason_code: str, output_language: str) -> str:
    zh_reasons = {
        "missing_openai_api_key": "未配置 LLM API Key，本次日志综合解释未执行。",
        "missing_chat_model": "未配置聊天模型，本次日志综合解释未执行。",
        "json_parse_failed": "LLM 返回内容无法解析为结构化 JSON，本次使用规则解析结果。",
        "request_failed": "LLM 请求失败，本次使用规则解析和验证清单结果。",
        "empty_log_input": "没有可分析的日志文本或文件内容，未执行 LLM 综合解释。",
        "not_attempted": "本次未尝试 LLM 日志综合解释。",
    }
    en_reasons = {
        "missing_openai_api_key": "No LLM API key is configured, so live log synthesis was skipped.",
        "missing_chat_model": "No chat model is configured, so live log synthesis was skipped.",
        "json_parse_failed": "The LLM response could not be parsed as structured JSON, so rule results were used.",
        "request_failed": "The LLM request failed, so parser findings and validation guidance were used.",
        "empty_log_input": "No analyzable log text or file content was provided, so live synthesis was skipped.",
        "not_attempted": "Live LLM log synthesis was not attempted for this run.",
    }
    return _localized(
        output_language,
        zh_reasons.get(reason_code, f"LLM 日志综合解释未执行，原因码：{reason_code}。"),
        en_reasons.get(reason_code, f"LLM log synthesis was skipped. Reason code: {reason_code}."),
    )


@dataclass(slots=True)
class LogsAnalyzeSkillExecutor:
    kb_service: KnowledgeBaseService
    llm_service: LLMService
    base_debug_builder: Callable[..., dict[str, Any]]

    def _language_label(self, language: str) -> str:
        return "Simplified Chinese" if language.startswith("zh") else "English"

    def _llm_analysis_config(self, chat_config: ChatRuntimeConfig) -> ChatRuntimeConfig:
        return replace(
            chat_config,
            temperature=min(chat_config.temperature, 0.2),
            max_tokens=min(chat_config.max_tokens, 650),
            timeout_ms=max(chat_config.timeout_ms, 45000),
        )

    def _log_llm_messages(
        self,
        *,
        request: UnifiedTaskRequest,
        result: dict[str, Any],
        output_language: str,
    ) -> list[dict[str, str]]:
        compact_payload = {
            "summary": result["summary"],
            "log_summary": result["log_summary"],
            "issue_families": result["issue_families"][:8],
            "findings": result["findings"][:6],
            "suspected_causes": result["suspected_causes"][:6],
            "suggestions": result["suggestions"][:6],
            "parser_diagnostics": {
                "modules": (result.get("parser_diagnostics") or {}).get("modules", [])[:8],
                "resource_paths": (result.get("parser_diagnostics") or {}).get("resource_paths", [])[:8],
                "callstack_lines": (result.get("parser_diagnostics") or {}).get("callstack_lines", [])[:8],
            },
            "structured_events": result["structured_events"][:12],
            "input_context": {
                "input_mode": (result.get("input_context") or {}).get("input_mode"),
                "log_source": (result.get("input_context") or {}).get("log_source"),
                "notes": (result.get("input_context") or {}).get("notes"),
            },
            "accepted_knowledge_references": [
                {
                    "title": item.get("title"),
                    "source": item.get("source"),
                    "snippet": item.get("snippet"),
                    "score": item.get("score"),
                }
                for item in result.get("retrieved_references", [])[:3]
            ],
            "retrieval_quality_gate": (result.get("retrieval_quality_gate") or {}),
        }
        system_prompt = (
            "You are a senior Unreal Engine crash and gameplay log triage engineer. "
            f"Return natural language fields in {self._language_label(output_language)}. "
            "Use parser facts as the source of truth. Treat accepted knowledge references only as optional support; "
            "do not invent references when the retrieval quality gate was skipped. "
            "If the log is too short, explain uncertainty and what evidence to capture next. "
            "Return JSON only with keys: analysis, likely_root_cause, key_points, priority, recommendations. "
            "key_points and recommendations must be arrays of short strings, and priority must be low, medium, or high."
        )
        user_prompt = "\n\n".join(
            [
                f"User request:\n{request.payload.get('user_query') or 'Analyze this Unreal Engine log.'}",
                f"Editor context:\n{build_context_summary(request)}",
                f"Log facts:\n{dumps_pretty(compact_payload)}",
            ]
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _run_log_llm_analysis(
        self,
        *,
        request: UnifiedTaskRequest,
        result: dict[str, Any],
        output_language: str,
        chat_config: ChatRuntimeConfig,
    ) -> dict[str, Any]:
        if not result.get("log_summary", {}).get("line_count"):
            return {
                "ok": False,
                "payload": None,
                "reason": "not_attempted",
                "error": "empty_log_input",
                "provider": "openai_compatible",
                "model": chat_config.model,
                "profile_id": chat_config.profile_id,
                "usage": {},
            }
        llm_result = self.llm_service.complete_json_object(
            messages=self._log_llm_messages(
                request=request,
                result=result,
                output_language=output_language,
            ),
            config=self._llm_analysis_config(chat_config),
        )
        raw_text = str(llm_result.get("text") or "").strip()
        if not llm_result.get("ok") and llm_result.get("reason") == "json_parse_failed" and raw_text:
            return {
                **llm_result,
                "ok": True,
                "payload": {
                    "analysis": raw_text,
                    "likely_root_cause": "",
                    "key_points": [],
                    "priority": "medium" if result.get("issue_families") else "low",
                    "recommendations": [],
                },
                "reason": "completed_text_fallback",
                "structured": False,
            }
        if llm_result.get("ok"):
            llm_result["structured"] = True
        return llm_result

    def _log_llm_analysis_view(
        self,
        *,
        result: dict[str, Any],
        llm_result: dict[str, Any],
        output_language: str,
    ) -> dict[str, Any]:
        payload = llm_result.get("payload") if llm_result.get("ok") else None
        payload = payload if isinstance(payload, dict) else {}
        status = "completed" if llm_result.get("ok") else "skipped"
        reason_code = None if status == "completed" else _llm_skip_reason_code(llm_result)
        reason = None if reason_code is None else _localized_llm_skip_reason(reason_code, output_language)
        key_points = [str(item).strip() for item in payload.get("key_points") or [] if str(item).strip()]
        recommendations = [
            str(item).strip() for item in payload.get("recommendations") or [] if str(item).strip()
        ]
        priority = str(payload.get("priority") or "").strip().lower()
        if priority not in {"low", "medium", "high"}:
            error_count = int((result.get("log_summary") or {}).get("error_count") or 0)
            warning_count = int((result.get("log_summary") or {}).get("warning_count") or 0)
            if error_count:
                priority = "high"
            elif warning_count:
                priority = "medium"
            else:
                priority = "low"
        if status == "completed":
            text = str(payload.get("analysis") or payload.get("likely_root_cause") or "").strip()
            if not text:
                text = _localized(
                    output_language,
                    "LLM 已完成日志综合解释，但没有返回额外说明；请结合下方问题类型和建议动作继续排查。",
                    "The LLM log synthesis completed but did not return additional prose; use the issue families and suggested actions below.",
                )
        else:
            text = _localized(
                output_language,
                "LLM 日志综合解释未执行；当前结果来自确定性日志解析、问题签名识别和验证清单。",
                "LLM log synthesis was skipped; this result comes from deterministic parsing, signature detection, and validation guidance.",
            )
        return {
            "status": status,
            "reason": reason,
            "reason_code": reason_code,
            "text": text,
            "likely_root_cause": str(payload.get("likely_root_cause") or "").strip(),
            "key_points": key_points[:5],
            "recommendations": recommendations[:5],
            "priority": priority,
            "model": llm_result.get("model"),
            "profile_id": llm_result.get("profile_id"),
        }

    def execute(
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
        workflow = run_log_analysis_workflow(
            request=request,
            kb_service=self.kb_service,
            task_id=task_id,
            run_id=run_id,
            output_language=output_language,
        )
        result = workflow["result"]
        base_debug = self.base_debug_builder(request=request, routing=routing, trace_id=trace_id)
        issue_family_labels = [
            item.replace("_", " ").title() for item in result["issue_families"][:5]
        ]
        parser_diagnostics = result["parser_diagnostics"]
        input_context = result.get("input_context") or {}
        modules = parser_diagnostics.get("modules") or []
        resource_paths = parser_diagnostics.get("resource_paths") or []
        suggestions = result["suggestions"][:4]
        issue_count = len(result["issue_families"]) or 1
        validation_plan = build_log_validation_plan(
            result=result,
            output_language=output_language,
        )
        llm_result = self._run_log_llm_analysis(
            request=request,
            result=result,
            output_language=output_language,
            chat_config=chat_config,
        )
        llm_analysis = self._log_llm_analysis_view(
            result=result,
            llm_result=llm_result,
            output_language=output_language,
        )
        user_text = _localized(
            output_language,
            f"已完成日志分析，识别到 {issue_count} 组问题特征。",
            f"Log analysis completed and identified {issue_count} issue-family candidate(s).",
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
                    block_type="llm_analysis",
                    title=_localized(output_language, "LLM 综合分析", "LLM Analysis"),
                    text=llm_analysis["text"],
                    data=llm_analysis,
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
        user_view["blocks"].append(
            UserViewBlock(
                block_type="validation_plan",
                title=_localized(output_language, "验证清单", "Validation Plan"),
                text="\n".join(
                    f"- {item.get('title')}: {item.get('text')}"
                    for item in validation_plan["items"][:6]
                ),
                data=validation_plan,
            ).model_dump(mode="json")
        )
        data = {
            **result,
            "sources": [
                {"title": item["title"], "source": item["source"]}
                for item in result["retrieved_references"]
            ],
            "citations": result["retrieved_references"],
            "context_summary": build_context_summary(request),
            "warnings": workflow["warnings"],
            "validation_plan": validation_plan,
            "llm_analysis": llm_analysis,
            "llm_analysis_raw": llm_result,
        }
        step_results = [
            *workflow["step_results"],
            {
                "step_id": "llm_log_analysis_synthesis",
                "title": "LLM Log Analysis Synthesis",
                "status": "completed" if llm_result.get("ok") else "skipped",
                "summary": llm_result.get("reason") or "not_attempted",
                "details": llm_analysis,
            },
            {
                "step_id": "build_validation_plan",
                "title": "Build Validation Plan",
                "status": "completed",
                "summary": f"Generated {len(validation_plan['items'])} log validation item(s).",
                "details": validation_plan,
            },
        ]
        base_debug["retrieval"] = workflow["retrieval_trace"]
        base_debug["tools"] = [
            *workflow["tools"],
            {
                "tool_id": "llm_log_analysis_synthesis",
                "status": "completed" if llm_result.get("ok") else "skipped",
                "summary": llm_result.get("reason") or "not_attempted",
            },
            {
                "tool_id": "build_validation_plan",
                "status": "completed",
                "summary": f"Generated {len(validation_plan['items'])} log validation item(s).",
            },
        ]
        base_debug["step_results"] = step_results
        base_debug["raw_result"] = data
        base_debug["warnings"] = workflow["warnings"]
        return {
            "user_view": user_view,
            "debug_view": base_debug,
            "data": data,
            "retrieval_trace": workflow["retrieval_trace"],
            "planner_diagnostics": routing["route"],
            "step_results": step_results,
            "action_proposals": workflow["action_proposals"],
            "errors": [],
            "assistant_message": user_text,
            "artifacts": workflow["artifacts"],
            "usage": llm_result.get("usage") or {},
        }
