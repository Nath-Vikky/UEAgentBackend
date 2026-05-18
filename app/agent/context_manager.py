from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.agent.active_context import build_active_context
from app.agent.context_builder import build_context_summary
from app.agent.memory_providers import (
    MemoryProviderResult,
    MemoryQuery,
    SessionLongTermMemoryProvider,
    WebMemoryProvider,
)
from app.core.settings import Settings
from app.db.models.session import MessageModel, SessionModel
from app.db.repositories.sessions import list_session_tasks
from app.schemas.requests import UnifiedTaskRequest

CHAT_HISTORY_TASK_TYPES = {"agent_chat", "project_qa"}
DEFAULT_CHAR_BUDGET = 6000
DEFAULT_RECENT_MESSAGES = 8
DEFAULT_TOOL_TASKS = 3
DEFAULT_WEB_MEMORY_ITEMS = 3
DEFAULT_EDITOR_OPERATION_TASKS = 3


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


def _proposal_preview_by_id(task: Any) -> dict[str, dict[str, Any]]:
    previews: dict[str, dict[str, Any]] = {}
    for proposal in list(task.action_proposals_json or []):
        if not isinstance(proposal, dict):
            continue
        proposal_id = str(proposal.get("proposal_id") or "")
        preview = proposal.get("dry_run_preview")
        if proposal_id and isinstance(preview, dict):
            previews[proposal_id] = dict(preview)
    return previews


