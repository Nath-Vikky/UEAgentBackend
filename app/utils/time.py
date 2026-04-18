from __future__ import annotations

from datetime import UTC, datetime


def now_utc() -> datetime:
    return datetime.now(UTC)


def utc_isoformat(value: datetime | None = None) -> str:
    return (value or now_utc()).isoformat()

