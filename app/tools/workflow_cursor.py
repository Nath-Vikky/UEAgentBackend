from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class WorkflowCursor:
    """Lightweight state cursor for multi-step tool workflows.

    The cursor is a hint for planning/debugging, not an execution authority.
    Confirmed-write operations must still go through Proposal confirmation.
    """

    workflow_id: str | None = None
    step_index: int = 0
    active_target: str | None = None
    active_asset: str | None = None
    active_graph: str | None = None
    last_tool_id: str | None = None
    last_result_ref: str | None = None
    cursor_state: str = "active"
    confirmed_until_step: int | None = None
    spatial_context: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)

    def advance(
        self,
        *,
        tool_id: str,
        action: str,
        result_ref: str | None = None,
        active_target: str | None = None,
        active_asset: str | None = None,
        active_graph: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowCursor:
        self.history.append(self.summary())
        self.step_index += 1
        self.last_tool_id = tool_id
        self.last_result_ref = result_ref or self.last_result_ref
        self.active_target = active_target or self.active_target
        self.active_asset = active_asset or self.active_asset
        self.active_graph = active_graph or self.active_graph
        if metadata:
            self.spatial_context.update(metadata)
        self.spatial_context["last_action"] = action
        return self

    def mark_confirmed(self, *, step_index: int | None = None) -> WorkflowCursor:
        self.confirmed_until_step = self.step_index if step_index is None else max(0, int(step_index))
        return self

    def summary(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "step_index": self.step_index,
            "active_target": self.active_target,
            "active_asset": self.active_asset,
            "active_graph": self.active_graph,
            "last_tool_id": self.last_tool_id,
            "last_result_ref": self.last_result_ref,
            "cursor_state": self.cursor_state,
            "confirmed_until_step": self.confirmed_until_step,
            "spatial_context": dict(self.spatial_context),
        }

    def prompt_excerpt(self) -> str:
        parts = [
            f"Workflow step: {self.step_index}",
            f"State: {self.cursor_state}",
        ]
        if self.active_target:
            parts.append(f"Active target: {self.active_target}")
        if self.active_asset:
            parts.append(f"Active asset: {self.active_asset}")
        if self.active_graph:
            parts.append(f"Active graph: {self.active_graph}")
        if self.last_tool_id:
            parts.append(f"Last tool: {self.last_tool_id}")
        if self.last_result_ref:
            parts.append(f"Last result reference: {self.last_result_ref}")
        return "\n".join(parts)

