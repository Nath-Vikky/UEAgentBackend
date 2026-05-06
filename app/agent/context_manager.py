from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.agent.active_context import build_active_context
from app.agent.context_builder import build_context_summary
from app.agent.memory_manager import recall_long_term_memory
from app.db.models.session import MessageModel, SessionModel
from app.db.repositories.sessions import list_session_tasks
from app.schemas.requests import UnifiedTaskRequest

CHAT_HISTORY_TASK_TYPES = {"agent_chat", "project_qa"}
DEFAULT_CHAR_BUDGET = 6000
DEFAULT_RECENT_MESSAGES = 8
DEFAULT_TOOL_TASKS = 3


def _clip(value: str, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 3, 0)]}..."


def _latest_user_message(request: UnifiedTaskRequest) -> str:
    for item in reversed(request.session.messages):
        if item.role == "user" and item.content.strip():
            return item.content.strip()
    return str(request.payload.get("user_query") or "").strip()


def _message_signature(item: dict[str, Any]) -> tuple[str, str]:
    return (str(item.get("role") or ""), str(item.get("content") or ""))


def _request_messages(request: UnifiedTaskRequest) -> list[dict[str, Any]]:
    return [
        {
            "role": item.role,
            "content": item.content,
            "language": item.language,
            "source": "request",
        }
        for item in request.session.messages
        if item.content.strip()
    ]


def _stored_messages(db: Session, session_id: str, limit: int) -> list[dict[str, Any]]:
    statement = (
        select(MessageModel)
        .where(MessageModel.session_id == session_id)
        .order_by(desc(MessageModel.created_at), desc(MessageModel.message_id))
        .limit(limit)
    )
    latest_messages = list(reversed(list(db.scalars(statement))))
    return [
        {
            "role": item.role,
            "content": item.content,
            "language": item.language or "auto",
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "source": "session_history",
        }
        for item in latest_messages
        if item.content.strip()
    ]


def _merge_recent_messages(
    *,
    stored: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    limit: int,
    per_message_chars: int,
) -> list[dict[str, Any]]:
    merged = [*stored, *incoming]
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in reversed(merged):
        signature = _message_signature(item)
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(item)
    deduped.reverse()
    recent = deduped[-limit:]
    return [
        {
            **item,
            "content": _clip(str(item.get("content") or ""), per_message_chars),
        }
        for item in recent
    ]


def _tool_context(db: Session, session_id: str, limit: int) -> list[dict[str, Any]]:
    items = []
    for task in list_session_tasks(db, session_id, limit=20):
        if task.task_type in CHAT_HISTORY_TASK_TYPES:
            continue
        user_view = dict(task.user_view_json or {})
        data = dict(task.data_json or {})
        items.append(
            {
                "task_id": task.task_id,
                "run_id": task.run_id,
                "task_type": task.task_type,
                "status": task.status,
                "finish_reason": task.finish_reason,
                "title": user_view.get("title"),
                "status_hint": user_view.get("status_hint"),
                "summary": _clip(
                    str(user_view.get("text") or task.assistant_message or data.get("summary") or ""),
                    360,
                ),
                "created_at": task.created_at.isoformat() if task.created_at else None,
            }
        )
        if len(items) >= limit:
            break
    return items


def _session_summary(db: Session, session_id: str) -> dict[str, Any]:
    session_model = db.get(SessionModel, session_id)
    metadata = dict(session_model.metadata_json or {}) if session_model else {}
    summary = metadata.get("memory_summary") or metadata.get("session_summary")
    if isinstance(summary, dict):
        summary_text = str(summary.get("summary_text") or summary.get("text") or "").strip()
        return {
            **summary,
            "status": "available" if summary_text else str(summary.get("status") or "not_available"),
            "summary_text": _clip(summary_text, 900),
            "source": summary.get("source") or "session_metadata",
        }
    return {
        "status": "available" if summary else "not_available",
        "summary_text": _clip(str(summary or ""), 900),
        "source": "session_metadata" if summary else "not_configured",
    }


def _estimate_chars(bundle: dict[str, Any]) -> int:
    total = 0
    for section in ("recent_messages", "tool_context"):
        for item in bundle.get(section, []):
            total += len(str(item.get("content") or item.get("summary") or ""))
    total += len(str(bundle.get("session_summary", {}).get("summary_text") or ""))
    for item in bundle.get("long_term_memory", {}).get("items", []):
        total += len(str(item.get("text") or ""))
    total += len(str(bundle.get("active_context") or ""))
    total += len(str(bundle.get("editor_context") or ""))
    return total


