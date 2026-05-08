from __future__ import annotations

from typing import Any


def _localized(language: str, zh_text: str, en_text: str) -> str:
    return zh_text if language.startswith("zh") else en_text


def _item(
    item_id: str,
    title: str,
    text: str,
    *,
    category: str,
    source: str,
    automation_level: str = "manual_or_editor",
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "title": title,
        "text": text,
        "category": category,
        "source": source,
        "status": "suggested",
        "automation_level": automation_level,
    }


def build_code_generation_validation_plan(
    *,
    result: dict[str, Any],
    output_language: str,
) -> dict[str, Any]:
    generated_items = result.get("generated_items") or []
    joined_code = "\n".join(str(item.get("code") or "") for item in generated_items)
    joined_paths = "\n".join(str(item.get("file_path") or "") for item in generated_items)
    lowered = f"{joined_code}\n{joined_paths}".lower()
    items: list[dict[str, Any]] = [
        _item(
            "copy_draft_to_project",
            _localized(output_language, "手动放置代码草稿", "Manually place the code draft"),
            _localized(
                output_language,
                "确认建议路径后，手动把草稿复制到 UE 工程对应的 Public / Private 目录；后端不会自动写入文件。",
                "Confirm the suggested paths, then manually copy the draft into the matching Public / Private folders; the backend does not write files.",
            ),
            category="adoption",
            source="code_generation",
        ),
        _item(
            "compile_generated_code",
            _localized(output_language, "编译生成代码", "Compile generated code"),
            _localized(
                output_language,
                "编译目标模块，确认 include、API 宏、类名、Build.cs 依赖和 UE 反射宏没有问题。",
                "Compile the target module and verify includes, API macros, class names, Build.cs dependencies, and Unreal reflection macros.",
            ),
            category="compile",
            source="code_generation",
        ),
    ]
    if "enhancedinput" in lowered or "inputmappingcontext" in lowered or "inputaction" in lowered:
        items.append(
            _item(
                "configure_enhanced_input_assets",
                _localized(output_language, "配置 Enhanced Input 资产", "Configure Enhanced Input assets"),
                _localized(
                    output_language,
                    "在编辑器中创建或指定 Input Action 和 Input Mapping Context，并确认 Build.cs 包含 EnhancedInput 模块依赖。",
                    "Create or assign Input Action and Input Mapping Context assets in the editor, and confirm Build.cs includes the EnhancedInput module dependency.",
                ),
                category="editor_setup",
                source="code_generation",
            )
        )
    preflight_report = result.get("preflight_report") or {}
    preflight_summary = preflight_report.get("summary") or {}
    if preflight_report:
        finding_count = int(preflight_summary.get("finding_count") or 0)
        status = str(preflight_report.get("status") or "unknown")
        items.append(
            _item(
                "review_codegen_preflight",
                _localized(output_language, "复查代码生成预检结果", "Review code generation preflight"),
                _localized(
                    output_language,
                    f"后端轻量预检状态为 {status}，发现 {finding_count} 个结构、路径、UE 反射或 Enhanced Input 相关提示；复制进工程前先处理 warning/error。",
                    f"Backend preflight status is {status} with {finding_count} structure, path, UE reflection, or Enhanced Input finding(s); review warnings/errors before copying the draft into the project.",
                ),
                category="preflight",
                source="code_preflight",
            )
        )
    if "linetracesinglebychannel" in lowered or "line trace" in lowered:
        items.append(
            _item(
                "verify_trace_channel",
                _localized(output_language, "验证射线通道和碰撞响应", "Verify trace channel and collision response"),
                _localized(
                    output_language,
                    "在 PIE 中测试射线交互距离、碰撞通道、忽略自身和 DebugDraw 是否符合预期。",
                    "In PIE, test trace distance, collision channel, self-ignore behavior, and DebugDraw visibility.",
                ),
                category="editor_validation",
                source="code_generation",
            )
        )
    if "oncomponentbeginoverlap" in lowered or "overlap" in lowered:
        items.append(
            _item(
                "verify_overlap_setup",
                _localized(output_language, "验证 Overlap 设置", "Verify overlap setup"),
                _localized(
                    output_language,
                    "确认 Owner 的碰撞组件启用了 Generate Overlap Events，并且碰撞预设能触发 BeginOverlap。",
                    "Confirm the owner's collision component has Generate Overlap Events enabled and its collision preset can trigger BeginOverlap.",
                ),
                category="editor_validation",
                source="code_generation",
            )
        )
    if "ugameinstancesubsystem" in lowered or "uworldsubsystem" in lowered:
        items.append(
            _item(
                "verify_subsystem_lifecycle",
                _localized(output_language, "验证 Subsystem 生命周期", "Verify subsystem lifecycle"),
                _localized(
                    output_language,
                    "启动 PIE、切换关卡并退出，确认 Initialize / Deinitialize 调用时机和持有对象清理符合预期。",
                    "Start PIE, change levels, and exit to confirm Initialize / Deinitialize timing and held-object cleanup behavior.",
                ),
                category="runtime_validation",
                source="code_generation",
            )
        )
    items.append(
        _item(
            "run_pie_smoke_test",
            _localized(output_language, "运行 PIE 烟测", "Run a PIE smoke test"),
            _localized(
                output_language,
                "在最小测试地图中运行生成代码相关功能，并观察 Output Log 是否出现 warning、ensure 或加载错误。",
                "Run the generated-code feature in a minimal test map and watch Output Log for warnings, ensures, or loading errors.",
            ),
            category="runtime_validation",
            source="code_generation",
        )
    )
    return {
        "status": "ready",
        "items": items,
        "generated_item_count": len(generated_items),
        "write_policy": result.get("write_policy") or {"written_to_disk": False},
        "automation_boundary": _localized(
            output_language,
            "当前只生成验证建议，不自动写入工程、不自动编译或运行 UE 测试。",
            "This version only generates validation advice; it does not write files, compile, or run UE tests automatically.",
        ),
    }


