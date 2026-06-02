from __future__ import annotations

from app.agent.graph_adapter import (
    graph_framework_readiness_report,
    langgraph_adapter_blueprint,
    review_fix_validate_graph_spec,
)


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
    assert blueprint["readiness"]["requested_framework"] == "langgraph_optional"


def test_graph_framework_readiness_keeps_framework_neutral_default() -> None:
    report = graph_framework_readiness_report(
        review_fix_validate_graph_spec(),
        requested_framework="framework_neutral",
        langgraph_available=False,
    )

    assert report["status"] == "framework_neutral"
    assert report["selected_runtime"] == "self_hosted_graph"
    assert report["framework_candidates"][0]["framework"] == "langgraph"
    assert report["framework_candidates"][0]["available"] is False


def test_graph_framework_readiness_blocks_active_langgraph_when_missing() -> None:
    report = graph_framework_readiness_report(
        review_fix_validate_graph_spec(),
        requested_framework="langgraph_active",
        langgraph_available=False,
    )

    assert report["status"] == "blocked_missing_dependency"
    assert report["selected_runtime"] == "self_hosted_graph"
    assert "Install optional agent dependencies" in report["recommendation"]


def test_graph_framework_readiness_marks_active_langgraph_ready_when_available() -> None:
    report = graph_framework_readiness_report(
        review_fix_validate_graph_spec(),
        requested_framework="langgraph_active",
        langgraph_available=True,
    )

    assert report["status"] == "ready"
    assert report["selected_runtime"] == "langgraph_candidate"
