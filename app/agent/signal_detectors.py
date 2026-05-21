from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.schemas.requests import UnifiedTaskRequest
from app.tools.registry import candidate_tools_for_text, get_tool_spec


DetectorPayload = dict[str, Any]
DetectorFn = Callable[[str, UnifiedTaskRequest, DetectorPayload], DetectorPayload | None]


@dataclass(frozen=True, slots=True)
class SignalDetector:
    """Small independent routing-signal detector.

    Detectors are currently used as a compatibility diagnostics layer. The
    existing router still owns final decisions, while this registry records the
    scored signals that would be useful for a future scoring-based router.
    """

    name: str
    priority: int
    detect: DetectorFn
    description: str = ""

    def evaluate(
        self,
        user_text: str,
        request: UnifiedTaskRequest,
        context: DetectorPayload,
    ) -> DetectorPayload | None:
        result = self.detect(user_text, request, context)
        if not result:
            return None
        confidence = max(0.0, min(float(result.get("confidence") or 0.0), 1.0))
        if confidence <= 0:
            return None
        return {
            "detector": self.name,
            "description": self.description,
            "priority": self.priority,
            "confidence": round(confidence, 4),
            "score": round(self.priority * confidence, 4),
            "route_hint": result.get("route_hint"),
            "selected_tool_id": result.get("selected_tool_id"),
            "detail": result.get("detail", {}),
        }


INVENTORY_SCOPE_HINTS = {
    "current project",
    "current game project",
    "this project",
    "project assets",
    "project inventory",
    "current level",
    "current scene",
    "level objects",
    "scene objects",
    "当前关卡",
    "当前场景",
    "当前项目",
    "当前工程",
    "项目里",
    "工程里",
    "关卡里",
    "关卡中",
    "场景里",
    "场景中",
    "地图里",
    "地图中",
}

INVENTORY_FACT_HINTS = {
    "asset",
    "assets",
    "blueprint",
    "material",
    "texture",
    "static mesh",
    "skeletal mesh",
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
    "code file",
    "cpp",
    "module",
    "property",
    "roughness",
    "metallic",
    "base color",
    "basecolor",
    "normal",
    "opacity",
    "dependency",
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
    "材质",
    "贴图",
    "静态网格体",
    "骨骼网格体",
    "代码文件",
    "模块",
    "属性",
    "依赖",
}

INVENTORY_QUESTION_HINTS = {
    "which",
    "what",
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
    "查询",
    "多少",
}

UE_KNOWLEDGE_HINTS = {
    "unreal",
    "unreal engine",
    "ue4",
    "ue5",
    "ue c++",
    "uobject",
    "uclass",
    "uproperty",
    "ufunction",
    "gas",
    "enhanced input",
    "nanite",
    "blueprint",
    "虚幻",
    "虚幻引擎",
    "蓝图",
    "增强输入",
    "多线程",
    "反射",
    "生命周期",
    "资产加载",
}

UE_QUESTION_HINTS = {
    "how",
    "what",
    "why",
    "difference",
    "compare",
    "best practice",
    "怎么",
    "如何",
    "什么",
    "为什么",
    "区别",
    "对比",
}

PROJECT_CONTEXT_HINTS = {
    "this file",
    "current file",
    "this module",
    "current module",
    "this project",
    "current project",
    "knowledge base",
    "kb",
    "当前文件",
    "这个文件",
    "当前模块",
    "当前项目",
    "知识库",
}

DIRECT_COMMAND_HINTS = {
    "review",
    "analyze",
    "generate",
    "validate",
    "inspect",
    "check",
    "审查",
    "分析",
    "生成",
    "校验",
    "检查",
}


def _contains_any(text_lower: str, hints: set[str]) -> list[str]:
    return [hint for hint in hints if hint.lower() in text_lower]


def _legacy(context: DetectorPayload) -> DetectorPayload:
    return dict(context.get("legacy_signals") or {})