def build_log_validation_plan(
    *,
    result: dict[str, Any],
    output_language: str,
) -> dict[str, Any]:
    issue_families = set(result.get("issue_families") or [])
    diagnostics = result.get("parser_diagnostics") or {}
    modules = diagnostics.get("modules") or []
    resources = diagnostics.get("resource_paths") or []
    items: list[dict[str, Any]] = [
        _item(
            "capture_full_log_window",
            _localized(output_language, "截取完整日志窗口", "Capture the full log window"),
            _localized(
                output_language,
                "保留首个 Error/Fatal 前后至少 100-200 行日志，避免只分析到后续连锁错误。",
                "Keep at least 100-200 lines around the first Error/Fatal so the analysis does not focus only on downstream errors.",
            ),
            category="reproduction",
            source="log_analysis",
        ),
        _item(
            "reproduce_once_in_editor",
            _localized(output_language, "在编辑器中复现一次", "Reproduce once in editor"),
            _localized(
                output_language,
                "记录复现步骤、当前地图、选中资产、触发操作和时间点，方便下一轮 Agent Chat 或 Logs Analyze 继续分析。",
                "Record reproduction steps, current map, selected assets, trigger action, and timestamp for the next Agent Chat or Logs Analyze pass.",
            ),
            category="reproduction",
            source="log_analysis",
        ),
    ]
    if "access_violation" in issue_families:
        items.append(
            _item(
                "inspect_lifetime_and_null_checks",
                _localized(output_language, "检查生命周期和空指针", "Inspect lifetime and null checks"),
                _localized(
                    output_language,
                    "从 callstack 顶部模块开始检查 UObject / Actor / Component 是否已销毁、未初始化或跨线程访问。",
                    "Start from the top callstack module and inspect whether UObject / Actor / Component instances are destroyed, uninitialized, or accessed across threads.",
                ),
                category="code_review",
                source="log_analysis",
            )
        )
    if "asset_load_failure" in issue_families or resources:
        items.append(
            _item(
                "verify_asset_paths_and_redirectors",
                _localized(output_language, "验证资产路径和 Redirector", "Verify asset paths and redirectors"),
                _localized(
                    output_language,
                    "检查日志中的 /Game/ 路径是否存在，执行 Fix Up Redirectors，并确认相关资产已被正确 cook。",
                    "Check whether the /Game/ paths in the log exist, run Fix Up Redirectors, and confirm related assets are cooked correctly.",
                ),
                category="asset_validation",
                source="log_analysis",
            )
        )
    if "shader_or_compile" in issue_families:
        items.append(
            _item(
                "review_first_compile_error",
                _localized(output_language, "优先查看首个编译错误", "Review the first compile error first"),
                _localized(
                    output_language,
                    "从第一个编译或 Shader 错误开始修复，后续错误可能只是连锁结果。",
                    "Fix the first compile or shader error first; later errors may be cascading failures.",
                ),
                category="compile",
                source="log_analysis",
            )
        )
    if modules:
        items.append(
            _item(
                "focus_modules",
                _localized(output_language, "聚焦相关模块", "Focus related modules"),
                _localized(
                    output_language,
                    f"优先排查日志中出现频率较高的模块：{', '.join(modules[:5])}。",
                    f"Prioritize modules that appear in the log: {', '.join(modules[:5])}.",
                ),
                category="triage",
                source="log_analysis",
            )
        )
    return {
        "status": "ready",
        "items": items,
        "issue_families": sorted(issue_families),
        "resource_paths": resources[:8],
        "automation_boundary": _localized(
            output_language,
            "当前只生成排查和复现建议，不自动运行编辑器或调试器。",
            "This version only generates triage and reproduction advice; it does not launch the editor or debugger automatically.",
        ),
    }


