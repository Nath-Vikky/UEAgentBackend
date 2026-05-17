from __future__ import annotations

import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.rag.curation import (
    build_curation_markdown,
    build_knowledge_curation_suggestions,
    build_web_memory_curation_suggestions,
    extract_curation_result,
    write_curation_artifact,
)


def test_curation_suggests_distillation_when_web_fills_local_gap() -> None:
    result = build_knowledge_curation_suggestions(
        query="UE Enhanced Input 怎么绑定动作？",
        retrieved_docs=[],
        local_docs=[],
        web_memory_docs=[],
        web_docs=[
            {
                "title": "Enhanced Input in Unreal Engine",
                "source_url": "https://dev.epicgames.com/documentation/en-us/unreal-engine/enhanced-input",
                "source_type": "official",
                "text": "Enhanced Input uses Input Actions and Mapping Contexts.",
            }
        ],
        retrieval_quality_gate={"status": "passed"},
    )

    assert result["status"] == "suggested"
    assert result["writes_to_kb"] is False
    assert result["auto_apply"] is False
    assert result["candidates"][0]["reason"] == "local_kb_gap_found_controlled_web_evidence"
    assert "requires_human_distillation" in result["candidates"][0]["safety_notes"]
    assert result["candidates"][0]["official_domain"] is True
    assert result["candidates"][0]["curation_candidate_score"] > 0


def test_curation_does_not_suggest_when_local_evidence_exists() -> None:
    result = build_knowledge_curation_suggestions(
        query="Actor 生命周期",
        retrieved_docs=[{"title": "Actor lifecycle"}],
        local_docs=[],
        web_memory_docs=[],
        web_docs=[{"title": "Actor lifecycle online"}],
        retrieval_quality_gate={"status": "passed"},
    )

    assert result["status"] == "not_needed"
    assert result["candidate_count"] == 0


def test_curation_suggests_manual_note_for_insufficient_evidence() -> None:
    result = build_knowledge_curation_suggestions(
        query="项目里自定义 SaveGame 约定是什么？",
        retrieved_docs=[],
        local_docs=[],
        web_memory_docs=[],
        web_docs=[],
        retrieval_quality_gate={"status": "insufficient"},
    )

    assert result["status"] == "suggested"
    assert result["candidates"][0]["action"] == "consider_manual_note"
    assert result["candidates"][0]["suggested_domain"] == "project-notes"


def test_web_memory_curation_scores_high_value_official_entries() -> None:
    result = build_web_memory_curation_suggestions(
        items=[
            {
                "query": "Enhanced Input",
                "title": "Enhanced Input in Unreal Engine",
                "url": "https://dev.epicgames.com/documentation/en-us/unreal-engine/enhanced-input",
                "domain": "dev.epicgames.com",
                "snippet": "Enhanced Input uses Input Actions and Mapping Contexts.",
                "source_type": "official",
                "source_score": 0.82,
                "quality_score": 0.9,
                "helpful_count": 2,
                "recall_count": 3,
            }
        ],
        min_score=0.45,
    )

    candidate = result["candidates"][0]
    assert result["status"] == "suggested"
    assert candidate["official_domain"] is True
    assert candidate["suggested_domain"] == "code_reference"
    assert candidate["priority"] in {"medium", "high"}
    assert candidate["curation_candidate_score"] >= 0.45


def test_curation_artifact_writes_markdown_and_json() -> None:
    output_dir = Path(".test-runtime") / f"curation-{uuid.uuid4().hex}"
    result = build_web_memory_curation_suggestions(
        items=[
            {
                "query": "Blueprint asset naming",
                "title": "Blueprint Asset Checklist",
                "url": "https://dev.epicgames.com/documentation/en-us/unreal-engine/blueprints",
                "domain": "dev.epicgames.com",
                "snippet": "Blueprint assets should follow project naming rules.",
                "source_type": "official",
                "source_score": 0.75,
                "quality_score": 0.8,
                "helpful_count": 1,
                "recall_count": 2,
            }
        ],
        min_score=0.4,
    )

    try:
        artifact = write_curation_artifact(
            result,
            output_dir=output_dir,
            generated_at=datetime(2026, 5, 17, 12, 0, tzinfo=UTC),
        )

        markdown = (output_dir / "kb-curation-20260517-120000.md").read_text(encoding="utf-8")
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)
    assert artifact["status"] == "completed"
    assert artifact["writes_to_kb"] is False
    assert artifact["candidate_count"] == 1
    assert "Knowledge Curation Suggestions" in markdown
    assert "Manual review checklist" in markdown


def test_extract_curation_result_accepts_nested_task_response() -> None:
    result = build_knowledge_curation_suggestions(
        query="Enhanced Input",
        retrieved_docs=[],
        local_docs=[],
        web_memory_docs=[],
        web_docs=[{"title": "Enhanced Input", "source_url": "https://dev.epicgames.com/test"}],
        retrieval_quality_gate={"status": "passed"},
    )

    assert extract_curation_result({"data": {"knowledge_curation": result}}) == result
    assert "No Candidates" in build_curation_markdown({"candidates": [], "writes_to_kb": False})