def build_context_bundle(
    *,
    db: Session,
    request: UnifiedTaskRequest,
    routing: dict[str, Any],
    actual_task_type: str | None = None,
    char_budget: int = DEFAULT_CHAR_BUDGET,
    recent_message_limit: int = DEFAULT_RECENT_MESSAGES,
    tool_task_limit: int = DEFAULT_TOOL_TASKS,
) -> dict[str, Any]:
    session_id = request.session.session_id
    stored = _stored_messages(db, session_id, limit=recent_message_limit * 2)
    incoming = _request_messages(request)
    recent_messages = _merge_recent_messages(
        stored=stored,
        incoming=incoming,
        limit=recent_message_limit,
        per_message_chars=700,
    )
    latest_user_message = _latest_user_message(request)
    long_term_memory = recall_long_term_memory(
        db,
        project_name=request.context.project_name,
        query=latest_user_message,
        limit=5,
    )
    bundle = {
        "version": "context_bundle_v1",
        "input_summary": {
            "session_id": session_id,
            "requested_task_type": request.task_type,
            "actual_task_type": actual_task_type,
            "route_type": routing.get("intent", {}).get("route_type"),
            "selected_tool_id": routing.get("route", {}).get("selected_tool_id"),
            "latest_user_message": _clip(latest_user_message, 700),
        },
        "active_context": build_active_context(request=request, routing=routing),
        "editor_context": build_context_summary(request),
        "language_context": dict(routing.get("locale") or {}),
        "recent_messages": recent_messages,
        "session_summary": _session_summary(db, session_id),
        "long_term_memory": long_term_memory,
        "project_inventory_context": {
            "status": "pending_execution",
            "note": "Project Inventory query results are attached after tool execution when selected.",
        },
        "retrieval_context": {
            "status": "pending_execution",
            "note": "RAG retrieval chunks are attached after retrieval when selected.",
        },
        "tool_context": _tool_context(db, session_id, limit=tool_task_limit),
        "source_policy": {
            "chat_history": "Only agent_chat/project_qa messages are persisted to chat history.",
            "tool_tasks": "Tool tasks are summarized separately and do not pollute chat history.",
            "raw_payload": "Raw request remains in Debug View; Context Bundle keeps compact excerpts only.",
        },
    }
    estimated_chars = _estimate_chars(bundle)
    bundle["budget"] = {
        "char_budget": char_budget,
        "estimated_chars": estimated_chars,
        "within_budget": estimated_chars <= char_budget,
        "recent_message_limit": recent_message_limit,
        "tool_task_limit": tool_task_limit,
        "truncation_policy": "Keep latest messages, long-term memory snippets, and compact excerpts.",
    }
    if estimated_chars > char_budget:
        bundle["budget"]["warnings"] = ["context_bundle_over_budget_compact_excerpts_used"]
    else:
        bundle["budget"]["warnings"] = []
    return bundle


def context_bundle_prompt_excerpt(context_bundle: dict[str, Any]) -> str:
    lines = ["Context Bundle v1:"]
    editor_context = context_bundle.get("editor_context") or {}
    if editor_context:
        lines.append(f"- Editor context: {editor_context}")
    active_context = context_bundle.get("active_context") or {}
    if active_context:
        lines.append(
            "- Active context: "
            f"project={active_context.get('project')}, "
            f"asset={active_context.get('asset')}, "
            f"code={active_context.get('code')}, "
            f"log={active_context.get('log')}"
        )
    inventory_context = context_bundle.get("project_inventory_context") or {}
    if inventory_context.get("has_snapshot"):
        summary = inventory_context.get("summary") or {}
        lines.append(
            "- Project inventory: "
            f"snapshot={inventory_context.get('snapshot_id')}, "
            f"assets={summary.get('asset_count', 0)}, "
            f"code_files={summary.get('code_file_count', 0)}, "
            f"selected_assets={inventory_context.get('selected_assets') or []}, "
            f"current_file={inventory_context.get('current_file')}"
        )
    session_summary = context_bundle.get("session_summary") or {}
    if session_summary.get("status") == "available":
        lines.append(f"- Session summary: {session_summary.get('summary_text')}")
    recent_messages = context_bundle.get("recent_messages") or []
    if recent_messages:
        lines.append("- Recent messages:")
        for item in recent_messages[-6:]:
            lines.append(f"  - {item.get('role')}: {item.get('content')}")
    tool_context = context_bundle.get("tool_context") or []
    if tool_context:
        lines.append("- Recent tool task summaries:")
        for item in tool_context:
            lines.append(f"  - {item.get('task_type')}[{item.get('status')}]: {item.get('summary')}")
    long_term_memory = context_bundle.get("long_term_memory") or {}
    if long_term_memory.get("items"):
        lines.append("- Long-term project memory:")
        for item in long_term_memory.get("items", [])[:5]:
            lines.append(
                f"  - {item.get('category')}[{item.get('score', 0)}]: {item.get('text')}"
            )
    return "\n".join(lines)
