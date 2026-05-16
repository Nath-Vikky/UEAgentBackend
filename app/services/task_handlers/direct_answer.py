from __future__ import annotations

from typing import Any

from app.agent.context_builder import build_context_summary
from app.agent.self_reflection import build_self_reflection
from app.i18n.language import localized as _localized
from app.schemas.common import QuickAction, UserViewBlock
from app.services.task_handlers.base import TaskExecutionContext


class DirectAnswerHandler:
    """Executes normal free-chat responses without invoking retrieval tools."""

    handler_id = "direct_answer"

    def execute(self, host: Any, context: TaskExecutionContext) -> dict[str, Any]:
        request = context.request
        routing = context.routing
        output_language = context.output_language

        base_debug = host._base_debug(
            request=request,
            routing=routing,
            trace_id=context.trace_id,
            context_bundle=context.context_bundle,
        )
        complete_kwargs = {
            "messages": host._direct_answer_messages(
                request,
                output_language=output_language,
                context_bundle=context.context_bundle,
            ),
            "config": context.chat_config,
        }
        if context.stream_sink:
            complete_kwargs["stream_sink"] = (
                lambda text_delta: host._emit_stream_event(
                    context.stream_sink,
                    "assistant_delta",
                    {"text": text_delta},
                    run_id=context.run_id,
                    task_id=context.task_id,
                )
            )
        llm_result = host.llm_service.complete(**complete_kwargs)
        used_live_llm = llm_result["ok"]
        answer_text = (
            llm_result["text"]
            if used_live_llm
            else host._direct_answer_fallback_text(output_language, llm_result["reason"])
        )
        if not used_live_llm and (context.context_bundle.get("long_term_memory") or {}).get("items"):
            memory_lines = [
                f"- {item.get('text')}"
                for item in (context.context_bundle.get("long_term_memory") or {}).get("items", [])[:3]
            ]
            answer_text += _localized(
                output_language,
                "\n\n我还能参考到这些项目长期记忆：\n" + "\n".join(memory_lines),
                "\n\nI can also reference these long-term project memories:\n" + "\n".join(memory_lines),
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
                "profile_id": context.chat_config.profile_id,
            },
            "context_summary": build_context_summary(request),
            "context_bundle": context.context_bundle,
        }
        self_reflection = build_self_reflection(
            route_type="direct_answer",
            output_language=output_language,
            answer_text=answer_text,
            confidence=float(data["confidence"]),
            answer_generation_mode=data["answer_generation"]["mode"],
            live_llm_used=used_live_llm,
            warnings=data["warnings"],
        )
        data["self_reflection"] = self_reflection
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
        base_debug["self_reflection"] = self_reflection
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
