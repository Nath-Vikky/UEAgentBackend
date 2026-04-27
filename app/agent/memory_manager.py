from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.session import SessionModel
from app.db.repositories.sessions import list_session_messages
from app.utils.time import now_utc

DEFAULT_TRIGGER_MESSAGE_COUNT = 8
DEFAULT_KEEP_RECENT_MESSAGES = 6
DEFAULT_MAX_SUMMARY_CHARS = 1800
DEFAULT_LONG_TERM_MEMORY_LIMIT = 12


def _clip(value: str, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 3, 0)]}..."


def _message_line(item: Any, *, limit: int = 220) -> str:
    role = str(getattr(item, "role", "user") or "user")
    content = _clip(str(getattr(item, "content", "") or ""), limit)
    return f"{role}: {content}"


def _build_summary_text(messages: list[Any], *, keep_recent_messages: int, max_summary_chars: int) -> str:
    summarized = messages[:-keep_recent_messages] if keep_recent_messages > 0 else messages
    if not summarized:
        summarized = messages
    user_lines = [_message_line(item) for item in summarized if getattr(item, "role", "") == "user"]
    assistant_lines = [
        _message_line(item, limit=180) for item in summarized if getattr(item, "role", "") == "assistant"
    ]
    lines = [
        "Session memory summary v1.",
        f"Summarized {len(summarized)} older chat message(s); keep recent turns verbatim separately.",
    ]
    if user_lines:
        lines.append("Older user requests:")
        lines.extend(f"- {line}" for line in user_lines[-6:])
    if assistant_lines:
        lines.append("Older assistant outcomes:")
        lines.extend(f"- {line}" for line in assistant_lines[-4:])
    return _clip("\n".join(lines), max_summary_chars)


def _tokenize(value: str) -> set[str]:
    lowered = str(value or "").lower()
    tokens = set(re.findall(r"[a-zA-Z0-9_]{2,}", lowered))
    tokens.update(re.findall(r"[\u4e00-\u9fff]{2,}", value))
    return tokens


def _classify_memory(text: str) -> tuple[str, bool]:
    lowered = text.lower()
    remember_hints = ("记住", "remember", "项目约定", "约定", "convention", "rule", "规则")
    preference_hints = ("偏好", "prefer", "preference", "默认", "default")
    version_hints = ("ue版本", "unreal engine", "ue 5", "ue5", "engine version")
    naming_hints = ("命名", "prefix", "前缀", "bp_", "sm_", "m_", "naming")
    if any(hint in lowered or hint in text for hint in version_hints):
        return ("project_version", True)
    if any(hint in lowered or hint in text for hint in naming_hints):
        return ("naming_rule", True)
    if any(hint in lowered or hint in text for hint in preference_hints):
        return ("user_preference", True)
    if any(hint in lowered or hint in text for hint in remember_hints):
        return ("project_rule", True)
    return ("note", False)


