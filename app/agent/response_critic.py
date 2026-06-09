from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


INTERNAL_TOOLING_MARKERS = (
    "mcp_get_",
    "MCP/TCP",
    "MCP TCP",
    "MCP provider",
    "ToolSpec",
    "JSON-RPC",
    "raw payload",
    "raw JSON",
    "tool_id",
    "tool_name",
    "selected_asset_count=",
    "local Project Inventory read-only tool",
    "Project Inventory read-only tool",
    "read-only tool",
    "本地 Project Inventory 只读工具",
    "Project Inventory 只读工具",
    "只读工具",
)

INTERNAL_DATA_KEYS = {
    "arguments",
    "input_schema",
    "local_tool",
    "mcp_tool",
    "raw_payload",
    "raw_result",
    "result",
    "schema",
    "tool_id",
    "tool_name",
    "transport",
}


def apply_response_critic(
    execution: dict[str, Any],
    *,
    output_language: str,
) -> dict[str, Any]:
    """Keep User View human-readable while preserving raw diagnostics in Debug View."""

    updated = dict(execution)
    user_view = deepcopy(dict(updated.get("user_view") or {}))
    assistant_message = str(updated.get("assistant_message") or user_view.get("text") or "")
    original_visible = _visible_text(user_view, assistant_message)

    sanitized_message = sanitize_user_visible_text(assistant_message, output_language=output_language)
    sanitized_user_view = sanitize_user_view(user_view, output_language=output_language)
    if sanitized_message and sanitized_user_view.get("text") != sanitized_message:
        sanitized_user_view["text"] = sanitized_message

    sanitized_visible = _visible_text(sanitized_user_view, sanitized_message)
    report = build_response_critic_report(
        original_visible=original_visible,
        sanitized_visible=sanitized_visible,
        output_language=output_language,
    )

    updated["assistant_message"] = sanitized_message
    updated["user_view"] = sanitized_user_view
    data = dict(updated.get("data") or {})
    data["response_critic"] = report
    if "answer" in data:
        data["answer"] = sanitized_message
    updated["data"] = data
    debug_view = dict(updated.get("debug_view") or {})
    debug_view["response_critic"] = report
    updated["debug_view"] = debug_view
    return updated


def build_response_critic_report(
    *,
    original_visible: str,
    sanitized_visible: str,
    output_language: str,
) -> dict[str, Any]:
    leaked_markers = _leaked_markers(original_visible)
    remaining_markers = _leaked_markers(sanitized_visible)
    answer_ok = bool(sanitized_visible.strip())
    return {
        "version": "response_critic_v1",
        "answer_ok": answer_ok,
        "leaked_internal_tooling": bool(leaked_markers),
        "remaining_internal_tooling": bool(remaining_markers),
        "leaked_markers": leaked_markers,
        "remaining_markers": remaining_markers,
        "repair_applied": bool(leaked_markers) or original_visible != sanitized_visible,
        "repair_instruction": (
            _localized(
                output_language,
                "User View 已转换为自然语言展示，内部工具细节保留在 Debug View。",
                "User View was converted to a natural-language answer; internal tool details remain in Debug View.",
            )
            if leaked_markers or original_visible != sanitized_visible
            else ""
        ),
    }


def sanitize_user_view(user_view: dict[str, Any], *, output_language: str) -> dict[str, Any]:
    sanitized = dict(user_view)
    sanitized["title"] = sanitize_user_visible_text(
        str(sanitized.get("title") or ""),
        output_language=output_language,
    )
    sanitized["text"] = sanitize_user_visible_text(
        str(sanitized.get("text") or ""),
        output_language=output_language,
    )
    blocks: list[dict[str, Any]] = []
    for block in list(sanitized.get("blocks") or []):
        if not isinstance(block, dict):
            continue
        clean_block = dict(block)
        clean_block["title"] = sanitize_user_visible_text(
            str(clean_block.get("title") or ""),
            output_language=output_language,
        )
        clean_block["text"] = sanitize_user_visible_text(
            str(clean_block.get("text") or ""),
            output_language=output_language,
        )
        if isinstance(clean_block.get("data"), dict):
            clean_block["data"] = _sanitize_user_view_data(clean_block["data"])
        blocks.append(clean_block)
    sanitized["blocks"] = blocks
    return sanitized


