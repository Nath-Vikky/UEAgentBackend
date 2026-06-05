from __future__ import annotations

import re
from typing import Any

from app.i18n.language import (
    CHINESE_REPLY_HINTS,
    DEFAULT_OUTPUT_LANGUAGE,
    ENGLISH_REPLY_HINTS,
    detect_language,
    localized as _localized,
    normalize_output_language,
)
from app.agent.signal_detectors import evaluate_signal_detectors
from app.schemas.requests import UnifiedTaskRequest
from app.tools.registry import (
    TASK_TYPE_TO_TOOL_ID,
    candidate_tools_for_text,
    detect_tool_for_text,
    get_tool_spec,
)

PROJECT_HINTS = {
    "project",
    "module",
    "config",
    "schema",
    "asset",
    "trace",
    "log",
    "interface",
    "workflow",
    "review",
    "architecture",
    "document",
    "documentation",
    "repo",
    "repository",
    "项目",
    "工程",
    "模块",
    "配置",
    "规范",
    "日志",
    "接口",
    "资产",
    "静态网格体",
    "蓝图",
    "材质",
    "贴图",
    "nanite",
    "文档",
    "架构",
    "仓库",
    "代码库",
}
TASK_ACTION_HINTS = {
    "review",
    "analyze",
    "generate",
    "validate",
    "inspect",
    "plan",
    "execute",
    "check",
    "perf",
    "审查",
    "分析",
    "生成",
    "校验",
    "检查",
    "规划",
    "执行",
    "性能",
}
CONTEXT_REFERENCE_HINTS = {
    "this file",
    "current file",
    "that file",
    "this module",
    "current module",
    "that module",
    "this project",
    "current game project",
    "current project",
    "that project",
    "project docs",
    "project doc",
    "project document",
    "project documentation",
    "repo",
    "repository",
    "knowledge base",
    "kb",
    "documentation",
    "docs",
    "backend.md",
    "current asset",
    "these assets",
    "当前文件",
    "这个文件",
    "该文件",
    "当前模块",
    "这个模块",
    "该模块",
    "当前项目",
    "当前工程",
    "这个项目",
    "这个工程",
    "该项目",
    "该工程",
    "项目文档",
    "项目知识库",
    "知识库",
    "文档",
    "接口文档",
    "后端文档",
    "当前资产",
    "这些资产",
}
EXPLICIT_TASK_REASONS = {
    "code_review": {
        "zh": "前端已经显式发起代码审查任务，后端按多步审查工作流处理。",
        "en": "The frontend explicitly requested code review, so the backend is using the review workflow.",
    },
    "code_generate": {
        "zh": "前端已经显式发起代码生成任务，后端将返回草稿与补丁计划。",
        "en": "The frontend explicitly requested code generation, so the backend is returning a draft and patch plan.",
    },
    "logs_analyze": {
        "zh": "前端已经显式发起日志分析任务，后端按日志分析工作流处理。",
        "en": "The frontend explicitly requested log analysis, so the backend is using the log-analysis workflow.",
    },
    "config_generate": {
        "zh": "前端已经显式发起配置生成任务，后端按配置生成工作流处理。",
        "en": "The frontend explicitly requested config generation, so the backend is using the config-generation workflow.",
    },
    "config_validate": {
        "zh": "前端已经显式发起配置校验任务，后端按只读校验路径处理。",
        "en": "The frontend explicitly requested config validation, so the backend is using the read-only validation path.",
    },
    "assets_inspect": {
        "zh": "前端已经显式发起资产检查任务，后端按只读资产检查路径处理。",
        "en": "The frontend explicitly requested asset inspection, so the backend is using the read-only inspection path.",
    },
    "perf_analyze": {
        "zh": "前端已经显式发起性能分析任务，后端按性能分析工作流处理。",
        "en": "The frontend explicitly requested performance analysis, so the backend is using the performance workflow.",
    },
}
DETERMINISTIC_PANELS = {
    "codereview",
    "loganalyzer",
    "configgenerator",
    "assetinspector",
    "perfanalysis",
}
PROJECT_QA_PANELS = {"projectqa"}
READONLY_MCP_TOOL_IDS = {"mcp_get_editor_context", "mcp_get_blueprint_graph", "mcp_get_widget_tree"}
PROJECT_INVENTORY_SCOPE_HINTS = {
    "current project",
    "current game project",
    "this project",
    "that project",
    "project assets",
    "project inventory",
    "current repository",
    "current asset",
    "current actor",
    "current object",
    "current material",
    "current level",
    "current scene",
    "selected asset",
    "selected actor",
    "selected object",
    "selected material",
    "currently selected",
    "this asset",
    "this actor",
    "this object",
    "this material",
    "that asset",
    "that actor",
    "that material",
    "these assets",
    "asset details",
    "level objects",
    "scene objects",
    "当前选中",
    "当前选择",
    "选中的",
    "这个对象",
    "这个物体",
    "这个材质",
    "该对象",
    "该材质",
    "当前关卡",
    "当前场景",
    "当前项目",
    "当前工程",
    "这个项目",
    "这个工程",
    "项目里",
    "项目中",
    "工程里",
    "工程中",
    "关卡里",
    "关卡中",
    "场景里",
    "场景中",
    "地图里",
    "地图中",
}
PROJECT_INVENTORY_FACT_HINTS = {
    "asset",
    "assets",
    "blueprint",
    "staticmesh",
    "static mesh",
    "skeletalmesh",
    "skeletal mesh",
    "material",
    "texture",
    "component",
    "components",
    "variable",
    "variables",
    "function",
    "functions",
    "graph",
    "graphs",
    "event graph",
    "eventgraph",
    "node",
    "nodes",
    "pin",
    "pins",
    "actor",
    "actors",
    "level actor",
    "level actors",
    "object",
    "objects",
    "placed object",
    "placed objects",
    "material instance",
    "material parameter",
    "material parameters",
    "nanite",
    "lod",
    "mesh",
    "code file",
    "cpp",
    ".cpp",
    ".h",
    "module",
    "setting",
    "settings",
    "property",
    "properties",
    "roughness",
    "metallic",
    "base color",
    "basecolor",
    "normal",
    "opacity",
    "dependency",
    "dependencies",
    "referencer",
    "referencers",
    "关卡",
    "场景",
    "对象",
    "物体",
    "物件",
    "材质实例",
    "材质参数",
    "参数",
    "资产",
    "蓝图",
    "静态网格体",
    "骨骼网格体",
    "材质",
    "贴图",
    "网格体",
    "代码文件",
    "模块",
    "属性",
    "设置",
    "依赖",
    "引用",
}
PROJECT_INVENTORY_QUESTION_HINTS = {
    "which",
    "what",
    "what is",
    "what are",
    "list",
    "show",
    "find",
    "search",
    "how many",
    "有哪些",
    "有什么",
    "哪些",
    "列出",
    "列一下",
    "列举",
    "查看",
    "查询",
    "有没有",
    "多少",
}
UE_KNOWLEDGE_DOMAIN_HINTS = {
    "unreal",
    "unreal engine",
    "ue4",
    "ue5",
    "ue c++",
    "uecpp",
    "uobject",
    "uclass",
    "ustruct",
    "uenum",
    "uproperty",
    "ufunction",
    "actor",
    "character",
    "component",
    "subsystem",
    "game instance subsystem",
    "world subsystem",
    "enhanced input",
    "input action",
    "input mapping context",
    "gas",
    "gameplay ability",
    "ability system",
    "abilitysystemcomponent",
    "attributeset",
    "gameplayeffect",
    "gameplay tag",
    "replication",
    "rpc",
    "doreplifetime",
    "onrep",
    "http",
    "websocket",
    "tcp",
    "socket",
    "async",
    "asynctask",
    "frunnable",
    "parallelfor",
    "taskgraph",
    "tarray",
    "tmap",
    "tset",
    "delegate",
    "multicast",
    "fstring",
    "fname",
    "ftext",
    "timer",
    "developersettings",
    "dataasset",
    "虚幻",
    "虚幻引擎",
    "生命周期",
    "增强输入",
    "输入映射",
    "角色",
    "组件",
    "子系统",
    "技能系统",
    "能力系统",
    "属性集",
    "技能效果",
    "玩法标签",
    "游戏标签",
    "网络同步",
    "属性同步",
    "远程调用",
    "接口请求",
    "网络请求",
    "长连接",
    "多线程",
    "线程",
    "异步",
    "异步任务",
    "反射",
    "反射宏",
    "容器",
    "数组",
    "字典",
    "集合",
    "委托",
    "事件",
    "字符串",
    "文本",
    "定时器",
    "配置",
    "项目设置",
    "数据资产",
}
UE_KNOWLEDGE_QUESTION_HINTS = {
    "what",
    "why",
    "how",
    "when",
    "which",
    "explain",
    "implement",
    "example",
    "sample",
    "code",
    "best practice",
    "difference",
    "compare",
    "怎么",
    "如何",
    "是什么",
    "为什么",
    "什么时候",
    "哪些",
    "哪个",
    "区别",
    "用法",
    "写",
    "实现",
    "示例",
    "例子",
    "代码",
    "最佳实践",
    "怎么选",
    "该用",
    "应该",
    "讲一下",
    "解释",
}
UE_KNOWLEDGE_ACRONYM_HINTS = {
    "ue4",
    "ue5",
    "uecpp",
    "gas",
    "http",
    "rpc",
    "tcp",
    "json",
    "c++",
    "uobject",
    "uclass",
    "ustruct",
    "uenum",
    "uproperty",
    "ufunction",
}


