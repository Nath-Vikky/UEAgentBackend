from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class WorkflowState:
    run_id: str
    task_id: str
    session_id: str
    task_type: str
    raw_input: dict[str, Any]
    normalized_input: dict[str, Any] = field(default_factory=dict)
    retrieved_context: dict[str, Any] = field(default_factory=dict)
    tool_outputs: dict[str, Any] = field(default_factory=dict)
    step_results: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    action_proposals: list[dict[str, Any]] = field(default_factory=list)
    status: str = "completed"