def detect_inventory_query(
    user_text: str,
    request: UnifiedTaskRequest,
    context: DetectorPayload,
) -> DetectorPayload | None:
    legacy = _legacy(context)
    text_lower = user_text.lower()
    scope_hits = _contains_any(text_lower, INVENTORY_SCOPE_HINTS)
    fact_hits = _contains_any(text_lower, INVENTORY_FACT_HINTS)
    question_hits = _contains_any(text_lower, INVENTORY_QUESTION_HINTS)
    if legacy.get("project_inventory_query"):
        confidence = 0.95
    elif scope_hits and fact_hits and question_hits:
        confidence = min(0.9, 0.45 + 0.1 * len(scope_hits) + 0.1 * len(fact_hits) + 0.08 * len(question_hits))
    else:
        return None
    return {
        "confidence": confidence,
        "route_hint": "project_qa",
        "selected_tool_id": "query_project_inventory",
        "detail": {
            "scope_hits": scope_hits[:5],
            "fact_hits": fact_hits[:5],
            "question_hits": question_hits[:5],
            "legacy_project_inventory_query": bool(legacy.get("project_inventory_query")),
        },
    }


def detect_tool_keyword(
    user_text: str,
    request: UnifiedTaskRequest,
    context: DetectorPayload,
) -> DetectorPayload | None:
    selected_tool_id = context.get("selected_tool_id")
    candidates = candidate_tools_for_text(user_text)
    tool_ids = [selected_tool_id] if selected_tool_id else []
    tool_ids += [tool_id for tool_id in candidates if tool_id not in tool_ids]
    if not tool_ids:
        return None
    tool_id = str(tool_ids[0])
    spec = get_tool_spec(tool_id)
    return {
        "confidence": 0.9 if selected_tool_id else 0.72,
        "route_hint": spec.route_preference if spec else "single_tool",
        "selected_tool_id": tool_id,
        "detail": {
            "candidate_tool_ids": tool_ids[:5],
            "task_type": spec.task_type if spec else None,
        },
    }


def detect_ue_knowledge(
    user_text: str,
    request: UnifiedTaskRequest,
    context: DetectorPayload,
) -> DetectorPayload | None:
    legacy = _legacy(context)
    text_lower = user_text.lower()
    domain_hits = _contains_any(text_lower, UE_KNOWLEDGE_HINTS)
    question_hits = _contains_any(text_lower, UE_QUESTION_HINTS)
    if legacy.get("ue_knowledge_query"):
        confidence = 0.9
    elif domain_hits and (question_hits or len(user_text.strip()) <= 24):
        confidence = min(0.86, 0.42 + 0.08 * len(domain_hits) + 0.08 * len(question_hits))
    else:
        return None
    return {
        "confidence": confidence,
        "route_hint": "project_qa",
        "selected_tool_id": "retrieve_project_knowledge",
        "detail": {
            "domain_hits": domain_hits[:8],
            "question_hits": question_hits[:5],
            "legacy_ue_knowledge_query": bool(legacy.get("ue_knowledge_query")),
        },
    }


def detect_project_context(
    user_text: str,
    request: UnifiedTaskRequest,
    context: DetectorPayload,
) -> DetectorPayload | None:
    legacy = _legacy(context)
    text_lower = user_text.lower()
    context_hits = _contains_any(text_lower, PROJECT_CONTEXT_HINTS)
    if legacy.get("strong_project_signal"):
        confidence = 0.82
    elif legacy.get("weak_project_signal"):
        confidence = 0.45
    elif context_hits:
        confidence = min(0.7, 0.35 + 0.08 * len(context_hits))
    else:
        return None
    return {
        "confidence": confidence,
        "route_hint": "project_qa" if confidence >= 0.7 else "direct_answer",
        "detail": {
            "context_hits": context_hits[:6],
            "legacy_strength": "strong"
            if legacy.get("strong_project_signal")
            else "weak"
            if legacy.get("weak_project_signal")
            else "none",
        },
    }


