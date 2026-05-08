from __future__ import annotations

from types import SimpleNamespace

from app.core.settings import Settings
from app.rag.retrieval.agentic import (
    evaluate_evidence,
    refine_retrieval_if_needed,
    rewrite_query_for_retrieval,
)
from app.rag.schemas import RetrievalCandidate, RetrievalResult
from app.schemas.requests import ContextInput


def _candidate(*, score: float = 0.08) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id="chunk_demo",
        doc_id="doc_demo",
        title="Demo",
        source_path="knowledge/demo.md",
        domain="code_reference",
        section_path="root",
        text="EnhancedInput UInputAction UEnhancedInputComponent BindAction",
        lexical_score=score,
        semantic_score=0.0,
        final_score=score,
    )


def _result(
    *,
    docs: list[RetrievalCandidate] | None = None,
    confidence: float = 0.12,
    warnings: list[str] | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        mode="lexical_only",
        degraded_mode=False,
        reason="test",
        filters_applied={"domains": ["code_reference"]},
        retrieved_docs=docs or [],
        confidence=confidence,
        answer="",
        citations=[],
        warnings=warnings or [],
    )


def _chunk() -> SimpleNamespace:
    return SimpleNamespace(
        chunk_id="chunk_enhanced_input",
        doc_id="doc_enhanced_input",
        title="Enhanced Input Character Example",
        source_path="knowledge/code-reference/enhanced-input-character.md",
        domain="code_reference",
        section_path="root",
        text=(
            "EnhancedInput UInputAction UInputMappingContext "
            "UEnhancedInputComponent AddMappingContext BindAction Character"
        ),
        metadata_json={},
        module="RushBa",
        doc_type="code",
    )


def test_evaluate_evidence_marks_empty_result_insufficient() -> None:
    quality = evaluate_evidence(_result(warnings=["no_retrieval_hits"]))

    assert quality["status"] == "insufficient"
    assert quality["reason"] == "no_retrieved_docs"
    assert quality["retrieved_count"] == 0


def test_evaluate_evidence_marks_confident_result_sufficient() -> None:
    quality = evaluate_evidence(_result(docs=[_candidate()], confidence=0.55))

    assert quality["status"] == "sufficient"
    assert quality["reason"] == "sufficient"


def test_rewrite_query_adds_domain_and_ue_term_hints() -> None:
    rewritten = rewrite_query_for_retrieval(
        query="\u89d2\u8272\u589e\u5f3a\u8f93\u5165\u4ee3\u7801\u600e\u4e48\u5199",
        domain_filters=["code_reference"],
        context=ContextInput(project_name="Demo", current_module="RushBa"),
    )

    assert "EnhancedInput" in rewritten
    assert "Build.cs" in rewritten
    assert "module RushBa" in rewritten


def test_refine_retrieval_runs_second_round_when_initial_evidence_is_weak() -> None:
    selected, trace, warnings = refine_retrieval_if_needed(
        query="\u89d2\u8272\u589e\u5f3a\u8f93\u5165\u4ee3\u7801\u600e\u4e48\u5199",
        context=ContextInput(project_name="Demo", current_module="RushBa"),
        payload={"domain_filters": ["code_reference"]},
        chunks=[_chunk()],
        settings=Settings(openai_api_key="", embedding_enabled=False, rag_mode="lexical", rag_top_k=3),
        output_language="zh-CN",
        initial_result=_result(warnings=["no_retrieval_hits"]),
    )

    assert trace["selected_round"] == 2
    assert trace["attempts"][1]["rewrite_applied"] is True
    assert selected.retrieved_docs
    assert "agentic_rag_query_rewrite_used" in warnings
