from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from importlib.util import find_spec
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentGraphNode:
    node_id: str
    role: str
    description: str
    side_effect_level: str = "read_only"
    owned_tool_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "role": self.role,
            "description": self.description,
            "side_effect_level": self.side_effect_level,
            "owned_tool_id": self.owned_tool_id,
        }


@dataclass(frozen=True, slots=True)
class AgentGraphEdge:
    source: str
    target: str
    condition: str = "always"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "condition": self.condition,
        }


@dataclass(frozen=True, slots=True)
class AgentGraphSpec:
    graph_id: str
    entrypoint: str
    terminal_nodes: tuple[str, ...]
    nodes: tuple[AgentGraphNode, ...] = field(default_factory=tuple)
    edges: tuple[AgentGraphEdge, ...] = field(default_factory=tuple)
    adapter_status: str = "framework_neutral_blueprint"

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "entrypoint": self.entrypoint,
            "terminal_nodes": list(self.terminal_nodes),
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "adapter_status": self.adapter_status,
        }


@lru_cache(maxsize=16)
def _module_available(module_name: str) -> bool:
    return find_spec(module_name) is not None


def review_fix_validate_graph_spec() -> AgentGraphSpec:
    """Describe the existing review/fix/validate chain as a graph blueprint."""

    return AgentGraphSpec(
        graph_id="review_fix_validate",
        entrypoint="review",
        terminal_nodes=("validate",),
        nodes=(
            AgentGraphNode(
                node_id="review",
                role="ReviewerAgent",
                description="Run deterministic UE C++ review with optional LLM synthesis.",
                side_effect_level="read_only",
                owned_tool_id="review_code_file",
            ),
            AgentGraphNode(
                node_id="fix_draft",
                role="FixDraftAgent",
                description="Generate advisory, non-destructive fix drafts when review findings pass the gate.",
                side_effect_level="plan_only",
                owned_tool_id="generate_code_draft",
            ),
            AgentGraphNode(
                node_id="validate",
                role="ValidationAgent",
                description="Validate generated draft output or emit a review-only validation checklist.",
                side_effect_level="read_only",
                owned_tool_id="validate_generated_fix",
            ),
        ),
        edges=(
            AgentGraphEdge(source="review", target="fix_draft", condition="review_to_fix_gate_passed"),
            AgentGraphEdge(source="review", target="validate", condition="review_to_fix_gate_skipped"),
            AgentGraphEdge(source="fix_draft", target="validate", condition="always"),
        ),
    )


def graph_framework_readiness_report(
    spec: AgentGraphSpec,
    *,
    requested_framework: str = "framework_neutral",
    langgraph_available: bool | None = None,
) -> dict[str, Any]:
    """Describe whether this graph should stay self-hosted or move to LangGraph.

    This is intentionally a readiness report rather than a runtime dependency.
    The backend can expose framework suitability in Debug View while keeping the
    stable self-contained execution path. If LangGraph is installed through the
    optional `agent` extra, this report becomes a clear migration signal.
    """

    available = _module_available("langgraph") if langgraph_available is None else langgraph_available
    if requested_framework == "langgraph_active":
        status = "ready" if available else "blocked_missing_dependency"
        recommendation = (
            "LangGraph can own orchestration for this graph."
            if available
            else "Install optional agent dependencies or switch to langgraph_optional/framework_neutral."
        )
    elif requested_framework == "langgraph_optional":
        status = "available" if available else "optional_unavailable"
        recommendation = (
            "Keep current execution stable, but this graph can be migrated incrementally."
            if available
            else "Current self-hosted graph remains active; LangGraph is optional and not installed."
        )
    else:
        status = "framework_neutral"
        recommendation = "Keep the dependency-free graph as the stable default path."

    return {
        "version": "graph_framework_readiness_v1",
        "graph_id": spec.graph_id,
        "requested_framework": requested_framework,
        "selected_runtime": "self_hosted_graph" if status != "ready" else "langgraph_candidate",
        "status": status,
        "recommendation": recommendation,
        "framework_candidates": [
            {
                "framework": "langgraph",
                "available": available,
                "optional_dependency": "ue-agent-backend[agent]",
                "best_for": [
                    "multi_step_agent_orchestration",
                    "conditional_edges",
                    "checkpointable_workflows",
                ],
                "adoption_boundary": (
                    "May replace orchestration wiring, but must preserve Tool Registry, Proposal confirmation, "
                    "Debug View, and UEAgentTool execution contracts."
                ),
            }
        ],
        "graph_shape": spec.to_dict(),
        "migration_notes": [
            "Do not make LangGraph a hard dependency for local users.",
            "Start with read-only or plan-only graphs before confirmed-write Proposal graphs.",
            "Keep the existing AgentGraphSpec as the source of truth so self-hosted and LangGraph modes share one contract.",
        ],
    }


def langgraph_adapter_blueprint(spec: AgentGraphSpec) -> dict[str, Any]:
    """Return a dependency-free LangGraph-style wiring blueprint.

    The project does not import LangGraph here. This shape is meant for future
    adapter work and documentation while keeping the current self-contained
    backend stable.
    """

    return {
        "adapter": "langgraph_blueprint",
        "graph_id": spec.graph_id,
        "entrypoint": spec.entrypoint,
        "nodes": {node.node_id: node.role for node in spec.nodes},
        "edges": [edge.to_dict() for edge in spec.edges],
        "terminal_nodes": list(spec.terminal_nodes),
        "requires_dependency": False,
        "readiness": graph_framework_readiness_report(spec, requested_framework="langgraph_optional"),
    }


__all__ = [
    "AgentGraphEdge",
    "AgentGraphNode",
    "AgentGraphSpec",
    "graph_framework_readiness_report",
    "langgraph_adapter_blueprint",
    "review_fix_validate_graph_spec",
]
