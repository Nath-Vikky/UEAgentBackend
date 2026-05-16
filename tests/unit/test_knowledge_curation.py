from __future__ import annotations

from app.rag.curation import build_knowledge_curation_suggestions


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