def build_asset_validation_plan(
    *,
    result: dict[str, Any],
    output_language: str,
) -> dict[str, Any]:
    violations = result.get("violations") or []
    type_insights = result.get("type_insights") or []
    relationships = result.get("relationship_summary") or []
    asset_types = {str(item.get("asset_type") or "") for item in type_insights}
    rule_ids = {str(item.get("rule_id") or "") for item in violations}
    items: list[dict[str, Any]] = [
        _item(
            "review_renames_before_apply",
            _localized(output_language, "人工确认重命名建议", "Manually confirm rename suggestions"),
            _localized(
                output_language,
                "重命名前先确认团队命名规范、引用关系和地图/蓝图依赖；后端不会自动重命名资产。",
                "Before renaming, confirm team naming rules, references, and map/Blueprint dependencies; the backend does not rename assets automatically.",
            ),
            category="asset_management",
            source="asset_inspection",
        ),
        _item(
            "fix_redirectors_after_rename",
            _localized(output_language, "重命名后修复 Redirector", "Fix redirectors after renaming"),
            _localized(
                output_language,
                "如在编辑器中采纳重命名，随后对目录执行 Fix Up Redirectors 并保存相关包。",
                "If renames are applied in editor, run Fix Up Redirectors for the folder and save related packages.",
            ),
            category="asset_management",
            source="asset_inspection",
        ),
    ]
    if "Blueprint" in asset_types:
        items.append(
            _item(
                "compile_referenced_blueprints",
                _localized(output_language, "编译相关蓝图", "Compile related Blueprints"),
                _localized(
                    output_language,
                    "编译选中蓝图及其引用链上的关键蓝图，确认父类、组件、变量暴露和依赖没有报错。",
                    "Compile the selected Blueprint and key Blueprints in its reference chain, checking parent class, components, exposed variables, and dependencies.",
                ),
                category="blueprint",
                source="asset_inspection",
            )
        )
    if "StaticMesh" in asset_types:
        items.append(
            _item(
                "open_static_mesh_editor",
                _localized(output_language, "检查 StaticMesh 设置", "Inspect StaticMesh settings"),
                _localized(
                    output_language,
                    "打开 Static Mesh Editor，确认 Nanite、LOD、Collision、Material Slots 和 Lightmap 设置符合项目目标。",
                    "Open Static Mesh Editor and verify Nanite, LOD, Collision, Material Slots, and Lightmap settings match project goals.",
                ),
                category="asset_quality",
                source="asset_inspection",
            )
        )
    if "placeholder_asset_name" in rule_ids or "asset_name_spaces" in rule_ids:
        items.append(
            _item(
                "search_content_browser_after_rename",
                _localized(output_language, "重命名后搜索确认", "Search after renaming"),
                _localized(
                    output_language,
                    "采纳命名修改后，在 Content Browser 搜索旧名和新名，确认没有遗留占位资产或误引用。",
                    "After adopting naming changes, search old and new names in Content Browser to confirm no placeholder assets or mistaken references remain.",
                ),
                category="asset_management",
                source="asset_inspection",
            )
        )
    if relationships:
        items.append(
            _item(
                "review_reference_viewer",
                _localized(output_language, "检查 Reference Viewer", "Inspect Reference Viewer"),
                _localized(
                    output_language,
                    "打开 Reference Viewer 查看依赖和被引用关系，确认重命名、移动或删除不会破坏地图和蓝图。",
                    "Open Reference Viewer to inspect dependencies and referencers, confirming rename, move, or delete actions will not break maps or Blueprints.",
                ),
                category="dependency",
                source="asset_inspection",
            )
        )
    return {
        "status": "ready",
        "items": items,
        "asset_types": sorted(item for item in asset_types if item),
        "rule_ids": sorted(item for item in rule_ids if item),
        "automation_boundary": _localized(
            output_language,
            "当前只生成资产检查和编辑器操作建议，不自动修改、保存或迁移资产。",
            "This version only generates asset inspection and editor-operation advice; it does not modify, save, or migrate assets automatically.",
        ),
    }
