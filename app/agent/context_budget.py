from __future__ import annotations

from typing import Any

from app.utils.json_tools import dumps_pretty


CONTEXT_BUDGET_VERSION = "context_budget_v1"


def _as_text(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, dict | list):
        return dumps_pretty(value)
    return str(value)


def _chars(value: Any) -> int:
    return len(_as_text(value))


def _section_char_counts(context_bundle: dict[str, Any]) -> dict[str, int]:
    recent_messages = sum(_chars(item.get("content")) for item in context_bundle.get("recent_messages", []))
    tool_context = sum(_chars(item.get("summary") or item) for item in context_bundle.get("tool_context", []))
    memory = _chars(context_bundle.get("session_summary"))
    memory += _chars(context_bundle.get("active_target_memory"))
    memory += _chars(context_bundle.get("long_term_memory"))
    memory += _chars(context_bundle.get("file_memory"))
    memory += _chars(context_bundle.get("web_memory"))
    memory += _chars(context_bundle.get("memory"))
    return {
        "recent_messages": recent_messages,
        "active_ue_context": _chars(context_bundle.get("active_context")),
        "project_inventory": _chars(context_bundle.get("project_inventory_context")),
        "retrieval_context": _chars(context_bundle.get("retrieval_context")),
        "memory": memory,
        "tool_results": tool_context,
        "editor_operations": _chars(context_bundle.get("recent_editor_operations")),
        "system_policy": _chars(context_bundle.get("source_policy")),
    }


def build_context_budget_report(
    context_bundle: dict[str, Any],
    *,
    char_budget: int | None = None,
) -> dict[str, Any]:
    """Build an explainable per-source context budget report.

    This complements the existing coarse `context_bundle["budget"]` block. It is
    intentionally deterministic so CI, eval, and Debug View can all rely on it.
    """

    existing_budget = dict(context_bundle.get("budget") or {})
    budget = int(char_budget or existing_budget.get("char_budget") or 0)
    counts = _section_char_counts(context_bundle)
    total = sum(counts.values())
    if not budget:
        budget = total or 1
    percentages = {
        key: round((value / max(total, 1)) * 100.0, 2)
        for key, value in counts.items()
    }
    top_sources = [
        {"source": key, "chars": value, "percentage": percentages[key]}
        for key, value in sorted(counts.items(), key=lambda item: item[1], reverse=True)
        if value > 0
    ][:5]
    warnings = list(existing_budget.get("warnings") or [])
    if total > budget and "context_budget_exceeded" not in warnings:
        warnings.append("context_budget_exceeded")
    if counts["tool_results"] > budget * 0.25 and "tool_results_context_heavy" not in warnings:
        warnings.append("tool_results_context_heavy")
    if counts["recent_messages"] > budget * 0.35 and "recent_messages_context_heavy" not in warnings:
        warnings.append("recent_messages_context_heavy")
    return {
        "version": CONTEXT_BUDGET_VERSION,
        "char_budget": budget,
        "estimated_chars": total,
        "within_budget": total <= budget,
        "section_char_counts": counts,
        "section_percentages": percentages,
        "top_sources": top_sources,
        "warnings": warnings,
        "policy": {
            "raw_tool_results": "summarize_before_prompt_injection",
            "project_inventory": "inject_summary_first_then_focused_details",
            "rag": "inject_top_k_evidence_only_when_selected",
            "history": "keep_recent_messages_and_compact_older_turns",
        },
    }


__all__ = ["CONTEXT_BUDGET_VERSION", "build_context_budget_report"]
