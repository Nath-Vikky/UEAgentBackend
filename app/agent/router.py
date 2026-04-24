from __future__ import annotations

import re
from typing import Any

from app.schemas.requests import UnifiedTaskRequest
from app.tools.registry import TASK_TYPE_TO_TOOL_ID, candidate_tools_for_text, get_tool_spec

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

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
TOOL_KEYWORDS = {
    "code review": "review_ue_cpp_files",
    "review": "review_ue_cpp_files",
    "审查": "review_ue_cpp_files",
    "logs": "analyze_ue_log",
    "log": "analyze_ue_log",
    "日志": "analyze_ue_log",
    "config generate": "generate_design_config",
    "generate config": "generate_design_config",
    "生成配置": "generate_design_config",
    "config validate": "validate_design_config",
    "validate config": "validate_design_config",
    "校验配置": "validate_design_config",
    "asset inspect": "inspect_asset_metadata",
    "inspect asset": "inspect_asset_metadata",
    "selected asset": "inspect_asset_metadata",
    "资产检查": "inspect_asset_metadata",
    "检查资产": "inspect_asset_metadata",
    "检查当前资产": "inspect_asset_metadata",
    "检查选中资产": "inspect_asset_metadata",
    "perf": "analyze_memory_perf_signals",
    "performance": "analyze_memory_perf_signals",
    "memory": "analyze_memory_perf_signals",
    "性能": "analyze_memory_perf_signals",
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
PROJECT_INVENTORY_SCOPE_HINTS = {
    "current project",
    "current game project",
    "this project",
    "that project",
    "project assets",
    "project inventory",
    "current repository",
    "当前项目",
    "当前工程",
    "这个项目",
    "这个工程",
    "项目里",
    "项目中",
    "工程里",
    "工程中",
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
    "dependency",
    "dependencies",
    "referencer",
    "referencers",
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
    "list",
    "show",
    "find",
    "search",
    "how many",
    "有哪些",
    "哪些",
    "列出",
    "列一下",
    "列举",
    "查看",
    "查询",
    "有没有",
    "多少",
}


def _hint_present(latest_text: str, text_lower: str, hint: str) -> bool:
    if any("\u4e00" <= ch <= "\u9fff" for ch in hint):
        return hint in latest_text
    pattern = re.compile(rf"\b{re.escape(hint.lower())}\b")
    return bool(pattern.search(text_lower))


def detect_language(text: str) -> str:
    if _CJK_RE.search(text):
        return "zh-CN"
    return "en-US"


def _localized(language: str, zh_text: str, en_text: str) -> str:
    return zh_text if language.startswith("zh") else en_text


def _preferred_language(
    latest_text: str,
    runtime_preference: str,
    session_preference: str | None,
) -> dict[str, str]:
    detected_language = detect_language(latest_text)
    lowered = latest_text.lower()
    if "用英文回答" in latest_text or "reply in english" in lowered:
        return {
            "detected_input_language": detected_language,
            "preferred_output_language": "en-US",
            "final_output_language": "en-US",
            "language_source": "explicit_override",
        }
    if "用中文回答" in latest_text or "reply in chinese" in lowered:
        return {
            "detected_input_language": detected_language,
            "preferred_output_language": "zh-CN",
            "final_output_language": "zh-CN",
            "language_source": "explicit_override",
        }
    if runtime_preference != "auto":
        return {
            "detected_input_language": detected_language,
            "preferred_output_language": runtime_preference,
            "final_output_language": runtime_preference,
            "language_source": "explicit_override",
        }
    if latest_text.strip():
        return {
            "detected_input_language": detected_language,
            "preferred_output_language": "auto",
            "final_output_language": detected_language,
            "language_source": "latest_user_message",
        }
    if session_preference:
        return {
            "detected_input_language": detected_language,
            "preferred_output_language": "auto",
            "final_output_language": session_preference,
            "language_source": "session_preference",
        }
    return {
        "detected_input_language": detected_language,
        "preferred_output_language": "auto",
        "final_output_language": detected_language,
        "language_source": "default",
    }


def _detect_tool_id(latest_text: str, text_lower: str) -> str | None:
    for token, tool_id in TOOL_KEYWORDS.items():
        if _hint_present(latest_text, text_lower, token):
            return tool_id
    return None


def _looks_like_project_inventory_query(latest_text: str, text_lower: str) -> bool:
    has_scope = any(
        _hint_present(latest_text, text_lower, hint) for hint in PROJECT_INVENTORY_SCOPE_HINTS
    )
    has_fact = any(
        _hint_present(latest_text, text_lower, hint) for hint in PROJECT_INVENTORY_FACT_HINTS
    )
    has_question = any(
        _hint_present(latest_text, text_lower, hint) for hint in PROJECT_INVENTORY_QUESTION_HINTS
    )
    return has_scope and has_fact and has_question


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
    }


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
        },
    }


def classify_request(
    request: UnifiedTaskRequest,
    *,
    session_preference: str | None = None,
) -> dict[str, Any]:
    messages = request.session.messages
    latest_text = messages[-1].content if messages else str(request.payload.get("user_query") or "")
    locale = _preferred_language(
        latest_text,
        request.runtime_options.preferred_output_language,
        session_preference,
    )
    language = locale["final_output_language"]
    text_lower = latest_text.lower()

    if request.task_type == "project_qa":
        signals = _agent_chat_signals(request, latest_text=latest_text, text_lower=text_lower)
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

    if signals["project_inventory_query"]:
        reason = _localized(
            language,
            "用户在自由聊天中询问当前项目的资产、代码或元数据事实，因此后端选择查询 Project Inventory。",
            "The user asked for current-project asset, code, or metadata facts in chat, so the backend selected Project Inventory query.",
        )
        return {
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

    if signals["deterministic_panel"] or signals["task_hint_count"] > 0 or selected_tool_id:
        spec = get_tool_spec(selected_tool_id)
        candidate_tool_ids = [selected_tool_id] if selected_tool_id else candidate_tools_for_text(text_lower)
        route_type = spec.route_preference if spec else "single_tool"
        reason = _localized(
            language,
            "检测到明确的工程动作词或确定性功能面板，优先按工程任务路径处理。",
            "Detected explicit engineering action signals or a deterministic panel, so the request is routed as an engineering task.",
        )
        return {
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
                "selected_tool_id": selected_tool_id,
                "candidate_tool_ids": candidate_tool_ids,
                "planner_confidence": 0.86,
                "decision_source": "heuristic_task_signal",
                "routing_mode": "heuristic",
                "project_signal_strength": "strong" if signals["strong_project_signal"] else "weak",
                "context_present": signals["context_present"],
                "project_hint_count": signals["project_hint_count"],
                "context_reference_present": signals["context_reference_present"],
                "explicit_kb_scope": signals["explicit_kb_scope"],
            },
        }

    if signals["strong_project_signal"]:
        reason = _localized(
            language,
            "请求明确指向当前项目、文件、模块或知识库内容，因此优先进入项目问答路径。",
            "The request clearly points to the current project, file, module, or knowledge-base scope, so it is routed into project QA.",
        )
        return {
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

    if signals["weak_project_signal"]:
        reason = _localized(
            language,
            "虽然当前带有工程上下文，但用户消息没有明确请求项目知识检索，因此先按自由聊天处理。",
            "Project context is present, but the message does not clearly request project-specific retrieval, so it stays in direct chat first.",
        )
        return {
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

    reason = _localized(
        language,
        "当前请求没有足够的工程上下文或项目知识信号，因此按普通对话处理。",
        "The request does not contain enough engineering context or project-knowledge signals, so it is treated as direct chat.",
    )
    return {
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
