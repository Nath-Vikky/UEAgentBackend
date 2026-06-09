from __future__ import annotations

import re
from typing import Any


ROUTE_KEYWORD_VERIFIER_VERSION = "route_keyword_verifier_v1"

HARD_WRITE_KEYWORDS = (
    "add",
    "append",
    "apply",
    "attach",
    "connect",
    "create",
    "delete",
    "move",
    "place",
    "rename",
    "replace",
    "save",
    "set",
    "spawn",
    "update",
    "\u4fee\u6539",
    "\u6539\u540d",
    "\u91cd\u547d\u540d",
    "\u5220\u9664",
    "\u79fb\u52a8",
    "\u521b\u5efa",
    "\u65b0\u5efa",
    "\u6dfb\u52a0",
    "\u653e\u7f6e",
    "\u8fde\u63a5",
    "\u8bbe\u7f6e",
    "\u66ff\u6362",
    "\u4fdd\u5b58",
)

ACTIVE_CONTEXT_KEYWORDS = (
    "this",
    "that",
    "it",
    "selected",
    "current",
    "active",
    "opened",
    "\u8fd9\u4e2a",
    "\u90a3\u4e2a",
    "\u5b83",
    "\u5f53\u524d",
    "\u9009\u4e2d",
    "\u6253\u5f00\u7684",
    "\u521a\u624d\u90a3\u4e2a",
)

SMALLTALK_KEYWORDS = (
    "hello",
    "hi",
    "thanks",
    "thank you",
    "who are you",
    "good morning",
    "good night",
    "\u4f60\u597d",
    "\u8c22\u8c22",
    "\u4f60\u662f\u8c01",
    "\u65e9\u4e0a\u597d",
    "\u665a\u4e0a\u597d",
    "\u804a\u804a",
)

KNOWLEDGE_KEYWORDS = (
    "what is",
    "why",
    "how",
    "explain",
    "best practice",
    "lifecycle",
    "pattern",
    "risk",
    "\u4ec0\u4e48\u662f",
    "\u4e3a\u4ec0\u4e48",
    "\u600e\u4e48",
    "\u5982\u4f55",
    "\u89e3\u91ca",
    "\u539f\u7406",
    "\u6700\u4f73\u5b9e\u8df5",
    "\u98ce\u9669",
)

DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "asset": (
        "asset",
        "static mesh",
        "skeletal mesh",
        "nanite",
        "lod",
        "collision",
        "\u8d44\u4ea7",
        "\u9759\u6001\u7f51\u683c",
        "\u9aa8\u9abc\u7f51\u683c",
        "\u78b0\u649e",
    ),
    "blueprint": (
        "blueprint",
        "event graph",
        "beginplay",
        "node",
        "pin",
        "print string",
        "\u84dd\u56fe",
        "\u8282\u70b9",
        "\u5f15\u811a",
        "\u4e8b\u4ef6\u56fe",
    ),
    "widget": (
        "widget",
        "umg",
        "button",
        "canvas",
        "ui",
        "\u63a7\u4ef6",
        "\u6309\u94ae",
        "\u754c\u9762",
    ),
    "material": (
        "material",
        "roughness",
        "scalar",
        "vector",
        "texture",
        "\u6750\u8d28",
        "\u53c2\u6570",
        "\u7c97\u7cd9\u5ea6",
        "\u8d34\u56fe",
    ),
    "level_actor": (
        "actor",
        "level",
        "scene",
        "transform",
        "location",
        "rotation",
        "\u5173\u5361",
        "\u573a\u666f",
        "\u4f4d\u7f6e",
        "\u65cb\u8f6c",
    ),
    "code": (
        "code",
        "c++",
        "cpp",
        "header",
        "function",
        "compile",
        "\u4ee3\u7801",
        "\u7f16\u8bd1",
        "\u51fd\u6570",
    ),
    "log": (
        "log",
        "error",
        "warning",
        "crash",
        "\u65e5\u5fd7",
        "\u9519\u8bef",
        "\u8b66\u544a",
        "\u5d29\u6e83",
    ),
}


def analyze_route_keywords(text: str) -> dict[str, Any]:
    """Return a compact evidence report for Router v3.

    The report is intentionally advisory. It should help the LLM/reviewer
    catch risky overrides, but it must not become another hard-coded router.
    """

    raw = str(text or "")
    lowered = raw.lower()
    hard_write = _matches(raw, lowered, HARD_WRITE_KEYWORDS)
    active_context = _matches(raw, lowered, ACTIVE_CONTEXT_KEYWORDS)
    smalltalk = _matches(raw, lowered, SMALLTALK_KEYWORDS)
    knowledge = _matches(raw, lowered, KNOWLEDGE_KEYWORDS)
    domain_matches = {
        domain: matches
        for domain, keywords in DOMAIN_KEYWORDS.items()
        if (matches := _matches(raw, lowered, keywords))
    }
    domain_hint_count = sum(len(items) for items in domain_matches.values())
    task_signal_count = len(hard_write) + len(knowledge) + domain_hint_count
    pure_smalltalk = bool(smalltalk) and not hard_write and not active_context and task_signal_count == 0
    top_domain = _top_domain(domain_matches)
    return {
        "version": ROUTE_KEYWORD_VERIFIER_VERSION,
        "hard_write_signal": bool(hard_write),
        "active_context_reference": bool(active_context),
        "smalltalk_signal": bool(smalltalk),
        "pure_smalltalk_signal": pure_smalltalk,
        "knowledge_signal": bool(knowledge),
        "domain_hint_count": domain_hint_count,
        "task_signal_count": task_signal_count,
        "top_domain": top_domain,
        "matched": {
            "hard_write": hard_write,
            "active_context": active_context,
            "smalltalk": smalltalk,
            "knowledge": knowledge,
            "domain": domain_matches,
        },
    }


def target_kind_from_keyword_report(report: dict[str, Any]) -> str:
    domain = str(report.get("top_domain") or "")
    return {
        "asset": "selected_asset",
        "blueprint": "current_blueprint",
        "widget": "widget",
        "material": "selected_material_instance",
        "level_actor": "selected_actor",
        "code": "current_code_file",
        "log": "current_log",
    }.get(domain, "selected_context")


def _top_domain(domain_matches: dict[str, list[str]]) -> str:
    if not domain_matches:
        return ""
    return sorted(domain_matches.items(), key=lambda item: (-len(item[1]), item[0]))[0][0]


def _matches(raw: str, lowered: str, keywords: tuple[str, ...]) -> list[str]:
    matched: list[str] = []
    for keyword in keywords:
        if _keyword_present(raw, lowered, keyword) and keyword not in matched:
            matched.append(keyword)
    return matched


def _keyword_present(raw: str, lowered: str, keyword: str) -> bool:
    key = keyword.lower()
    if not key:
        return False
    if key.isascii():
        if " " in key or any(char in key for char in "+#"):
            return key in lowered
        return re.search(rf"(?<![A-Za-z0-9_]){re.escape(key)}(?![A-Za-z0-9_])", lowered) is not None
    return keyword in raw


__all__ = [
    "ROUTE_KEYWORD_VERIFIER_VERSION",
    "analyze_route_keywords",
    "target_kind_from_keyword_report",
]
