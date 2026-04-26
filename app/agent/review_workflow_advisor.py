from __future__ import annotations

from typing import Any


def _localized(language: str, zh_text: str, en_text: str) -> str:
    return zh_text if language.startswith("zh") else en_text


def _scope_label(result: dict[str, Any]) -> str:
    review_scope = result.get("review_scope") or {}
    return str(
        review_scope.get("file_path")
        or review_scope.get("requested_file_path")
        or review_scope.get("source_kind")
        or "inline_input"
    )


def _issue_title(issue: dict[str, Any]) -> str:
    return str(issue.get("title") or issue.get("rule_id") or "review finding")


def _fix_suggestion_for_rule(rule_id: str, language: str) -> str:
    zh = {
        "raw_pointer_ownership": "把裸 UObject 指针改为 TObjectPtr / TWeakObjectPtr；如果必须裸指针，补充所有权和生命周期注释。",
        "tick_hot_path": "确认 Tick 内只保留轻量逻辑；把加载、查询或复杂计算迁移到事件驱动、缓存或异步路径。",
        "thread_context": "确认 UObject / World / Editor 对象访问发生在游戏线程；必要时用 AsyncTask 切回 GameThread。",
        "hardcoded_asset_path": "将硬编码 /Game/ 路径改为软引用、DataAsset 配置或编辑器可配置字段。",
        "sync_load_usage": "把 LoadObject / StaticLoadObject / TryLoad 从高频路径移出，优先使用软引用和异步加载。",
        "blueprint_surface": "复核 BlueprintCallable / BlueprintReadWrite 是否必须公开；内部实现尽量保持 C++ 私有边界。",
        "include_pollution": "用前向声明和 .cpp include 缩小头文件依赖，减少模块耦合和编译成本。",
    }
    en = {
        "raw_pointer_ownership": "Replace raw UObject pointers with TObjectPtr / TWeakObjectPtr, or document ownership and lifetime explicitly.",
        "tick_hot_path": "Keep Tick lightweight; move loading, lookup, or heavy computation into event-driven, cached, or async paths.",
        "thread_context": "Ensure UObject / World / editor-object access happens on the game thread; use AsyncTask to hop back when needed.",
        "hardcoded_asset_path": "Replace hard-coded /Game/ paths with soft references, DataAsset configuration, or editor-configurable fields.",
        "sync_load_usage": "Move LoadObject / StaticLoadObject / TryLoad out of hot paths; prefer soft references and async loading.",
        "blueprint_surface": "Re-check whether BlueprintCallable / BlueprintReadWrite exposure is required; keep internals private in C++ when possible.",
        "include_pollution": "Use forward declarations and move heavy includes into .cpp files to reduce module coupling and build cost.",
    }
    return _localized(
        language,
        zh.get(rule_id, "结合上下文确认问题是否成立；若成立，先做最小修改，再补充验证步骤。"),
        en.get(rule_id, "Confirm the finding in context; if valid, make the smallest safe change and add validation steps."),
    )


def _validation_item(item_id: str, title: str, text: str, *, category: str, source: str = "backend_rule") -> dict[str, Any]:
    return {
        "item_id": item_id,
        "title": title,
        "text": text,
        "category": category,
        "source": source,
        "status": "suggested",
        "automation_level": "manual_or_editor",
    }


def _base_validation_items(language: str, source_label: str) -> list[dict[str, Any]]:
    return [
        _validation_item(
            "compile_module",
            _localized(language, "编译相关模块", "Compile the touched module"),
            _localized(
                language,
                f"编译包含 `{source_label}` 的模块，确认没有 C++ 编译错误、缺失 include 或 Build.cs 依赖问题。",
                f"Compile the module containing `{source_label}` and verify there are no C++ errors, missing includes, or Build.cs dependency issues.",
            ),
            category="compile",
        ),
        _validation_item(
            "open_editor_and_pie",
            _localized(language, "打开编辑器并运行 PIE 烟测", "Open the editor and run a PIE smoke test"),
            _localized(
                language,
                "在 UE 编辑器中打开相关地图或测试场景，运行一次 PIE，观察 Output Log 是否出现崩溃、ensure、warning 或资产加载错误。",
                "Open the related map or test scene in the UE editor, run PIE once, and watch Output Log for crashes, ensures, warnings, or asset-loading errors.",
            ),
            category="editor",
        ),
    ]