def sanitize_user_visible_text(text: str, *, output_language: str) -> str:
    clean = str(text or "")
    if not clean.strip():
        return clean
    clean = _replace_count_assignments(clean, output_language=output_language)
    replacements = _zh_replacements() if output_language.startswith("zh") else _en_replacements()
    for pattern, replacement in replacements:
        clean = re.sub(pattern, replacement, clean, flags=re.IGNORECASE)
    clean = _drop_internal_lines(clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return clean


def _sanitize_user_view_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize_user_view_data(item)
            for key, item in value.items()
            if str(key) not in INTERNAL_DATA_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_user_view_data(item) for item in value]
    return value


def _replace_count_assignments(text: str, *, output_language: str) -> str:
    label = "选中资产数量：" if output_language.startswith("zh") else "Selected asset count: "
    return re.sub(r"\bselected_asset_count\s*=\s*(\d+)\b", rf"{label}\1", text)


def _drop_internal_lines(text: str) -> str:
    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            kept.append(line)
            continue
        if stripped.lower().startswith(("tool_id:", "tool_name:", "arguments:", "transport:")):
            continue
        if stripped.startswith(('"tool_id"', '"tool_name"', '"arguments"', '"transport"')):
            continue
        kept.append(line)
    return "\n".join(kept)


def _zh_replacements() -> list[tuple[str, str]]:
    return [
        (r"当前请求上下文中已有选中资产；MCP/TCP 未启用或不可用时，后端使用该上下文作为兜底。", "我已读取当前选中的资产上下文。"),
        (r"已通过\s*本地 Project Inventory 只读工具读取", "已从当前项目快照读取"),
        (r"已通过\s*Project Inventory 只读工具读取", "已从当前项目快照读取"),
        (r"已通过\s*UEAgentTool TCP 只读工具读取", "已从当前编辑器读取"),
        (r"已通过\s*[^。\n]*只读工具读取", "已读取"),
        (r"本地 Project Inventory 只读工具", "当前项目快照"),
        (r"Project Inventory 只读工具", "当前项目快照"),
        (r"UEAgentTool TCP 只读工具", "当前编辑器"),
        (r"只读工具", "上下文读取"),
        (r"MCP/TCP", "编辑器实时连接"),
        (r"\bMCP TCP\b", "编辑器实时连接"),
        (r"\bmcp_get_[A-Za-z0-9_]+\b", "编辑器上下文读取"),
        (r"\bToolSpec\b", "工具定义"),
        (r"\bJSON-RPC\b", "内部通信"),
        (r"raw payload|raw JSON", "原始调试数据"),
    ]


def _en_replacements() -> list[tuple[str, str]]:
    return [
        (
            r"Selected assets are already available in request context; the backend used that context as fallback because MCP/TCP is disabled or unavailable\.",
            "I read the currently selected asset context.",
        ),
        (r"Read (.*?) through local Project Inventory read-only tool", r"Read \1 from the current project snapshot"),
        (r"Read (.*?) through Project Inventory read-only tool", r"Read \1 from the current project snapshot"),
        (r"Read (.*?) through UEAgentTool TCP read-only tool", r"Read \1 from the current editor"),
        (r"local Project Inventory read-only tool", "current project snapshot"),
        (r"Project Inventory read-only tool", "current project snapshot"),
        (r"UEAgentTool TCP read-only tool", "current editor"),
        (r"read-only tool", "context reader"),
        (r"MCP/TCP", "live editor connection"),
        (r"\bMCP TCP\b", "live editor connection"),
        (r"\bmcp_get_[A-Za-z0-9_]+\b", "editor context reader"),
        (r"\bToolSpec\b", "tool definition"),
        (r"\bJSON-RPC\b", "internal transport"),
        (r"raw payload|raw JSON", "raw debug data"),
    ]


def _visible_text(user_view: dict[str, Any], assistant_message: str) -> str:
    pieces = [
        str(user_view.get("title") or ""),
        str(user_view.get("text") or ""),
        assistant_message,
    ]
    for block in list(user_view.get("blocks") or []):
        if isinstance(block, dict):
            pieces.append(str(block.get("title") or ""))
            pieces.append(str(block.get("text") or ""))
    return "\n".join(piece for piece in pieces if piece)


def _leaked_markers(text: str) -> list[str]:
    lower = str(text or "").lower()
    leaked: list[str] = []
    for marker in INTERNAL_TOOLING_MARKERS:
        if marker.lower() in lower and marker not in leaked:
            leaked.append(marker)
    return leaked


def _localized(language: str, zh_text: str, en_text: str) -> str:
    return zh_text if language.startswith("zh") else en_text
