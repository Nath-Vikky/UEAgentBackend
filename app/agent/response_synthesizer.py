from __future__ import annotations

from copy import deepcopy
from typing import Any


def synthesize_execution_response(
    execution: dict[str, Any],
    *,
    output_language: str,
    route_type: str,
    selected_tool_id: str | None = None,
) -> dict[str, Any]:
    """Normalize user-facing response fields before critic/composer projection.

    Handlers still own domain-specific wording. This layer only makes the
    contract explicit: User View must have a title/text/blocks shape, and
    assistant_message must mirror human-readable text rather than raw tool
    payloads.
    """

    updated = dict(execution)
    user_view = deepcopy(dict(updated.get("user_view") or {}))
    data = dict(updated.get("data") or {})
    debug_view = dict(updated.get("debug_view") or {})

    title_source = "handler"
    text_source = "handler"
    assistant_source = "handler"

    if not str(user_view.get("title") or "").strip():
        user_view["title"] = _default_title(route_type=route_type, output_language=output_language)
        title_source = "default_title"

    if not isinstance(user_view.get("blocks"), list):
        user_view["blocks"] = []

    assistant_message = str(updated.get("assistant_message") or "").strip()
    text = str(user_view.get("text") or "").strip()
    if not text:
        text, text_source = _fallback_text(
            assistant_message=assistant_message,
            data=data,
            blocks=user_view.get("blocks") or [],
            output_language=output_language,
        )
        user_view["text"] = text

    if not assistant_message:
        assistant_message = str(user_view.get("text") or "").strip()
        assistant_source = "user_view_text"
    if not assistant_message:
        assistant_message = _default_empty_answer(output_language)
        assistant_source = "default_empty_answer"
        if not str(user_view.get("text") or "").strip():
            user_view["text"] = assistant_message
            text_source = "default_empty_answer"

    report = {
        "version": "response_synthesizer_v1",
        "route_type": route_type,
        "selected_tool_id": selected_tool_id,
        "title_source": title_source,
        "text_source": text_source,
        "assistant_message_source": assistant_source,
        "block_count": len(user_view.get("blocks") or []),
        "user_view_ready": bool(str(user_view.get("title") or "").strip() and str(user_view.get("text") or "").strip()),
    }

    updated["user_view"] = user_view
    updated["assistant_message"] = assistant_message
    data["response_synthesizer"] = report
    debug_view["response_synthesizer"] = report
    updated["data"] = data
    updated["debug_view"] = debug_view
    return updated


def _fallback_text(
    *,
    assistant_message: str,
    data: dict[str, Any],
    blocks: list[Any],
    output_language: str,
) -> tuple[str, str]:
    if assistant_message:
        return assistant_message, "assistant_message"
    for key in ("answer", "summary", "message", "analysis"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip(), f"data.{key}"
    for block in blocks:
        if not isinstance(block, dict):
            continue
        for key in ("text", "summary", "content"):
            value = block.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip(), f"block.{key}"
    return _default_empty_answer(output_language), "default_empty_answer"


def _default_title(*, route_type: str, output_language: str) -> str:
    if output_language.startswith("zh"):
        if route_type == "single_tool":
            return "工具结果"
        if route_type == "project_qa":
            return "项目问答"
        if route_type == "direct_answer":
            return "回答"
        if route_type == "proposal_wait":
            return "待确认提案"
        return "任务结果"
    if route_type == "single_tool":
        return "Tool Result"
    if route_type == "project_qa":
        return "Project Answer"
    if route_type == "direct_answer":
        return "Answer"
    if route_type == "proposal_wait":
        return "Proposal Pending"
    return "Task Result"


def _default_empty_answer(output_language: str) -> str:
    if output_language.startswith("zh"):
        return "我还没有拿到足够的可展示结果。请查看调试信息，或补充上下文后再试。"
    return "I do not have enough displayable result content yet. Please check diagnostics or provide more context."