def _hint_present(latest_text: str, text_lower: str, hint: str) -> bool:
    if any("\u4e00" <= ch <= "\u9fff" for ch in hint):
        return hint in latest_text or hint.lower() in text_lower
    pattern = re.compile(rf"\b{re.escape(hint.lower())}\b")
    return bool(pattern.search(text_lower))


def _ue_knowledge_hint_present(latest_text: str, text_lower: str, hint: str) -> bool:
    normalized = hint.lower()
    if normalized in UE_KNOWLEDGE_ACRONYM_HINTS:
        return normalized in text_lower
    return _hint_present(latest_text, text_lower, hint)


def _language_payload(
    *,
    detected_language: str,
    preferred_output_language: str,
    final_output_language: str,
    language_source: str,
) -> dict[str, str]:
    return {
        "detected_input_language": detected_language,
        "preferred_output_language": preferred_output_language,
        "final_output_language": final_output_language,
        "language_source": language_source,
    }


def _message_language_override(latest_text: str, lowered: str) -> str | None:
    if any(hint in lowered or hint in latest_text for hint in ENGLISH_REPLY_HINTS):
        return "en-US"
    if any(hint in lowered or hint in latest_text for hint in CHINESE_REPLY_HINTS):
        return "zh-CN"
    return None


def _editor_language_preference(request: UnifiedTaskRequest) -> str | None:
    candidates = [
        request.payload.get("preferred_output_language"),
        request.payload.get("output_language"),
        request.payload.get("locale"),
        request.context.editor_state.get("preferred_output_language"),
        request.context.editor_state.get("output_language"),
        request.context.editor_state.get("language"),
        request.context.editor_state.get("locale"),
        request.context.editor_state.get("culture"),
        request.context.editor_state.get("editor_locale"),
        request.context.editor_state.get("user_locale"),
    ]
    for value in candidates:
        normalized = normalize_output_language(str(value) if value is not None else None)
        if normalized and normalized != "auto":
            return normalized
    return None