def _validation_items_for_rules(rule_ids: set[str], language: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if "raw_pointer_ownership" in rule_ids:
        items.append(
            _validation_item(
                "validate_uobject_lifetime",
                _localized(language, "验证 UObject 生命周期", "Validate UObject lifetime"),
                _localized(
                    language,
                    "在对象创建、关卡切换、销毁或 GC 后复测相关功能，确认没有悬空引用、访问已销毁对象或未被 UPROPERTY 持有的风险。",
                    "Retest object creation, level transition, destruction, or GC paths and confirm there are no dangling references or untracked UObject ownership risks.",
                ),
                category="runtime_safety",
            )
        )
    if "tick_hot_path" in rule_ids or "sync_load_usage" in rule_ids:
        items.append(
            _validation_item(
                "validate_runtime_hitch",
                _localized(language, "验证运行时卡顿风险", "Validate runtime hitch risk"),
                _localized(
                    language,
                    "在 PIE 中触发相关逻辑，观察帧时间和日志；如果之前在 Tick 或高频路径同步加载资产，重点确认没有明显 hitch。",
                    "Trigger the related flow in PIE and watch frame time and logs; if assets were synchronously loaded from Tick or hot paths, verify there is no obvious hitch.",
                ),
                category="performance",
            )
        )
    if "thread_context" in rule_ids:
        items.append(
            _validation_item(
                "validate_game_thread_access",
                _localized(language, "验证线程上下文", "Validate thread context"),
                _localized(
                    language,
                    "检查异步回调和线程切换路径，确认 UObject、World、Actor、Component 或编辑器对象只在安全线程访问。",
                    "Inspect async callbacks and thread handoff paths, confirming UObject, World, Actor, Component, or editor objects are accessed only on safe threads.",
                ),
                category="runtime_safety",
            )
        )
    if "hardcoded_asset_path" in rule_ids:
        items.append(
            _validation_item(
                "validate_asset_reference",
                _localized(language, "验证资产引用", "Validate asset reference"),
                _localized(
                    language,
                    "如果把硬编码路径改为软引用或配置项，请在编辑器里重新指定资产，并测试重命名、迁移或缺失资产时的表现。",
                    "If hard-coded paths are replaced with soft references or configuration, reassign the asset in editor and test rename, migration, or missing-asset behavior.",
                ),
                category="asset_reference",
            )
        )
    if "blueprint_surface" in rule_ids:
        items.append(
            _validation_item(
                "validate_blueprint_compile",
                _localized(language, "验证蓝图调用面", "Validate Blueprint API surface"),
                _localized(
                    language,
                    "编译引用该 API 的蓝图，确认节点签名、变量权限和调用路径仍符合预期。",
                    "Compile Blueprints that reference this API and confirm node signatures, variable permissions, and call paths remain expected.",
                ),
                category="blueprint",
            )
        )
    if "include_pollution" in rule_ids:
        items.append(
            _validation_item(
                "validate_clean_build",
                _localized(language, "验证 clean build", "Validate a clean build"),
                _localized(
                    language,
                    "调整 include 或前向声明后，执行一次干净编译，确认没有隐藏依赖被错误移除。",
                    "After include or forward-declaration changes, run a clean build and confirm no hidden dependency was removed incorrectly.",
                ),
                category="compile",
            )
        )
    return items


def build_review_workflow_advice(
    *,
    result: dict[str, Any],
    localized_issues: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    llm_analysis: dict[str, Any],
    output_language: str,
) -> dict[str, Any]:
    source_label = _scope_label(result)
    issue_count = len(result.get("issue_list") or [])
    rule_ids = {str(item.get("rule_id") or "") for item in localized_issues if item.get("rule_id")}
    read_status = str((result.get("review_scope") or {}).get("read_status") or "unknown")

    fix_items: list[dict[str, Any]] = []
    for index, issue in enumerate(localized_issues[:5], start=1):
        rule_id = str(issue.get("rule_id") or "general_review")
        fix_items.append(
            {
                "priority": index,
                "rule_id": rule_id,
                "severity": issue.get("severity") or "medium",
                "target": source_label,
                "finding": _issue_title(issue),
                "suggested_change": _fix_suggestion_for_rule(rule_id, output_language),
                "rationale": str(issue.get("reason") or issue.get("impact") or "").strip(),
                "write_policy": "not_written",
                "is_virtual": True,
            }
        )
    if not fix_items:
        fix_items.append(
            {
                "priority": 1,
                "rule_id": "review_followup",
                "severity": "info",
                "target": source_label,
                "finding": _localized(output_language, "未发现高风险规则命中", "No high-risk rule hits detected"),
                "suggested_change": _localized(
                    output_language,
                    "本轮不建议生成代码修改草稿；可以把人工复核重点放在架构意图、命名一致性和测试覆盖上。",
                    "No code-change draft is recommended for this run; focus human review on architecture intent, naming consistency, and test coverage.",
                ),
                "rationale": "",
                "write_policy": "not_written",
                "is_virtual": True,
            }
        )

    validation_items = _base_validation_items(output_language, source_label)
    validation_items.extend(_validation_items_for_rules(rule_ids, output_language))
    validation_items.append(
        _validation_item(
            "review_output_log",
            _localized(output_language, "复查 Output Log", "Review Output Log"),
            _localized(
                output_language,
                "完成修改或人工确认后，把相关 Output Log 片段贴回 Logs Analyze 或 Agent Chat，继续让后端分析是否存在新风险。",
                "After changes or manual confirmation, paste relevant Output Log excerpts into Logs Analyze or Agent Chat so the backend can check for new risks.",
            ),
            category="follow_up",
        )
    )

    workflow_steps = [
        {
            "step_id": "collect_selected_code",
            "title": _localized(output_language, "采集选中代码", "Collect selected code"),
            "status": "completed" if read_status != "error" else "error",
            "summary": _localized(
                output_language,
                f"读取范围：{source_label}，状态：{read_status}。",
                f"Scope: {source_label}; read status: {read_status}.",
            ),
        },
        {
            "step_id": "rule_scan",
            "title": _localized(output_language, "规则扫描", "Rule scan"),
            "status": "completed",
            "summary": _localized(
                output_language,
                f"发现 {issue_count} 个规则命中。",
                f"Detected {issue_count} rule-based finding(s).",
            ),
        },
        {
            "step_id": "llm_review_synthesis",
            "title": _localized(output_language, "LLM 综合解释", "LLM synthesis"),
            "status": llm_analysis.get("status") or "unknown",
            "summary": str(llm_analysis.get("reason") or llm_analysis.get("text") or "")[:240],
        },
        {
            "step_id": "draft_fix_plan",
            "title": _localized(output_language, "生成修复草稿", "Draft fix plan"),
            "status": "completed",
            "summary": _localized(
                output_language,
                f"生成 {len(fix_items)} 条非破坏性修复草稿建议。",
                f"Generated {len(fix_items)} non-destructive fix draft item(s).",
            ),
        },
        {
            "step_id": "build_validation_plan",
            "title": _localized(output_language, "生成验证清单", "Build validation plan"),
            "status": "completed",
            "summary": _localized(
                output_language,
                f"生成 {len(validation_items)} 条编译、PIE、资产和日志验证建议。",
                f"Generated {len(validation_items)} compile, PIE, asset, and log validation item(s).",
            ),
        },
    ]

    return {
        "agent_workflow": {
            "version": "review_fix_validation_workflow_v1",
            "status": "completed" if read_status != "error" else "degraded",
            "summary": _localized(
                output_language,
                "本轮按“采集代码 -> 规则扫描 -> 知识库参考 -> LLM 解释 -> 修复草稿 -> 验证清单”的轻量 Agent 工作流执行。",
                "This run followed a lightweight Agent workflow: collect code -> rule scan -> knowledge guidance -> LLM explanation -> fix draft -> validation plan.",
            ),
            "source": source_label,
            "steps": workflow_steps,
            "frontend_ui": "optional_cards_after_existing_code_review_blocks",
        },
        "fix_draft": {
            "status": "ready",
            "write_policy": {
                "written_to_disk": False,
                "reason": "Code Review fix drafts are advisory only in this personal-project scope.",
            },
            "items": fix_items,
            "recommendation_count": len(recommendations),
        },
        "validation_plan": {
            "status": "ready",
            "items": validation_items,
            "risk_focus": sorted(rule_ids),
            "automation_boundary": _localized(
                output_language,
                "当前只生成验证建议，不自动运行 UE 测试或修改工程。",
                "This version only generates validation advice; it does not run UE tests or modify the project.",
            ),
        },
    }
