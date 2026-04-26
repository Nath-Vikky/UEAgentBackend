from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.agent.context_builder import build_context_summary
from app.agent.validation_advisor import build_log_validation_plan
from app.schemas.common import CitationPreview, QuickAction, UserViewBlock
from app.schemas.requests import UnifiedTaskRequest
from app.services.kb_service import KnowledgeBaseService
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


@dataclass(slots=True)
class LogsAnalyzeSkillExecutor:
    kb_service: KnowledgeBaseService
    base_debug_builder: Callable[..., dict[str, Any]]

    def execute(
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
        }
        step_results = [
            *workflow["step_results"],
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
        }