def _preferred_language(
    latest_text: str,
    runtime_preference: str,
    session_preference: str | None,
    editor_preference: str | None = None,
) -> dict[str, str]:
    detected_language = detect_language(latest_text)
    lowered = latest_text.lower()

    message_override = _message_language_override(latest_text, lowered)
    if message_override:
        return _language_payload(
            detected_language=detected_language,
            preferred_output_language=message_override,
            final_output_language=message_override,
            language_source="message_override",
        )

    normalized_runtime = normalize_output_language(runtime_preference)
    if normalized_runtime and normalized_runtime != "auto":
        return _language_payload(
            detected_language=detected_language,
            preferred_output_language=normalized_runtime,
            final_output_language=normalized_runtime,
            language_source="explicit_override",
        )

    normalized_session = normalize_output_language(session_preference)
    if normalized_session and normalized_session != "auto":
        return _language_payload(
            detected_language=detected_language,
            preferred_output_language=normalized_session,
            final_output_language=normalized_session,
            language_source="session_preference",
        )

    normalized_editor = normalize_output_language(editor_preference)
    if normalized_editor and normalized_editor != "auto":
        return _language_payload(
            detected_language=detected_language,
            preferred_output_language=normalized_editor,
            final_output_language=normalized_editor,
            language_source="editor_locale",
        )

    return _language_payload(
        detected_language=detected_language,
        preferred_output_language=DEFAULT_OUTPUT_LANGUAGE,
        final_output_language=DEFAULT_OUTPUT_LANGUAGE,
        language_source="default",
    )


def _looks_like_blueprint_node_template_request(latest_text: str, text_lower: str) -> bool:
    has_blueprint_target = bool(
        re.search(
            r"(?<![A-Za-z0-9_])BP_[A-Za-z][A-Za-z0-9_]{1,63}(?![A-Za-z0-9_])",
            latest_text,
            flags=re.IGNORECASE,
        )
        or re.search(r"/Game/[A-Za-z0-9_./-]+", latest_text, flags=re.IGNORECASE)
    )
    has_print_string = any(
        token in text_lower or token in latest_text
        for token in ("print string", "printstring", "\u6253\u5370\u5b57\u7b26\u4e32", "\u6253\u5370\u6587\u672c")
    )
    has_action = bool(re.search(r"\b(?:add|create|insert|place)\b", text_lower)) or any(
        token in latest_text
        for token in ("\u6dfb\u52a0", "\u52a0\u4e0a", "\u52a0\u4e00\u4e2a", "\u52a0\u4e2a", "\u589e\u52a0", "\u521b\u5efa", "\u63d2\u5165", "\u653e\u7f6e")
    )
    return has_blueprint_target and has_print_string and has_action