def _compact_operation_target(
    *,
    operation_type: str,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    target: dict[str, Any] = {}
    for key in (
        "asset_path",
        "final_asset_path",
        "blueprint_path",
        "material_instance_path",
        "actor_class",
        "actor_reference",
        "actor_label",
        "actor_name",
        "parameter_name",
        "parameter_type",
        "transform_mode",
    ):
        value = result.get(key)
        if value in (None, "", [], {}):
            value = payload.get(key)
        if value not in (None, "", [], {}):
            target[key] = value
    if operation_type == "place_actor_in_level" and "actor_class" not in target:
        actor_class = payload.get("actor_class") or result.get("actor_class")
        if actor_class:
            target["actor_class"] = actor_class
    if operation_type == "set_material_instance_parameter" and "material_instance_path" not in target:
        material_path = payload.get("material_instance_path") or result.get("material_instance_path")
        if material_path:
            target["material_instance_path"] = material_path
    if operation_type in {"place_actor_in_level", "set_actor_transform"}:
        actor_reference = (
            target.get("actor_reference")
            or target.get("actor_label")
            or target.get("actor_name")
            or result.get("actor_label")
            or result.get("actor_name")
            or payload.get("actor_reference")
            or payload.get("actor_label")
        )
        if actor_reference:
            target["actor_reference"] = actor_reference
    return target


def _recent_editor_operations(db: Session, session_id: str, limit: int) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for task in list_session_tasks(db, session_id, limit=30):
        previews = _proposal_preview_by_id(task)
        data = dict(task.data_json or {})
        operation_results = list(data.get("editor_operation_results") or [])
        for operation_result in reversed(operation_results):
            if not isinstance(operation_result, dict):
                continue
            proposal_id = str(operation_result.get("proposal_id") or "")
            preview = previews.get(proposal_id, {})
            payload = dict(preview.get("operation_payload") or {})
            result = dict(operation_result.get("result") or {})
            operation_type = str(operation_result.get("operation_type") or preview.get("operation_type") or "")
            item = {
                "task_id": task.task_id,
                "run_id": task.run_id,
                "proposal_id": proposal_id or None,
                "operation_type": operation_type,
                "tool_id": operation_result.get("tool_id") or preview.get("tool_id"),
                "execution_state": operation_result.get("execution_state"),
                "success": bool(operation_result.get("success")),
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "received_at": operation_result.get("received_at"),
                "target": _compact_operation_target(
                    operation_type=operation_type,
                    payload=payload,
                    result=result,
                ),
                "operation_payload": payload,
                "result": result,
                "undo_hint": operation_result.get("undo_hint"),
            }
            items.append(item)
            if len(items) >= limit:
                break
        if len(items) >= limit:
            break
    last_successful = next((item for item in items if item.get("success")), None)
    return {
        "version": "recent_editor_operations_v1",
        "status": "available" if items else "not_available",
        "items": items,
        "last_successful": last_successful,
        "count": len(items),
        "policy": "Only confirmed UE plugin execution results are reused as active editor context.",
    }


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


def _domain_hints(request: UnifiedTaskRequest) -> list[str]:
    raw_hints = [
        *list(request.context.kb_domains_hint or []),
        *list(request.payload.get("domain_filters") or []),
        *list(request.payload.get("domain_hints") or []),
    ]
    hints: list[str] = []
    seen: set[str] = set()
    for item in raw_hints:
        text = str(item or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        hints.append(text)
    return hints


def _provider_source(result: MemoryProviderResult) -> dict[str, Any]:
    return {
        "provider_id": result.provider_id,
        "status": result.status,
        "item_count": len(result.items),
        "summary": result.summary,
    }


def _memory_item(provider_id: str, item: dict[str, Any]) -> dict[str, Any]:
    if provider_id == "web_memory":
        return {
            "provider_id": provider_id,
            "entry_id": item.get("entry_id"),
            "title": item.get("title"),
            "url": item.get("url"),
            "domain": item.get("domain"),
            "source_type": item.get("source_type"),
            "provider": item.get("provider"),
            "score": item.get("score"),
            "ranking": item.get("ranking"),
            "text": _clip(str(item.get("snippet") or ""), 520),
            "retrieval_source": "web_memory",
        }
    return {
        "provider_id": provider_id,
        "memory_id": item.get("memory_id"),
        "category": item.get("category"),
        "score": item.get("score"),
        "project_name": item.get("project_name"),
        "text": _clip(str(item.get("text") or ""), 520),
        "retrieval_source": provider_id,
    }


def _build_memory_context(
    *,
    query: str,
    long_term_result: MemoryProviderResult,
    web_memory_result: MemoryProviderResult | None,
) -> dict[str, Any]:
    providers = [long_term_result]
    if web_memory_result is not None:
        providers.append(web_memory_result)
    items: list[dict[str, Any]] = []
    for result in providers:
        for item in result.items:
            items.append(_memory_item(result.provider_id, item))
    return {
        "version": "memory_context_v1",
        "query": _clip(query, 240),
        "sources": [_provider_source(result) for result in providers],
        "items": items,
        "policy": {
            "session_long_term_memory": "Project/session-scoped compact memory from chat history.",
            "web_memory": "Cached web-search summaries only; never treated as formal KB and never writes to knowledge/.",
            "dedupe": "Providers remain separate so local project memory is not mixed with cached web evidence.",
        },
    }


def _estimate_chars(bundle: dict[str, Any]) -> int:
    total = 0
    for section in ("recent_messages", "tool_context"):
        for item in bundle.get(section, []):
            total += len(str(item.get("content") or item.get("summary") or ""))
    total += len(str(bundle.get("session_summary", {}).get("summary_text") or ""))
    for item in bundle.get("long_term_memory", {}).get("items", []):
        total += len(str(item.get("text") or ""))
    for item in bundle.get("memory", {}).get("items", []):
        if item.get("provider_id") == "web_memory":
            total += len(str(item.get("text") or ""))
    total += len(str(bundle.get("active_context") or ""))
    total += len(str(bundle.get("editor_context") or ""))
    total += len(str(bundle.get("recent_editor_operations") or ""))
    return total


def build_context_bundle(
    *,
    db: Session,
    request: UnifiedTaskRequest,
    routing: dict[str, Any],
    settings: Settings | None = None,
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
    long_term_memory_result = SessionLongTermMemoryProvider(db).recall(
        MemoryQuery(
            project_name=request.context.project_name,
            query=latest_user_message,
            limit=5,
        )
    )
    web_memory_result: MemoryProviderResult | None = None
    if settings is not None:
        web_memory_result = WebMemoryProvider(db, settings).recall(
            MemoryQuery(
                project_name=request.context.project_name,
                query=latest_user_message,
                limit=DEFAULT_WEB_MEMORY_ITEMS,
                domain_hints=_domain_hints(request),
            )
        )
    memory_context = _build_memory_context(
        query=latest_user_message,
        long_term_result=long_term_memory_result,
        web_memory_result=web_memory_result,
    )
    editor_operations_context = _recent_editor_operations(
        db,
        session_id,
        limit=DEFAULT_EDITOR_OPERATION_TASKS,
    )
    active_context = build_active_context(request=request, routing=routing)
    active_context["editor_operation"] = {
        "status": editor_operations_context["status"],
        "last_successful": editor_operations_context["last_successful"],
        "recent_count": editor_operations_context["count"],
    }
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
        "active_context": active_context,
        "editor_context": build_context_summary(request),
        "language_context": dict(routing.get("locale") or {}),
        "recent_messages": recent_messages,
        "session_summary": _session_summary(db, session_id),
        "long_term_memory": long_term_memory_result.raw,
        "web_memory": web_memory_result.raw
        if web_memory_result
        else {
            "status": "skipped",
            "reason": "settings_not_provided",
            "items": [],
            "summary": {"writes_to_kb": False},
        },
        "memory": memory_context,
        "project_inventory_context": {
            "status": "pending_execution",
            "note": "Project Inventory query results are attached after tool execution when selected.",
        },
        "retrieval_context": {
            "status": "pending_execution",
            "note": "RAG retrieval chunks are attached after retrieval when selected.",
        },
        "tool_context": _tool_context(db, session_id, limit=tool_task_limit),
        "recent_editor_operations": editor_operations_context["items"],
        "source_policy": {
            "chat_history": "Only agent_chat/project_qa messages are persisted to chat history.",
            "tool_tasks": "Tool tasks are summarized separately and do not pollute chat history.",
            "raw_payload": "Raw request remains in Debug View; Context Bundle keeps compact excerpts only.",
            "editor_operations": editor_operations_context["policy"],
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
    editor_operations = context_bundle.get("recent_editor_operations") or []
    if editor_operations:
        lines.append("- Recent confirmed editor operations:")
        for item in editor_operations[:3]:
            lines.append(
                "  - "
                f"{item.get('operation_type')}[{item.get('execution_state')}]: "
                f"target={item.get('target')}"
            )
    long_term_memory = context_bundle.get("long_term_memory") or {}
    if long_term_memory.get("items"):
        lines.append("- Long-term project memory:")
        for item in long_term_memory.get("items", [])[:5]:
            lines.append(
                f"  - {item.get('category')}[{item.get('score', 0)}]: {item.get('text')}"
            )
    web_memory = context_bundle.get("web_memory") or {}
    if web_memory.get("items"):
        lines.append("- Web memory (cached web evidence, not formal KB):")
        for item in web_memory.get("items", [])[:3]:
            title = item.get("title") or item.get("url") or "web memory"
            snippet = item.get("snippet") or item.get("text") or ""
            lines.append(f"  - {title}[{item.get('score', 0)}]: {_clip(str(snippet), 300)}")
    return "\n".join(lines)