def detect_direct_command(
    user_text: str,
    request: UnifiedTaskRequest,
    context: DetectorPayload,
) -> DetectorPayload | None:
    if request.task_type != "agent_chat":
        return None
    text_lower = user_text.lower()
    command_hits = _contains_any(text_lower, DIRECT_COMMAND_HINTS)
    legacy = _legacy(context)
    task_hint_count = int(legacy.get("task_hint_count") or 0)
    if task_hint_count > 0:
        confidence = min(0.82, 0.5 + 0.08 * task_hint_count)
    elif command_hits:
        confidence = min(0.7, 0.42 + 0.08 * len(command_hits))
    else:
        return None
    return {
        "confidence": confidence,
        "route_hint": "single_tool",
        "detail": {
            "command_hits": command_hits[:6],
            "legacy_task_hint_count": task_hint_count,
        },
    }


SIGNAL_DETECTORS: list[SignalDetector] = [
    SignalDetector("inventory_query", 100, detect_inventory_query, "Current-project inventory facts"),
    SignalDetector("tool_keyword", 95, detect_tool_keyword, "Explicit tool keyword"),
    SignalDetector("direct_command", 90, detect_direct_command, "Engineering command verb"),
    SignalDetector("ue_knowledge", 80, detect_ue_knowledge, "UE/C++ knowledge question"),
    SignalDetector("project_context", 60, detect_project_context, "Project context reference"),
]


def evaluate_signal_detectors(
    user_text: str,
    request: UnifiedTaskRequest,
    *,
    legacy_signals: DetectorPayload | None = None,
    selected_tool_id: str | None = None,
    mode: str = "compatibility_observer",
    min_confidence: float = 0.72,
    min_margin: float = 8.0,
) -> DetectorPayload:
    context = {
        "legacy_signals": legacy_signals or {},
        "selected_tool_id": selected_tool_id,
    }
    items: list[DetectorPayload] = []
    errors: list[DetectorPayload] = []
    for detector in SIGNAL_DETECTORS:
        try:
            result = detector.evaluate(user_text, request, context)
        except Exception as exc:  # pragma: no cover - defensive isolation
            errors.append({"detector": detector.name, "error": type(exc).__name__})
            continue
        if result:
            items.append(result)
    items.sort(key=lambda item: (float(item["score"]), int(item["priority"])), reverse=True)
    recommendation = _signal_router_recommendation(
        items,
        mode=mode,
        min_confidence=min_confidence,
        min_margin=min_margin,
    )
    return {
        "items": items,
        "top": items[0] if items else None,
        "errors": errors,
        "mode": mode,
        "recommendation": recommendation,
    }


def _signal_router_recommendation(
    items: list[DetectorPayload],
    *,
    mode: str,
    min_confidence: float,
    min_margin: float,
) -> DetectorPayload:
    if not items:
        return {
            "status": "no_signal",
            "mode": mode,
            "route_hint": None,
            "selected_tool_id": None,
            "confidence": 0.0,
            "score_margin": 0.0,
            "override_eligible": False,
            "override_applied": False,
            "thresholds": {
                "min_confidence": min_confidence,
                "min_margin": min_margin,
            },
        }
    top = items[0]
    runner_up = items[1] if len(items) > 1 else None
    runner_up_score = float(runner_up.get("score") or 0.0) if runner_up else 0.0
    margin = float(top.get("score") or 0.0) - runner_up_score
    confidence = float(top.get("confidence") or 0.0)
    route_hint = top.get("route_hint")
    override_eligible = bool(route_hint) and confidence >= min_confidence and margin >= min_margin
    return {
        "status": "eligible" if override_eligible else "shadow_only",
        "mode": mode,
        "route_hint": route_hint,
        "selected_tool_id": top.get("selected_tool_id"),
        "detector": top.get("detector"),
        "confidence": round(confidence, 4),
        "score": top.get("score"),
        "score_margin": round(margin, 4),
        "override_eligible": override_eligible,
        "override_applied": False,
        "thresholds": {
            "min_confidence": min_confidence,
            "min_margin": min_margin,
        },
    }
