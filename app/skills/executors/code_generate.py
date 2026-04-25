from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.agent.context_builder import build_context_summary
from app.schemas.common import CitationPreview, QuickAction, UserViewBlock
from app.schemas.requests import UnifiedTaskRequest
from app.services.code_generation_service import CodeGenerationService
from app.services.kb_service import KnowledgeBaseService
from app.services.llm_service import ChatRuntimeConfig, LLMService


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


@dataclass(slots=True)
class CodeGenerateSkillExecutor:
    kb_service: KnowledgeBaseService
    llm_service: LLMService
    base_debug_builder: Callable[..., dict[str, Any]]

    def execute(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        trace_id: str,
        output_language: str,
        chat_config: ChatRuntimeConfig,
        context_bundle: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base_debug = self.base_debug_builder(
            request=request,
            routing=routing,
            trace_id=trace_id,
            context_bundle=context_bundle,
        )
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
                    block_type="generated_items",
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
            "context_bundle": context_bundle,
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
