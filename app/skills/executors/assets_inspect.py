from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.agent.context_builder import build_context_summary
from app.schemas.common import CitationPreview, UserViewBlock
from app.schemas.requests import UnifiedTaskRequest
from app.services.kb_service import KnowledgeBaseService
from app.services.llm_service import ChatRuntimeConfig, LLMService
from app.tools.asset_inspect import inspect_asset_metadata
from app.tools.retrieval import retrieve_support_notes
from app.utils.json_tools import dumps_pretty


def _localized(language: str, zh_text: str, en_text: str) -> str:
    return zh_text if language.startswith("zh") else en_text


def _llm_skip_reason_code(result: dict[str, Any]) -> str:
    reason = str(result.get("reason") or "").strip()
    error = str(result.get("error") or "").strip()
    if reason == "not_attempted" and error:
        return error
    return reason or error or "not_attempted"


def _localized_llm_skip_reason(reason_code: str, output_language: str) -> str:
    zh_reasons = {
        "missing_openai_api_key": "未配置 LLM API Key，本次未执行在线综合分析。",
        "missing_chat_model": "未配置聊天模型，本次未执行在线综合分析。",
        "json_parse_failed": "LLM 返回内容无法解析为结构化 JSON，本次改用规则检查结果。",
        "request_failed": "LLM 请求失败，本次改用资产规则和关系摘要结果。",
        "empty_asset_selection": "没有可分析的资产输入，未执行 LLM 综合分析。",
        "not_attempted": "本次未尝试 LLM 综合分析。",
    }
    en_reasons = {
        "missing_openai_api_key": "No LLM API key is configured, so live synthesis was skipped.",
        "missing_chat_model": "No chat model is configured, so live synthesis was skipped.",
        "json_parse_failed": "The LLM response could not be parsed as structured JSON, so rule results were used.",
        "request_failed": "The LLM request failed, so asset rules and relationship summaries were used.",
        "empty_asset_selection": "No analyzable asset input was provided, so live synthesis was skipped.",
        "not_attempted": "Live LLM synthesis was not attempted for this run.",
    }
    return _localized(
        output_language,
        zh_reasons.get(reason_code, f"LLM 综合分析未执行，原因码：{reason_code}。"),
        en_reasons.get(reason_code, f"LLM synthesis was skipped. Reason code: {reason_code}."),
    )


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
    llm_service: LLMService
    base_debug_builder: Callable[..., dict[str, Any]]

    def _language_label(self, language: str) -> str:
        return "Simplified Chinese" if language.startswith("zh") else "English"

    def _asset_llm_messages(
        self,
        *,
        request: UnifiedTaskRequest,
        result: dict[str, Any],
        support: dict[str, Any],
        localized_violations: list[dict[str, Any]],
        localized_rename_suggestions: list[dict[str, Any]],
        output_language: str,
    ) -> list[dict[str, str]]:
        compact_payload = {
            "summary": result["summary"],
            "violations": localized_violations[:8],
            "rename_suggestions": localized_rename_suggestions[:8],
            "type_insights": result["type_insights"][:8],
            "relationship_summary": result["relationship_summary"][:8],
            "supporting_rule_count": len(support["citations"]),
        }
        system_prompt = (
            "You are a senior Unreal Engine technical artist and gameplay tools reviewer. "
            f"Return natural language fields in {self._language_label(output_language)}. "
            "Explain the selected assets in a practical, human-readable way. "
            "Use the deterministic rule results as facts, but avoid sounding like a raw linter. "
            "If no serious issue exists, say that clearly and suggest what to inspect next. "
            "Return JSON only with keys: analysis, key_points, priority, recommendations. "
            "key_points and recommendations must be arrays of short strings."
        )
        user_prompt = "\n\n".join(
            [
                f"User request:\n{request.payload.get('user_query') or 'Inspect selected assets.'}",
                f"Editor context:\n{build_context_summary(request)}",
                f"Asset inspection facts:\n{dumps_pretty(compact_payload)}",
            ]
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _run_asset_llm_analysis(
        self,
        *,
        request: UnifiedTaskRequest,
        result: dict[str, Any],
        support: dict[str, Any],
        localized_violations: list[dict[str, Any]],
        localized_rename_suggestions: list[dict[str, Any]],
        output_language: str,
        chat_config: ChatRuntimeConfig,
    ) -> dict[str, Any]:
        if not result["summary"]["asset_count"]:
            return {
                "ok": False,
                "payload": None,
                "reason": "not_attempted",
                "error": "empty_asset_selection",
                "provider": "openai_compatible",
                "model": chat_config.model,
                "profile_id": chat_config.profile_id,
                "usage": {},
            }
        return self.llm_service.complete_json_object(
            messages=self._asset_llm_messages(
                request=request,
                result=result,
                support=support,
                localized_violations=localized_violations,
                localized_rename_suggestions=localized_rename_suggestions,
                output_language=output_language,
            ),
            config=chat_config,
        )

    def _asset_llm_analysis_view(
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
            violation_count = result["summary"]["violation_count"]
            if violation_count >= 3:
                priority = "high"
            elif violation_count:
                priority = "medium"
            else:
                priority = "low"
        if status == "completed":
            text = str(payload.get("analysis") or "").strip()
            if not text:
                text = _localized(
                    output_language,
                    "LLM 已完成资产综合分析，但没有返回额外说明；请结合下方规则问题和关系摘要继续判断。",
                    "The LLM asset analysis completed but did not return additional prose; use the findings and relationship summary below.",
                )
        else:
            text = _localized(
                output_language,
                "LLM 资产综合分析未执行；当前结果来自确定性资产规则、类型摘要和依赖关系检查。",
                "LLM asset analysis was skipped; this result comes from deterministic asset rules, type summaries, and dependency checks.",
            )
        return {
            "status": status,
            "reason": reason,
            "reason_code": reason_code,
            "text": text,
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
        trace_id: str,
        output_language: str,
        chat_config: ChatRuntimeConfig,
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
        llm_result = self._run_asset_llm_analysis(
            request=request,
            result=result,
            support=support,
            localized_violations=localized_violations,
            localized_rename_suggestions=localized_rename_suggestions,
            output_language=output_language,
            chat_config=chat_config,
        )
        llm_analysis = self._asset_llm_analysis_view(
            result=result,
            llm_result=llm_result,
            output_language=output_language,
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
        user_view["blocks"].append(
            UserViewBlock(
                block_type="llm_analysis",
                title=_localized(output_language, "LLM 综合分析", "LLM Analysis"),
                text=llm_analysis["text"],
                data=llm_analysis,
            ).model_dump(mode="json")
        )
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
            "llm_analysis": llm_analysis,
            "llm_analysis_raw": llm_result,
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
            {
                "tool_id": "llm_asset_inspection_synthesis",
                "status": "completed" if llm_result.get("ok") else "skipped",
                "summary": llm_result.get("reason") or "not_attempted",
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
                        "llm_analysis": llm_analysis,
                    },
                }
            ],
            "usage": llm_result.get("usage") or {},
        }
