from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.agent.context_builder import build_context_summary
from app.schemas.common import CitationPreview, QuickAction, UserViewBlock
from app.schemas.requests import UnifiedTaskRequest
from app.services.kb_service import KnowledgeBaseService
from app.services.llm_service import ChatRuntimeConfig, LLMService
from app.utils.json_tools import dumps_pretty
from app.workflows.graphs.code_review import run_code_review_workflow


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
        "json_parse_failed": "LLM 返回内容无法解析为结构化 JSON，本次改用规则扫描结果。",
        "request_failed": "LLM 请求失败，本次改用规则扫描和知识库检索结果。",
        "file_read_failed_or_empty_source": "文件读取失败或源码内容为空，未执行 LLM 综合分析。",
        "empty_asset_selection": "没有可分析的资产输入，未执行 LLM 综合分析。",
        "not_attempted": "本次未尝试 LLM 综合分析。",
    }
    en_reasons = {
        "missing_openai_api_key": "No LLM API key is configured, so live synthesis was skipped.",
        "missing_chat_model": "No chat model is configured, so live synthesis was skipped.",
        "json_parse_failed": "The LLM response could not be parsed as structured JSON, so rule results were used.",
        "request_failed": "The LLM request failed, so rule scanning and retrieval results were used.",
        "file_read_failed_or_empty_source": "The file could not be read or the source excerpt was empty.",
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


@dataclass(slots=True)
class CodeReviewSkillExecutor:
    kb_service: KnowledgeBaseService
    llm_service: LLMService
    base_debug_builder: Callable[..., dict[str, Any]]

    def _language_label(self, language: str) -> str:
        return "Simplified Chinese" if language.startswith("zh") else "English"

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

    def _llm_analysis_from_review(
        self,
        *,
        result: dict[str, Any],
        llm_review: dict[str, Any],
        llm_payload: dict[str, Any],
        output_language: str,
    ) -> dict[str, Any]:
        status = "completed" if llm_review.get("ok") else "skipped"
        reason_code = None if status == "completed" else _llm_skip_reason_code(llm_review)
        reason = None if reason_code is None else _localized_llm_skip_reason(reason_code, output_language)
        issues = llm_payload.get("issues") if isinstance(llm_payload.get("issues"), list) else []
        recommendations = (
            llm_payload.get("recommendations")
            if isinstance(llm_payload.get("recommendations"), list)
            else []
        )
        key_points: list[str] = []
        for item in issues[:3]:
            if isinstance(item, dict):
                text = str(item.get("title") or item.get("reason") or "").strip()
            else:
                text = str(item).strip()
            if text:
                key_points.append(text)
        for item in recommendations[:2]:
            text = str(item.get("suggestion") if isinstance(item, dict) else item).strip()
            if text:
                key_points.append(text)
        severity_summary = result.get("severity_summary") or {}
        if severity_summary.get("high"):
            priority = "high"
        elif severity_summary.get("medium"):
            priority = "medium"
        else:
            priority = "low"
        if status == "completed":
            text = str(llm_payload.get("summary") or "").strip()
            if not text:
                text = _localized(
                    output_language,
                    "LLM 已完成综合审查，但没有返回额外摘要；请结合下方问题和建议继续判断。",
                    "The LLM synthesis completed but did not return an additional summary; use the findings and recommendations below.",
                )
        else:
            text = _localized(
                output_language,
                "LLM 综合分析未执行；当前结果来自确定性规则扫描、项目知识库检索和后端降级解释。",
                "LLM analysis was skipped; this result comes from deterministic rule scanning, project retrieval, and backend fallback explanation.",
            )
        return {
            "status": status,
            "reason": reason,
            "reason_code": reason_code,
            "text": text,
            "key_points": key_points[:5],
            "priority": priority,
            "model": llm_review.get("model"),
            "profile_id": llm_review.get("profile_id"),
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
        workflow = run_code_review_workflow(
            request=request,
            kb_service=self.kb_service,
            task_id=task_id,
            run_id=run_id,
            output_language=output_language,
        )
        result = workflow["result"]
        base_debug = self.base_debug_builder(request=request, routing=routing, trace_id=trace_id)
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
        llm_analysis = self._llm_analysis_from_review(
            result=result,
            llm_review=llm_review,
            llm_payload=llm_payload,
            output_language=output_language,
        )
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
                    block_type="llm_analysis",
                    title=_localized(output_language, "LLM 综合分析", "LLM Analysis"),
                    text=llm_analysis["text"],
                    data=llm_analysis,
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
            "llm_analysis": llm_analysis,
            "localized_review": {
                "llm_analysis": llm_analysis,
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
