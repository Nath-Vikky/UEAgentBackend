from __future__ import annotations

from dataclasses import dataclass, field
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
    }


__all__ = [
    "AgentGraphEdge",
    "AgentGraphNode",
    "AgentGraphSpec",
    "langgraph_adapter_blueprint",
    "review_fix_validate_graph_spec",
]
