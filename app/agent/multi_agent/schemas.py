from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AgentNodeResult:
    node_id: str
    role: str
    status: str
    input_summary: str
    output_summary: str
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    latency_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "role": self.role,
            "status": self.status,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "data": self.data,
            "warnings": self.warnings,
            "latency_ms": self.latency_ms,
        }


@dataclass(slots=True)
class DecisionGate:
    gate_id: str
    status: str
    reason: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "status": self.status,
            "reason": self.reason,
            "details": self.details,
        }


@dataclass(slots=True)
class AgentChainResult:
    chain_id: str
    status: str
    phase_results: list[AgentNodeResult] = field(default_factory=list)
    decision_gates: list[DecisionGate] = field(default_factory=list)
    user_view_blocks: list[dict[str, Any]] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    debug_trace: dict[str, Any] = field(default_factory=dict)
    step_results: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "status": self.status,
            "phase_count": len(self.phase_results),
            "phases": [item.to_dict() for item in self.phase_results],
            "decision_gates": [item.to_dict() for item in self.decision_gates],
            "warnings": self.warnings,
        }
