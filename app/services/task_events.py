from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.schemas.responses import UnifiedTaskResponse
from app.utils.time import now_utc

StreamEventSink = Callable[[dict[str, Any]], None]


def build_stream_event(
    *,
    event: str,
    payload: dict[str, Any],
    run_id: str | None,
    task_id: str | None,
    seq: int,
) -> dict[str, Any]:
    return {
        "event": event,
        "seq": seq,
        "timestamp": now_utc().isoformat(),
        "run_id": run_id,
        "task_id": task_id,
        "payload": payload,
    }


class StreamEventEmitter:
    """Small stateful helper for SSE event envelope construction."""

    def __init__(self) -> None:
        self._sequence = 0

    def emit(
        self,
        sink: StreamEventSink | None,
        event: str,
        payload: dict[str, Any],
        *,
        run_id: str | None = None,
        task_id: str | None = None,
    ) -> None:
        if not sink:
            return
        self._sequence += 1
        sink(
            build_stream_event(
                event=event,
                payload=payload,
                run_id=run_id,
                task_id=task_id,
                seq=self._sequence,
            )
        )


def build_persisted_event_payloads(
    *,
    task_id: str,
    run_id: str,
    response: UnifiedTaskResponse,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []

    def append(event: str, payload: dict[str, Any]) -> None:
        payloads.append(
            build_stream_event(
                event=event,
                payload=payload,
                run_id=run_id,
                task_id=task_id,
                seq=len(payloads) + 1,
            )
        )

    append("run_started", {"task_type": response.task.task_type})
    append("route_selected", response.planner_diagnostics)

    if response.retrieval_trace.get("mode") not in {None, "", "not_used"}:
        append("retrieval_started", {"mode": response.retrieval_trace.get("mode")})
        append(
            "retrieval_completed",
            {
                "mode": response.retrieval_trace.get("mode"),
                "retrieved_docs": response.retrieval_trace.get("retrieved_docs", []),
            },
        )

    for step in response.step_results:
        step_payload = step.model_dump(mode="json")
        append("step_started", {"step_id": step.step_id, "title": step.title})
        append("step_completed", step_payload)

    if response.assistant_message:
        append("text_delta", {"text": response.assistant_message})

    for proposal in response.action_proposals:
        append("proposal_emitted", proposal.model_dump(mode="json"))

    append(
        "run_completed",
        {
            "status": response.task.status,
            "finish_reason": response.task.finish_reason,
        },
    )
    return payloads


def build_run_cancelled_event_payload(
    *,
    run_id: str,
    task_id: str,
    finish_reason: str | None,
    seq: int,
) -> dict[str, Any]:
    return build_stream_event(
        event="run_cancelled",
        payload={"status": "cancelled", "finish_reason": finish_reason},
        run_id=run_id,
        task_id=task_id,
        seq=seq,
    )
