from __future__ import annotations

from typing import Any


def build_audit_entry(
    event_type: str,
    payload: dict[str, Any],
    *,
    task_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "session_id": session_id,
        "event_type": event_type,
        "payload": payload,
    }
