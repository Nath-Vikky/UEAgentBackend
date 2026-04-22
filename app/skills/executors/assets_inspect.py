from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.agent.context_builder import build_context_summary
from app.schemas.common import CitationPreview, UserViewBlock
from app.schemas.requests import UnifiedTaskRequest
from app.services.kb_service import KnowledgeBaseService
from app.tools.asset_inspect import inspect_asset_metadata
from app.tools.retrieval import retrieve_support_notes


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


def _localized_asset_issue_items(
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


@dataclass(slots=True)
class AssetsInspectSkillExecutor:
    kb_service: KnowledgeBaseService
    base_debug_builder: Callable[..., dict[str, Any]]

    def execute(
        self,
        *,
        request: UnifiedTaskRequest,
        routing: dict[str, Any],
        trace_id: str,
        output_language: str,
    ) -> dict[str, Any]:
        base_debug = self.base_debug_builder(request=request, routing=routing, trace_id=trace_id)
        result = inspect_asset_metadata(request.payload, request.context)
        localized_violations = _localized_asset_issue_items(
            result["violations"],
            output_language=output_language,
        )
        localized_rename_suggestions = _localized_asset_recommendation_items(
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
                    (
                        f"Inspected {result['summary']['asset_count']} asset(s) and "
                        f"found {result['summary']['violation_count']} issue(s)."
                    ),
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