def _looks_like_readonly_mcp_blueprint_graph_request(latest_text: str, text_lower: str) -> bool:
    if _looks_like_editor_write_request(latest_text, text_lower):
        return False
    has_read_intent = _has_readonly_sensing_intent(latest_text, text_lower)
    has_graph_target = (
        "blueprint graph" in text_lower
        or "eventgraph" in text_lower
        or "event graph" in text_lower
        or ("blueprint" in text_lower and "graph" in text_lower)
        or "\u84dd\u56fe\u56fe\u8868" in latest_text
        or "\u84dd\u56fe\u8282\u70b9" in latest_text
    )
    return has_read_intent and has_graph_target


def _looks_like_readonly_mcp_widget_tree_request(latest_text: str, text_lower: str) -> bool:
    if _looks_like_editor_write_request(latest_text, text_lower):
        return False
    has_read_intent = _has_readonly_sensing_intent(latest_text, text_lower)
    has_widget_tree_target = (
        "widget tree" in text_lower
        or "umg tree" in text_lower
        or ("widget" in text_lower and "tree" in text_lower)
        or "\u63a7\u4ef6\u6811" in latest_text
        or ("UMG" in latest_text and "\u5c42\u7ea7" in latest_text)
    )
    return has_read_intent and has_widget_tree_target


def _looks_like_readonly_mcp_editor_context_request(latest_text: str, text_lower: str) -> bool:
    if _looks_like_editor_write_request(latest_text, text_lower):
        return False
    has_read_intent = _has_readonly_sensing_intent(latest_text, text_lower)
    has_editor_context_target = (
        "editor context" in text_lower
        or "editor status" in text_lower
        or "editor state" in text_lower
        or "live editor" in text_lower
        or "current editor status" in text_lower
        or "current editor state" in text_lower
        or "当前编辑器状态" in latest_text
        or "编辑器上下文" in latest_text
        or "实时编辑器状态" in latest_text
    )
    return has_read_intent and has_editor_context_target


def _has_readonly_sensing_intent(latest_text: str, text_lower: str) -> bool:
    return bool(re.search(r"\b(?:get|read|show|inspect|list|view|describe)\b", text_lower)) or any(
        token in latest_text
        for token in (
            "\u8bfb\u53d6",
            "\u67e5\u770b",
            "\u67e5\u8be2",
            "\u5217\u51fa",
            "\u663e\u793a",
            "\u770b\u4e00\u4e0b",
            "\u6709\u54ea\u4e9b",
        )
    )


def _looks_like_editor_write_request(latest_text: str, text_lower: str) -> bool:
    if re.search(
        r"\b(?:add|create|insert|place|set|update|change|delete|remove|move|rename|duplicate|connect|compile)\b",
        text_lower,
    ):
        return True
    return any(
        token in latest_text
        for token in (
            "\u6dfb\u52a0",
            "\u52a0\u4e0a",
            "\u63d2\u5165",
            "\u521b\u5efa",
            "\u653e\u7f6e",
            "\u8bbe\u7f6e",
            "\u4fee\u6539",
            "\u5220\u9664",
            "\u79fb\u52a8",
            "\u91cd\u547d\u540d",
            "\u590d\u5236",
            "\u8fde\u63a5",
            "\u7f16\u8bd1",
        )
    )


def _detect_tool_id(latest_text: str, text_lower: str) -> str | None:
    if _looks_like_blueprint_node_template_request(latest_text, text_lower):
        return "editor_add_blueprint_node_template"
    if _looks_like_readonly_mcp_editor_context_request(latest_text, text_lower):
        return "mcp_get_editor_context"
    if _looks_like_readonly_mcp_widget_tree_request(latest_text, text_lower):
        return "mcp_get_widget_tree"
    if _looks_like_readonly_mcp_blueprint_graph_request(latest_text, text_lower):
        return "mcp_get_blueprint_graph"
    return detect_tool_for_text(latest_text) or detect_tool_for_text(text_lower)


def _looks_like_project_inventory_query(latest_text: str, text_lower: str) -> bool:
    has_scope = any(
        _hint_present(latest_text, text_lower, hint) for hint in PROJECT_INVENTORY_SCOPE_HINTS
    )
    has_fact = any(
        _hint_present(latest_text, text_lower, hint) for hint in PROJECT_INVENTORY_FACT_HINTS
    )
    has_question = any(
        _hint_present(latest_text, text_lower, hint) for hint in PROJECT_INVENTORY_QUESTION_HINTS
    ) or "?" in latest_text or "？" in latest_text or "是什么" in latest_text or "有哪些" in latest_text
    return has_scope and has_fact and has_question


def _ue_knowledge_signal(latest_text: str, text_lower: str) -> dict[str, Any]:
    domain_hint_count = sum(
        1
        for hint in UE_KNOWLEDGE_DOMAIN_HINTS
        if _ue_knowledge_hint_present(latest_text, text_lower, hint)
    )
    has_question = any(
        _hint_present(latest_text, text_lower, hint) for hint in UE_KNOWLEDGE_QUESTION_HINTS
    ) or "?" in latest_text or "？" in latest_text
    compact_lookup = domain_hint_count > 0 and len(latest_text.strip()) <= 24
    return {
        "ue_knowledge_query": domain_hint_count > 0 and (has_question or compact_lookup),
        "ue_knowledge_hint_count": domain_hint_count,
        "ue_knowledge_question_present": has_question,
    }


