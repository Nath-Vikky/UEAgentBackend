from __future__ import annotations

from app.agent.graph_adapter import langgraph_adapter_blueprint, review_fix_validate_graph_spec


def test_review_fix_validate_graph_spec_matches_existing_chain_shape() -> None:
    spec = review_fix_validate_graph_spec()

    assert spec.graph_id == "review_fix_validate"
    assert spec.entrypoint == "review"
    assert spec.terminal_nodes == ("validate",)
    assert [node.node_id for node in spec.nodes] == ["review", "fix_draft", "validate"]
    assert {node.node_id: node.side_effect_level for node in spec.nodes} == {
        "review": "read_only",
        "fix_draft": "plan_only",
        "validate": "read_only",
    }
    assert [edge.condition for edge in spec.edges] == [
        "review_to_fix_gate_passed",
        "review_to_fix_gate_skipped",
        "always",
    ]


def test_langgraph_blueprint_is_dependency_free_and_serializable() -> None:
    blueprint = langgraph_adapter_blueprint(review_fix_validate_graph_spec())

    assert blueprint["adapter"] == "langgraph_blueprint"
    assert blueprint["requires_dependency"] is False
    assert blueprint["nodes"] == {
        "review": "ReviewerAgent",
        "fix_draft": "FixDraftAgent",
        "validate": "ValidationAgent",
    }
    assert blueprint["edges"][0]["source"] == "review"
