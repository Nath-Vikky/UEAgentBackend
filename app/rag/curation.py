from __future__ import annotations

from hashlib import sha1
from typing import Any


CURATION_MODE = "kb_curation_suggestion_v1"


def build_knowledge_curation_suggestions(
    *,
    query: str,
    retrieved_docs: list[dict[str, Any]],
    local_docs: list[dict[str, Any]],
    web_memory_docs: list[dict[str, Any]],
    web_docs: list[dict[str, Any]],
    retrieval_quality_gate: dict[str, Any],
) -> dict[str, Any]:
    """Suggest KB maintenance actions without writing any knowledge files."""

    candidates: list[dict[str, Any]] = []
    local_evidence_available = bool(local_docs or _local_retrieved_docs(retrieved_docs))
    if not local_evidence_available:
        for item in web_memory_docs[:2]:
            candidates.append(
                _candidate(
                    query=query,
                    item=item,
                    reason="local_kb_gap_reused_web_memory",
                    suggested_domain="engine-notes",
                    action="consider_distilled_note",
                    confidence=0.55,
                )
            )
        for item in web_docs[:2]:
            candidates.append(
                _candidate(
                    query=query,
                    item=item,
                    reason="local_kb_gap_found_controlled_web_evidence",
                    suggested_domain="engine-notes",
                    action="consider_distilled_note",
                    confidence=0.62,
                )
            )
    if not candidates and retrieval_quality_gate.get("status") in {"failed", "insufficient"}:
        candidates.append(
            {
                "candidate_id": _candidate_id(query, "manual_note", "kb_gap"),
                "action": "consider_manual_note",
                "reason": "retrieval_quality_gate_insufficient",
                "suggested_domain": "project-notes",
                "title": _title_from_query(query),
                "source_type": "manual_followup",
                "source_url": "",
                "evidence_preview": str(query or "")[:240],
                "confidence": 0.35,
                "safety_notes": [
                    "suggestion_only",
                    "requires_human_review",
                    "does_not_write_to_kb",
                ],
            }
        )
    return {
        "status": "suggested" if candidates else "not_needed",
        "mode": CURATION_MODE,
        "writes_to_kb": False,
        "auto_apply": False,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def _candidate(
    *,
    query: str,
    item: dict[str, Any],
    reason: str,
    suggested_domain: str,
    action: str,
    confidence: float,
) -> dict[str, Any]:
    title = str(item.get("title") or item.get("source_path") or _title_from_query(query)).strip()
    source_url = str(item.get("source_url") or item.get("url") or item.get("source_path") or "").strip()
    source_type = str(item.get("source_type") or item.get("retrieval_source") or "unknown").strip()
    preview = str(item.get("text") or item.get("snippet") or item.get("summary") or "").strip()[:360]
    return {
        "candidate_id": _candidate_id(query, title, source_url or source_type),
        "action": action,
        "reason": reason,
        "suggested_domain": suggested_domain,
        "title": title[:160],
        "source_type": source_type,
        "source_url": source_url,
        "evidence_preview": preview,
        "confidence": confidence,
        "safety_notes": [
            "suggestion_only",
            "requires_human_distillation",
            "does_not_write_to_kb",
        ],
    }


def _local_retrieved_docs(retrieved_docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    external_sources = {"web_memory", "web_search"}
    return [
        item
        for item in retrieved_docs
        if str(item.get("retrieval_source") or "").strip() not in external_sources
    ]


def _title_from_query(query: str) -> str:
    text = " ".join(str(query or "").strip().split())
    return text[:80] or "Untitled KB note"


def _candidate_id(query: str, title: str, source: str) -> str:
    digest = sha1(f"{query}|{title}|{source}".encode()).hexdigest()[:12]
    return f"cur_{digest}"