def _explicit_task_routing(task_type: str, language: str) -> dict[str, Any]:
    tool_id = TASK_TYPE_TO_TOOL_ID.get(task_type)
    spec = get_tool_spec(tool_id)
    route_type = spec.route_preference if spec else "single_tool"
    reason_pack = EXPLICIT_TASK_REASONS.get(task_type, {})
    reason = reason_pack.get("zh" if language.startswith("zh") else "en") or _localized(
        language,
        "前端已经显式指定任务类型，后端按确定性任务路径处理。",
        "The frontend already chose a concrete task type, so the backend is using a deterministic task route.",
    )
    return {
        "intent": {
            "intent_type": "task_request",
            "knowledge_relevance": "strong",
            "requires_rag": bool(spec and spec.requires_retrieval),
            "requires_tool": True,
            "route_type": route_type,
            "reason": reason,
        },
        "route": {
            "route_type": route_type,
            "route_reason": reason,
            "selected_tool_id": tool_id,
            "candidate_tool_ids": [tool_id] if tool_id else [],
            "planner_confidence": 0.97,
            "decision_source": "explicit_task_type",
            "routing_mode": "deterministic",
            "project_signal_strength": "strong",
        },
    }


def _agent_chat_signals(
    request: UnifiedTaskRequest,
    *,
    latest_text: str,
    text_lower: str,
) -> dict[str, Any]:
    active_panel = (request.context.active_panel or request.context.selected_panel or "").lower()
    domain_filters = request.payload.get("domain_filters") or []
    context_present = bool(
        request.context.project_name
        or request.context.current_file
        or request.context.current_module
        or request.context.selected_assets
        or request.context.recent_open_files
    )
    project_hint_count = sum(1 for hint in PROJECT_HINTS if _hint_present(latest_text, text_lower, hint))
    task_hint_count = sum(1 for hint in TASK_ACTION_HINTS if _hint_present(latest_text, text_lower, hint))
    context_reference_present = any(
        _hint_present(latest_text, text_lower, hint) for hint in CONTEXT_REFERENCE_HINTS
    )
    ue_knowledge = _ue_knowledge_signal(latest_text, text_lower)
    explicit_kb_scope = bool(request.context.kb_domains_hint or domain_filters)
    explicit_project_panel = active_panel in PROJECT_QA_PANELS
    strong_project_signal = bool(
        explicit_project_panel
        or explicit_kb_scope
        or context_reference_present
        or project_hint_count >= 2
        or _looks_like_project_inventory_query(latest_text, text_lower)
    )
    weak_project_signal = bool(not strong_project_signal and (context_present or project_hint_count == 1))
    return {
        "active_panel": active_panel,
        "context_present": context_present,
        "project_hint_count": project_hint_count,
        "task_hint_count": task_hint_count,
        "context_reference_present": context_reference_present,
        "explicit_kb_scope": explicit_kb_scope,
        "deterministic_panel": active_panel in DETERMINISTIC_PANELS,
        "explicit_project_panel": explicit_project_panel,
        "strong_project_signal": strong_project_signal,
        "weak_project_signal": weak_project_signal,
        "project_inventory_query": _looks_like_project_inventory_query(latest_text, text_lower),
        **ue_knowledge,
    }


def _with_signal_detector_trace(
    request: UnifiedTaskRequest,
    *,
    latest_text: str,
    signals: dict[str, Any],
    selected_tool_id: str | None = None,
    signal_mode: str = "compatibility_observer",
    signal_min_confidence: float = 0.72,
    signal_min_margin: float = 8.0,
) -> dict[str, Any]:
    detection = evaluate_signal_detectors(
        latest_text,
        request,
        legacy_signals=signals,
        selected_tool_id=selected_tool_id,
        mode=signal_mode,
        min_confidence=signal_min_confidence,
        min_margin=signal_min_margin,
    )
    return {
        **signals,
        "signal_detector_trace": detection["items"],
        "top_signal_detector": detection["top"],
        "signal_detector_errors": detection["errors"],
        "signal_detector_mode": detection["mode"],
        "signal_router_recommendation": detection["recommendation"],
    }


def _signal_router_debug(signals: dict[str, Any]) -> dict[str, Any]:
    recommendation = signals.get("signal_router_recommendation") or {
        "status": "not_evaluated",
        "mode": signals.get("signal_detector_mode", "not_evaluated"),
        "override_applied": False,
    }
    return {
        "signal_detector_trace": signals.get("signal_detector_trace", []),
        "top_signal_detector": signals.get("top_signal_detector"),
        "signal_detector_mode": signals.get("signal_detector_mode", "not_evaluated"),
        "signal_router_recommendation": recommendation,
        "signal_router_override_applied": bool(recommendation.get("override_applied")),
    }


