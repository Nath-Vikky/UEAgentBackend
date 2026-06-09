from __future__ import annotations

from typing import Any


TOOL_USE_SUMMARY_VERSION = "tool_use_summary_v1"


def _count_items(value: Any) -> int | None:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        for key in ("items", "retrieved_docs", "citations", "errors", "warnings"):
            if isinstance(value.get(key), list):
                return len(value[key])
    return None


def _safe_keys(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    blocked = {
        "raw",
        "raw_payload",
        "structuredContent",
        "content",
        "result",
        "debug",
        "debug_view",
        "normalized_request",
    }
    return sorted(key for key in value.keys() if key not in blocked)[:12]


def _compact_text(value: Any, *, limit: int = 180) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 3, 0)]}..."


def summarize_tool_use(
    *,
    tool_id: str,
    result: dict[str, Any] | None = None,
    status: str | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    result = dict(result or {})
    resolved_status = status or str(result.get("status") or "completed")
    output = result.get("output") if isinstance(result.get("output"), dict) else result
    item_count = _count_items(output)
    warning_count = len(output.get("warnings") or []) if isinstance(output, dict) else 0
    error_count = len(output.get("errors") or []) if isinstance(output, dict) else 0
    user_summary = summary or result.get("summary") or output.get("answer") if isinstance(output, dict) else ""
    if not user_summary:
        if item_count is not None:
            user_summary = f"{tool_id} returned {item_count} item(s)."
        else:
            user_summary = f"{tool_id} completed with status {resolved_status}."
    return {
        "version": TOOL_USE_SUMMARY_VERSION,
        "tool_id": tool_id,
        "status": resolved_status,
        "user_summary": _compact_text(user_summary),
        "item_count": item_count,
        "warning_count": warning_count,
        "error_count": error_count,
        "safe_output_keys": _safe_keys(output),
        "raw_payload_hidden": True,
    }


def summarize_tool_uses(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        summaries.append(
            summarize_tool_use(
                tool_id=str(item.get("tool_id") or "unknown_tool"),
                result=item,
                status=str(item.get("status") or ""),
                summary=str(item.get("summary") or ""),
            )
        )
    return summaries


__all__ = ["TOOL_USE_SUMMARY_VERSION", "summarize_tool_use", "summarize_tool_uses"]
