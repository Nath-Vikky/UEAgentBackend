from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models.session import SessionModel
from app.db.repositories.sessions import list_session_messages
from app.utils.time import now_utc

DEFAULT_TRIGGER_MESSAGE_COUNT = 8
DEFAULT_KEEP_RECENT_MESSAGES = 6
DEFAULT_MAX_SUMMARY_CHARS = 1800


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
    cross-project memory. It gives the next turn a stable summary without making
    the current personal-project backend look like an enterprise memory system.
    """

    session_model = db.get(SessionModel, session_id)
    if not session_model:
        return {"status": "not_available", "reason": "session_not_found"}

    messages = list_session_messages(db, session_id, limit=500)
    message_count = len(messages)
    if message_count < trigger_message_count:
        return {
            "status": "not_triggered",
            "reason": "message_count_below_threshold",
            "message_count": message_count,
            "trigger_message_count": trigger_message_count,
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
        "updated_at": now_utc().isoformat(),
    }
    metadata = dict(session_model.metadata_json or {})
    metadata["memory_summary"] = summary
    session_model.metadata_json = metadata
    db.add(session_model)
    db.commit()
    db.refresh(session_model)
    return summary
