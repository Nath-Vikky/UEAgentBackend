from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha1
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


CURATION_MODE = "kb_curation_suggestion_v1"
CURATION_ARTIFACT_MODE = "kb_curation_artifact_v1"
OFFICIAL_DOC_DOMAINS = ("dev.epicgames.com", "docs.unrealengine.com", "unrealengine.com")


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


def build_web_memory_curation_suggestions(
    *,
    items: list[dict[str, Any]],
    limit: int = 20,
    min_score: float = 0.45,
) -> dict[str, Any]:
    """Build human-review curation candidates from stored Web Memory entries.

    This keeps the KB boundary safe: Web Memory can recommend distilled notes,
    but the function never writes into the formal knowledge directory.
    """

    candidates: list[dict[str, Any]] = []
    for item in items:
        candidate = _candidate(
            query=str(item.get("query") or item.get("title") or ""),
            item=item,
            reason="web_memory_high_value_candidate",
            suggested_domain=_suggested_domain(item),
            action="consider_distilled_note",
            confidence=max(
                _coerce_float(item.get("quality_score")),
                _coerce_float(item.get("source_score")),
                _coerce_float(item.get("score")),
                0.35,
            ),
        )
        if float(candidate["curation_candidate_score"]) >= min_score:
            candidates.append(candidate)

    candidates = sorted(
        candidates,
        key=lambda item: (
            float(item.get("curation_candidate_score") or 0),
            int(item.get("helpful_count") or 0),
            int(item.get("recall_count") or 0),
        ),
        reverse=True,
    )[: max(1, limit)]
    return {
        "status": "suggested" if candidates else "not_needed",
        "mode": CURATION_ARTIFACT_MODE,
        "writes_to_kb": False,
        "auto_apply": False,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "scoring_policy": curation_scoring_policy(),
    }


def score_curation_candidate(candidate: dict[str, Any]) -> float:
    confidence = _coerce_float(candidate.get("confidence"))
    source_score = _coerce_float(candidate.get("source_score"), default=confidence)
    quality_score = _coerce_float(candidate.get("quality_score"), default=source_score)
    helpful_norm = min(_coerce_int(candidate.get("helpful_count")) / 5.0, 1.0)
    recall_norm = min(_coerce_int(candidate.get("recall_count")) / 5.0, 1.0)
    official_boost = 1.0 if candidate.get("official_domain") else 0.0
    unhelpful_penalty = min(_coerce_int(candidate.get("unhelpful_count")) * 0.08, 0.25)
    score = (
        confidence * 0.22
        + source_score * 0.22
        + quality_score * 0.24
        + helpful_norm * 0.12
        + recall_norm * 0.10
        + official_boost * 0.10
        - unhelpful_penalty
    )
    return round(max(0.0, min(1.0, score)), 4)


def curation_scoring_policy() -> dict[str, Any]:
    return {
        "confidence_weight": 0.22,
        "source_score_weight": 0.22,
        "quality_score_weight": 0.24,
        "helpful_feedback_weight": 0.12,
        "recall_count_weight": 0.10,
        "official_domain_weight": 0.10,
        "unhelpful_penalty_per_vote": 0.08,
        "unhelpful_penalty_max": 0.25,
        "priority_thresholds": {"high": 0.72, "medium": 0.50, "low": 0.0},
    }


