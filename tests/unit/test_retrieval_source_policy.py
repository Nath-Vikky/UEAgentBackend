from __future__ import annotations

from app.rag.source_policy import (
    build_retrieval_quality_gate,
    build_source_arbitration,
    merge_retrieval_warnings,
)


def test_source_arbitration_keeps_local_sources_ahead_of_web_memory_and_web() -> None:
    arbitration = build_source_arbitration(
        rag_count=0,
        local_count=1,
        web_memory_count=1,
        web_count=1,
        web_search={"trigger_reason": "explicit_user_request"},
    )

    assert arbitration["primary_source"] == "local_grep"
    assert arbitration["source_counts"] == {
        "rag": 0,
        "local_grep": 1,
        "web_memory": 1,
        "web_search": 1,
    }
    assert arbitration["web_memory_used"] is True
    assert arbitration["web_used"] is True


def test_retrieval_quality_gate_tracks_each_evidence_family() -> None:
    gate = build_retrieval_quality_gate(
        evidence_count=2,
        rag_count=1,
        local_count=0,
        web_memory_count=1,
        web_count=0,
        agentic_rag={"selected_round": 2},
        selected_query="Enhanced Input Mapping Context",
    )

    assert gate["status"] == "passed"
    assert gate["retrieved_count"] == 2
    assert gate["rag_retrieved_count"] == 1
    assert gate["web_memory_retrieved_count"] == 1
    assert gate["selected_round"] == 2


def test_warning_merge_removes_no_hit_warnings_after_fallback_evidence() -> None:
    warnings = merge_retrieval_warnings(
        rag_warnings=["no_retrieval_hits", "evidence_insufficient"],
        result_warnings=[],
        local_docs=[],
        web_memory_docs=[{"title": "cached"}],
        web_docs=[],
        web_memory_store={"status": "completed", "stored_count": 1, "updated_count": 0},
        web_search={"status": "skipped", "warnings": ["provider_disabled"]},
    )

    assert "no_retrieval_hits" not in warnings
    assert "evidence_insufficient" not in warnings
    assert "web_memory_fallback_used" in warnings
    assert "web_memory_updated" in warnings
    assert "provider_disabled" in warnings
