from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class IngestionJobStatus:
    job_id: str
    status: str
    payload: dict[str, Any]
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "payload": self.payload,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "result": self.result,
            "error": self.error,
        }


class InProcessIngestionJobQueue:
    """Small in-process queue for local KB ingestion jobs.

    This intentionally avoids Redis/Celery. It is a bridge between synchronous
    imports and a future background worker, suitable for a single-user local
    backend.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._jobs: dict[str, IngestionJobStatus] = {}

    async def enqueue(
        self,
        payload: dict[str, Any],
        *,
        job_id: str | None = None,
    ) -> IngestionJobStatus:
        resolved_job_id = job_id or f"kb_import_{uuid.uuid4().hex}"
        if resolved_job_id in self._jobs:
            raise ValueError(f"duplicate_ingestion_job_id:{resolved_job_id}")
        status = IngestionJobStatus(
            job_id=resolved_job_id,
            status="queued",
            payload=dict(payload),
        )
        self._jobs[resolved_job_id] = status
        await self._queue.put(resolved_job_id)
        return status

    async def next_job(self) -> IngestionJobStatus:
        job_id = await self._queue.get()
        status = self._jobs[job_id]
        status.status = "running"
        status.updated_at = utc_now()
        return status

    def complete(self, job_id: str, result: dict[str, Any] | None = None) -> IngestionJobStatus:
        status = self._require_job(job_id)
        was_running = status.status == "running"
        status.status = "completed"
        status.result = result or {}
        status.error = None
        status.updated_at = utc_now()
        if was_running:
            self._queue.task_done()
        return status

    def fail(self, job_id: str, error: str) -> IngestionJobStatus:
        status = self._require_job(job_id)
        was_running = status.status == "running"
        status.status = "failed"
        status.error = error
        status.updated_at = utc_now()
        if was_running:
            self._queue.task_done()
        return status

    def get(self, job_id: str) -> IngestionJobStatus | None:
        return self._jobs.get(job_id)

    def snapshot(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self._jobs.values()]

    def _require_job(self, job_id: str) -> IngestionJobStatus:
        status = self.get(job_id)
        if not status:
            raise KeyError(f"unknown_ingestion_job_id:{job_id}")
        return status


default_ingestion_job_queue = InProcessIngestionJobQueue()


async def enqueue_import_job(
    payload: dict[str, Any],
    *,
    job_id: str | None = None,
) -> IngestionJobStatus:
    return await default_ingestion_job_queue.enqueue(payload, job_id=job_id)


__all__ = [
    "InProcessIngestionJobQueue",
    "IngestionJobStatus",
    "default_ingestion_job_queue",
    "enqueue_import_job",
    "utc_now",
]
