from __future__ import annotations

import re
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.settings import Settings
from app.db.models.web_memory import WebMemoryEntryModel, WebMemoryFeedbackModel
from app.db.repositories.web_memory import (
    add_web_memory_feedback,
    count_web_memory_entries,
    delete_expired_web_memory_entries,
    get_web_memory_entry,
    get_web_memory_entry_by_url,
    list_active_web_memory_entries,
    list_recent_web_memory_entries,
    save_web_memory_entry,
    trim_web_memory_entries,
)
from app.db.repositories.web_memory_fts import (
    search_web_memory_fts_entries,
    sync_web_memory_fts_entries,
)
from app.rag.indexing.sparse import tokenize_query
from app.utils.time import now_utc


class WebMemoryService:
    """Small local cache for controlled Web Search summaries.

    This is not a crawler and not a KB writer. It stores URL/domain/snippet
    metadata so repeated UE documentation questions can reuse recent evidence.
    """

    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.settings.web_memory_enabled,
            "status": "ready" if self.settings.web_memory_enabled else "disabled",
            "reason": "ready" if self.settings.web_memory_enabled else "disabled_by_settings",
            "entry_count": count_web_memory_entries(self.db),
            "ttl_days": self.settings.web_memory_ttl_days,
            "max_results": self.settings.web_memory_max_results,
            "max_entries": self.settings.web_memory_max_entries,
            "min_score": self.settings.web_memory_min_score,
            "fts_enabled": self.settings.web_memory_fts_enabled,
            "stores_full_web_pages": False,
            "writes_to_kb": False,
        }

    def remember_web_search_result(
        self,
        *,
        query: str,
        web_search: dict[str, Any],
        source_task_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.settings.web_memory_enabled:
            return self._skipped_result(reason="disabled_by_settings")
        if web_search.get("status") != "completed":
            return self._skipped_result(reason=f"web_search_{web_search.get('status') or 'not_completed'}")

        items = [item for item in web_search.get("items", []) if isinstance(item, dict)]
        if not items:
            return self._skipped_result(reason="no_web_search_items")

        deleted_expired = delete_expired_web_memory_entries(self.db)
        stored = 0
        updated = 0
        skipped_low_score = 0
        now = now_utc()
        expires_at = now + timedelta(days=max(self.settings.web_memory_ttl_days, 1))
        query_terms = _query_terms(query)
        changed_entries: list[WebMemoryEntryModel] = []
        for item in items:
            score = _coerce_score(item.get("score"))
            if score < self.settings.web_memory_min_score:
                skipped_low_score += 1
                continue
            url = str(item.get("url") or item.get("source_path") or "").strip()
            if not url:
                continue
            existing = get_web_memory_entry_by_url(self.db, url)
            if existing:
                entry = existing
                updated += 1
            else:
                entry = WebMemoryEntryModel(entry_id=f"webmem_{uuid.uuid4().hex}", url=url)
                entry.helpful_count = 0
                entry.unhelpful_count = 0
                stored += 1
            entry.query = query
            entry.query_terms_json = query_terms
            entry.title = str(item.get("title") or url)[:255]
            entry.domain = str(item.get("domain") or "").lower().strip()[:255]
            entry.snippet = str(item.get("snippet") or item.get("text") or "")[:1200]
            entry.source_type = str(item.get("source_type") or "web")[:64]
            entry.provider = str(item.get("provider") or web_search.get("provider") or "unknown")[:64]
            entry.source_score = score
            entry.quality_score = _quality_score(score, entry.helpful_count or 0, entry.unhelpful_count or 0)
            entry.tags_json = ["web_search", entry.source_type]
            entry.metadata_json = {
                "published_at": item.get("published_at"),
                "trigger_reason": web_search.get("trigger_reason"),
                "search_reason": web_search.get("reason"),
                "rank": item.get("rank"),
                "stores_full_web_page": False,
            }
            entry.source_task_id = source_task_id
            entry.expires_at = expires_at
            entry.updated_at = now
            save_web_memory_entry(self.db, entry)
            changed_entries.append(entry)

        fts_sync = {"available": False, "reason": "disabled_by_settings", "synced_count": 0}
        if self.settings.web_memory_fts_enabled and changed_entries:
            fts_sync = sync_web_memory_fts_entries(self.db, changed_entries)
        trimmed = trim_web_memory_entries(self.db, max_entries=self.settings.web_memory_max_entries)
        return {
            "status": "completed",
            "reason": "stored_web_search_summaries",
            "stored_count": stored,
            "updated_count": updated,
            "skipped_low_score_count": skipped_low_score,
            "deleted_expired_count": deleted_expired,
            "trimmed_count": trimmed,
            "fts_sync": fts_sync,
            "writes_to_kb": False,
        }

    def recall(
        self,
        *,
        query: str,
        domain_hints: list[str] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        if not self.settings.web_memory_enabled:
            return self._empty_recall(query=query, status="skipped", reason="disabled_by_settings")
        terms = _query_terms(query)
        if not terms:
            return self._empty_recall(query=query, status="skipped", reason="empty_query")

        deleted_expired = delete_expired_web_memory_entries(self.db)
        max_candidates = max(self.settings.web_memory_max_entries, 20)
        entries = list_active_web_memory_entries(
            self.db,
            domain_hints=domain_hints or [],
            limit=max_candidates,
        )
        result_limit = max(1, min(limit or self.settings.web_memory_max_results, 10))
        ranked: list[tuple[WebMemoryEntryModel, dict[str, Any]]] = []
        search_mode = "python_token"
        fts5 = {
            "enabled": self.settings.web_memory_fts_enabled,
            "used": False,
            "reason": "disabled_by_settings" if not self.settings.web_memory_fts_enabled else "not_attempted",
        }
        if self.settings.web_memory_fts_enabled:
            fts_sync = sync_web_memory_fts_entries(self.db, entries)
            fts_result = search_web_memory_fts_entries(
                self.db,
                terms=terms,
                domain_hints=domain_hints or [],
                limit=result_limit,
            )
            fts5 = {
                "enabled": True,
                "used": bool(fts_result.items),
                "reason": fts_result.reason,
                "sync": fts_sync,
                "search": fts_result.diagnostics,
            }
            if fts_result.items:
                ranked = [
                    (
                        entry,
                        _recall_ranking(entry, terms, fts_score=fts_score),
                    )
                    for entry, fts_score in fts_result.items
                ][:result_limit]
                search_mode = "sqlite_fts5"

        if not ranked:
            scored = [(entry, _recall_ranking(entry, terms)) for entry in entries]
            ranked = [
                (entry, ranking)
                for entry, ranking in sorted(scored, key=lambda item: float(item[1]["score"]), reverse=True)
                if ranking["score"] > 0
            ][:result_limit]
            if self.settings.web_memory_fts_enabled:
                search_mode = "python_token_fallback"
        now = now_utc()
        for entry, _ranking in ranked:
            metadata = dict(entry.metadata_json or {})
            metadata["recall_count"] = int(metadata.get("recall_count") or 0) + 1
            metadata["last_recalled_query"] = query[:240]
            metadata["last_recalled_at"] = now.isoformat()
            entry.metadata_json = metadata
            entry.last_accessed_at = now
            self.db.add(entry)
        if ranked:
            self.db.commit()

        return {
            "query": query,
            "mode": "web_memory",
            "status": "completed",
            "reason": "matched" if ranked else "no_matching_memory",
            "items": [
                _entry_to_item(entry, score=ranking["score"], rank=index, ranking=ranking)
                for index, (entry, ranking) in enumerate(ranked, 1)
            ],
            "summary": {
                "result_count": len(ranked),
                "candidate_count": len(entries),
                "deleted_expired_count": deleted_expired,
                "domain_hints": domain_hints or [],
                "terms": terms,
                "search_mode": search_mode,
                "fts5": fts5,
                "ranking_policy": _ranking_policy(),
                "writes_to_kb": False,
            },
        }

    def list_recent(self, *, limit: int = 20) -> dict[str, Any]:
        entries = list_recent_web_memory_entries(self.db, limit=max(1, min(limit, 100)))
        return {
            "status": "completed",
            "items": [_entry_to_item(entry, score=entry.quality_score, rank=index) for index, entry in enumerate(entries, 1)],
            "summary": {"entry_count": count_web_memory_entries(self.db)},
        }

    def record_feedback(
        self,
        *,
        entry_id: str,
        rating: str,
        task_id: str | None = None,
        comment: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        entry = get_web_memory_entry(self.db, entry_id)
        if not entry:
            return None
        clean_rating = rating.lower().strip()
        if clean_rating not in {"helpful", "unhelpful"}:
            clean_rating = "unhelpful"
        if clean_rating == "helpful":
            entry.helpful_count = (entry.helpful_count or 0) + 1
        else:
            entry.unhelpful_count = (entry.unhelpful_count or 0) + 1
        entry.quality_score = _quality_score(entry.source_score, entry.helpful_count or 0, entry.unhelpful_count or 0)
        entry.updated_at = now_utc()
        save_web_memory_entry(self.db, entry)
        add_web_memory_feedback(
            self.db,
            WebMemoryFeedbackModel(
                feedback_id=f"webfb_{uuid.uuid4().hex}",
                entry_id=entry.entry_id,
                rating=clean_rating,
                task_id=task_id,
                comment=comment[:1000],
                metadata_json=metadata or {},
            ),
        )
        return {"status": "completed", "entry": _entry_to_item(entry, score=entry.quality_score, rank=1)}

    def prune(self) -> dict[str, Any]:
        return {
            "status": "completed",
            "deleted_expired_count": delete_expired_web_memory_entries(self.db),
            "trimmed_count": trim_web_memory_entries(self.db, max_entries=self.settings.web_memory_max_entries),
            "entry_count": count_web_memory_entries(self.db),
        }

    @staticmethod
    def _skipped_result(*, reason: str) -> dict[str, Any]:
        return {
            "status": "skipped",
            "reason": reason,
            "stored_count": 0,
            "updated_count": 0,
            "skipped_low_score_count": 0,
            "deleted_expired_count": 0,
            "trimmed_count": 0,
            "writes_to_kb": False,
        }

    @staticmethod
    def _empty_recall(*, query: str, status: str, reason: str) -> dict[str, Any]:
        return {
            "query": query,
            "mode": "web_memory",
            "status": status,
            "reason": reason,
            "items": [],
            "summary": {
                "result_count": 0,
                "candidate_count": 0,
                "deleted_expired_count": 0,
                "domain_hints": [],
                "terms": _query_terms(query),
                "search_mode": "none",
                "fts5": {"enabled": False, "used": False, "reason": reason},
                "ranking_policy": _ranking_policy(),
                "writes_to_kb": False,
            },
        }


def build_web_memory_status(db: Session, settings: Settings) -> dict[str, Any]:
    return WebMemoryService(db, settings).status()


def _entry_to_item(
    entry: WebMemoryEntryModel,
    *,
    score: float,
    rank: int,
    ranking: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = dict(entry.metadata_json or {})
    item = {
        "rank": rank,
        "entry_id": entry.entry_id,
        "title": entry.title,
        "url": entry.url,
        "domain": entry.domain,
        "snippet": entry.snippet,
        "source_type": entry.source_type,
        "provider": entry.provider,
        "score": round(score, 4),
        "source_score": entry.source_score,
        "quality_score": entry.quality_score,
        "helpful_count": entry.helpful_count or 0,
        "unhelpful_count": entry.unhelpful_count or 0,
        "recall_count": _safe_int(metadata.get("recall_count")),
        "expires_at": entry.expires_at.isoformat() if entry.expires_at else None,
        "retrieval_source": "web_memory",
    }
    if ranking:
        item["ranking"] = ranking
    return item


def _query_terms(query: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for token in tokenize_query(query):
        normalized = token.lower().strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            terms.append(normalized)
    return terms


def _recall_ranking(
    entry: WebMemoryEntryModel,
    terms: list[str],
    *,
    fts_score: float | None = None,
) -> dict[str, Any]:
    if not terms:
        return {
            "score": 0.0,
            "score_source": "empty_query",
            "matched_terms": [],
            "lexical_score": 0.0,
            "quality_score": entry.quality_score,
            "source_score": entry.source_score,
            "feedback_boost": 0.0,
            "fts_score": fts_score,
        }
    text = f"{entry.title}\n{entry.snippet}\n{entry.domain}".lower()
    matched_terms = [term for term in terms if re.search(re.escape(term), text)]
    lexical = len(matched_terms) / max(len(terms), 1)
    if lexical <= 0:
        python_score = 0.0
    else:
        feedback_boost = min((entry.helpful_count or 0) * 0.03, 0.15) - min(
            (entry.unhelpful_count or 0) * 0.05,
            0.25,
        )
        python_score = max(0.0, min(1.0, lexical * 0.7 + entry.quality_score * 0.25 + feedback_boost))
    feedback_boost = min((entry.helpful_count or 0) * 0.03, 0.15) - min(
        (entry.unhelpful_count or 0) * 0.05,
        0.25,
    )
    fts_blended = None
    if fts_score is not None:
        fts_blended = min(1.0, max(0.0, fts_score) * 0.85 + entry.quality_score * 0.15)
    final_score = max(python_score, fts_blended or 0.0)
    score_source = "fts5_blend" if fts_blended is not None and fts_blended >= python_score else "python_token"
    return {
        "score": round(final_score, 4),
        "score_source": score_source,
        "matched_terms": matched_terms[:12],
        "matched_term_count": len(matched_terms),
        "query_term_count": len(terms),
        "lexical_score": round(lexical, 4),
        "quality_score": entry.quality_score,
        "source_score": entry.source_score,
        "feedback_boost": round(feedback_boost, 4),
        "helpful_count": entry.helpful_count or 0,
        "unhelpful_count": entry.unhelpful_count or 0,
        "fts_score": round(fts_score, 4) if fts_score is not None else None,
        "fts_blended_score": round(fts_blended, 4) if fts_blended is not None else None,
    }


def _ranking_policy() -> dict[str, Any]:
    return {
        "python_token": {
            "lexical_weight": 0.7,
            "quality_weight": 0.25,
            "helpful_boost_per_vote": 0.03,
            "helpful_boost_max": 0.15,
            "unhelpful_penalty_per_vote": 0.05,
            "unhelpful_penalty_max": 0.25,
        },
        "fts5_blend": {
            "fts_weight": 0.85,
            "quality_weight": 0.15,
            "final_score": "max(python_token_score, fts5_blended_score)",
        },
    }


def _recall_score(entry: WebMemoryEntryModel, terms: list[str]) -> float:
    """Compatibility helper for tests or callers that only need the score."""
    return float(_recall_ranking(entry, terms)["score"])


def _quality_score(source_score: float, helpful_count: int, unhelpful_count: int) -> float:
    return round(max(0.0, min(1.0, source_score + helpful_count * 0.05 - unhelpful_count * 0.08)), 4)


def _coerce_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(score, 1.0))


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