def _extract_long_term_memory_items(
    *,
    session_id: str,
    project_name: str | None,
    messages: list[Any],
    existing_items: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    items = list(existing_items)
    seen_text = {str(item.get("text") or "").strip() for item in items}
    for message in messages:
        if getattr(message, "role", "") != "user":
            continue
        content = str(getattr(message, "content", "") or "").strip()
        if not content:
            continue
        category, should_store = _classify_memory(content)
        if not should_store:
            continue
        text = _clip(content, 420)
        if text in seen_text:
            continue
        seen_text.add(text)
        items.append(
            {
                "memory_id": f"mem_{uuid.uuid4().hex}",
                "scope": "project" if project_name else "session",
                "project_name": project_name,
                "category": category,
                "text": text,
                "source_session_id": session_id,
                "source": "deterministic_message_extraction",
                "created_at": now_utc().isoformat(),
                "last_seen_at": now_utc().isoformat(),
            }
        )
    return items[-limit:]


def _score_memory_item(item: dict[str, Any], query_tokens: set[str], project_name: str | None) -> float:
    text_tokens = _tokenize(str(item.get("text") or ""))
    if not text_tokens:
        return 0.0
    overlap = len(query_tokens & text_tokens)
    score = overlap / max(len(query_tokens), 1)
    if project_name and item.get("project_name") == project_name:
        score += 0.35
    if str(item.get("category") or "") in {"project_version", "naming_rule", "project_rule"}:
        score += 0.15
    return round(min(score, 1.0), 4)


def recall_long_term_memory(
    db: Session,
    *,
    project_name: str | None,
    query: str,
    limit: int = 5,
) -> dict[str, Any]:
    query_tokens = _tokenize(query)
    statement = select(SessionModel)
    if project_name:
        statement = statement.where(SessionModel.project_name == project_name)
    sessions = list(db.scalars(statement.limit(200)))
    scored_items: list[dict[str, Any]] = []
    for session_model in sessions:
        metadata = dict(session_model.metadata_json or {})
        for item in list(metadata.get("long_term_memory_items") or []):
            if not isinstance(item, dict):
                continue
            score = _score_memory_item(item, query_tokens, project_name)
            if score <= 0 and query_tokens:
                continue
            scored_items.append({**item, "score": score})
    scored_items.sort(key=lambda item: (float(item.get("score") or 0.0), str(item.get("last_seen_at") or "")), reverse=True)
    deduped: list[dict[str, Any]] = []
    seen_text: set[str] = set()
    for item in scored_items:
        text = str(item.get("text") or "").strip()
        if not text or text in seen_text:
            continue
        seen_text.add(text)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return {
        "status": "available" if deduped else "not_found",
        "mode": "sqlite_keyword_recall",
        "project_name": project_name,
        "query": _clip(query, 300),
        "items": deduped,
        "count": len(deduped),
    }


def update_session_memory(
    db: Session,
    session_id: str,
    *,
    trigger_message_count: int = DEFAULT_TRIGGER_MESSAGE_COUNT,
    keep_recent_messages: int = DEFAULT_KEEP_RECENT_MESSAGES,
    max_summary_chars: int = DEFAULT_MAX_SUMMARY_CHARS,
) -> dict[str, Any]:
    """Persist a compact, deterministic session summary for prompt context.

    This is intentionally lightweight: no LLM dependency, no new table, and no
    user profiling. It gives future turns a stable summary plus project-scoped
    memory snippets without pretending to be an enterprise memory system.
    """

    session_model = db.get(SessionModel, session_id)
    if not session_model:
        return {"status": "not_available", "reason": "session_not_found"}

    messages = list_session_messages(db, session_id, limit=500)
    message_count = len(messages)
    metadata = dict(session_model.metadata_json or {})
    existing_memory_items = list(metadata.get("long_term_memory_items") or [])
    long_term_memory_items = _extract_long_term_memory_items(
        session_id=session_id,
        project_name=session_model.project_name,
        messages=messages,
        existing_items=[item for item in existing_memory_items if isinstance(item, dict)],
        limit=DEFAULT_LONG_TERM_MEMORY_LIMIT,
    )
    metadata["long_term_memory_items"] = long_term_memory_items
    session_model.metadata_json = metadata
    db.add(session_model)
    db.commit()
    db.refresh(session_model)
    if message_count < trigger_message_count:
        return {
            "status": "not_triggered",
            "reason": "message_count_below_threshold",
            "message_count": message_count,
            "trigger_message_count": trigger_message_count,
            "long_term_memory": {
                "mode": "sqlite_keyword_memory_v1",
                "item_count": len(long_term_memory_items),
                "latest_items": long_term_memory_items[-3:],
            },
        }

    summarized_message_count = max(message_count - keep_recent_messages, 0)
    summary_text = _build_summary_text(
        messages,
        keep_recent_messages=keep_recent_messages,
        max_summary_chars=max_summary_chars,
    )
    summary = {
        "status": "available",
        "version": "memory_summary_v1",
        "strategy": "deterministic_recent_compaction_v1",
        "source": "session_history",
        "summary_text": summary_text,
        "message_count": message_count,
        "summarized_message_count": summarized_message_count,
        "recent_message_count": min(keep_recent_messages, message_count),
        "trigger_message_count": trigger_message_count,
        "max_summary_chars": max_summary_chars,
        "long_term_memory": {
            "mode": "sqlite_keyword_memory_v1",
            "item_count": len(long_term_memory_items),
            "latest_items": long_term_memory_items[-3:],
        },
        "updated_at": now_utc().isoformat(),
    }
    metadata["memory_summary"] = summary
    metadata["long_term_memory_items"] = long_term_memory_items
    session_model.metadata_json = metadata
    db.add(session_model)
    db.commit()
    db.refresh(session_model)
    return summary