def _apply_signal_router_override(
    routing: dict[str, Any],
    *,
    language: str,
    signal_mode: str,
) -> dict[str, Any]:
    if signal_mode != "scoring_active":
        return routing
    route = dict(routing.get("route") or {})
    recommendation = dict(route.get("signal_router_recommendation") or {})
    if not recommendation.get("override_eligible"):
        return routing
    route_hint = str(recommendation.get("route_hint") or "")
    if route_hint not in {"direct_answer", "project_qa", "single_tool", "workflow"}:
        return routing
    selected_tool_id = recommendation.get("selected_tool_id")
    previous_route_type = route.get("route_type")
    previous_tool_id = route.get("selected_tool_id")
    if previous_route_type == route_hint and previous_tool_id == selected_tool_id:
        return routing

    updated = {
        "locale": dict(routing.get("locale") or {}),
        "intent": dict(routing.get("intent") or {}),
        "route": route,
    }
    recommendation["override_applied"] = True
    recommendation["previous_route_type"] = previous_route_type
    recommendation["previous_tool_id"] = previous_tool_id
    reason = _localized(
        language,
        "Signal Router active 模式命中高置信信号，因此覆盖启发式路由。",
        "Signal Router active mode found a high-confidence signal and overrode the heuristic route.",
    )
    route.update(
        {
            "route_type": route_hint,
            "route_reason": reason,
            "selected_tool_id": selected_tool_id,
            "candidate_tool_ids": [selected_tool_id] if selected_tool_id else [],
            "planner_confidence": max(
                float(route.get("planner_confidence") or 0.0),
                float(recommendation.get("confidence") or 0.0),
            ),
            "decision_source": "signal_router_active",
            "routing_mode": "scoring_active",
            "signal_router_recommendation": recommendation,
            "signal_router_override_applied": True,
        }
    )
    if route_hint == "direct_answer":
        updated["intent"].update(
            {
                "intent_type": "casual_chat",
                "knowledge_relevance": "none",
                "requires_rag": False,
                "requires_tool": False,
                "route_type": "direct_answer",
                "reason": reason,
            }
        )
        route["selected_tool_id"] = None
        route["candidate_tool_ids"] = []
    elif route_hint == "project_qa":
        tool_id = str(selected_tool_id or "retrieve_project_knowledge")
        updated["intent"].update(
            {
                "intent_type": "project_qa",
                "knowledge_relevance": "strong",
                "requires_rag": tool_id != "query_project_inventory",
                "requires_tool": tool_id == "query_project_inventory",
                "route_type": "project_qa",
                "reason": reason,
            }
        )
        route["selected_tool_id"] = tool_id
        route["candidate_tool_ids"] = [tool_id]
    else:
        spec = get_tool_spec(str(selected_tool_id or ""))
        updated["intent"].update(
            {
                "intent_type": "task_request",
                "knowledge_relevance": "possible",
                "requires_rag": bool(spec and spec.requires_retrieval),
                "requires_tool": True,
                "route_type": route_hint,
                "reason": reason,
            }
        )
    return updated


def _project_qa_response(
    *,
    language: str,
    reason: str,
    planner_confidence: float,
    decision_source: str,
    signal_strength: str,
    signals: dict[str, Any],
    selected_tool_id: str | None = None,
    candidate_tool_ids: list[str] | None = None,
) -> dict[str, Any]:
    candidates = candidate_tool_ids or ["retrieve_project_knowledge"]
    return {
        "intent": {
            "intent_type": "project_qa",
            "knowledge_relevance": "strong" if signal_strength == "strong" else "possible",
            "requires_rag": "retrieve_project_knowledge" in candidates,
            "requires_tool": bool(selected_tool_id),
            "route_type": "project_qa",
            "reason": reason,
        },
        "route": {
            "route_type": "project_qa",
            "route_reason": reason,
            "selected_tool_id": selected_tool_id,
            "candidate_tool_ids": candidates,
            "planner_confidence": planner_confidence,
            "decision_source": decision_source,
            "routing_mode": "heuristic" if decision_source != "explicit_task_type" else "deterministic",
            "project_signal_strength": signal_strength,
            "context_present": signals["context_present"],
            "project_hint_count": signals["project_hint_count"],
            "context_reference_present": signals["context_reference_present"],
            "explicit_kb_scope": signals["explicit_kb_scope"],
            "project_inventory_query": signals.get("project_inventory_query", False),
            "ue_knowledge_query": signals.get("ue_knowledge_query", False),
            "ue_knowledge_hint_count": signals.get("ue_knowledge_hint_count", 0),
            **_signal_router_debug(signals),
        },
    }