def build_curation_markdown(
    curation_result: dict[str, Any],
    *,
    title: str = "Knowledge Curation Suggestions",
    generated_at: datetime | None = None,
) -> str:
    timestamp = (generated_at or datetime.now(UTC)).isoformat()
    candidates = [
        item for item in curation_result.get("candidates", []) if isinstance(item, dict)
    ]
    lines = [
        f"# {title}",
        "",
        f"- Generated at: `{timestamp}`",
        f"- Mode: `{curation_result.get('mode') or CURATION_ARTIFACT_MODE}`",
        f"- Status: `{curation_result.get('status') or 'unknown'}`",
        f"- Candidate count: `{len(candidates)}`",
        "- Writes to formal KB: `false`",
        "- Safety: suggestion-only, requires human distillation before adding to `knowledge/`.",
        "",
    ]
    if not candidates:
        lines.extend(
            [
                "## No Candidates",
                "",
                "No curation candidates met the current scoring threshold.",
            ]
        )
        return "\n".join(lines).rstrip() + "\n"

    lines.extend(
        [
            "## Candidate Summary",
            "",
            "| Priority | Score | Suggested Domain | Title | Source |",
            "| --- | ---: | --- | --- | --- |",
        ]
    )
    for item in candidates:
        lines.append(
            "| "
            f"`{item.get('priority') or 'low'}` | "
            f"{float(item.get('curation_candidate_score') or 0):.4f} | "
            f"`{item.get('suggested_domain') or 'engine-notes'}` | "
            f"{_escape_table_text(str(item.get('title') or 'Untitled'))} | "
            f"{_escape_table_text(str(item.get('source_url') or item.get('source_type') or 'unknown'))} |"
        )

    lines.extend(["", "## Candidates", ""])
    for index, item in enumerate(candidates, 1):
        lines.extend(
            [
                f"### {index}. {item.get('title') or 'Untitled'}",
                "",
                f"- Candidate ID: `{item.get('candidate_id')}`",
                f"- Priority: `{item.get('priority') or 'low'}`",
                f"- Score: `{float(item.get('curation_candidate_score') or 0):.4f}`",
                f"- Action: `{item.get('action') or 'consider_distilled_note'}`",
                f"- Reason: `{item.get('reason') or 'unspecified'}`",
                f"- Suggested domain: `{item.get('suggested_domain') or 'engine-notes'}`",
                f"- Source type: `{item.get('source_type') or 'unknown'}`",
                f"- Source URL/path: `{item.get('source_url') or ''}`",
                f"- Official domain: `{bool(item.get('official_domain'))}`",
                f"- Helpful / unhelpful: `{item.get('helpful_count') or 0}` / `{item.get('unhelpful_count') or 0}`",
                f"- Recall count: `{item.get('recall_count') or 0}`",
                "",
                "Evidence preview:",
                "",
                f"> {_blockquote_text(str(item.get('evidence_preview') or ''))}",
                "",
                "Manual review checklist:",
                "",
                "- Verify the source is relevant to Unreal Engine or the current project.",
                "- Rewrite the evidence as a short local note instead of copying the source verbatim.",
                "- Choose the final `knowledge/` domain folder before importing or committing.",
                "- Re-run KB refresh/reindex after adding the distilled note.",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_curation_artifact(
    curation_result: dict[str, Any],
    *,
    output_dir: str | Path,
    prefix: str = "kb-curation",
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    timestamp = generated_at or datetime.now(UTC)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    suffix = timestamp.strftime("%Y%m%d-%H%M%S")
    markdown_path = output_path / f"{prefix}-{suffix}.md"
    json_path = output_path / f"{prefix}-{suffix}.json"
    markdown = build_curation_markdown(curation_result, generated_at=timestamp)
    markdown_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json.dumps(curation_result, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "status": "completed",
        "mode": CURATION_ARTIFACT_MODE,
        "candidate_count": int(curation_result.get("candidate_count") or 0),
        "markdown_path": markdown_path.as_posix(),
        "json_path": json_path.as_posix(),
        "writes_to_kb": False,
    }


def extract_curation_result(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Accept raw curation payloads or nested task responses."""

    if _looks_like_curation_result(payload):
        return payload
    for key in ("knowledge_curation",):
        nested = payload.get(key)
        if isinstance(nested, dict) and _looks_like_curation_result(nested):
            return nested
    for parent_key in ("data", "debug_view", "retrieval_trace"):
        parent = payload.get(parent_key)
        if not isinstance(parent, dict):
            continue
        nested = parent.get("knowledge_curation")
        if isinstance(nested, dict) and _looks_like_curation_result(nested):
            return nested
        trace = parent.get("retrieval_trace")
        if isinstance(trace, dict):
            nested = trace.get("knowledge_curation")
            if isinstance(nested, dict) and _looks_like_curation_result(nested):
                return nested
    return None


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
    metrics = _candidate_metrics(item=item, confidence=confidence, source_url=source_url)
    candidate = {
        "candidate_id": _candidate_id(query, title, source_url or source_type),
        "action": action,
        "reason": reason,
        "suggested_domain": suggested_domain,
        "title": title[:160],
        "source_type": source_type,
        "source_url": source_url,
        "evidence_preview": preview,
        "confidence": confidence,
        **metrics,
        "safety_notes": [
            "suggestion_only",
            "requires_human_distillation",
            "does_not_write_to_kb",
        ],
    }
    candidate["curation_candidate_score"] = score_curation_candidate(candidate)
    candidate["priority"] = _priority(candidate["curation_candidate_score"])
    return candidate


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


def _candidate_metrics(
    *,
    item: dict[str, Any],
    confidence: float,
    source_url: str,
) -> dict[str, Any]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    recall_count = item.get("recall_count", metadata.get("recall_count"))
    source_score = _coerce_float(item.get("source_score"), default=_coerce_float(item.get("score"), default=confidence))
    quality_score = _coerce_float(item.get("quality_score"), default=source_score)
    return {
        "source_score": source_score,
        "quality_score": quality_score,
        "helpful_count": _coerce_int(item.get("helpful_count")),
        "unhelpful_count": _coerce_int(item.get("unhelpful_count")),
        "recall_count": _coerce_int(recall_count),
        "official_domain": _is_official_source(source_url or str(item.get("domain") or "")),
    }


def _suggested_domain(item: dict[str, Any]) -> str:
    text = " ".join(
        str(item.get(key) or "")
        for key in ("query", "title", "snippet", "text", "domain", "source_type")
    ).lower()
    if any(token in text for token in ("code", "cpp", "c++", "enhanced input", "uobject", "actor")):
        return "code_reference"
    if any(token in text for token in ("asset", "blueprint", "material", "static mesh", "nanite")):
        return "asset_rules"
    if any(token in text for token in ("performance", "tick", "thread", "async", "render")):
        return "perf_notes"
    return "engine_notes"


def _is_official_source(source: str) -> bool:
    domain = urlparse(source).netloc.lower() if "://" in source else source.lower()
    return any(domain == official or domain.endswith(f".{official}") for official in OFFICIAL_DOC_DOMAINS)


def _priority(score: float) -> str:
    if score >= 0.72:
        return "high"
    if score >= 0.50:
        return "medium"
    return "low"


def _coerce_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return default


def _coerce_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _looks_like_curation_result(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("candidates"), list) and "writes_to_kb" in payload


def _escape_table_text(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")[:180]


def _blockquote_text(text: str) -> str:
    clean = " ".join(text.split())
    return clean[:500] or "(empty preview)"