def _direct_answer_response(
    *,
    language: str,
    reason: str,
    planner_confidence: float,
    knowledge_relevance: str,
    decision_source: str,
    signal_strength: str,
    signals: dict[str, Any],
) -> dict[str, Any]:
    return {
        "intent": {
            "intent_type": "casual_chat",
            "knowledge_relevance": knowledge_relevance,
            "requires_rag": False,
            "requires_tool": False,
            "route_type": "direct_answer",
            "reason": reason,
        },
        "route": {
            "route_type": "direct_answer",
            "route_reason": reason,
            "selected_tool_id": None,
            "candidate_tool_ids": [],
            "planner_confidence": planner_confidence,
            "decision_source": decision_source,
            "routing_mode": "heuristic",
            "project_signal_strength": signal_strength,
            "context_present": signals["context_present"],
            "project_hint_count": signals["project_hint_count"],
            "context_reference_present": signals["context_reference_present"],
            "explicit_kb_scope": signals["explicit_kb_scope"],
            "project_inventory_query": signals.get("project_inventory_query", False),
            "ue_knowledge_query": signals.get("ue_knowledge_query", False),
            "ue_knowledge_hint_count": signals.get("ue_knowledge_hint_count", 0),
            **_signal_router_debug(signals),
        },
    }


def classify_request(
    request: UnifiedTaskRequest,
    *,
    session_preference: str | None = None,
    signal_mode: str = "compatibility_observer",
    signal_min_confidence: float = 0.72,
    signal_min_margin: float = 8.0,
) -> dict[str, Any]:
    messages = request.session.messages
    latest_text = messages[-1].content if messages else str(request.payload.get("user_query") or "")
    locale = _preferred_language(
        latest_text,
        request.runtime_options.preferred_output_language,
        session_preference,
        _editor_language_preference(request),
    )
    language = locale["final_output_language"]
    text_lower = latest_text.lower()

    if request.task_type == "project_qa":
        signals = _agent_chat_signals(request, latest_text=latest_text, text_lower=text_lower)
        signals = _with_signal_detector_trace(
            request,
            latest_text=latest_text,
            signals=signals,
            selected_tool_id="query_project_inventory"
            if signals["project_inventory_query"]
            else "retrieve_project_knowledge",
            signal_mode=signal_mode,
            signal_min_confidence=signal_min_confidence,
            signal_min_margin=signal_min_margin,
        )
        if signals["project_inventory_query"]:
            reason = _localized(
                language,
                "前端显式发起项目问答，且问题询问当前项目资产、代码或元数据事实，因此后端选择 Project Inventory 查询。",
                "The frontend explicitly requested project QA, and the question asks for current-project asset, code, or metadata facts, so the backend selected Project Inventory query.",
            )
            return {
                "locale": locale,
                **_project_qa_response(
                    language=language,
                    reason=reason,
                    planner_confidence=0.98,
                    decision_source="explicit_project_qa_inventory_signal",
                    signal_strength="strong",
                    signals=signals,
                    selected_tool_id="query_project_inventory",
                    candidate_tool_ids=["query_project_inventory", "retrieve_project_knowledge"],
                ),
            }
        reason = _localized(
            language,
            "前端已经显式要求项目问答，后端将优先走知识检索路径。",
            "The frontend explicitly requested project QA, so the backend will use the retrieval-backed project QA path.",
        )
        return {
            "locale": locale,
            **_project_qa_response(
                language=language,
                reason=reason,
                planner_confidence=0.98,
                decision_source="explicit_task_type",
                signal_strength="strong",
                signals=signals,
            ),
        }

    if request.task_type != "agent_chat":
        explicit = _explicit_task_routing(request.task_type, language)
        return {"locale": locale, **explicit}

    signals = _agent_chat_signals(request, latest_text=latest_text, text_lower=text_lower)
    selected_tool_id = _detect_tool_id(latest_text, text_lower)
    selected_tool_spec = get_tool_spec(selected_tool_id)
    selected_engineering_tool_id = (
        selected_tool_id
        if selected_tool_spec and selected_tool_spec.task_type != "project_qa"
        else None
    )
    signals = _with_signal_detector_trace(
        request,
        latest_text=latest_text,
        signals=signals,
        selected_tool_id=selected_tool_id,
        signal_mode=signal_mode,
        signal_min_confidence=signal_min_confidence,
        signal_min_margin=signal_min_margin,
    )

    if signals["project_inventory_query"] and selected_engineering_tool_id not in READONLY_MCP_TOOL_IDS:
        reason = _localized(
            language,
            "用户在自由聊天中询问当前项目的资产、代码或元数据事实，因此后端选择查询 Project Inventory。",
            "The user asked for current-project asset, code, or metadata facts in chat, so the backend selected Project Inventory query.",
        )
        routing_result = {
            "locale": locale,
            **_project_qa_response(
                language=language,
                reason=reason,
                planner_confidence=0.9,
                decision_source="heuristic_project_inventory_signal",
                signal_strength="strong",
                signals=signals,
                selected_tool_id="query_project_inventory",
                candidate_tool_ids=["query_project_inventory", "retrieve_project_knowledge"],
            ),
        }
        return _apply_signal_router_override(routing_result, language=language, signal_mode=signal_mode)

    if signals["deterministic_panel"] or signals["task_hint_count"] > 0 or selected_engineering_tool_id:
        spec = get_tool_spec(selected_engineering_tool_id)
        candidate_tool_ids = (
            [selected_engineering_tool_id]
            if selected_engineering_tool_id
            else [
                tool_id
                for tool_id in candidate_tools_for_text(latest_text)
                if (get_tool_spec(tool_id) and get_tool_spec(tool_id).task_type != "project_qa")
            ]
        )
        route_type = spec.route_preference if spec else "single_tool"
        reason = _localized(
            language,
            "检测到明确的工程动作词或确定性功能面板，优先按工程任务路径处理。",
            "Detected explicit engineering action signals or a deterministic panel, so the request is routed as an engineering task.",
        )
        routing_result = {
            "intent": {
                "intent_type": "task_request",
                "knowledge_relevance": "strong" if signals["context_present"] or signals["project_hint_count"] else "possible",
                "requires_rag": bool(spec and spec.requires_retrieval),
                "requires_tool": True,
                "route_type": route_type,
                "reason": reason,
            },
            "locale": locale,
            "route": {
                "route_type": route_type,
                "route_reason": reason,
                "selected_tool_id": selected_engineering_tool_id,
                "candidate_tool_ids": candidate_tool_ids,
                "planner_confidence": 0.86,
                "decision_source": "heuristic_task_signal",
                "routing_mode": "heuristic",
                "project_signal_strength": "strong" if signals["strong_project_signal"] else "weak",
                "context_present": signals["context_present"],
                "project_hint_count": signals["project_hint_count"],
                "context_reference_present": signals["context_reference_present"],
                "explicit_kb_scope": signals["explicit_kb_scope"],
                **_signal_router_debug(signals),
            },
        }
        return _apply_signal_router_override(routing_result, language=language, signal_mode=signal_mode)

    if signals["strong_project_signal"]:
        reason = _localized(
            language,
            "请求明确指向当前项目、文件、模块或知识库内容，因此优先进入项目问答路径。",
            "The request clearly points to the current project, file, module, or knowledge-base scope, so it is routed into project QA.",
        )
        routing_result = {
            "locale": locale,
            **_project_qa_response(
                language=language,
                reason=reason,
                planner_confidence=0.88,
                decision_source="heuristic_strong_project_signal",
                signal_strength="strong",
                signals=signals,
            ),
        }
        return _apply_signal_router_override(routing_result, language=language, signal_mode=signal_mode)

    if signals["ue_knowledge_query"]:
        reason = _localized(
            language,
            "用户在自由聊天中询问 UE/C++ 技术知识，后端将先检索本地知识库，再由 LLM 综合回答。",
            "The user asked a UE/C++ technical knowledge question in chat, so the backend will retrieve local knowledge first and let the LLM synthesize the answer.",
        )
        routing_result = {
            "locale": locale,
            **_project_qa_response(
                language=language,
                reason=reason,
                planner_confidence=0.87,
                decision_source="heuristic_ue_knowledge_signal",
                signal_strength="strong",
                signals=signals,
                selected_tool_id="retrieve_project_knowledge",
                candidate_tool_ids=["retrieve_project_knowledge"],
            ),
        }
        return _apply_signal_router_override(routing_result, language=language, signal_mode=signal_mode)

    if signals["weak_project_signal"]:
        reason = _localized(
            language,
            "虽然当前带有工程上下文，但用户消息没有明确请求项目知识检索，因此先按自由聊天处理。",
            "Project context is present, but the message does not clearly request project-specific retrieval, so it stays in direct chat first.",
        )
        routing_result = {
            "locale": locale,
            **_direct_answer_response(
                language=language,
                reason=reason,
                planner_confidence=0.68,
                knowledge_relevance="possible",
                decision_source="heuristic_weak_project_signal",
                signal_strength="weak",
                signals=signals,
            ),
        }
        return _apply_signal_router_override(routing_result, language=language, signal_mode=signal_mode)

    reason = _localized(
        language,
        "当前请求没有足够的工程上下文或项目知识信号，因此按普通对话处理。",
        "The request does not contain enough engineering context or project-knowledge signals, so it is treated as direct chat.",
    )
    routing_result = {
        "locale": locale,
        **_direct_answer_response(
            language=language,
            reason=reason,
            planner_confidence=0.79,
            knowledge_relevance="none",
            decision_source="heuristic_direct_chat",
            signal_strength="none",
            signals=signals,
        ),
    }
    return _apply_signal_router_override(routing_result, language=language, signal_mode=signal_mode)
